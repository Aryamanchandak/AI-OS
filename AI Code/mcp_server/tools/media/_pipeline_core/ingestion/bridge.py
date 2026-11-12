"""Bridge pipeline disk artifacts into the SQLite provenance store."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from tools.media._pipeline_core.backup import backup_db
from tools.media._pipeline_core.shared.contracts import ArtifactRow, ClaimRow, EpisodeRow, RunRow
from tools.media._pipeline_core.storage.client import get_store

DEFAULT_PODCAST_DATA_DIR = Path(
    "/Users/aryamanchandak/Documents/AI Code/Core truth storage/Podcast_Data"
)

_ARTIFACT_SPECS = (
    ("audio", "audio", ".mp3"),
    ("transcript", "transcripts", ".json"),
    ("extraction", "extractions", ".json"),
    ("research_items", "research_items", ".json"),
    ("brief_markdown", "briefs", ".md"),
)


def sync_episode_artifacts(episode_id: str) -> dict[str, int | str]:
    """Sync on-disk pipeline artifacts for one episode into SQLite provenance."""
    try:
        store = get_store()
        data_dir = _resolve_podcast_data_dir()
        extraction_payload = _load_json_if_exists(data_dir / "extractions" / f"{episode_id}.json")

        store.upsert_episode(
            EpisodeRow(
                episode_id=episode_id,
                show_name=_extract_text(extraction_payload, "show_name"),
                title=_extract_text(extraction_payload, "title"),
                source_url=_extract_text(extraction_payload, "source_url"),
                status="synced",
            )
        )
        artifacts_synced = 0
        for artifact_type, folder, suffix in _ARTIFACT_SPECS:
            artifact_path = data_dir / folder / f"{episode_id}{suffix}"
            if artifact_path.exists():
                store.save_artifact(
                    ArtifactRow(
                        episode_id=episode_id,
                        artifact_type=artifact_type,
                        artifact_path=str(artifact_path),
                    )
                )
                artifacts_synced += 1

        claims_synced = 0
        for index, claim in enumerate(_extract_claims(extraction_payload)):
            store.upsert_claim(
                ClaimRow(
                    claim_id=_claim_id(episode_id, claim, index),
                    episode_id=episode_id,
                    claim_type=_claim_field(claim, "type"),
                    quote=_claim_field(claim, "quote"),
                    summary=_claim_field(claim, "summary"),
                )
            )
            claims_synced += 1

        store.log_run(
            RunRow(
                episode_id=episode_id,
                stage="bridge_sync",
                status="completed",
                message=f"artifacts={artifacts_synced} claims={claims_synced}",
            )
        )
        backup_db(reason=f"bridge_sync:{episode_id}")
        return {
            "episode_id": episode_id,
            "artifacts_synced": artifacts_synced,
            "claims_synced": claims_synced,
        }
    except Exception:
        backup_db(reason=f"bridge_sync_failed:{episode_id}")
        raise


def _resolve_podcast_data_dir() -> Path:
    return Path(os.getenv("PODCAST_DATA_DIR", str(DEFAULT_PODCAST_DATA_DIR)))


def _load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field, "")
    return value if isinstance(value, str) else ""


def _extract_claims(payload: dict[str, Any]) -> list[dict[str, Any]]:
    claims = payload.get("claims", [])
    return [claim for claim in claims if isinstance(claim, dict)]


def _claim_field(claim: dict[str, Any], field: str) -> str:
    value = claim.get(field, "")
    return value if isinstance(value, str) else ""


def _claim_id(episode_id: str, claim: dict[str, Any], index: int) -> str:
    existing = claim.get("claim_id")
    if isinstance(existing, str) and existing:
        return existing
    raw = "||".join(
        [
            episode_id,
            _claim_field(claim, "type"),
            _claim_field(claim, "summary"),
            _claim_field(claim, "quote"),
            str(index),
        ]
    )
    return f"{episode_id}_claim_{hashlib.md5(raw.encode('utf-8')).hexdigest()[:12]}"
