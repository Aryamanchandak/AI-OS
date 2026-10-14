"""Trajectory recording — the assignment's evidence artifact.

`start_recording(...)` opens a trajectory directory and returns a Recorder.
Everything the cascade does flows through it:

    traj_dir/
      manifest.json          — task, layers attempted, verdict, counters
      events.jsonl           — append-only event log, one JSON per line
      layer_1_extract/       — per-layer artifacts (screenshots, snapshots)
      layer_2a_hotkeys/
      layer_2b_ax/
      layer_3_vision/

Per-layer subdirs are load-bearing, not cosmetic. The assignment requires
one task to complete with *zero* vision calls, and the cleanest proof of a
negative is a directory that does not exist: if `layer_3_vision/` is absent
and `manifest.json` reports `vision_calls: 0`, the claim is checkable
without trusting the narrative. `Recorder.vision_calls` is incremented in
exactly one place (`note_llm_call` with layer="layer_3_vision"), so the
counter cannot silently drift from the artifacts on disk.
"""
from __future__ import annotations

import json
import os
import time
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
    """Append-only trajectory writer. Cheap to call; never raises into the
    cascade — a recording failure must not fail an otherwise-good run."""

    root: Path
    task: str
    goal: str
    started_at: float = field(default_factory=time.time)
    events: int = 0
    vision_calls: int = 0
    text_llm_calls: int = 0
    layers_attempted: list[str] = field(default_factory=list)

    # ── event log ──────────────────────────────────────────────────────────
    def log(self, kind: str, **payload: Any) -> None:
        """Append one event. Swallows IO errors by design (see class doc)."""
        rec = {
            "t": round(time.time() - self.started_at, 3),
            "kind": kind,
            **payload,
        }
        try:
            with (self.root / "events.jsonl").open("a") as f:
                f.write(json.dumps(rec, default=str) + "\n")
            self.events += 1
        except OSError:
            pass

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
        try:
            if isinstance(data, bytes):
                p.write_bytes(data)
            else:
                p.write_text(data)
        except OSError:
            return ""
        self.log("artifact", layer=layer, path=str(p.relative_to(self.root)))
        return str(p)

    # ── close-out ──────────────────────────────────────────────────────────
    def finish(self, *, success: bool, path: str, note: str = "",
               turns: int = 0) -> dict:
        """Write manifest.json and return it. `path` is the layer that
        actually produced the answer — the cascade's verdict."""
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
        }
        try:
            (self.root / "manifest.json").write_text(
                json.dumps(manifest, indent=2, default=str)
            )
        except OSError:
            pass
        self.log("finish", **{k: manifest[k] for k in
                              ("success", "resolved_at_layer", "vision_calls")})
        return manifest


def start_recording(task: str, goal: str, *,
                    root: str | os.PathLike | None = None) -> Recorder:
    """Open a trajectory directory and return the Recorder driving it.

    The directory name carries the task and a timestamp so repeated runs of
    the same task sort chronologically and never collide."""
    base = Path(root) if root else Path("state") / "trajectories"
    stamp = time.strftime("%Y%m%d_%H%M%S")
    d = base / f"{task}_{stamp}"
    d.mkdir(parents=True, exist_ok=True)
    rec = Recorder(root=d, task=task, goal=goal)
    rec.log("start", task=task, goal=goal, cwd=str(Path.cwd()))
    return rec
