"""Local one-way interview practice app. Run: python app.py  then open http://localhost:5050"""
import json
import random
import re
import tempfile
import threading
import time
import traceback
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory

load_dotenv(Path(__file__).parent / ".env")

import analysis  # noqa: E402
import charts  # noqa: E402
import llm  # noqa: E402

ROOT = Path(__file__).parent
DATA = ROOT / "data"
QDIR = DATA / "questions"
ADIR = DATA / "attempts"
CONTEXT_FILE = DATA / "context.txt"
for d in (QDIR, ADIR):
    d.mkdir(parents=True, exist_ok=True)

TYPES = ["competency", "motivational", "mba_essay", "chart", "case", "commercial_awareness"]

app = Flask(__name__, static_folder="static")

# Allowed whole-number seconds; keep in step with the inputs in static/index.html.
PREP_RANGE = (0, 300)
ANSWER_RANGE = (15, 600)


def _timers(raw_prep, raw_answer):
    """Return (prep_s, answer_s) as ints, or raise ValueError with a message safe to show."""
    out = []
    for label, raw, (lo, hi) in (("Prep", raw_prep, PREP_RANGE), ("Answer", raw_answer, ANSWER_RANGE)):
        text = raw if isinstance(raw, str) else (str(raw) if isinstance(raw, int) and not isinstance(raw, bool) else "")
        if not re.fullmatch(r"[0-9]+", text) or not lo <= int(text) <= hi:
            raise ValueError(f"{label} time must be a whole number of seconds from {lo} to {hi}.")
        out.append(int(text))
    return tuple(out)


def _id():
    return time.strftime("%Y%m%d-%H%M%S") + f"-{random.randint(100, 999)}"


def _err(e, code=500):
    traceback.print_exc()
    return jsonify({"error": str(e)}), code


def _public_q(qid, q):
    return {
        "id": qid,
        "type": q.get("type"),
        "question": q.get("question"),
        "context_note": q.get("context_note", ""),
        "chart_url": f"/data/questions/{qid}.png" if q.get("chart") else None,
    }


@app.get("/")
def index():
    return send_from_directory(ROOT / "static", "index.html")


@app.get("/data/<path:p>")
def data_file(p):
    return send_from_directory(DATA, p)


@app.route("/api/context", methods=["GET", "POST"])
def context():
    if request.method == "POST":
        CONTEXT_FILE.write_text(request.json.get("context", ""), encoding="utf-8")
    text = CONTEXT_FILE.read_text(encoding="utf-8") if CONTEXT_FILE.exists() else ""
    return jsonify({"context": text, "calibrated": analysis.BASELINE_PATH.exists()})


def _prompts():
    defaults = {"question": llm.GEN_SYSTEM, "evaluation": llm.GRADE_SYSTEM}
    folder = DATA / "prompts"
    return {key: (folder / f"{key}.md").read_text(encoding="utf-8")
            if (folder / f"{key}.md").exists() else default
            for key, default in defaults.items()}


@app.route("/api/prompts", methods=["GET", "POST"])
def prompts():
    if request.method == "POST":
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "Provide both prompts as text."}), 400
        if body.get("reset") is True:
            values = {"question": llm.GEN_SYSTEM, "evaluation": llm.GRADE_SYSTEM}
        else:
            values = {key: body.get(key) for key in ("question", "evaluation")}
            if any(not isinstance(value, str) or not value.strip() for value in values.values()):
                return jsonify({"error": "Both prompts must contain text."}), 400
        folder = DATA / "prompts"
        folder.mkdir(parents=True, exist_ok=True)
        for key, value in values.items():
            (folder / f"{key}.md").write_text(value, encoding="utf-8")
    return jsonify(_prompts())


@app.post("/api/question")
def question():
    try:
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            return jsonify({"error": "Send the request as a JSON object."}), 400
        try:
            prep_s, answer_s = _timers(body.get("prep", 30), body.get("answer", 90))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        qtype = body.get("type", "mix")
        if qtype not in TYPES:
            qtype = random.choice(TYPES)
        recent = []
        for f in sorted(QDIR.glob("*.json"), reverse=True)[:20]:
            try:
                recent.append(json.loads(f.read_text(encoding="utf-8"))["question"])
            except Exception:  # noqa: BLE001
                pass
        ctx = CONTEXT_FILE.read_text(encoding="utf-8") if CONTEXT_FILE.exists() else ""
        q = llm.generate_question(qtype, ctx, prep_s, answer_s, recent,
                                  system_prompt=_prompts()["question"])
        qid = _id()
        if q.get("chart"):
            try:
                charts.render(q["chart"], QDIR / f"{qid}.png")
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                q["chart"] = None
                q["context_note"] = (q.get("context_note") or "") + f" (chart failed to render: {e})"
        (QDIR / f"{qid}.json").write_text(json.dumps(q, indent=2), encoding="utf-8")
        return jsonify(_public_q(qid, q))
    except Exception as e:  # noqa: BLE001
        return _err(e)


def _ext(mimetype):
    return ".mp4" if "mp4" in (mimetype or "") else ".webm"


