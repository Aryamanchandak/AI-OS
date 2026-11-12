import os
import sys
import re
import json
import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

MEMORY_DIR = "/Users/aryamanchandak/Documents/Obsidian Vault/Aryamans Vault/Agent MD"
TOKEN_BUDGET_CHARS = 8000   # ~2000 tokens at ~4 chars/token
RECENT_DAYS = 7

_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
_model = "gpt-4o-mini"  # mini is sufficient for title/notes generation, faster and cheaper

# Patterns that suggest prompt injection attempts in memory files
_INJECTION_PATTERNS = [
    re.compile(r'tell\s+application', re.IGNORECASE),
    re.compile(r'do\s+shell\s+script', re.IGNORECASE),
    re.compile(r'ignore\s+previous\s+instructions', re.IGNORECASE),
    re.compile(r'disregard.{0,20}(instructions|system)', re.IGNORECASE),
    re.compile(r'you\s+are\s+now\s+a', re.IGNORECASE),
    re.compile(r'<\|(system|user|assistant)\|>', re.IGNORECASE),
]


def _sanitize_memory(content: str) -> str:
    """Strip lines from memory file content that match known prompt-injection patterns."""
    lines = content.splitlines()
    clean = []
    for line in lines:
        if any(p.search(line) for p in _INJECTION_PATTERNS):
            clean.append('[redacted]')
        else:
            clean.append(line)
    return '\n'.join(clean)


# ---------- Private helpers ----------

def _parse_filename_date(filename: str) -> datetime.datetime | None:
    """Parse datetime from a memory filename like '2026-04-10_14-32_some-title.md'."""
    try:
        parts = filename.replace(".md", "").split("_")
        return datetime.datetime.strptime(f"{parts[0]}_{parts[1]}", "%Y-%m-%d_%H-%M")
    except Exception:
        return None


def _extract_section(content: str, section_header: str) -> str:
    """
    Extract text under a markdown section header, up to the next header line.
    Returns empty string if the header is not found.
    """
    lines = content.splitlines()
    collecting = False
    result = []
    for line in lines:
        if line.strip() == section_header.strip():
            collecting = True
            continue
        if collecting:
            if line.startswith("#"):
                break
            result.append(line)
    return "\n".join(result).strip()


# ---------- Public write functions ----------

def generate_session_title(messages: list) -> str:
    """
    Generate a 3-5 word hyphen-separated slug summarising the session.
    Falls back to 'general-session' on any failure.
    """
    try:
        sample = messages[:6]
        conv = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Bot'}: {m['content']}"
            for m in sample
        )
        response = _client.chat.completions.create(
            model=_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Return ONLY a 3-5 word lowercase hyphen-separated title summarising "
                        "this conversation. No punctuation, no explanation, just the slug."
                    ),
                },
                {"role": "user", "content": conv},
            ],
            timeout=30,
        )
        raw = response.choices[0].message.content.strip().lower()
        # Take first line only, sanitise to alphanumeric + hyphens
        slug = raw.splitlines()[0]
        slug = "".join(c if c.isalnum() or c == "-" else "-" for c in slug).strip("-")
        slug = "-".join(p for p in slug.split("-") if p)  # collapse multiple hyphens
        return slug or "general-session"
    except Exception:
        return "general-session"


def generate_carry_forward_notes(messages: list, current_plan: dict | None) -> str:
    """
    Extract bullet-point carry-forward notes from the session via gpt-4o-mini.
    Returns '(none)' if the session is too short or the call fails.
    """
    if len(messages) <= 2:
        return "(none)"
    try:
        conv = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Bot'}: {m['content']}"
            for m in messages
        )
        plan_section = ""
        if current_plan:
            plan_section = f"\n\nConfirmed plan:\n{json.dumps(current_plan, indent=2)}"
        response = _client.chat.completions.create(
            model=_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract carry-forward notes from this session. Focus on: "
                        "unconfirmed follow-ups, stated preferences, pending decisions, "
                        "unresolved commitments, AND any feedback the user gave about how a "
                        "plan played out (e.g. tasks took longer/shorter than planned, what was "
                        "rescheduled, what was skipped, time blocks that were too tight or too "
                        "loose). These calibrate future plans. "
                        "Return ONLY a short markdown bullet list (2-6 bullets max). "
                        "No preamble, no closing remarks."
                    ),
                },
                {"role": "user", "content": conv + plan_section},
            ],
            timeout=30,
        )
        notes = response.choices[0].message.content.strip()
        return notes if notes else "(none)"
    except Exception:
        return "(none)"


