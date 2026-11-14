"""Settings, read once from `.env` and the environment. Nothing here is printed."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env(path: Path) -> None:
    """Minimal KEY=VALUE loader. Values already in the environment win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


@dataclass(frozen=True)
class Settings:
    port: int
    engine_url: str
    engine_token: str
    gateway_url: str
    gateway_provider: str
    workspace: Path
    data: Path
    run_timeout: int

    @classmethod
    def load(cls) -> Settings:
        load_env(ROOT / ".env")
        env = os.environ.get
        return cls(
            port=int(env("FTB_PORT", "8120")),
            engine_url=env("S17_BASE_URL", "http://127.0.0.1:8113").rstrip("/"),
            engine_token=env("S17_CONTROL_TOKEN", ""),
            gateway_url=env("GLC_BASE_URL", "http://127.0.0.1:8111").rstrip("/"),
            gateway_provider=env("FTB_GATEWAY_PROVIDER", "gemini"),
            workspace=Path(env("FTB_WORKSPACE", str(ROOT / "workspace"))).resolve(),
            data=Path(env("FTB_DATA", str(ROOT / "data"))).resolve(),
            run_timeout=int(env("FTB_RUN_TIMEOUT", "900")),
        )
