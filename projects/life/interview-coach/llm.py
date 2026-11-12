"""Claude calls: generate a question, grade an answer."""
import json
import os
import re
from pathlib import Path

from anthropic import Anthropic

import schema

PROMPT_DIR = Path(__file__).parent / "prompts"

_client = None


def client():
    global _client
    if _client is None:
        _client = Anthropic()  # reads ANTHROPIC_API_KEY from env
    return _client


def model():
    return os.getenv("CLAUDE_MODEL", "claude-opus-5-5")


def _parse_json(text):
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.MULTILINE).strip()
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object in model output")
    return json.loads(t[start : end + 1])


def _json_call(system, user, max_tokens, validate=None):
    last_err = None
    for _ in range(2):  # one retry on malformed or invalid JSON
        msg = client().messages.create(
            model=model(),
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        try:
            reply = _parse_json(text)
            if validate:
                validate(reply)
            return reply
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise RuntimeError(f"Claude returned an unusable reply twice: {last_err}")


# ---------------------------------------------------------------- questions


GEN_SYSTEM = (PROMPT_DIR / "question.md").read_text(encoding="utf-8")


def generate_question(qtype, context, prep_s, answer_s, recent_questions, system_prompt=None):
    recent = "\n".join(f"- {q}" for q in recent_questions) or "(none)"
    user = f"""Candidate context (what they are preparing for, written by the candidate):
<context>
{context or "(not provided - assume a competitive UK graduate / early-career analytics, finance or consulting role)"}
</context>

Question type: {qtype}
Prep time: {prep_s} seconds. Answer time: {answer_s} seconds.

Do not repeat or closely paraphrase these recent questions:
{recent}

Generate one question now."""
    q = _json_call(GEN_SYSTEM if system_prompt is None else system_prompt, user, 6000,
                   validate=schema.validate_question)
    q["type"] = q.get("type") or qtype
    if q["type"] != "chart":
        q["chart"] = None
    return q


# ---------------------------------------------------------------- grading

GRADE_SYSTEM = (PROMPT_DIR / "evaluation.md").read_text(encoding="utf-8")


def grade(question, context, prep_s, answer_s, annotated_transcript, metrics, system_prompt=None):
    hidden = {
        "type": question.get("type"),
        "question": question.get("question"),
        "context_note": question.get("context_note"),
        "chart": question.get("chart"),
        "assessing": question.get("assessing"),
        "strong_answer_covers": question.get("strong_answer_covers"),
        "common_mistakes": question.get("common_mistakes"),
    }
    user = f"""Candidate context:
<context>
{context or "(not provided)"}
</context>

Question shown (with the assessor notes the candidate did NOT see):
<question>
{json.dumps(hidden, indent=2)}
</question>

Prep time: {prep_s} s. Answer time limit: {answer_s} s.

Annotated transcript (timestamps are seconds from start of recording; [pause Xs] = silence; [looks away: ...] = gaze off the camera lens; [not in frame] = face not detected):
<transcript>
{annotated_transcript or "(no speech detected)"}
</transcript>

Delivery metrics:
<metrics>
{json.dumps(metrics, indent=2)}
</metrics>

Assess the answer now."""
    return _json_call(GRADE_SYSTEM if system_prompt is None else system_prompt, user, 4000,
                      validate=schema.validate_grade)
