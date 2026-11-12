"""
FastAPI router for /tax/* endpoints.

Mount in dashboard.py with:
    from core.web.routes import router
    app.include_router(router)

Endpoints:
  GET  /tax                          → triage UI page
  GET  /tax/settings                 → bucket + AI settings page
  POST /tax/upload                   → upload SBI .xls; returns ingest stats
  GET  /tax/api/queue                → list of payments needing review
  GET  /tax/api/payment/{id}/context → one payment + context + suggestion
  POST /tax/api/payment/{id}/classify → {bucket, apply_retro}
  GET  /tax/api/buckets              → list active buckets
  POST /tax/api/buckets              → {name} → add
  PATCH /tax/api/buckets/{id}        → {name?, archived?} → rename/archive
  GET  /tax/api/settings             → {mode, llm_endpoint, llm_model}
  POST /tax/api/settings             → update settings
  POST /tax/api/test_llm             → ping the configured LLM endpoint
  GET  /tax/export.xlsx              → download annotated Excel
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Body
from fastapi.responses import HTMLResponse, FileResponse

from core import config
from core.classify.manual import (
    get_active_classifier, RuleBasedClassifier,
)
from core.ingest.excel import ingest
from core.schema.db import connect
from core.web import templates


router = APIRouter(prefix="/tax", tags=["tax"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def page_triage():
    return templates.TRIAGE_HTML


@router.get("/settings", response_class=HTMLResponse)
def page_settings():
    return templates.SETTINGS_HTML


# ---------------------------------------------------------------------------
# Upload + auto-classify pass
# ---------------------------------------------------------------------------

@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, "No file")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".xls", ".xlsx", ".tsv", ".csv"):
        raise HTTPException(400, f"Unsupported extension: {suffix}")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(await file.read())
        tmp.close()
        stats = ingest(tmp.name, db_path=config.DB_PATH)
    finally:
        Path(tmp.name).unlink(missing_ok=True)

    auto_count = _auto_classify_high_confidence()
    stats["auto_classified"] = auto_count
    return stats


def _auto_classify_high_confidence() -> int:
    """Apply rule-based classifier to all unclassified rows above auto-apply threshold."""
    with connect() as conn:
        clf = RuleBasedClassifier(conn)
        rows = conn.execute(
            "SELECT * FROM payments "
            "WHERE (category IS NULL OR category = '') "
            "  AND COALESCE(txn_kind, 'upi') NOT IN ('reversal','interest','charges')"
        ).fetchall()
        auto = 0
        for r in rows:
            sugg = clf.suggest(dict(r))
            if sugg.bucket and sugg.confidence >= config.CONFIDENCE_AUTO_APPLY:
                conn.execute(
                    "UPDATE payments SET category = ?, category_source = 'auto' "
                    "WHERE id = ?",
                    (sugg.bucket, r["id"]),
                )
                auto += 1
        return auto


# ---------------------------------------------------------------------------
# Triage queue
# ---------------------------------------------------------------------------

@router.get("/api/queue")
def queue(limit: int = 100):
    """Payments needing review: no category, oldest first, reversals excluded."""
    with connect() as conn:
        rows = conn.execute("""
            SELECT id, occurred_at, amount, direction,
                   COALESCE(txn_kind, 'upi') AS txn_kind,
                   counterparty_name, counterparty_vpa,
                   COALESCE(source, 'sms') AS source
            FROM payments
            WHERE (category IS NULL OR category = '')
              AND COALESCE(txn_kind, 'upi') != 'reversal'
            ORDER BY occurred_at ASC, id ASC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]


@router.get("/api/payment/{pid}/context")
def payment_context(pid: int):
    with connect() as conn:
        p = conn.execute("SELECT * FROM payments WHERE id = ?", (pid,)).fetchone()
        if not p:
            raise HTTPException(404, "payment not found")
        payment = dict(p)

        cal_raw = payment.get("calendar_events")
        try:
            cal = json.loads(cal_raw) if cal_raw else []
        except (json.JSONDecodeError, TypeError):
            cal = []

        past = []
        if payment.get("counterparty_vpa") or payment.get("counterparty_name"):
            past_rows = conn.execute("""
                SELECT category, COUNT(*) AS n
                FROM payments
                WHERE category IS NOT NULL AND category != ''
                  AND ((counterparty_vpa = ? AND counterparty_vpa IS NOT NULL)
                    OR (counterparty_name = ? AND counterparty_name IS NOT NULL))
                  AND id != ?
                GROUP BY category
                ORDER BY n DESC
            """, (payment.get("counterparty_vpa"),
                  payment.get("counterparty_name"), pid)).fetchall()
            past = [dict(r) for r in past_rows]

        retro_count = 0
        if payment.get("counterparty_vpa") or payment.get("counterparty_name"):
            retro_count = conn.execute("""
                SELECT COUNT(*) FROM payments
                WHERE (category IS NULL OR category = '')
                  AND id != ?
                  AND ((counterparty_vpa = ? AND counterparty_vpa IS NOT NULL)
                    OR (counterparty_name = ? AND counterparty_name IS NOT NULL))
            """, (pid, payment.get("counterparty_vpa"),
                  payment.get("counterparty_name"))).fetchone()[0]

        clf = get_active_classifier(conn)
        sugg = clf.suggest(payment)

        buckets = [r[0] for r in conn.execute(
            "SELECT name FROM buckets WHERE archived_at IS NULL ORDER BY name"
        )]

        queue_remaining = conn.execute(
            "SELECT COUNT(*) FROM payments "
            "WHERE (category IS NULL OR category = '') "
            "  AND COALESCE(txn_kind, 'upi') != 'reversal'"
        ).fetchone()[0]

        mode = conn.execute(
            "SELECT value FROM tax_settings WHERE key = 'mode'"
        ).fetchone()
        mode = mode[0] if mode else "manual"

        return {
            "payment": payment,
            "calendar_events": cal,
            "past_classifications": past,
            "retro_unclassified_count": retro_count,
            "suggestion": {
                "bucket": sugg.bucket,
                "confidence": sugg.confidence,
                "reason": sugg.reason,
            },
            "buckets": buckets,
            "queue_remaining": queue_remaining,
            "mode": mode,
        }


