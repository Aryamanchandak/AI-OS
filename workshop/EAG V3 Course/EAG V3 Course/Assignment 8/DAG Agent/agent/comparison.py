"""Domain-neutral evidence validation, unit alignment and explicit scoring."""

import copy
from decimal import Decimal, InvalidOperation
import math
import re

from agent.skills import load_config


def _text(value):
    return " ".join(str(value).split()).casefold()


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Numeric value must be a finite number, not text or boolean")
    if not math.isfinite(value):
        raise ValueError("Numeric value must be finite")
    return Decimal(str(value))


def validate_request(request):
    if not isinstance(request, dict) or not str(request.get("question", "")).strip():
        raise ValueError("A comparison question is required")
    for key, minimum, maximum in (("options", 2, 12), ("criteria", 1, 15)):
        entries = request.get(key)
        if not isinstance(entries, list) or not minimum <= len(entries) <= maximum:
            raise ValueError(f"{key} requires {minimum}-{maximum} entries")
        ids = [e.get("id", "") for e in entries if isinstance(e, dict)]
        if len(ids) != len(entries) or any(not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", i) for i in ids):
            raise ValueError(f"{key} IDs must be lowercase identifiers")
        if len(set(ids)) != len(ids):
            raise ValueError(f"{key} IDs must be unique")
    source_ids = {}
    for option in request["options"]:
        if not str(option.get("name", "")).strip():
            raise ValueError("Every option needs a name")
        for source in option.get("sources", []):
            sid = source.get("id", "")
            if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]{0,79}", sid):
                raise ValueError("Source IDs must be present and valid")
            identity = {k: source.get(k) for k in ("text", "url", "path", "as_of", "search")}
            if sid in source_ids and source_ids[sid] != identity:
                raise ValueError("One source ID cannot identify different evidence")
            source_ids[sid] = identity
        if len(option.get("sources", [])) > 6:
            raise ValueError("At most six sources per option are supported")
    for criterion in request["criteria"]:
        if criterion.get("kind", "text") not in {"text", "number"}:
            raise ValueError("Criterion kind must be text or number")
        if criterion.get("direction", "none") not in {"lower", "higher", "none"}:
            raise ValueError("Criterion direction must be lower, higher or none")
        if "weight" in criterion:
            if _number(criterion["weight"]) < 0:
                raise ValueError("Weights cannot be negative")
        if "maximum" in criterion:
            _number(criterion["maximum"])
        if "minimum" in criterion:
            _number(criterion["minimum"])
        if criterion.get("minimum", -math.inf) > criterion.get("maximum", math.inf):
            raise ValueError("Minimum cannot exceed maximum")
    if request.get("prioritise") and request["prioritise"] not in {c["id"] for c in request["criteria"]}:
        raise ValueError("Unknown priority criterion")
    if request.get("chart") and request["chart"] not in {c["id"] for c in request["criteria"]}:
        raise ValueError("Unknown chart criterion")
    return copy.deepcopy(request)


def _convert(value, source_unit, target_unit):
    if source_unit == target_unit:
        return float(value)
    units = load_config("units.yaml")
    source, target = units.get(source_unit), units.get(target_unit)
    if not source or not target or source["dimension"] != target["dimension"]:
        return None
    return float(value * Decimal(str(source["scale"])) / Decimal(str(target["scale"])))


def _observation(raw, criterion, sources):
    if not isinstance(raw, dict):
        raise ValueError("An evidence observation must be an object")
    if raw.get("value") is None:
        return {"status": "missing", "value": None, "reason": raw.get("reason", "Not found")}
    source = sources.get(raw.get("source"))
    if source is None:
        raise ValueError("Evidence references an unknown source")
    quote = str(raw.get("quote", ""))
    if not quote.strip() or _text(quote) not in _text(source.get("text", "")):
        raise ValueError("Evidence passage is absent from its source")
    status = raw.get("status", "fact")
    if status not in {"fact", "inference"}:
        raise ValueError("Evidence status must be fact or inference")
    if raw.get("as_of") and raw["as_of"] != source.get("as_of") and _text(raw["as_of"]) not in _text(source["text"]):
        raise ValueError("Evidence date is absent from its source")
    value = raw["value"]
    cell = {"status": status, "value": value, "source": source["id"], "quote": quote,
            "as_of": raw.get("as_of", source.get("as_of", "")),
            "scope": raw.get("scope", ""), "unit": raw.get("unit", ""),
            "original_value": value, "original_unit": raw.get("unit", "")}
    if criterion.get("kind", "text") == "number":
        number = _number(value)
        quoted_numbers = []
        for token in re.findall(r"[-+]?\d[\d,]*(?:\.\d+)?", quote):
            try:
                quoted_numbers.append(Decimal(token.replace(",", "")))
            except InvalidOperation:
                pass
        if status == "fact" and number not in quoted_numbers:
            raise ValueError("Numeric value does not appear in the verified passage")
        unit = criterion.get("unit", "")
        converted = _convert(number, cell["unit"], unit)
        cell["unit"] = unit
        if converted is None:
            cell.update(status="incomparable", reason="Incompatible units; no conversion supplied")
        else:
            period = raw.get("unit", "").split("/")[-1]
            aliases = load_config("units.yaml").get("_period_words", {}).get(period, [])
            if aliases and status == "fact" and not any(re.search(r"\b" + re.escape(a) + r"\b", quote, re.I) for a in aliases):
                raise ValueError("Measurement period is absent from the verified passage")
            cell["value"] = converted
            if cell["original_unit"] != unit:
                cell["calculation"] = f"{value} {cell['original_unit']} → {converted:g} {unit}"
    elif not isinstance(value, str) or not value.strip():
        raise ValueError("Text evidence needs a non-empty string")
    elif status == "fact" and _text(value) not in _text(quote):
        raise ValueError("Text value is not present in the verified passage; label interpretation as inference")
    return cell


