"""The rule sheet: what the user and the app have agreed the tool must do.

A model proposes; only the user confirms. Everything the engine is later asked
to build comes from this sheet, never straight from a document or a model reply.

Three guarantees live here, in code rather than in a prompt:

* a rule quoted from a document is checked against that document, word for word;
* nothing can be built while a rule is unconfirmed, a question is unanswered, or
  no example with a known answer has been confirmed;
* a follow-up can only *propose* changing or removing an agreed rule. Rules it
  does not mention are kept by this code, not by the model's memory.
"""
from __future__ import annotations

import copy
import json
import re
from typing import Any

MAX_DOCUMENT_CHARS = 200_000
MAX_RULES = 60
MAX_TEXT = 1_500
FIELD_TYPES = {"number", "text", "boolean", "table"}
_KEY = re.compile(r"^[a-z][a-z0-9_]{0,39}$")


class SheetError(ValueError):
    """The proposal or review was not usable. Shown to the user as-is."""


def new_sheet(route: str, request: str, document: str | None = None) -> dict:
    if route not in {"prompt", "document"}:
        raise SheetError("route must be 'prompt' or 'document'")
    if route == "document" and not (document or "").strip():
        raise SheetError("the document route needs the document text")
    if route == "prompt" and not request.strip():
        raise SheetError("describe the tool you want")
    if document and len(document) > MAX_DOCUMENT_CHARS:
        raise SheetError(f"the document is longer than {MAX_DOCUMENT_CHARS:,} characters")
    return {"route": route, "request": request.strip(), "document": document,
            "title": "", "summary": "", "inputs": [], "outputs": [],
            "rules": [], "questions": [], "examples": [], "next_id": 1}


# ---------------------------------------------------------------- quotes

def locate_quote(document: str, quote: str) -> tuple[int, int] | None:
    """Find `quote` in `document`, ignoring only differences in whitespace.

    Returns character offsets into the original document, so the passage can be
    highlighted. None means the model quoted something the document does not say.
    """
    wanted = " ".join(quote.split())
    if not wanted:
        return None
    flat: list[str] = []
    origin: list[int] = []
    for index, char in enumerate(document):
        if char.isspace():
            if flat and flat[-1] != " ":
                flat.append(" "); origin.append(index)
        else:
            flat.append(char); origin.append(index)
    found = "".join(flat).find(wanted)
    if found < 0:
        return None
    return origin[found], origin[found + len(wanted) - 1] + 1


# ---------------------------------------------------------------- proposals

