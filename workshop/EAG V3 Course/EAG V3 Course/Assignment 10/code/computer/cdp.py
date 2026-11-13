"""The `page` tool — Chrome DevTools Protocol against an Electron app.

This is the assignment's Electron path. An Electron app launched with
`--remote-debugging-port=NNNN` exposes the same CDP surface Chrome does, so
we can read the real DOM and evaluate JavaScript in the renderer instead of
guessing at pixels. That makes it a *structured* layer, not a vision one —
which is why the cascade places it beside Layer 1 rather than after 2b.

Framework-free by the same rule the browser skill follows: raw websockets
and httpx, no Playwright and no Electron SDK.

The one Electron-specific wrinkle worth knowing: `/json/list` returns every
target, including devtools pages, service workers and (in VS Code) several
webview iframes. Picking the wrong one yields a valid-looking connection to
a DOM that has nothing to do with the visible window, so `pick_target`
filters to real pages and prefers the one whose title matches.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
import websockets


@dataclass
class Target:
    id: str
    title: str
    url: str
    ws_url: str
    type: str


class CDPError(RuntimeError):
    pass


async def list_targets(port: int, *, timeout: float = 5.0) -> list[Target]:
    """Enumerate debuggable targets on `port`. Raises CDPError when nothing
    is listening — that is the common case (app not launched with the flag)
    and the cascade needs it distinguishable from 'connected but empty'."""
    url = f"http://127.0.0.1:{port}/json/list"
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get(url)
            r.raise_for_status()
            raw = r.json()
    except Exception as e:                               # noqa: BLE001
        raise CDPError(
            f"no CDP endpoint on port {port} ({type(e).__name__}). "
            f"Launch the app with --remote-debugging-port={port}."
        ) from e
    return [
        Target(id=t.get("id", ""), title=t.get("title", ""),
               url=t.get("url", ""), ws_url=t.get("webSocketDebuggerUrl", ""),
               type=t.get("type", ""))
        for t in raw if t.get("webSocketDebuggerUrl")
    ]


def pick_target(targets: list[Target], hint: str = "") -> Target:
    """Choose the page target, preferring a title/url match on `hint`."""
    pages = [t for t in targets if t.type == "page"] or targets
    if hint:
        h = hint.lower()
        for t in pages:
            if h in t.title.lower() or h in t.url.lower():
                return t
    if not pages:
        raise CDPError("CDP endpoint reachable but exposed no page targets")
    return pages[0]


class PageSession:
    """One CDP websocket, with `evaluate()` on top.

    Async-context-managed so the socket always closes — a leaked CDP
    connection keeps the renderer's debugger attached and visibly slows the
    app, which is a nasty thing to leave behind on someone's editor."""

    def __init__(self, ws_url: str, *, timeout: float = 20.0):
        self.ws_url = ws_url
        self.timeout = timeout
        self._ws: Any = None
        self._msg_id = 0

    async def __aenter__(self) -> "PageSession":
        # Electron DOMs can exceed the default 1 MiB frame cap; raising the
        # limit avoids a truncation that surfaces as an opaque close.
        self._ws = await websockets.connect(
            self.ws_url, max_size=32 * 1024 * 1024, open_timeout=self.timeout,
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def send(self, method: str, params: dict | None = None) -> dict:
        """Issue one CDP command and return its result.

        CDP multiplexes events and command replies on one socket, so we read
        until we see our own id rather than trusting the next frame."""
        if self._ws is None:
            raise CDPError("session not open")
        self._msg_id += 1
        msg_id = self._msg_id
        await self._ws.send(json.dumps(
            {"id": msg_id, "method": method, "params": params or {}}
        ))
        while True:
            raw = await self._ws.recv()
            msg = json.loads(raw)
            if msg.get("id") != msg_id:
                continue                      # an event, or another reply
            if "error" in msg:
                raise CDPError(f"{method}: {msg['error'].get('message')}")
            return msg.get("result", {})

    async def evaluate(self, expression: str, *, await_promise: bool = True) -> Any:
        """Evaluate JS in the page and return the value by JSON round-trip.

        `returnByValue` is what makes results usable here — without it CDP
        hands back a remote object handle that would need a second call to
        dereference."""
        res = await self.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": await_promise,
        })
        if res.get("exceptionDetails"):
            detail = res["exceptionDetails"]
            text = detail.get("exception", {}).get("description") or detail.get("text")
            raise CDPError(f"JS exception: {text}")
        return res.get("result", {}).get("value")

    async def title(self) -> str:
        return await self.evaluate("document.title") or ""

    async def text(self, max_chars: int = 20_000) -> str:
        """Visible text of the page — the Layer-1-equivalent read."""
        txt = await self.evaluate("document.body ? document.body.innerText : ''")
        txt = (txt or "").strip()
        return txt[:max_chars]


async def open_page(port: int, *, hint: str = "") -> tuple[PageSession, Target]:
    """Resolve a target on `port` and return an *unopened* session for it.

    Returning the session unentered keeps the `async with` at the call site,
    where the caller controls the lifetime."""
    targets = await list_targets(port)
    t = pick_target(targets, hint)
    return PageSession(t.ws_url), t