def compare(request):
    request = validate_request(request)
    cells, warnings = {}, []
    criteria = {c["id"]: c for c in request["criteria"]}
    sources = {s["id"]: s for o in request["options"] for s in o.get("sources", [])}
    for option in request["options"]:
        evidence = option.get("evidence", {})
        if set(evidence) - set(criteria):
            raise ValueError("Evidence contains an unknown criterion")
        row = cells[option["id"]] = {}
        for cid, criterion in criteria.items():
            raw = evidence.get(cid)
            if raw is None:
                row[cid] = {"status": "missing", "value": None, "reason": "No evidence supplied"}
                continue
            observations = [_observation(item, criterion, sources)
                            for item in (raw if isinstance(raw, list) else [raw])]
            if not observations:
                row[cid] = {"status": "missing", "value": None, "reason": "No observations"}
                continue
            signatures = {(str(c["value"]), c.get("unit"), c.get("as_of"), c.get("scope"), c["status"])
                          for c in observations}
            if len(signatures) > 1:
                row[cid] = {"status": "conflict", "value": None, "observations": observations}
            else:
                row[cid] = {**observations[0], "observations": observations}
    findings, eligible = {}, {}
    for cid, criterion in criteria.items():
        column = [row[cid] for row in cells.values()]
        complete = all(c["status"] == "fact" for c in column)
        dates = {c.get("as_of", "") for c in column}
        scopes = {c.get("scope", "") for c in column}
        comparable = complete and len(dates) == 1 and len(scopes) == 1
        if criterion.get("time_sensitive") and "" in dates:
            comparable = False
            warnings.append(f"{cid}: current comparison needs explicit as-of dates")
        if len(dates) > 1:
            warnings.append(f"{cid}: evidence dates differ or are missing; no best-option claim")
        if len(scopes) > 1:
            warnings.append(f"{cid}: definitions or measurement scope differ; no best-option claim")
        numeric = criterion.get("kind", "text") == "number"
        eligible[cid] = comparable and numeric
        finding = findings[cid] = {"comparable": comparable, "best": [], "range": None}
        if not eligible[cid]:
            continue
        values = {oid: row[cid]["value"] for oid, row in cells.items()}
        finding["range"] = max(values.values()) - min(values.values())
        direction = criterion.get("direction", "none")
        if direction != "none":
            best = (min if direction == "lower" else max)(values.values())
            finding["best"] = [oid for oid, value in values.items() if value == best]
    weighted = [c for c in criteria.values() if c.get("weight", 0) > 0]
    ranking = None
    if weighted and all(eligible[c["id"]] and c.get("direction", "none") != "none" for c in weighted):
        total_weight = sum(c["weight"] for c in weighted)
        scores = {oid: 0.0 for oid in cells}
        for c in weighted:
            values = [row[c["id"]]["value"] for row in cells.values()]
            low, high = min(values), max(values)
            for oid, row in cells.items():
                fraction = (row[c["id"]]["value"] - low) / (high - low) if high != low else 0.5
                if c["direction"] == "lower":
                    fraction = 1 - fraction
                scores[oid] += fraction * c["weight"] / total_weight
        ranking = sorted([{"option": oid, "score": round(score * 100, 4)} for oid, score in scores.items()],
                         key=lambda row: (-row["score"], row["option"]))
    constraints = {}
    for oid, row in cells.items():
        constraints[oid] = {}
        for cid, c in criteria.items():
            if "maximum" in c or "minimum" in c:
                constraints[oid][cid] = (None if row[cid]["status"] != "fact" or not eligible[cid] else
                    (row[cid]["value"] <= c.get("maximum", math.inf) and
                     row[cid]["value"] >= c.get("minimum", -math.inf)))
    if ranking:
        if any(value is None for checks in constraints.values() for value in checks.values()):
            ranking = None
        else:
            ranking = [r for r in ranking if all(constraints[r["option"]].values())]
    return {"request": request, "cells": cells, "sources": sources, "findings": findings,
            "ranking": ranking, "constraints": constraints, "warnings": warnings,
            "scoring_method": "Explicit weights; per-criterion min-max scaling, ties receive equal scores"}
