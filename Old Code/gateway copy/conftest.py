"""Deterministic defaults for the self-contained gateway test suite."""

import os

import pytest


os.environ.setdefault("AI_OS_PREVIEW", "1")
os.environ.setdefault("AI_OS_TOKEN", "gateway-test-token")


@pytest.fixture
def anyio_backend():
    return "asyncio"