def build_memory_markdown(
    session_dt: datetime.datetime,
    title: str,
    modes_visited: list,
    messages: list,
    current_plan: dict | None,
    carry_forward: str,
) -> str:
    """Assemble the full markdown string for a memory file. No API calls."""
    dt_str = session_dt.strftime("%Y-%m-%d %H:%M")
    modes_str = " → ".join(modes_visited)

    lines = [
        f"# Session: {dt_str}",
        f"# Title: {title}",
        f"## Modes visited: {modes_str}",
        "",
        "### Conversation",
    ]
    for m in messages:
        speaker = "You" if m["role"] == "user" else "Bot"
        lines.append(f"**{speaker}:** {m['content']}")
        lines.append("")

    lines += [
        "### Plan Executed",
    ]
    if current_plan:
        lines.append("```json")
        lines.append(json.dumps(current_plan, indent=2))
        lines.append("```")
    else:
        lines.append("(no plan confirmed this session)")

    lines += [
        "",
        "### Carry-Forward Notes",
        carry_forward,
    ]

    return "\n".join(lines)


def save_session(
    messages: list,
    modes_visited: list,
    current_plan: dict | None,
    session_start_time: datetime.datetime,
) -> str:
    """
    Orchestrate title generation, carry-forward notes, markdown assembly, and disk write.
    Returns the absolute path of the file written.
    """
    os.makedirs(MEMORY_DIR, exist_ok=True)

    title = generate_session_title(messages)
    carry_forward = generate_carry_forward_notes(messages, current_plan)
    content = build_memory_markdown(
        session_dt=session_start_time,
        title=title,
        modes_visited=modes_visited,
        messages=messages,
        current_plan=current_plan,
        carry_forward=carry_forward,
    )

    filename = session_start_time.strftime("%Y-%m-%d_%H-%M") + "_" + title + ".md"
    path = os.path.join(MEMORY_DIR, filename)

    # Avoid clobbering if a file with this name already exists (same-minute session restart)
    if os.path.exists(path):
        base = path[:-3]  # strip .md
        counter = 1
        while os.path.exists(f"{base}_{counter}.md"):
            counter += 1
        path = f"{base}_{counter}.md"

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    return path


# ---------- Public read function ----------

def load_memory_context() -> str:
    """
    Load recent memory files and return a formatted context string for injection
    into the system prompt. Returns '' if no memory files exist.

    Priority:
      1. Carry-Forward Notes from all sessions within the last RECENT_DAYS days
      2. Full Conversation from the most recent session (if budget remains)
    Caps total output at TOKEN_BUDGET_CHARS characters.
    """
    if not os.path.exists(MEMORY_DIR):
        return ""

    md_files = [f for f in os.listdir(MEMORY_DIR) if f.endswith(".md")]
    if not md_files:
        return ""

    # Pair each file with its parsed datetime; skip unparseable filenames
    dated_files = []
    for f in md_files:
        dt = _parse_filename_date(f)
        if dt is not None:
            dated_files.append((dt, f))

    if not dated_files:
        return ""

    # Sort descending (most recent first)
    dated_files.sort(key=lambda x: x[0], reverse=True)

    now = datetime.datetime.now()
    cutoff = now - datetime.timedelta(days=RECENT_DAYS)

    accumulated = []
    budget_used = 0

    # --- Step 1: Carry-Forward Notes from last RECENT_DAYS days ---
    recent_notes_parts = []
    for dt, fname in dated_files:
        if dt < cutoff:
            continue
        try:
            fpath = os.path.join(MEMORY_DIR, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            content = _sanitize_memory(content)
            notes = _extract_section(content, "### Carry-Forward Notes")
            if notes and notes != "(none)":
                date_str = dt.strftime("%Y-%m-%d")
                chunk = f"[{date_str}]\n{notes}"
                if budget_used + len(chunk) <= TOKEN_BUDGET_CHARS:
                    recent_notes_parts.append(chunk)
                    budget_used += len(chunk)
        except Exception as e:
            print(f"[memory] Could not read {fname}: {e}", file=sys.stderr)

    if recent_notes_parts:
        accumulated.append("## Recent Carry-Forward Notes\n" + "\n\n".join(recent_notes_parts))

    # --- Step 2: Full conversation from the most recent file only ---
    if budget_used < TOKEN_BUDGET_CHARS and dated_files:
        most_recent_dt, most_recent_fname = dated_files[0]
        try:
            fpath = os.path.join(MEMORY_DIR, most_recent_fname)
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            content = _sanitize_memory(content)
            conv = _extract_section(content, "### Conversation")
            if conv:
                remaining = TOKEN_BUDGET_CHARS - budget_used
                if len(conv) > remaining:
                    conv = conv[:remaining] + "\n... [truncated]"
                date_str = most_recent_dt.strftime("%Y-%m-%d %H:%M")
                accumulated.append(f"## Most Recent Session ({date_str})\n{conv}")
        except Exception as e:
            print(f"[memory] Could not read {most_recent_fname}: {e}", file=sys.stderr)

    if not accumulated:
        return ""

    return "\n\n".join(accumulated)