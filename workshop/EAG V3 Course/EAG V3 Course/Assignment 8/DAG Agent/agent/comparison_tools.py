"""Tool contracts connecting evidence readers and comparison calculations."""

import json

from agent.comparison import compare
from agent.comparison_report import render_report


def collect_option(raw):
    from agent.sources import read_sources
    option = json.loads(raw)
    option["sources"] = read_sources(option.get("sources", []), option["name"])
    return json.dumps({"kind": "sources", "option": option})


def _decode(value):
    """Models often wrap JSON in a code fence or a sentence; read the object inside."""
    try:
        return json.loads(value)
    except ValueError:
        return json.loads(value[value.index("{"):value.rindex("}") + 1])


def align(raw, context):
    request = json.loads(raw)
    decoded = [_decode(value) for value in context.values()]
    for option in request["options"]:
        collected = next((d["option"] for d in decoded if d.get("kind") == "sources"
                          and d["option"]["id"] == option["id"]), None)
        if collected is None:
            raise ValueError("Missing collected evidence for " + option["id"])
        option["sources"] = collected["sources"]
        extraction = next((d for d in decoded if d.get("option") == option["id"]), None)
        option["evidence"] = extraction["evidence"] if extraction else collected.get("evidence", {})
        own_sources = {s["id"] for s in option["sources"]}
        for observation in option["evidence"].values():
            for cell in observation if isinstance(observation, list) else [observation]:
                if cell.get("value") is not None and cell.get("source") not in own_sources:
                    raise ValueError("Option evidence cites another option's source")
    return json.dumps(compare(request), allow_nan=False)


def report(raw, context):
    outputs = [json.loads(value) for nid, value in context.items() if nid != "interpretation"]
    result = next(d for d in outputs if "cells" in d)
    answer = render_report(result)
    if "interpretation" in context:
        from agent.interpretation import render_interpretation
        answer += render_interpretation(context["interpretation"], result)
    for output in outputs:
        if output.get("chart"):
            answer += "\nChart: " + output["chart"] + "\n"
        elif output.get("chart_error"):
            answer += "\nChart unavailable: " + output["chart_error"] + "\n"
    return answer


def chart(raw, context):
    from agent.charting import chart_comparison
    options = json.loads(raw)
    return json.dumps(chart_comparison(json.loads(next(iter(context.values()))),
                                     options["criterion"], options["directory"]))


REGISTRY = {"collect_option": collect_option, "align_comparison": align,
            "report_comparison": report, "chart_comparison": chart}


def research(raw):
    import re
    from agent.sources import read_sources
    try:
        spec = json.loads(raw)
    except ValueError:
        spec = {"query": raw, "urls": re.findall(r"https?://[^\s<>]+", raw)}
    urls = spec.get("urls", [])
    sources = ([{"id": f"web_{i}", "url": url} for i, url in enumerate(urls[:3], 1)]
               if urls else [{"id": "search", "search": spec.get("query", raw)}])
    return json.dumps({"query": spec.get("query", raw), "sources": read_sources(sources, "Web evidence")})


REGISTRY["research_sources"] = research
