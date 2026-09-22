"""Runtime bindings shared by in-process adapters and standalone workers."""

from __future__ import annotations

from gateway.platform.configuration import GLCPaths

_install_token: str | None = None


def bind_install_token(token: str | None) -> None:
    global _install_token
    _install_token = token


def get_install_token() -> str:
    global _install_token
    if _install_token is None:
        _install_token = GLCPaths().get_or_create_install_token()
    return _install_token