@app.post("/api/calibrate")
def calibrate():
    try:
        f = request.files["video"]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / ("calib" + _ext(f.mimetype))
            f.save(p)
            analysis.calibrate(p)
        return jsonify({"ok": True})
    except Exception as e:  # noqa: BLE001
        return _err(e, 400)


@app.post("/api/answer")
def answer():
    try:
        try:
            prep_s, answer_s = _timers(request.form.get("prep", "30"), request.form.get("answer", "90"))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        qid = request.form["qid"]
        q = json.loads((QDIR / f"{qid}.json").read_text(encoding="utf-8"))
        aid = _id()
        folder = ADIR / aid
        folder.mkdir(parents=True)
        f = request.files["video"]
        vname = "answer" + _ext(f.mimetype)
        vpath = folder / vname
        f.save(vpath)

        ctx = CONTEXT_FILE.read_text(encoding="utf-8") if CONTEXT_FILE.exists() else ""
        result = {
            "id": aid,
            "created": time.strftime("%Y-%m-%d %H:%M"),
            "question": _public_q(qid, q),
            "assessor_notes": {k: q.get(k) for k in ("assessing", "strong_answer_covers", "common_mistakes")},
            "prep": prep_s,
            "answer_limit": answer_s,
            "video_url": f"/data/attempts/{aid}/{vname}",
            "candidate_context": ctx,
            "evaluation_prompt": _prompts()["evaluation"],
            "status": "saved",
            "feedback": {},
        }
        _save_attempt(folder, result)
        return jsonify(_assess_attempt(folder, result, q))
    except Exception as e:  # noqa: BLE001
        return _err(e)


def _save_attempt(folder, result):
    # Replace the old result only once the new JSON has been fully written.
    with tempfile.NamedTemporaryFile(mode="w", dir=folder, suffix=".tmp", encoding="utf-8", delete=False) as f:
        json.dump(result, f, indent=2)
        pending = Path(f.name)
    pending.replace(folder / "result.json")


def _assess_attempt(folder, result, q):
    stage = "analysis"
    try:
        if "metrics" not in result:
            vpath = folder / Path(result["video_url"]).name
            result.update(analysis.analyse(vpath, result["answer_limit"]))
            result["status"] = "analysed"
            _save_attempt(folder, result)
        stage = "grading"
        if "evaluation_prompt" not in result:
            result["evaluation_prompt"] = _prompts()["evaluation"]
            _save_attempt(folder, result)
        if result["metrics"].get("speech_detected"):
            result["feedback"] = llm.grade(
                q, result["candidate_context"], result["prep"], result["answer_limit"],
                result["annotated_transcript"], result["metrics"],
                system_prompt=result["evaluation_prompt"],
            )
        else:
            result["feedback"] = {
                "overall_score": 1,
                "verdict": "No speech was detected in the recording. Check your microphone.",
                "retry_focus": "Make sure the browser has microphone access and speak clearly.",
                "content_scores": [], "what_worked": [], "top_fixes": [], "missed_points": [],
                "delivery_feedback": [], "model_answer": "",
            }
        result["status"] = "complete"
        result.pop("assessment_error", None)
    except Exception:  # noqa: BLE001
        result["status"] = f"{stage}_failed"
        result["assessment_error"] = (
            f"{stage.capitalize()} failed. Your recording is saved. "
            "Retry assessment to process this recording again."
        )
    _save_attempt(folder, result)
    return result


@app.post("/api/attempt/<aid>/retry")
def retry_assessment(aid):
    folder = ADIR / aid
    rp = folder / "result.json"
    if not rp.exists():
        return jsonify({"error": "not found"}), 404
    try:
        result = json.loads(rp.read_text(encoding="utf-8"))
        if result.get("status", "complete") == "complete":
            return jsonify(result)
        qid = result["question"]["id"]
        q = json.loads((QDIR / f"{qid}.json").read_text(encoding="utf-8"))
        return jsonify(_assess_attempt(folder, result, q))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@app.get("/api/history")
def history():
    items = []
    for d in sorted(ADIR.iterdir(), reverse=True):
        rp = d / "result.json"
        if not rp.exists():
            continue
        try:
            r = json.loads(rp.read_text(encoding="utf-8"))
            items.append({
                "id": r["id"], "created": r.get("created"), "type": r["question"].get("type"),
                "question": r["question"].get("question"), "score": r["feedback"].get("overall_score"),
            })
        except Exception:  # noqa: BLE001
            pass
    return jsonify(items[:100])


@app.get("/api/attempt/<aid>")
def attempt(aid):
    rp = ADIR / aid / "result.json"
    if not rp.exists():
        return jsonify({"error": "not found"}), 404
    return jsonify(json.loads(rp.read_text(encoding="utf-8")))


@app.get("/api/question/<qid>")
def get_question(qid):
    p = QDIR / f"{qid}.json"
    if not p.exists():
        return jsonify({"error": "not found"}), 404
    return jsonify(_public_q(qid, json.loads(p.read_text(encoding="utf-8"))))


if __name__ == "__main__":
    # Load Whisper in the background so the first answer isn't slow.
    threading.Thread(target=analysis.get_whisper, daemon=True).start()
    print("\n  Interview practice running at  http://localhost:5050\n")
    app.run(host="127.0.0.1", port=5050, threaded=True, debug=False)
