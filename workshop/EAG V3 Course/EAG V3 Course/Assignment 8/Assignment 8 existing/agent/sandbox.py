"""SandboxExecutor — runs Coder/Charter output in a separate process.

Contract the prompts are written against:
  * the script is plain Python 3, stdlib + numpy/matplotlib only
  * upstream node outputs arrive as a JSON file whose path is argv[1]
  * anything the script prints to stdout is the node's result
  * files written to the artifacts dir are collected and reported
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field

FENCE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.S)


class SandboxError(RuntimeError):
    pass


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    returncode: int
    artifacts: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def extract_code(text: str) -> str:
    """Pull the Python block out of a model response."""
    blocks = FENCE.findall(text)
    if not blocks:
        raise SandboxError("no ```python block found in the coder response")
    return max(blocks, key=len).strip()


def run(code: str, inputs: dict, artifacts_dir: pathlib.Path, timeout: int = 60) -> SandboxResult:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    before = set(artifacts_dir.iterdir())

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        script = tmp_path / "node.py"
        payload = tmp_path / "inputs.json"
        script.write_text(code)
        payload.write_text(json.dumps(inputs, indent=2, default=str))

        try:
            proc = subprocess.run(
                [sys.executable, str(script), str(payload), str(artifacts_dir)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmp,
            )
        except subprocess.TimeoutExpired:
            raise SandboxError(f"sandbox script timed out after {timeout}s")

    new_artifacts = sorted(str(p) for p in set(artifacts_dir.iterdir()) - before)
    return SandboxResult(
        stdout=proc.stdout.strip(),
        stderr=proc.stderr.strip(),
        returncode=proc.returncode,
        artifacts=new_artifacts,
    )
