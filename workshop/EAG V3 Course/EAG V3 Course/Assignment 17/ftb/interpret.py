"""Ask the model for a proposed rule sheet. The model proposes; `spec` decides what counts."""
from __future__ import annotations

import json
from pathlib import Path

from . import spec

_PROMPTS = Path(__file__).parent / "prompts"


def first_interpretation(gateway, sheet: dict) -> dict:
    """Route 1 (prompt) and route 2 (document) share this one call."""
    message = f"REQUEST:\n{sheet['request'] or '(none: build the calculator the document describes)'}\n"
    if sheet["route"] == "document":
        # The document is data. It is fenced, and the system prompt says never to obey it.
        # Whatever comes back is only ever a list of rule texts a person must confirm.
        message += f"\n<<<DOCUMENT\n{sheet['document']}\nDOCUMENT>>>\n"
    proposal = gateway.json_reply((_PROMPTS / "interpret.md").read_text(encoding="utf-8"), message)
    return spec.adopt_proposal(sheet, proposal)


def follow_up(gateway, sheet: dict, request: str) -> dict:
    if not request.strip():
        raise spec.SheetError("say what should change")
    agreed = {"title": sheet["title"], "inputs": sheet["inputs"], "outputs": sheet["outputs"],
              "rules": [{"id": rule["id"], "text": rule["text"]} for rule in sheet["rules"]]}
    message = (f"AGREED SHEET:\n{json.dumps(agreed, ensure_ascii=False, indent=1)}\n\n"
               f"CHANGE REQUEST:\n{request.strip()[:4_000]}\n")
    reply = gateway.json_reply((_PROMPTS / "followup.md").read_text(encoding="utf-8"), message)
    return spec.propose_changes(sheet, reply)


def build_goal(sheet: dict, *, has_previous_page: bool, change_request: str | None) -> str:
    """The only text the engine is given. Built from the agreed sheet, never from a document."""
    if has_previous_page:
        start = ("index.html already exists from the previous version. Read it, then edit it "
                 "so it satisfies the updated specification. Keep everything that still applies.")
        note = ("\nThis is a change to an existing tool. The user asked: "
                f"{json.dumps((change_request or '').strip()[:1_000])}. "
                "Every rule below is still required, including the ones that did not change.\n")
    else:
        start, note = "Create index.html.", ""
    return ((_PROMPTS / "build.md").read_text(encoding="utf-8")
            .replace("{start_step}", start).replace("{change_note}", note)
            .replace("{spec}", spec.spec_markdown(sheet)))
