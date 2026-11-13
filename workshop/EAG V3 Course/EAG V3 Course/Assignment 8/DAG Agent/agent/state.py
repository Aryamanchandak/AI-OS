"""Atomic, private execution checkpoints; completed nodes survive restarts."""

import json
import os
from pathlib import Path
import tempfile


class SessionStore:
    def __init__(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = directory / "state.json"

    def load(self):
        if not self.path.exists():
            return None
        try:
            value = json.loads(self.path.read_text())
            if value.get("version") != 1:
                raise ValueError("unsupported checkpoint version")
            return value
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("Invalid checkpoint; refusing to overwrite it") from exc

    def save(self, value):
        fd, temporary = tempfile.mkstemp(dir=self.path.parent, prefix=".state-")
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump({"version": 1, **value}, handle, allow_nan=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