def _text(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SheetError(f"{what} must be non-empty text")
    return value.strip()[:MAX_TEXT]


def _fields(raw: Any, what: str) -> list[dict]:
    if not isinstance(raw, list) or not raw:
        raise SheetError(f"the interpretation listed no {what}")
    fields = []
    for item in raw[:40]:
        if not isinstance(item, dict) or not _KEY.match(str(item.get("key", ""))):
            raise SheetError(f"every {what[:-1]} needs a lowercase key such as new_cash")
        kind = item.get("type", "number")
        if kind not in FIELD_TYPES:
            raise SheetError(f"{what[:-1]} {item['key']} has unknown type {kind!r}")
        field = {"key": item["key"], "label": str(item.get("label") or item["key"])[:120], "type": kind}
        if kind == "table":
            field["columns"] = [{"key": c["key"], "label": str(c.get("label") or c["key"])[:120],
                                 "type": c.get("type", "number")}
                                for c in item.get("columns", [])
                                if isinstance(c, dict) and _KEY.match(str(c.get("key", "")))]
            if not field["columns"]:
                raise SheetError(f"table {item['key']} needs columns")
        fields.append(field)
    return fields


def _take_id(sheet: dict, prefix: str) -> str:
    sheet["next_id"] += 1
    return f"{prefix}{sheet['next_id'] - 1}"


def _add_rule(sheet: dict, text: str, *, origin: str, quote: str | None = None,
              status: str = "proposed") -> dict:
    rule = {"id": _take_id(sheet, "r"), "text": _text(text, "a rule"), "status": status,
            "origin": origin, "quote": None, "span": None, "pending": None, "proposed_text": None}
    if sheet["route"] == "document" and origin == "model":
        rule["quote"] = (quote or "").strip()[:MAX_TEXT] or None
        span = locate_quote(sheet["document"] or "", rule["quote"] or "")
        rule["span"] = list(span) if span else None
    sheet["rules"].append(rule)
    return rule


def _add_questions(sheet: dict, raw: Any) -> None:
    for item in (raw if isinstance(raw, list) else [])[:20]:
        if isinstance(item, dict) and str(item.get("question", "")).strip():
            sheet["questions"].append({
                "id": _take_id(sheet, "q"), "question": _text(item["question"], "a question"),
                "why": str(item.get("why") or "")[:MAX_TEXT],
                "options": [str(o)[:200] for o in item.get("options", []) if str(o).strip()][:6]
                if isinstance(item.get("options"), list) else [],
                "answer": None})


def add_example(sheet: dict, name: str, input_: Any, expected: Any, *, working: str = "",
                origin: str = "model") -> dict:
    if not isinstance(input_, dict) or not isinstance(expected, dict) or not expected:
        raise SheetError("an example needs an input object and a non-empty expected object")
    example = {"id": _take_id(sheet, "e"), "name": _text(name, "an example name")[:160],
               "input": input_, "expected": expected, "working": str(working)[:4_000],
               "origin": origin, "confirmed": False}
    sheet["examples"].append(example)
    return example


def adopt_proposal(sheet: dict, proposal: dict) -> dict:
    """Turn a model's first interpretation into an unconfirmed sheet."""
    sheet = copy.deepcopy(sheet)
    sheet["title"] = _text(proposal.get("title"), "the title")[:120]
    sheet["summary"] = str(proposal.get("summary") or "")[:MAX_TEXT]
    sheet["inputs"] = _fields(proposal.get("inputs"), "inputs")
    sheet["outputs"] = _fields(proposal.get("outputs"), "outputs")
    rules = proposal.get("rules")
    if not isinstance(rules, list) or not rules:
        raise SheetError("the interpretation contained no calculation rules")
    for raw in rules[:MAX_RULES]:
        if isinstance(raw, dict):
            _add_rule(sheet, raw.get("text"), origin="model", quote=raw.get("quote"))
    _add_questions(sheet, proposal.get("questions"))
    example = proposal.get("example")
    if isinstance(example, dict) and isinstance(example.get("input"), dict):
        try:
            add_example(sheet, example.get("name") or "Worked example proposed by the model",
                        example["input"], example.get("expected"), working=example.get("working") or "")
        except SheetError:
            pass        # a malformed proposed example is dropped; the user must still supply one
    return sheet


# ---------------------------------------------------------------- follow-ups

def propose_changes(sheet: dict, reply: dict) -> dict:
    """Apply a model's follow-up as *proposals* on top of the agreed sheet."""
    sheet = copy.deepcopy(sheet)
    by_id = {rule["id"]: rule for rule in sheet["rules"]}
    touched = False
    for change in (reply.get("changes") if isinstance(reply.get("changes"), list) else [])[:MAX_RULES]:
        if not isinstance(change, dict):
            continue
        op, rule = change.get("op"), by_id.get(str(change.get("rule")))
        if op == "add":
            # Its source is the user's change request, not the document.
            _add_rule(sheet, change.get("text"), origin="followup"); touched = True
        elif op == "change" and rule:
            rule["pending"], rule["proposed_text"] = "change", _text(change.get("text"), "a changed rule")
            touched = True
        elif op == "remove" and rule:
            rule["pending"], rule["proposed_text"] = "remove", None
            touched = True
    if isinstance(reply.get("inputs"), list) and reply["inputs"]:
        sheet["inputs"] = _fields(reply["inputs"], "inputs"); touched = True
    if isinstance(reply.get("outputs"), list) and reply["outputs"]:
        sheet["outputs"] = _fields(reply["outputs"], "outputs"); touched = True
    _add_questions(sheet, reply.get("questions"))
    if not touched and not reply.get("questions"):
        raise SheetError("the follow-up did not change anything; say what should be different")
    # The agreed answers were worked out under the old rules. They are the
    # protected check, so the user must look at each one again.
    for example in sheet["examples"]:
        example["confirmed"] = False
    return sheet


# ---------------------------------------------------------------- the user's review

def apply_review(sheet: dict, review: dict) -> dict:
    """Record what the user decided. This is the only way anything becomes confirmed."""
    sheet = copy.deepcopy(sheet)
    decisions = {str(item.get("id")): item for item in review.get("rules", []) if isinstance(item, dict)}
    kept = []
    for rule in sheet["rules"]:
        decision = decisions.get(rule["id"])
        if decision is None:
            kept.append(rule); continue
        if rule["pending"]:
            accepted = bool(decision.get("accept_pending"))
            if rule["pending"] == "remove" and accepted:
                continue
            if rule["pending"] == "change" and accepted:
                rule["text"], rule["origin"] = rule["proposed_text"], "followup"
                rule["quote"], rule["span"] = None, None
            rule["pending"], rule["proposed_text"] = None, None
            kept.append(rule); continue
        if decision.get("remove"):
            continue
        text = str(decision.get("text") or "").strip()
        if text and text != rule["text"]:
            # The user's own wording replaces the model's; it no longer claims a source passage.
            rule.update(text=text[:MAX_TEXT], origin="user", quote=None, span=None)
        rule["status"] = "confirmed" if decision.get("confirmed") else "proposed"
        kept.append(rule)
    sheet["rules"] = kept
    for text in review.get("new_rules", []):
        if str(text).strip():
            _add_rule(sheet, str(text), origin="user", status="confirmed")

    answers = review.get("answers") if isinstance(review.get("answers"), dict) else {}
    for question in sheet["questions"]:
        answer = str(answers.get(question["id"]) or "").strip()
        if answer and question["answer"] is None:
            question["answer"] = answer[:MAX_TEXT]
            _add_rule(sheet, f"{question['question']} Decision: {answer}", origin="answer",
                      status="confirmed")

    examples = {str(item.get("id")): item for item in review.get("examples", []) if isinstance(item, dict)}
    kept_examples = []
    for example in sheet["examples"]:
        decision = examples.get(example["id"])
        if decision is None:
            kept_examples.append(example); continue
        if decision.get("remove"):
            continue
        for part in ("input", "expected"):
            if part in decision:
                value = decision[part]
                if isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except json.JSONDecodeError as error:
                        raise SheetError(f"example {example['name']!r}: {part} is not valid JSON "
                                         f"({error.msg})") from None
                if not isinstance(value, dict) or (part == "expected" and not value):
                    raise SheetError(f"example {example['name']!r}: {part} must be an object")
                example[part] = value
        example["confirmed"] = bool(decision.get("confirmed"))
        kept_examples.append(example)
    sheet["examples"] = kept_examples
    for item in review.get("new_examples", []):
        if isinstance(item, dict):
            parsed = {}
            for part in ("input", "expected"):
                try:
                    parsed[part] = json.loads(item[part]) if isinstance(item.get(part), str) else item.get(part)
                except json.JSONDecodeError as error:
                    raise SheetError(f"new example: {part} is not valid JSON ({error.msg})") from None
            add_example(sheet, item.get("name") or "My example", parsed["input"], parsed["expected"],
                        origin="user")["confirmed"] = True
    return sheet


def blockers(sheet: dict) -> list[str]:
    """Every reason this sheet may not be built yet. Empty means it is agreed."""
    found = []
    if not sheet["rules"]:
        found.append("There are no rules.")
    for rule in sheet["rules"]:
        if rule["pending"] == "change":
            found.append(f"Rule {rule['id']}: accept or reject the proposed change.")
        elif rule["pending"] == "remove":
            found.append(f"Rule {rule['id']}: accept or reject its proposed removal.")
        elif rule["status"] != "confirmed":
            found.append(f"Rule {rule['id']} is not confirmed.")
        elif sheet["route"] == "document" and rule["origin"] == "model" and not rule["span"]:
            found.append(f"Rule {rule['id']} cites a passage that is not in the document. "
                         "Reword it yourself or remove it.")
    for question in sheet["questions"]:
        if question["answer"] is None:
            found.append(f"Unanswered: {question['question']}")
    confirmed = [example for example in sheet["examples"] if example["confirmed"]]
    if not confirmed:
        found.append("Confirm at least one example with a known answer. It becomes the check "
                     "the generated tool must pass.")
    for example in sheet["examples"]:
        if not example["confirmed"]:
            found.append(f"Example {example['name']!r} is not confirmed. Confirm or remove it.")
    return found


# ---------------------------------------------------------------- what the engine receives

def _describe(fields: list[dict]) -> str:
    lines = []
    for field in fields:
        if field["type"] == "table":
            columns = ", ".join(f"{c['key']} ({c['type']}, \"{c['label']}\")" for c in field["columns"])
            lines.append(f"- `{field['key']}`: list of rows, labelled \"{field['label']}\". "
                         f"Each row: {columns}")
        else:
            lines.append(f"- `{field['key']}`: {field['type']}, labelled \"{field['label']}\"")
    return "\n".join(lines)


def spec_markdown(sheet: dict) -> str:
    """The agreed sheet as the engine sees it. Confirmed rules only; never the raw document."""
    if blockers(sheet):
        raise SheetError("the sheet is not fully agreed yet")
    rules = "\n".join(f"{n}. {rule['text']}" for n, rule in enumerate(sheet["rules"], 1))
    return (f"# {sheet['title']}\n\n{sheet['summary']}\n\n"
            f"## Inputs: the keys of `input` passed to calculate(input)\n\n{_describe(sheet['inputs'])}\n\n"
            f"## Outputs: the keys of the object calculate(input) returns\n\n{_describe(sheet['outputs'])}\n\n"
            f"## Rules agreed with the user\n\n{rules}\n")


def cases(sheet: dict) -> dict:
    """The confirmed examples, in the shape checks/check_tool.js reads."""
    return {"tolerance": 0.005,
            "cases": [{"name": e["name"], "input": e["input"], "expected": e["expected"]}
                      for e in sheet["examples"] if e["confirmed"]]}
