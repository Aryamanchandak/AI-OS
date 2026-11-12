import os
import json
import asyncio
from fastapi import APIRouter
from pydantic import BaseModel
from openai import OpenAI

_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
_MODEL = "gpt-4o"

optimizer_router = APIRouter(prefix="/optimizer")

# ── Prompts ───────────────────────────────────────────────────────────────────

DEFAULT_GUIDE_PROMPT = """You are a prompt and plan optimization assistant. Your job is to help the user improve one section at a time through conversation.

When the user sends a message, choose exactly one path:
- EXPLAIN: If they ask why the section is the way it is — put your explanation in "reasoning", leave "rewritten_content" unchanged.
- REWRITE: If they ask you to change something — rewrite in "rewritten_content", explain the change in "reasoning".
- ASK: If the request is ambiguous or you lack context to do it well — ask one focused question via "clarifying_question", leave "rewritten_content" unchanged. Always prefer asking over guessing.

Additional rules:
- If the chat reveals a project fact worth preserving, surface it in "suggested_context_update".
- Stay strictly in scope: only modify the current section, never others.
- Be direct and terse. No preamble, no lectures, no editorializing."""

_CONTEXT_EXTRACTOR = """You are extracting structured project context from a user's freeform dump.

Return ONLY valid JSON with this exact schema:
{
  "goal": "one or two sentences on what is being built and why",
  "tech_stack": ["array", "of", "technologies"],
  "constraints": ["array of constraints — deadlines, infra limits, things off-limits, team size"],
  "key_decisions": ["decisions already made that should not be re-litigated"],
  "architecture_notes": "any load-bearing architectural notes, or empty string",
  "open_questions": ["things the user explicitly hasn't decided yet"]
}

Rules:
- Use empty array or empty string for fields with no info. Do not invent.
- Be terse. This is going into a system prompt, not a report."""


def _section_detector(mode: str) -> str:
    kind_opts = (
        "one of: system | role | context | examples | output_format | constraints | other"
        if mode == "prompt"
        else "one of: phase | module | criteria | rationale | overview | other"
    )
    doc_type = "prompt" if mode == "prompt" else "technical plan written in markdown"
    return f"""You are splitting a {doc_type} into its constituent sections.

Return ONLY valid JSON with this exact schema:
{{
  "sections": [
    {{
      "title": "short label, 2-6 words",
      "kind": "{kind_opts}",
      "content": "VERBATIM text from the input — do not paraphrase or summarize",
      "rationale": "one sentence explaining why this section exists as a distinct unit"
    }}
  ]
}}

Splitting rules:
- Prefer splitting on existing markdown headers (# / ## / ###) when present.
- Otherwise split on semantic boundaries: role changes, topic shifts, phase transitions.
- Each section should be 1-3 paragraphs. Merge tiny fragments. Split overly long sections at natural sub-topics.
- The "content" field MUST contain the original text exactly as written.
- If the input has no clear structure, fall back to one section with kind="other"."""


def _iteration_prompt(mode: str, project_context, full_document: str, section: dict,
                      user_message: str, guide_prompt: str | None) -> str:
    ctx = json.dumps(project_context, indent=2) if project_context else "(no context provided)"
    guide = guide_prompt or DEFAULT_GUIDE_PROMPT
    return f"""{guide}

MODE: {"Prompt optimization" if mode == "prompt" else "Plan iteration"}

PROJECT CONTEXT:
{ctx}

FULL DOCUMENT (for cross-section awareness):
{full_document}

CURRENT SECTION:
Title: {section.get("title", "")}
Kind: {section.get("kind", "")}
Rationale: {section.get("rationale", "")}
Content:
\"\"\"
{section.get("content", "")}
\"\"\"

USER MESSAGE: {user_message}

Return ONLY valid JSON:
{{
  "rewritten_content": "new content, or unchanged if explaining/asking",
  "reasoning": "plain English explanation of your response",
  "clarifying_question": "a question OR null",
  "suggested_context_update": "a context update OR null"
}}"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _call_json(system: str, user_message: str, max_tokens: int = 2000) -> dict:
    resp = _client.chat.completions.create(
        model=_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_object"},
        max_tokens=max_tokens,
    )
    return json.loads(resp.choices[0].message.content)


# ── Request models ────────────────────────────────────────────────────────────

class ExtractContextReq(BaseModel):
    raw: str

class DetectSectionsReq(BaseModel):
    raw_input: str
    mode: str = "prompt"

class IterateSectionReq(BaseModel):
    mode: str
    section: dict
    full_document: str
    project_context: dict | None = None
    user_message: str
    guide_prompt: str | None = None


# ── Routes ────────────────────────────────────────────────────────────────────

@optimizer_router.post("/extract_context")
async def extract_context(req: ExtractContextReq):
    result = await asyncio.to_thread(_call_json, _CONTEXT_EXTRACTOR, req.raw, 1500)
    return {"extracted": result, "raw": req.raw}


@optimizer_router.post("/detect_sections")
async def detect_sections(req: DetectSectionsReq):
    system = _section_detector(req.mode)
    result = await asyncio.to_thread(_call_json, system, req.raw_input, 4000)
    sections = result.get("sections", [])
    return {
        "sections": [
            {
                "id": f"s{i + 1}",
                "title": s.get("title", ""),
                "kind": s.get("kind", "other"),
                "content": s.get("content", ""),
                "rationale": s.get("rationale", ""),
                "history": [],
            }
            for i, s in enumerate(sections)
        ]
    }


@optimizer_router.post("/iterate_section")
async def iterate_section(req: IterateSectionReq):
    system = _iteration_prompt(
        mode=req.mode,
        project_context=req.project_context,
        full_document=req.full_document,
        section=req.section,
        user_message=req.user_message,
        guide_prompt=req.guide_prompt,
    )
    result = await asyncio.to_thread(_call_json, system, req.user_message, 3000)
    return {
        "rewritten_content": result.get("rewritten_content", req.section.get("content", "")),
        "reasoning": result.get("reasoning", ""),
        "clarifying_question": result.get("clarifying_question"),
        "suggested_context_update": result.get("suggested_context_update"),
    }
