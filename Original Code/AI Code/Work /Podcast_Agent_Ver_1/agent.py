"""Agentic entry point.

Lists the podcasts from podcasts.yaml, lets you pick one, then hands control to a
Gemini agent that drives the MCP server (server.py) over stdio. Gemini decides which
tools to call — RSS first, YouTube as a fallback — to fetch, transcribe, summarise,
save, and render a Prefab UI for the latest episode.

The agent uses a manual MCP↔Gemini function-calling bridge rather than the SDK's
experimental `tools=[session]` auto-calling, which currently crashes on FastMCP tool
schemas (deepcopy of the live session + a boolean-schema filter bug in google-genai).

Run:  python agent.py            (interactive picker)
      python agent.py 6          (pick podcast #6 non-interactively)
"""
import asyncio
import os
import sys
import webbrowser

from google import genai
from google.genai import types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from config import AGENT_MODEL
from pipeline import load_podcasts

SERVER = StdioServerParameters(command=sys.executable, args=["server.py"])
MAX_STEPS = 25

TASK_TEMPLATE = """\
You are an autonomous podcast-summarising agent. Summarise the LATEST episode of the
podcast below by calling the available MCP tools, in this order:

Podcast name: {name}
RSS feed: {rss}

Steps:
1. Call get_latest_rss_episode with the RSS feed.
2. If it returns a non-null audio_url, call download_audio with that audio_url.
   If audio_url is null, call find_youtube_episode with the podcast name (and the
   episode title if you have it), then call download_audio with the returned YouTube url.
3. Call transcribe_audio with the audio_path.
4. Call summarise_transcript with the transcript_ref, the episode title, the source_url,
   and duration_seconds from the download step.
5. Call save_outputs with the podcast name, episode title, transcript_ref and summary_ref.
6. Call render_summary_ui with the podcast name, episode title, summary_ref, transcript_ref,
   source_url, duration_seconds, and model "{model}".

When finished, reply with exactly one line: the html_path returned by render_summary_ui.
Do not invent data; rely only on tool results.
"""

# JSON-schema keys the Gemini API rejects in function-declaration parameters.
_DROP_SCHEMA_KEYS = {"$schema", "additionalProperties", "title", "$defs", "default"}


def _sanitise_schema(node):
    """Recursively strip unsupported keys so MCP tool schemas are Gemini-compatible."""
    if isinstance(node, dict):
        return {
            k: _sanitise_schema(v)
            for k, v in node.items()
            if k not in _DROP_SCHEMA_KEYS
        }
    if isinstance(node, list):
        return [_sanitise_schema(v) for v in node]
    return node


def _mcp_tools_to_gemini(mcp_tools) -> list[types.FunctionDeclaration]:
    return [
        types.FunctionDeclaration(
            name=t.name,
            description=t.description or "",
            parameters_json_schema=_sanitise_schema(t.inputSchema or {"type": "object"}),
        )
        for t in mcp_tools
    ]


def _tool_payload(result) -> dict:
    """Turn an MCP CallToolResult into a JSON dict for the model."""
    text = "".join(
        getattr(b, "text", "") for b in (getattr(result, "content", None) or [])
    )
    if getattr(result, "isError", False):
        return {"error": text or "tool failed"}
    sc = getattr(result, "structuredContent", None)
    if isinstance(sc, dict):
        return sc
    if sc is not None:
        return {"result": sc}
    return {"result": text}


def pick_podcast(podcasts: list[dict], arg: str | None) -> dict:
    if arg and arg.isdigit() and 1 <= int(arg) <= len(podcasts):
        return podcasts[int(arg) - 1]
    print("\nAvailable podcasts:")
    for i, p in enumerate(podcasts, 1):
        print(f"  {i:2}. {p['name']}")
    while True:
        choice = input("\nPick a number: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(podcasts):
            return podcasts[int(choice) - 1]
        print("Invalid choice.")


async def run(selected: dict) -> None:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key or api_key.startswith("your_"):
        sys.exit("GEMINI_API_KEY is not set in .env")

    client = genai.Client(api_key=api_key)
    task = TASK_TEMPLATE.format(
        name=selected["name"], rss=selected["rss"], model=AGENT_MODEL
    )

    print(f"\n[agent] Summarising latest episode of: {selected['name']}")
    print("[agent] Connecting to MCP server and running pipeline…\n")

    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tool_list = (await session.list_tools()).tools
            config = types.GenerateContentConfig(
                tools=[types.Tool(function_declarations=_mcp_tools_to_gemini(tool_list))],
                temperature=0,
            )

            contents: list[types.Content] = [
                types.Content(role="user", parts=[types.Part(text=task)])
            ]
            final_text = ""

            for _ in range(MAX_STEPS):
                resp = await client.aio.models.generate_content(
                    model=AGENT_MODEL, contents=contents, config=config
                )
                cand = resp.candidates[0]
                parts = cand.content.parts or []
                contents.append(cand.content)

                calls = [p.function_call for p in parts if p.function_call]
                if not calls:
                    final_text = (resp.text or "").strip()
                    break

                response_parts = []
                for fc in calls:
                    print(f"[tool] {fc.name}")
                    result = await session.call_tool(fc.name, dict(fc.args or {}))
                    response_parts.append(
                        types.Part(
                            function_response=types.FunctionResponse(
                                name=fc.name, response=_tool_payload(result)
                            )
                        )
                    )
                contents.append(types.Content(role="user", parts=response_parts))
            else:
                print(f"[agent] Stopped after {MAX_STEPS} steps.")

    print(f"\n[agent] {final_text}")

    html_path = final_text.splitlines()[-1].strip() if final_text else ""
    if html_path.endswith(".html") and os.path.exists(html_path):
        print(f"[agent] Opening {html_path}")
        webbrowser.open(f"file://{os.path.abspath(html_path)}")


def main() -> None:
    podcasts = load_podcasts()
    if not podcasts:
        sys.exit("No podcasts found in podcasts.yaml")
    selected = pick_podcast(podcasts, sys.argv[1] if len(sys.argv) > 1 else None)
    asyncio.run(run(selected))


if __name__ == "__main__":
    main()