@router.post("/api/payment/{pid}/classify")
def classify(pid: int, body: dict = Body(...)):
    bucket = (body.get("bucket") or "").strip()
    apply_retro = bool(body.get("apply_retro", False))
    if not bucket:
        raise HTTPException(400, "bucket required")

    with connect() as conn:
        p = conn.execute("SELECT * FROM payments WHERE id = ?", (pid,)).fetchone()
        if not p:
            raise HTTPException(404)
        payment = dict(p)

        valid = conn.execute(
            "SELECT 1 FROM buckets WHERE name = ? AND archived_at IS NULL",
            (bucket,),
        ).fetchone()
        if not valid:
            raise HTTPException(400, f"unknown bucket: {bucket}")

        conn.execute(
            "UPDATE payments SET category = ?, category_source = 'user' WHERE id = ?",
            (bucket, pid),
        )

        retro_count = 0
        if apply_retro:
            retro_count = conn.execute("""
                UPDATE payments
                SET category = ?, category_source = 'auto'
                WHERE (category IS NULL OR category = '')
                  AND id != ?
                  AND ((counterparty_vpa = ? AND counterparty_vpa IS NOT NULL)
                    OR (counterparty_name = ? AND counterparty_name IS NOT NULL))
            """, (bucket, pid,
                  payment.get("counterparty_vpa"),
                  payment.get("counterparty_name"))).rowcount

        RuleBasedClassifier(conn).learn(payment, bucket)
        return {"ok": True, "retro_applied": retro_count}


# ---------------------------------------------------------------------------
# Buckets
# ---------------------------------------------------------------------------

@router.get("/api/buckets")
def list_buckets():
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, name, created_at, archived_at FROM buckets ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]


@router.post("/api/buckets")
def add_bucket(body: dict = Body(...)):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name required")
    if len(name) > 50:
        raise HTTPException(400, "name too long")
    try:
        with connect() as conn:
            conn.execute(
                "INSERT INTO buckets (name, created_at) VALUES (?, ?)",
                (name, _now()),
            )
            new_id = conn.execute(
                "SELECT id FROM buckets WHERE name = ?", (name,)
            ).fetchone()[0]
            return {"ok": True, "id": new_id, "name": name}
    except sqlite3.IntegrityError:
        raise HTTPException(409, "bucket already exists")


@router.patch("/api/buckets/{bid}")
def patch_bucket(bid: int, body: dict = Body(...)):
    with connect() as conn:
        existing = conn.execute("SELECT name FROM buckets WHERE id = ?", (bid,)).fetchone()
        if not existing:
            raise HTTPException(404)
        old_name = existing[0]

        if "name" in body:
            new_name = (body["name"] or "").strip()
            if not new_name:
                raise HTTPException(400, "name required")
            try:
                conn.execute("UPDATE buckets SET name = ? WHERE id = ?",
                             (new_name, bid))
            except sqlite3.IntegrityError:
                raise HTTPException(409, "name already in use")
            conn.execute("UPDATE payments SET category = ? WHERE category = ?",
                         (new_name, old_name))
            conn.execute("UPDATE category_rules SET category = ? WHERE category = ?",
                         (new_name, old_name))

        if "archived" in body:
            if body["archived"]:
                conn.execute(
                    "UPDATE buckets SET archived_at = ? WHERE id = ?",
                    (_now(), bid),
                )
            else:
                conn.execute(
                    "UPDATE buckets SET archived_at = NULL WHERE id = ?", (bid,)
                )

        return {"ok": True}


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@router.get("/api/settings")
def get_settings():
    with connect() as conn:
        rows = dict(conn.execute("SELECT key, value FROM tax_settings").fetchall())
        return rows


@router.post("/api/settings")
def set_settings(body: dict = Body(...)):
    allowed = {"mode", "llm_endpoint", "llm_model"}
    with connect() as conn:
        for k, v in body.items():
            if k not in allowed:
                continue
            if k == "mode" and v not in ("manual", "ai"):
                raise HTTPException(400, "mode must be 'manual' or 'ai'")
            conn.execute(
                "UPDATE tax_settings SET value = ? WHERE key = ?",
                (str(v), k),
            )
        return {"ok": True}


@router.post("/api/test_llm")
def test_llm(body: dict = Body(...)):
    """Ping the configured LLM endpoint to verify it's reachable."""
    endpoint = (body.get("endpoint") or "").rstrip("/")
    if not endpoint:
        raise HTTPException(400, "endpoint required")
    try:
        req = urllib.request.Request(f"{endpoint}/v1/models")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            models = [m.get("id") for m in data.get("data", []) if m.get("id")]
            return {"ok": True, "models": models}
    except (urllib.error.URLError, urllib.error.HTTPError,
            json.JSONDecodeError, TimeoutError, OSError) as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@router.get("/export.xlsx")
def export():
    from core.output.excel_export import export_xlsx
    out_path = export_xlsx(db_path=config.DB_PATH)
    return FileResponse(
        out_path,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        filename=f"transactions-{datetime.now():%Y%m%d}.xlsx",
    )
