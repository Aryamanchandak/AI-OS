"""Render only verified values and computed findings; no generated facts."""


def _safe(value):
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def _value(cell):
    status = cell["status"]
    if status in {"missing", "conflict", "incomparable"}:
        return {"missing": "Missing", "conflict": "Conflicting evidence",
                "incomparable": "Incompatible units"}[status]
    value = cell["value"]
    if isinstance(value, (int, float)):
        value = f"{value:,.4f}".rstrip("0").rstrip(".")
    suffix = f" {cell['unit']}" if cell.get("unit") else ""
    label = " (inference)" if status == "inference" else ""
    return _safe(value) + suffix + label + f" [{cell['source']}]"


def render_report(result):
    request = result["request"]
    options = {o["id"]: o["name"] for o in request["options"]}
    lines = ["# " + request["question"], ""]
    lines.extend("Assumption: " + _safe(a) for a in request.get("assumptions", []))
    prioritised = request.get("prioritise")
    if prioritised and result["findings"].get(prioritised, {}).get("best"):
        winners = result["findings"][prioritised]["best"]
        lines += [f"For your stated priority ({prioritised}), " +
                  ", ".join(options[o] for o in winners) + " has the best verified value.", ""]
    else:
        lines += ["The evidence supports the criterion-by-criterion trade-offs below. "
                  "No overall winner is assumed.", ""]
    criteria = request["criteria"]
    lines += ["| Option | " + " | ".join(_safe(c.get("label", c["id"])) for c in criteria) + " |",
              "|---|" + "---|" * len(criteria)]
    for oid, name in options.items():
        lines.append("| " + _safe(name) + " | " + " | ".join(
            _value(result["cells"][oid][c["id"]]) for c in criteria) + " |")
    lines += ["", "## Trade-offs", ""]
    for criterion in criteria:
        cid = criterion["id"]
        finding = result["findings"][cid]
        if finding["best"]:
            names = ", ".join(options[oid] for oid in finding["best"])
            lines.append(f"- {_safe(criterion.get('label', cid))}: {names} "
                         f"has the {'lowest' if criterion['direction'] == 'lower' else 'highest'} verified value. "
                         f"Spread: {finding['range']:g} {criterion.get('unit', '')}.")
        elif not finding["comparable"]:
            lines.append(f"- {_safe(criterion.get('label', cid))}: evidence is incomplete, conflicting, "
                         "inferred, or uses different measurement scopes/dates; no winner claimed.")
        else:
            values = [result["cells"][oid][cid]["value"] for oid in options]
            if len({str(v) for v in values}) == 1:
                lines.append(f"- {_safe(criterion.get('label', cid))}: all options report {_safe(values[0])}.")
            elif criterion.get("kind", "text") == "text":
                lines.append(f"- {_safe(criterion.get('label', cid))}: the options report different approaches. "
                             "The supplied evidence does not establish which suits your purpose best.")
    for oid, constraints in result["constraints"].items():
        for cid, passed in constraints.items():
            lines.append(f"- {_safe(options[oid])}, {cid} constraint: " +
                         ("unknown" if passed is None else "meets limit" if passed else "outside limit"))
    if result["ranking"]:
        lines += ["", "## Weighted ranking", "", result["scoring_method"], ""]
        for row in result["ranking"]:
            lines.append(f"- {_safe(options[row['option']])}: {row['score']:g}/100")
        lines += ["", "Scores describe these options under your supplied weights; they are not probabilities."]
    lines += ["", "## Evidence and limitations", ""]
    for sid, source in result["sources"].items():
        locator = source.get("url") or source.get("path") or "supplied text"
        lines.append(f"- [{sid}] {_safe(source.get('title', sid))} — {_safe(locator)}; "
                     f"as of {_safe(source.get('as_of') or 'not specified')}. "
                     f"{_safe(source.get('disclosure', ''))}")
        if source.get("error"):
            lines.append("  Source unavailable: " + _safe(source["error"]))
    for oid, row in result["cells"].items():
        for cid, cell in row.items():
            for observation in cell.get("observations", [cell]):
                if observation.get("quote"):
                    lines.append(f"- {_safe(options[oid])} / {cid}: “{_safe(observation['quote'])}” "
                                 f"[{observation['source']}]")
                if observation.get("calculation"):
                    lines.append("  Calculation: " + observation["calculation"])
    lines.extend("- " + warning for warning in result["warnings"])
    lines += ["", "A matching passage establishes where a value came from; it does not establish that "
              "the source is correct. Qualitative interpretations remain labelled as inferences."]
    return "\n".join(lines) + "\n"
