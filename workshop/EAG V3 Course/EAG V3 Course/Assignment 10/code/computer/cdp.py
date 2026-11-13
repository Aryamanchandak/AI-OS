"""Preserve the page-session interface; delegate CDP plumbing to cua-driver."""
from __future__ import annotations
from types import SimpleNamespace
from .backend import CuaError, get_driver
CDPError = CuaError

class PageSession:
    def __init__(self, driver):
        self.driver = driver
    async def __aenter__(self):
        return self
    async def __aexit__(self, *exc):
        return False
    async def evaluate(self, expression):
        return self.driver.call("page", {**self.driver.window_args(),
                                         "action": "execute_javascript", "javascript": expression})
    async def title(self):
        return await self.evaluate("document.title")
    async def text(self, max_chars=20_000):
        return str(self.driver.call("page", {**self.driver.window_args(), "action": "get_text"}))[:max_chars]

async def open_page(port, *, hint=""):
    if not port:
        raise CDPError("Electron task requires electron_debugging_port")
    driver = get_driver()
    target = driver.target or {}
    return PageSession(driver), SimpleNamespace(title=target.get("title", ""), url="", type="page")
