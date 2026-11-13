"""Supplement native cua-driver trajectories with cascade events and verdicts.

A run is submittable only when both the native recording and this manifest
finalize successfully. No recording or write failure is silently accepted.
"""
from __future__ import annotations

import json
import os
import time
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


LAYER_DIRS = {
    "extract":     "layer_1_extract",
    "page":        "layer_2c_page",
    "deterministic": "layer_2a_hotkeys",
    "ax":          "layer_2b_ax",
    "vision":      "layer_3_vision",
}


@dataclass
class Recorder:
    """Assignment evidence supplements the driver's native trajectory.

    Recording errors are fatal: a run without evidence is not submittable.
    """

    root: Path
    task: str
    goal: str
    started_at: float = field(default_factory=time.time)
    events: int = 0
    vision_calls: int = 0
    text_llm_calls: int = 0
    layers_attempted: list[str] = field(default_factory=list)
    driver_recording: bool = False
    _driver: Any = field(default=None, repr=False)
    _recording_active: bool = False

    def begin(self, driver):
        from .backend import CuaError
        if driver.call("get_recording_state", {}).get("enabled"):
            raise CuaError("Another driver recording is active; finish it before this run")
        state = driver.call("start_recording", {"output_dir": str(self.root / "driver"),
                                                "record_video": False})
        if not state.get("enabled"):
            raise CuaError("Driver did not enable trajectory recording")
        self._driver = driver
        self.driver_recording = self._recording_active = True
        self.log("driver_recording_started", output_dir="driver")

    def stop(self):
        if self._recording_active:
            try:
                state = self._driver.call("stop_recording", {})
                (self.root / "driver_recording_state.json").write_text(json.dumps(state, indent=2))
                if state.get("last_error"):
                    raise OSError(f"Driver recording error: {state['last_error']}")
                if state.get("enabled"):
                    raise OSError("Driver recording did not stop")
            finally:
                self._recording_active = False

    # ── event log ──────────────────────────────────────────────────────────
    def log(self, kind: str, **payload: Any) -> None:
        """Append one event, surfacing any evidence-write failure."""
        rec = {
            "t": round(time.time() - self.started_at, 3),
            "kind": kind,
            **payload,
        }
        with (self.root / "events.jsonl").open("a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        self.events += 1

    def enter_layer(self, layer: str) -> Path:
        """Mark a layer as attempted and return its artifact dir, creating it.

        Creation is deliberate and only happens here — a layer directory
        exists on disk if and only if the cascade actually reached that
        layer."""
        if layer not in self.layers_attempted:
            self.layers_attempted.append(layer)
        d = self.root / LAYER_DIRS.get(layer, layer)
        d.mkdir(parents=True, exist_ok=True)
        self.log("layer_enter", layer=layer)
        return d

    def note_llm_call(self, layer: str, *, provider: str = "", model: str = "",
                      tokens_in: int = 0, tokens_out: int = 0,
                      latency_ms: int = 0) -> None:
        """The single place vision/text call counters move."""
        if layer == "vision":
            self.vision_calls += 1
        else:
            self.text_llm_calls += 1
        self.log("llm_call", layer=layer, provider=provider, model=model,
                 tokens_in=tokens_in, tokens_out=tokens_out,
                 latency_ms=latency_ms)

    def artifact(self, layer: str, name: str, data: bytes | str) -> str:
        """Write a per-layer artifact and return its path."""
        d = self.root / LAYER_DIRS.get(layer, layer)
        d.mkdir(parents=True, exist_ok=True)
        p = d / name
        if isinstance(data, bytes):
            p.write_bytes(data)
        else:
            p.write_text(data)
        self.log("artifact", layer=layer, path=str(p.relative_to(self.root)))
        return str(p)

    # ── close-out ──────────────────────────────────────────────────────────
    def finish(self, *, success: bool, path: str, note: str = "",
               turns: int = 0) -> dict:
        """Write manifest.json and return it. `path` is the layer that
        actually produced the answer — the cascade's verdict."""
        self.stop()
        self.log("finish", success=success, resolved_at_layer=path, vision_calls=self.vision_calls)
        manifest = {
            "task": self.task,
            "goal": self.goal,
            "success": success,
            "resolved_at_layer": path,
            "layers_attempted": self.layers_attempted,
            "turns": turns,
            "vision_calls": self.vision_calls,
            "text_llm_calls": self.text_llm_calls,
            "zero_vision": self.vision_calls == 0,
            "elapsed_s": round(time.time() - self.started_at, 2),
            "note": note,
            "events": self.events,
            "driver_recording": self.driver_recording,
            "driver_trajectory": "driver" if self.driver_recording else None,
        }
        (self.root / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
        return manifest


def start_recording(task: str, goal: str, *,
                    root: str | os.PathLike | None = None) -> Recorder:
    """Open a trajectory directory and return the Recorder driving it.

    The directory name carries the task and a timestamp so repeated runs of
    the same task sort chronologically and never collide."""
    base = Path(root) if root else Path("state") / "trajectories"
    stamp = time.strftime("%Y%m%d_%H%M%S")
    base.mkdir(parents=True, exist_ok=True)
    safe_task = "".join(c if c.isalnum() or c in "_-" else "_" for c in task)[:80] or "computer"
    d = Path(tempfile.mkdtemp(prefix=f"{safe_task}_{stamp}_", dir=base)).resolve()
    rec = Recorder(root=d, task=task, goal=goal)
    rec.log("start", task=task, goal=goal, cwd=str(Path.cwd()))
    return rec
