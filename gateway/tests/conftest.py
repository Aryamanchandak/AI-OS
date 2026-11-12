"""Deterministic defaults for the self-contained gateway test suite."""

import os
from pathlib import Path

import pytest

import gateway.config


os.environ.setdefault("AI_OS_TOKEN", "gateway-test-token")
# The normal suite never reads gateway/.env; only golden tests point back at it.
REAL_ENV_FILE = gateway.config.ENV_FILE
gateway.config.ENV_FILE = Path(__file__).parent / "absent.env"


@pytest.fixture
def anyio_backend():
    return "asyncio"
