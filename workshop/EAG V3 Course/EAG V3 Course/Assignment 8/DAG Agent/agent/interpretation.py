"""Validate evidence references before displaying model interpretations."""

import json

from agent.comparison import _text


def render_interpretation(raw, result):
    try:
        payload = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
        notes = payload["notes"]
    except (ValueError, TypeError, KeyError):
        raise ValueError("Interpreter returned invalid JSON") from None
    if not isinstance(notes, list) or len(notes) > 4:
        raise ValueError("Interpreter must return at most four notes")
    lines = []
    for note in notes:
        if not isinstance(note, dict) or not isinstance(note.get("text"), str) or not note["text"].strip():
            raise ValueError("Interpretation must contain non-empty text")
        basis = note.get("basis")
        if not isinstance(basis, list) or not basis:
            raise ValueError("Interpretation needs supporting passages")
        ids = []
        for reference in basis:
            source = result["sources"].get(reference.get("source"))
            quote = reference.get("quote", "")
            if source is None or not quote.strip() or _text(quote) not in _text(source["text"]):
                raise ValueError("Interpretation cites an unknown source or absent passage")
            ids.append(source["id"])
        lines.append("- Inference: " + note["text"].replace("\n", " ") +
                     " " + " ".join(f"[{sid}]" for sid in dict.fromkeys(ids)))
    return "\n## Model interpretation\n\n" + "\n".join(lines) + "\n" if lines else ""
