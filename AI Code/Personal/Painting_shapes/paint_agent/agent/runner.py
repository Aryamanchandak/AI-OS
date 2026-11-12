"""
Gemini-powered agent that drives the paint MCP server.

Usage:
    cd paint_agent
    GEMINI_API_KEY=<your-key> python -m agent.runner
    GEMINI_API_KEY=<your-key> python -m agent.runner "draw circle radius 100 ..."
"""

import asyncio
import json
import os
import sys

from google import genai
from google.genai import types as gtypes
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agent.prompts import SYSTEM_PROMPT

# ---------------------------------------------------------------------------
# MCP → Gemini schema conversion
# ---------------------------------------------------------------------------

def _mcp_schema_to_gemini(input_schema: dict) -> gtypes.Schema:
    """
    Converts an MCP tool inputSchema (JSON Schema subset) into a google.genai Schema.
    Handles nested properties and required lists.
    """
    props = {}
    for name, prop in input_schema.get("properties", {}).items():
        json_type = prop.get("type", "string").upper()
        gemini_type = getattr(gtypes.Type, json_type, gtypes.Type.STRING)
        enum_vals = prop.get("enum")
        props[name] = gtypes.Schema(
            type=gemini_type,
            description=prop.get("description", ""),
            enum=enum_vals if enum_vals else None,
        )

    return gtypes.Schema(
        type=gtypes.Type.OBJECT,
        properties=props,
        required=input_schema.get("required", []),
    )


def _build_gemini_tool(mcp_tools) -> gtypes.Tool:
    declarations = [
        gtypes.FunctionDeclaration(
            name=t.name,
            description=t.description or "",
            parameters=_mcp_schema_to_gemini(t.inputSchema),
        )
        for t in mcp_tools
    ]
    return gtypes.Tool(function_declarations=declarations)


# ---------------------------------------------------------------------------
# MCP server subprocess parameters
# ---------------------------------------------------------------------------

def _server_params() -> StdioServerParameters:
    server_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        env={**os.environ, "PYTHONPATH": server_dir},
    )


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

async def run_agent(user_instruction: str):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            mcp_tools = (await session.list_tools()).tools
            gemini_tool = _build_gemini_tool(mcp_tools)

            config = gtypes.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=[gemini_tool],
            )

            # Seed the conversation
            history = [gtypes.Content(
                role="user",
                parts=[gtypes.Part(text=user_instruction)],
            )]

            print(f"\n[agent] User: {user_instruction}\n")

            while True:
                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=history,
                    config=config,
                )

                candidate = response.candidates[0]
                history.append(candidate.content)  # append model turn

                fn_calls = [
                    p.function_call
                    for p in candidate.content.parts
                    if p.function_call is not None
                ]

                if not fn_calls:
                    # Final text response — print and exit loop
                    for part in candidate.content.parts:
                        if part.text:
                            print(f"[agent] {part.text}")
                    break

                # Execute every function call, collect responses
                fn_response_parts = []
                for fc in fn_calls:
                    args = dict(fc.args)
                    print(f"[tool]   {fc.name}({json.dumps(args)})")

                    tool_result = await session.call_tool(fc.name, args)
                    result_text = "\n".join(
                        c.text for c in tool_result.content if hasattr(c, "text")
                    )
                    print(f"[result] {result_text}\n")

                    fn_response_parts.append(
                        gtypes.Part(
                            function_response=gtypes.FunctionResponse(
                                name=fc.name,
                                response={"result": result_text},
                            )
                        )
                    )

                # Append the tool results as a user turn and loop
                history.append(gtypes.Content(
                    role="user",
                    parts=fn_response_parts,
                ))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    if "GEMINI_API_KEY" not in os.environ:
        print("Error: GEMINI_API_KEY environment variable is not set.")
        sys.exit(1)

    if len(sys.argv) > 1:
        instruction = " ".join(sys.argv[1:])
    else:
        print("Paint Automation Agent  (powered by Gemini)")
        print("Example: draw a circle radius 120, square side 200, rectangle 400x150,")
        print("         write 'Hello World' in Georgia 28 inside the rectangle.\n")
        instruction = input("Your instruction: ").strip()
        if not instruction:
            print("No instruction. Exiting.")
            sys.exit(0)

    asyncio.run(run_agent(instruction))


if __name__ == "__main__":
    main()
