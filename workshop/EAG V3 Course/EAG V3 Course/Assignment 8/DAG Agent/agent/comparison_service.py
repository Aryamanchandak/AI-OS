"""Run the Planner's comparison DAG; explicitly reuse evidence snapshots."""

import hashlib
import json
from pathlib import Path

from agent.comparison import validate_request
from agent.executor import Executor, NodeResult
from agent.planner import Planner
from agent.skills import load_config, load_skills
from agent.state import SessionStore


def _fingerprint(option, criteria, live, skills):
    option = {k: v for k, v in option.items() if not (live and k == "evidence")}
    data = {"option": option, "live": live, "version": 1}
    if live:
        data["criteria"] = [{k: v for k, v in c.items() if k not in
                            {"weight", "direction", "maximum", "minimum"}} for c in criteria]
        data["prompt"] = skills["evidence_extractor"].prompt
    for source in option.get("sources", []):
        if source.get("path"):
            try:
                path = Path(source["path"])
                digest = ("unsupported" if path.name.startswith(".env") or path.stat().st_size > 2_000_000
                          else hashlib.sha256(path.read_bytes()).hexdigest())
            except OSError:
                digest = "unavailable"
            data.setdefault("file_hashes", {})[source["path"]] = digest
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def run_comparison(request, directory, *, llm=None, live=False, reuse=None, stop_after=None):
    directory = Path(directory)
    store = SessionStore(directory)
    saved = store.load()
    skills = load_skills(load_config())
    if saved:
        live = json.loads((directory / "mode.json").read_text())["live"]
        persisted = json.loads((directory / "request.json").read_text())
        if request is not None and request != persisted:
            raise ValueError("Use a new session directory for a changed comparison")
        request = persisted
        graph = None
    else:
        request = validate_request(request)
        (directory / "request.json").write_text(json.dumps(request, indent=2))
        (directory / "mode.json").write_text(json.dumps({"live": live}))
        graph = Planner(skills, llm).comparison_plan(request, live=live, artifacts_dir=directory / "artifacts")
    cached = json.loads((Path(reuse) / "cache.json").read_text()) if reuse else {}
    keys, initial = {}, {}
    for option in request["options"]:
        key = _fingerprint(option, request["criteria"], live, skills)
        keys[option["id"]] = key
        for prefix in (["read_", "extract_"] if live else ["read_"]):
            nid = prefix + option["id"]
            entry = cached.get(nid)
            if entry and key in entry.get("keys", [entry.get("key")]):
                initial[nid] = NodeResult(**entry["result"])
    executor = Executor(skills, llm, directory / "artifacts", store=store, initial_results=initial)
    log = executor.run(graph, request["question"], stop_after=stop_after)
    checkpoint = store.load()
    cache = {}
    for nid, result in checkpoint["results"].items():
        for prefix in ("read_", "extract_"):
            if nid.startswith(prefix) and result["error"] is None:
                oid = nid[len(prefix):]
                aliases = [keys[oid]]
                reader = checkpoint["results"].get("read_" + oid)
                if reader and reader["error"] is None:
                    collected = json.loads(reader["output"])["option"]
                    aliases.append(_fingerprint(collected, request["criteria"], live, skills))
                cache[nid] = {"keys": aliases, "result": result}
    (directory / "cache.json").write_text(json.dumps(cache))
    (directory / "run.json").write_text(log.to_json())
    result = None
    if log.status == "completed":
        result = json.loads(checkpoint["results"]["comparison"]["output"])
        (directory / "comparison.json").write_text(json.dumps(result, indent=2, allow_nan=False))
        (directory / "answer.md").write_text(log.answer)
    return result, log
