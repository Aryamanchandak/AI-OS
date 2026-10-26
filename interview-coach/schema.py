"""Checks Claude's JSON replies have the fields, types and ranges the prompts ask for."""
import math

TYPES = ("competency", "motivational", "mba_essay", "chart", "case", "commercial_awareness")
CHART_KINDS = ("bar", "grouped_bar", "stacked_bar", "line")


def _text(value, name, blank_ok=False):
    if not isinstance(value, str) or (not blank_ok and not value.strip()):
        raise ValueError(f"'{name}' must be {'a string' if blank_ok else 'non-empty text'}")


def _object(value, name):
    if not isinstance(value, dict):
        raise ValueError(f"'{name}' must be an object")
    return value


def _list(value, name, non_empty=False):
    if not isinstance(value, list) or (non_empty and not value):
        raise ValueError(f"'{name}' must be a{' non-empty' if non_empty else ''} list")
    return value


def _text_list(obj, key, non_empty=False):
    for i, item in enumerate(_list(obj.get(key), key, non_empty)):
        _text(item, f"{key}[{i}]")


def _score(value, name):
    # bool is an int in Python, so exclude it explicitly.
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10:
        raise ValueError(f"'{name}' must be a whole number from 1 to 10")


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"'{name}' must be a finite number")


def validate_chart(chart):
    _object(chart, "chart")
    if chart.get("kind") not in CHART_KINDS:
        raise ValueError(f"chart 'kind' must be one of {', '.join(CHART_KINDS)}")
    _text(chart.get("title"), "chart.title")
    for key in ("x_label", "y_label", "source_note"):
        if chart.get(key) is not None:
            _text(chart[key], f"chart.{key}", blank_ok=True)
    cats = _list(chart.get("categories"), "chart.categories", non_empty=True)
    if len(cats) > 8:
        raise ValueError("chart has more than 8 categories")
    for i, c in enumerate(cats):
        _text(c, f"chart.categories[{i}]")
    series = _list(chart.get("series"), "chart.series", non_empty=True)
    if len(series) > 4:
        raise ValueError("chart has more than 4 series")
    for i, s in enumerate(series):
        _object(s, f"chart.series[{i}]")
        _text(s.get("name"), f"chart.series[{i}].name")
        values = _list(s.get("values"), f"chart.series[{i}].values")
        if len(values) != len(cats):
            raise ValueError(f"chart.series[{i}] has {len(values)} values for {len(cats)} categories")
        for j, v in enumerate(values):
            _number(v, f"chart.series[{i}].values[{j}]")


def validate_question(q):
    _object(q, "reply")
    # generate_question() fills in a missing type from the request, so only a wrong one is an error.
    if q.get("type") is not None and q["type"] not in TYPES:
        raise ValueError("'type' is not a known question type")
    _text(q.get("question"), "question")
    if q.get("context_note") is not None:
        _text(q["context_note"], "context_note", blank_ok=True)
    for key in ("assessing", "strong_answer_covers", "common_mistakes"):
        _text_list(q, key, non_empty=True)
    if q.get("type") == "chart" and q.get("chart") is None:
        raise ValueError("a chart question needs 'chart' data")
    if q.get("chart") is not None:
        validate_chart(q["chart"])


def _items(g, key, fields):
    for i, item in enumerate(_list(g.get(key), key)):
        _object(item, f"{key}[{i}]")
        for f in fields:
            _text(item.get(f), f"{key}[{i}].{f}")


def validate_grade(g):
    _object(g, "reply")
    _score(g.get("overall_score"), "overall_score")
    _text(g.get("verdict"), "verdict")
    _text(g.get("retry_focus"), "retry_focus")
    _text(g.get("model_answer"), "model_answer", blank_ok=True)
    _text_list(g, "what_worked")
    _text_list(g, "missed_points")
    _items(g, "top_fixes", ("issue", "evidence", "fix"))
    _items(g, "delivery_feedback", ("issue", "evidence", "fix"))
    _list(g.get("content_scores"), "content_scores", non_empty=True)
    _items(g, "content_scores", ("dimension", "comment"))
    for i, item in enumerate(g["content_scores"]):
        _score(item.get("score"), f"content_scores[{i}].score")
