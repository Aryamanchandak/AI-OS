"""Headless tests for everything that does not need a camera or a permission grant.

The gate is a safety device, so it gets tested like one: the interesting cases
are all the ways it might arm when it shouldn't, or refuse to disarm when it
should.

    .venv/bin/python test_logic.py
"""

from __future__ import annotations

import sys

import numpy as np

import config
from actions import Executor
from fastpath import ScrollController
from gate import Gate, GateEvent
from recognizer import INDEX_MCP, Pose, Reading, _classify

FAILURES: list[str] = []


def check(name: str, condition: bool) -> None:
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}")
        FAILURES.append(name)


# --------------------------------------------------------------- fixtures --
def synth_hand(
    thumb_out: bool,
    index: bool,
    middle: bool,
    ring: bool,
    pinky: bool,
    thumb_up: bool = True,
) -> np.ndarray:
    """Build a plausible upright right hand with chosen fingers extended.

    Wrist at the bottom, fingers pointing up (smaller y). An extended finger
    puts its tip well beyond its PIP joint; a curled one pulls the tip back
    below the PIP, toward the wrist.
    """
    lm = np.zeros((21, 3), dtype=np.float32)
    lm[0] = (0.5, 0.9, 0.0)  # wrist

    # (mcp, pip, dip, tip) index groups and their x positions
    fingers = {
        "index": ((5, 6, 7, 8), 0.42, index),
        "middle": ((9, 10, 11, 12), 0.50, middle),
        "ring": ((13, 14, 15, 16), 0.58, ring),
        "pinky": ((17, 18, 19, 20), 0.66, pinky),
    }
    for _, (idxs, x, extended) in fingers.items():
        mcp, pip, dip, tip = idxs
        lm[mcp] = (x, 0.70, 0.0)
        lm[pip] = (x, 0.60, 0.0)
        if extended:
            lm[dip] = (x, 0.50, 0.0)
            lm[tip] = (x, 0.42, 0.0)
        else:
            # Curled: tip tucks back toward the palm, nearer the wrist than pip.
            lm[dip] = (x, 0.66, 0.0)
            lm[tip] = (x, 0.72, 0.0)

    # Thumb sits on the far side from the pinky when extended, and crosses
    # toward the pinky knuckle when tucked.
    lm[1] = (0.44, 0.80, 0.0)
    lm[2] = (0.40, 0.75, 0.0)
    if thumb_out:
        lm[3] = (0.34, 0.70, 0.0)
        lm[4] = (0.28, 0.62 if thumb_up else 0.98, 0.0)
    else:
        lm[3] = (0.46, 0.70, 0.0)
        lm[4] = (0.56, 0.66, 0.0)  # across the palm, close to pinky MCP
    return lm


def reading_at(pose: Pose, y: float) -> Reading:
    lm = np.zeros((21, 3), dtype=np.float32)
    lm[INDEX_MCP] = (0.5, y, 0.0)
    return Reading(pose=pose, landmarks=lm, handedness="Right")


# ------------------------------------------------------------- classifier --
def test_classifier() -> None:
    print("\nclassifier")
    check("open palm", _classify(synth_hand(True, True, True, True, True)) is Pose.OPEN_PALM)
    check("fist", _classify(synth_hand(False, False, False, False, False)) is Pose.FIST)
    check("two finger", _classify(synth_hand(False, True, True, False, False)) is Pose.TWO_FINGER)
    check("point", _classify(synth_hand(False, True, False, False, False)) is Pose.POINT)
    check("thumbs up",
          _classify(synth_hand(True, False, False, False, False, thumb_up=True)) is Pose.THUMBS_UP)
    check("thumbs down",
          _classify(synth_hand(True, False, False, False, False, thumb_up=False)) is Pose.THUMBS_DOWN)
    check("thumbs up != thumbs down",
          _classify(synth_hand(True, False, False, False, False, thumb_up=True))
          is not _classify(synth_hand(True, False, False, False, False, thumb_up=False)))


# ------------------------------------------------------------------- gate --
def test_gate() -> None:
    print("\ngate")
    g = Gate()
    check("starts asleep", not g.is_armed)

    # A single frame of the wake pose must not arm anything.
    check("one frame of open palm does not arm",
          g.update(Pose.OPEN_PALM, now=0.0) is GateEvent.NOTHING and not g.is_armed)

    # Nor does an interrupted hold -- reaching past the camera should not arm.
    g.update(Pose.NONE, now=0.1)
    g.update(Pose.OPEN_PALM, now=0.2)
    check("interrupted hold does not arm", not g.is_armed)

    # A sustained hold does.
    g2 = Gate()
    g2.update(Pose.OPEN_PALM, now=0.0)
    event = g2.update(Pose.OPEN_PALM, now=config.WAKE_DWELL_SECONDS + 0.01)
    check("sustained hold arms", event is GateEvent.WOKE and g2.is_armed)

    # Sleep is instant -- no dwell.
    check("fist disarms immediately",
          g2.update(Pose.FIST, now=1.0) is GateEvent.SLEPT and not g2.is_armed)

    # Idle timeout.
    g3 = Gate()
    g3.update(Pose.OPEN_PALM, now=0.0)
    g3.update(Pose.OPEN_PALM, now=config.WAKE_DWELL_SECONDS + 0.01)
    late = config.WAKE_DWELL_SECONDS + config.IDLE_DISARM_SECONDS + 1.0
    check("idle disarms",
          g3.update(Pose.NONE, now=late) is GateEvent.IDLE_TIMEOUT and not g3.is_armed)

    # The kill switch must work even if the recognizer is stuck on a pose.
    g4 = Gate()
    g4.update(Pose.OPEN_PALM, now=0.0)
    g4.update(Pose.OPEN_PALM, now=config.WAKE_DWELL_SECONDS + 0.01)
    check("armed before kill", g4.is_armed)
    g4.kill()
    check("kill disarms regardless of pose",
          g4.update(Pose.OPEN_PALM, now=1.0) is GateEvent.KILLED and not g4.is_armed)

    # And the killed flag must not linger and block the next wake.
    g4.update(Pose.OPEN_PALM, now=2.0)
    g4.update(Pose.OPEN_PALM, now=2.0 + config.WAKE_DWELL_SECONDS + 0.01)
    check("can re-arm after a kill", g4.is_armed)

    check("wake progress is 0 once armed", g4.wake_progress() == 0.0)


