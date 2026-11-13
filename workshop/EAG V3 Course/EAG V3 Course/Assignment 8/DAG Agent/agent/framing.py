"""Natural-language framing with explicit source provenance and clarification."""

import json
from pathlib import Path

from agent.comparison import validate_request


class ClarificationNeeded(ValueError):
    pass


def frame_comparison(query, llm, sources=(), previous=None):
    catalogue = {s["id"]: s for s in sources}
    if previous:
        for option in previous["options"]:
            for source in option.get("sources", []):
                catalogue[source["id"]] = source
    prompt = (Path(__file__).resolve().parent.parent / "prompts/comparison_framer.md").read_text()
    previous_summary = None
    if previous:
        previous_summary = {"question": previous["question"], "criteria": previous["criteria"],
                            "options": [{"id": o["id"], "name": o["name"],
                                         "sources": [s["id"] for s in o.get("sources", [])]}
                                        for o in previous["options"]]}
    payload = {"question": query, "sources": [{"id": sid, "title": s.get("title", ""),
                 "url": s.get("url", ""), "path": s.get("path", "")} for sid, s in catalogue.items()],
               "previous": previous_summary}
    raw = llm.complete(prompt, json.dumps(payload))
    try:
        parsed = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except (ValueError, TypeError):
        raise ValueError("Framer returned invalid JSON; no research was started") from None
    if parsed.get("clarification"):
        raise ClarificationNeeded(parsed["clarification"])
    if not isinstance(parsed.get("criteria"), list) or not isinstance(parsed.get("options"), list):
        raise ValueError("Framer must return lists of options and criteria")
    for criterion in parsed.get("criteria", []):
        if not isinstance(criterion, dict):
            raise ValueError("Each criterion must be an object")
        # A model may suggest criteria, but cannot silently choose numerical
        # preferences on the user's behalf. Explicit --weight inputs own these.
        criterion.pop("weight", None)
    for option in parsed.get("options", []):
        if not isinstance(option, dict):
            raise ValueError("Each option must be an object")
        chosen = option.get("sources", [])
        if not isinstance(chosen, list):
            raise ValueError("Option sources must be a list of source IDs")
        if not chosen and previous:
            old = next((o for o in previous["options"] if o["id"] == option["id"]
                        and o["name"] == option["name"]), None)
            if old:
                chosen = [s["id"] for s in old.get("sources", [])]
        ids = [s if isinstance(s, str) else s.get("id") for s in chosen]
        if any(sid not in catalogue for sid in ids):
            raise ValueError("Framer invented a source; no research was started")
        option["sources"] = [dict(catalogue[sid]) for sid in ids]
        option.pop("evidence", None)
        if not ids:
            option["sources"] = [{"id": option["id"] + "_search",
                                   "search": option["name"] + " " + query}]
    return validate_request(parsed)
