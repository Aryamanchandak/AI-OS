"""The wake/sleep gate. Built first, because everything else is downstream of it.

An honest note on the privacy claim
-----------------------------------
The brief says cameras "are not interpreting anything until explicitly armed".
That cannot be literally true: something must watch for the wake gesture. Hand
landmarks are therefore extracted on every frame, always.

What *is* true, and is the property worth defending:

  while disarmed, no gesture is ever resolved into an action, no action is ever
  executed, no screen is ever captured, and nothing ever leaves this machine.

Landmark extraction is local, stateless and never recorded. The gate is the
structural boundary between "a camera saw a hand" and "the computer did
something". Keep it structural -- an `if armed:` buried inside an action handler
is not the same guarantee, because the next handler someone adds will forget it.
"""

from __future__ import annotations

import time
from enum import Enum, auto
from typing import Optional

import config
from recognizer import Pose


class State(Enum):
    ASLEEP = auto()
    ARMED = auto()


class GateEvent(Enum):
    NOTHING = auto()
    WOKE = auto()
    SLEPT = auto()
    IDLE_TIMEOUT = auto()
    KILLED = auto()


WAKE_POSE = Pose.OPEN_PALM
SLEEP_POSE = Pose.FIST


class Gate:
    """A two-state machine with dwell on entry and none on exit.

    Waking requires holding the wake pose for WAKE_DWELL_SECONDS. Sleeping does
    not, because the asymmetry is the point: reaching for coffee must never arm
    the system, but wanting out must always be instant.
    """

    def __init__(self) -> None:
        self._state = State.ASLEEP
        self._wake_pose_since: Optional[float] = None
        self._last_activity: float = time.monotonic()
        self._killed = False

    # ------------------------------------------------------------- queries --
    @property
    def is_armed(self) -> bool:
        return self._state is State.ARMED

    @property
    def state(self) -> State:
        return self._state

    def wake_progress(self) -> float:
        """0.0 -> 1.0 while the wake pose is being held. Drives the HUD ring.

        Showing this matters: a gate that arms with no visible build-up feels
        like it fired by accident even when it didn't.
        """
        if self._state is State.ARMED or self._wake_pose_since is None:
            return 0.0
        if config.WAKE_DWELL_SECONDS <= 0:
            return 1.0
        held = time.monotonic() - self._wake_pose_since
        return min(1.0, held / config.WAKE_DWELL_SECONDS)

    # -------------------------------------------------------------- inputs --
    def kill(self) -> None:
        """Force-disarm from outside the vision loop.

        Bound to a real key, never to a gesture. A misclassifying recognizer
        must not be able to trap you in the armed state -- if the only way out
        were a pose, a recognizer having a bad day would be a safety problem.
        """
        self._killed = True

    def update(self, pose: Pose, now: Optional[float] = None) -> GateEvent:
        now = now if now is not None else time.monotonic()

        if self._killed:
            self._killed = False
            if self._state is State.ARMED:
                self._to_asleep()
                return GateEvent.KILLED
            return GateEvent.NOTHING

        if self._state is State.ASLEEP:
            return self._update_asleep(pose, now)
        return self._update_armed(pose, now)

    # --------------------------------------------------------------- inner --
    def _update_asleep(self, pose: Pose, now: float) -> GateEvent:
        if pose is not WAKE_POSE:
            self._wake_pose_since = None
            return GateEvent.NOTHING

        if self._wake_pose_since is None:
            self._wake_pose_since = now

        if now - self._wake_pose_since >= config.WAKE_DWELL_SECONDS:
            self._state = State.ARMED
            self._wake_pose_since = None
            self._last_activity = now
            return GateEvent.WOKE

        return GateEvent.NOTHING

    def _update_armed(self, pose: Pose, now: float) -> GateEvent:
        if pose is SLEEP_POSE:
            self._to_asleep()
            return GateEvent.SLEPT

        if pose is not Pose.NONE:
            self._last_activity = now

        if now - self._last_activity >= config.IDLE_DISARM_SECONDS:
            self._to_asleep()
            return GateEvent.IDLE_TIMEOUT

        return GateEvent.NOTHING

    def _to_asleep(self) -> None:
        self._state = State.ASLEEP
        self._wake_pose_since = None
