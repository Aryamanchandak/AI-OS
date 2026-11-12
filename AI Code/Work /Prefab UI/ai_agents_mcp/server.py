"""
server.py — FastMCP server entry point

Responsibilities:
1. Create the MCP server
2. Register all tool UIs
3. Expose route_query — the single user-facing entry point

The route_query tool uses Gemini to classify user intent and returns
the appropriate Prefab UI. It is the only tool the host model should
present to the user directly.
"""

import os
from dotenv import load_dotenv
from fastmcp import FastMCP
from google import genai

import config

# ── TOOL MODULES ──────────────────────────────────────────────────────────────
from tools import (
    report_chatbot,
    meeting_recorder,
    podcast_agent,
    us_result_note,
    annual_report_analysis,
)

load_dotenv()

# ── SERVER SETUP ──────────────────────────────────────────────────────────────
mcp = FastMCP(
    name="AI Agents MCP",
    instructions=(
        "This server provides access to 5 AI-powered financial analysis tools. "
        "Always use route_query as the entry point — pass the user's raw message to it. "
        "Do not call the individual tool UIs directly."
    ),
)

# ── REGISTER TOOL UIs ─────────────────────────────────────────────────────────
# Each module's register() function attaches its build_ui() as an @mcp.tool(app=True).
# The individual UI tools are also app-tools and can be rendered directly if needed,
# but the model should route through route_query.

report_chatbot.register(mcp)
meeting_recorder.register(mcp)
podcast_agent.register(mcp)
us_result_note.register(mcp)
annual_report_analysis.register(mcp)

# ── GEMINI CLIENT ─────────────────────────────────────────────────────────────
_gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def _classify_intent(user_query: str) -> str:
    """
    Use Gemini to classify the user's query into one of the 5 system keys.
    Returns a key from config.VALID_SYSTEMS.
    Falls back to 'annual_report_analysis' if classification fails.
    """
    system_list = "\n".join(
        f"- {key}: {desc}"
        for key, desc in config.SYSTEM_DESCRIPTIONS.items()
    )

    prompt = (
        f"User query: {user_query}\n\n"
        f"Available systems:\n{system_list}\n\n"
        f"Return ONLY the key of the best matching system. "
        f"Valid keys: {', '.join(config.VALID_SYSTEMS)}"
    )

    response = _gemini_client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
        config={"system_instruction": config.ROUTER_SYSTEM_PROMPT},
    )

    result = response.text.strip().lower().replace('"', "").replace("'", "")

    if result not in config.VALID_SYSTEMS:
        # Graceful fallback — log the bad response for debugging
        print(
            f"[ROUTER] Gemini returned invalid key: '{result}' "
            f"— falling back to annual_report_analysis"
        )
        return "annual_report_analysis"

    return result


# ── TOOL MAP ──────────────────────────────────────────────────────────────────
_TOOL_MAP = {
    "report_chatbot":         report_chatbot,
    "meeting_recorder":       meeting_recorder,
    "podcast_agent":          podcast_agent,
    "us_result_note":         us_result_note,
    "annual_report_analysis": annual_report_analysis,
}


# ── ROUTE QUERY TOOL ──────────────────────────────────────────────────────────
@mcp.tool(app=True)
def route_query(query: str):
    """
    Main entry point for the AI Agents platform.
    Takes any natural language query, identifies which AI tool the user needs,
    and opens the correct interface.

    Examples:
    - "analyse Reliance's annual report" -> opens Annual Report Analysis
    - "I want to record a meeting" -> opens Meeting Recorder
    - "play the pharma sector podcast" -> opens Podcast Agent
    - "upload a Morningstar report" -> opens US Result Note
    - "chat with HDFC's concall documents" -> opens Report ChatBot
    """
    system_key = _classify_intent(query)
    print(f"[ROUTER] Query: '{query}' -> Routed to: '{system_key}'")

    # Call the plain build_ui() function on the matched module and return its PrefabApp
    tool_module = _TOOL_MAP[system_key]
    return tool_module.build_ui()


# ── ENTRY POINT ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run()
