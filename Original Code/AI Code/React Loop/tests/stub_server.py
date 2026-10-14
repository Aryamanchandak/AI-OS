"""A minimal stub MCP server — a TEST FIXTURE, not a deliverable.

It exists only so the loop's mechanics can be verified end-to-end without the
real (heavy) server or any network. It exposes a couple of deterministic tools
shaped like the real server's (get_time, currency_convert) plus one that always
errors, so the "tool failure is an observation" path can be exercised.

Runtime default still points at the real server (react_loop/config.py).
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("react-loop-stub")


@mcp.tool()
def get_time() -> str:
    """Return a fixed UTC timestamp (deterministic for tests)."""
    return "2026-07-04T12:00:00Z"


@mcp.tool()
def currency_convert(amount: float, from_currency: str, to_currency: str) -> str:
    """Convert an amount using a fixed fake rate (deterministic for tests)."""
    rate = 0.9  # pretend 1 USD = 0.9 EUR
    return f"{amount} {from_currency} = {round(amount * rate, 2)} {to_currency}"


@mcp.tool()
def always_fails() -> str:
    """A tool that always raises, to exercise the error-observation path."""
    raise RuntimeError("boom")


@mcp.tool()
def echo(text: str) -> str:
    """Return text, except a sentinel bad value used by recovery tests."""
    if text == "bad":
        return "ERROR: bad input"
    return text


if __name__ == "__main__":
    mcp.run()
