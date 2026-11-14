"""Turn the engine's journal into the lines the activity panel shows.

Pure functions over what S17Code recorded. Nothing is invented: every line
carries the sequence number of the journal event it came from.
"""
from __future__ import annotations

from typing import Any


def _tail(text: Any, limit: int = 1_500) -> str:
    text = str(text or "").strip()
    return text if len(text) <= limit else "…" + text[-limit:]


def _what(capability: str, arguments: dict) -> str:
    if capability == "run_command":
        return f"Run `{arguments.get('command', '')}`"
    if capability == "create_file":
        return f"Write {arguments.get('path', 'a file')}"
    if capability == "edit_code":
        return f"Edit {arguments.get('path', 'a file')}"
    if capability == "read_code":
        return f"Read {arguments.get('path', 'a file')}"
    if capability == "load_skill":
        return f"Load skill {arguments.get('name', '')}"
    if capability == "answer_with_evidence":
        return "Write the final summary"
    return capability.replace("_", " ").capitalize()


def lines(journal: dict, *, after: int = 0) -> list[dict]:
    """Activity lines for journal events with sequence > after."""
    nodes = journal.get("nodes") or {}
    out: list[dict] = []
    for event in journal.get("events") or []:
        seq = event["sequence"]
        if seq <= after:
            continue
        kind, node_id, payload = event["kind"], event.get("node_id"), event.get("payload") or {}
        node = nodes.get(node_id) or {}
        capability, arguments = node.get("skill", ""), node.get("input") or {}
        line = {"seq": seq, "kind": kind, "node": node_id, "capability": capability,
                "title": kind, "detail": "", "tone": "info"}
        if kind == "run_started":
            line["title"] = "Engine accepted the run"
        elif kind == "graph_patched":
            added = [f"{nid} ({(nodes.get(nid) or {}).get('skill', '?')})" for nid in payload.get("add") or []]
            reason = str(payload.get("reason") or "")
            if payload.get("finish"):
                line["title"], line["detail"] = "Planner ended the run", reason
                stopped = reason.startswith(("stopping:", "planner"))
                line["tone"] = "bad" if stopped else "info"
            elif added:
                line["title"], line["detail"] = "Planner added: " + ", ".join(added), reason
            else:
                line["title"], line["detail"] = "Planner is waiting on running work", reason
        elif kind == "task_started":
            line["title"] = _what(capability, arguments) + " …"
        elif kind == "task_succeeded":
            line["title"], line["tone"] = _what(capability, arguments), "ok"
            if capability == "run_command":
                # A command that exits 1 "succeeded" at running. For a person it is a failed check.
                code = payload.get("exit_code")
                passed = code == 0 and not payload.get("timed_out")
                line["tone"] = "ok" if passed else "bad"
                line["title"] += f" → exit {code}" + (" (timed out)" if payload.get("timed_out") else "")
                line["detail"] = _tail((payload.get("stdout") or "") + "\n" + (payload.get("stderr") or ""))
                line["check"] = "passed" if passed else "failed"
            elif capability == "edit_code":
                line["detail"] = f"replaced {payload.get('replaced', 1)} place(s)"
            elif capability == "create_file":
                line["detail"] = f"{payload.get('bytes', '?')} characters"
            elif capability == "answer_with_evidence":
                line["detail"] = _tail(payload.get("answer"), 800)
        elif kind == "task_failed":
            line["title"] = _what(capability, arguments) + " — refused or failed"
            line["detail"], line["tone"] = _tail(payload.get("error") or "task failed"), "bad"
        elif kind == "task_cancelled":
            line["title"] = _what(capability, arguments) + " — cancelled"
            line["detail"], line["tone"] = str(payload.get("reason") or ""), "warn"
        out.append(line)
    return out


def stop_reason(journal: dict | None) -> str:
    """Why the engine ended the run, in its own words, if it said."""
    for event in reversed((journal or {}).get("events") or []):
        if event["kind"] == "graph_patched" and (event.get("payload") or {}).get("finish"):
            return str(event["payload"].get("reason") or "")
    return ""