# -------------------------------------------------------------- fast path --
def test_scroll() -> None:
    print("\nfast path")
    s = ScrollController()

    check("wrong pose emits nothing", s.update(reading_at(Pose.OPEN_PALM, 0.5)) == 0.0)
    check("first frame emits nothing", s.update(reading_at(Pose.TWO_FINGER, 0.5)) == 0.0)

    # A hand held still must produce exactly zero, not slow drift.
    still = [s.update(reading_at(Pose.TWO_FINGER, 0.5)) for _ in range(10)]
    check("still hand does not drift", all(v == 0.0 for v in still))

    # Sustained downward motion produces downward scroll.
    s2 = ScrollController()
    s2.update(reading_at(Pose.TWO_FINGER, 0.30))
    downs = [s2.update(reading_at(Pose.TWO_FINGER, 0.30 + 0.03 * i)) for i in range(1, 12)]
    check("hand down -> positive scroll", any(v > 0 for v in downs))
    check("no upward scroll while moving down", all(v >= 0 for v in downs))

    s3 = ScrollController()
    s3.update(reading_at(Pose.TWO_FINGER, 0.80))
    ups = [s3.update(reading_at(Pose.TWO_FINGER, 0.80 - 0.03 * i)) for i in range(1, 12)]
    check("hand up -> negative scroll", any(v < 0 for v in ups))

    # Per-frame clamp holds even for an absurd jump.
    s4 = ScrollController()
    s4.update(reading_at(Pose.TWO_FINGER, 0.05))
    s4.update(reading_at(Pose.TWO_FINGER, 0.5))
    jump = s4.update(reading_at(Pose.TWO_FINGER, 0.95))
    check("clamped to SCROLL_MAX_PIXELS", abs(jump) <= config.SCROLL_MAX_PIXELS)

    # Losing the hand must reset, so re-entry is not read as one huge flick.
    s5 = ScrollController()
    s5.update(reading_at(Pose.TWO_FINGER, 0.2))
    s5.update(reading_at(Pose.TWO_FINGER, 0.25))
    s5.update(Reading(pose=Pose.NONE, landmarks=None, handedness=""))
    check("hand loss resets engagement", not s5.is_engaged)
    check("re-entry emits nothing", s5.update(reading_at(Pose.TWO_FINGER, 0.9)) == 0.0)

    # Acceleration: a faster hand must travel further per frame than a slow one.
    def travel(step: float) -> float:
        c = ScrollController()
        c.update(reading_at(Pose.TWO_FINGER, 0.1))
        return sum(abs(c.update(reading_at(Pose.TWO_FINGER, 0.1 + step * i)))
                   for i in range(1, 9))

    check("faster hand scrolls further", travel(0.05) > travel(0.015))


# --------------------------------------------------------------- executor --
def test_executor() -> None:
    print("\nexecutor (dry run)")
    e = Executor(dry_run=True)

    check("thumbs up fires approve",
          e.try_discrete(Pose.THUMBS_UP, now=100.0) is not None)

    # Held pose must not repeat -- this is the one that turns a gesture into
    # thirty Return keypresses.
    held = [e.try_discrete(Pose.THUMBS_UP, now=100.0 + i * 0.03) for i in range(1, 30)]
    check("held pose does not repeat", all(v is None for v in held))

    # Flicker within the cooldown must not re-fire either.
    e.try_discrete(Pose.NONE, now=100.5)
    check("flicker inside refractory is swallowed",
          e.try_discrete(Pose.THUMBS_UP, now=100.6) is None)

    # After the cooldown, a fresh entry fires again.
    e.try_discrete(Pose.NONE, now=101.5)
    check("fires again after refractory",
          e.try_discrete(Pose.THUMBS_UP, now=102.0) is not None)

    check("unbound pose does nothing",
          e.try_discrete(Pose.OPEN_PALM, now=110.0) is None)

    # reset() must clear edge state so re-arming into a held pose still fires.
    e2 = Executor(dry_run=True)
    e2.try_discrete(Pose.THUMBS_DOWN, now=200.0)
    e2.reset()
    check("reset allows the same pose to fire again",
          e2.try_discrete(Pose.THUMBS_DOWN, now=205.0) is not None)


def main() -> int:
    print("gesture-control logic tests")
    test_classifier()
    test_gate()
    test_scroll()
    test_executor()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failed: {', '.join(FAILURES)}")
        return 1
    print("all passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
