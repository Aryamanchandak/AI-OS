"""The executor: synthetic OS events.

Nothing here knows about hands. It receives "scroll N pixels" or "approve" and
posts the corresponding event through the same public interface a trackpad or
keyboard uses. That is the whole trick behind the no-per-app-integration claim:
applications cannot tell these events from hardware, so every app already knows
what to do with them.

Safety note, from section 9 of the brief: a misfired macro is annoying, a
misfired approve is dangerous. APPROVE sends Return into whatever window happens
to be focused. Run with DRY_RUN=True until you trust your own recognizer.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Callable, Optional

from AppKit import NSEvent, NSSystemDefined
from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventCreateScrollWheelEvent,
    CGEventPost,
    kCGHIDEventTap,
    kCGScrollEventUnitPixel,
)

import config
from recognizer import Pose

# Virtual keycodes (macOS).
KEY_RETURN = 36
KEY_ESCAPE = 53

# NX_KEYTYPE constants for the media keys.
NX_KEYTYPE_SOUND_UP = 0
NX_KEYTYPE_SOUND_DOWN = 1
NX_KEYTYPE_NEXT = 17
NX_KEYTYPE_PREVIOUS = 18


class Action(Enum):
    APPROVE = "approve"
    REJECT = "reject"
    NEXT_TRACK = "next track"
    VOLUME_UP = "volume up"
    VOLUME_DOWN = "volume down"


# The discrete half of the gesture dictionary. Hard-coded on purpose: the
# context-resolution layer that would make these app-dependent is explicitly
# out of scope for the weekend build.
DISCRETE_BINDINGS: dict[Pose, Action] = {
    Pose.THUMBS_UP: Action.APPROVE,
    Pose.THUMBS_DOWN: Action.REJECT,
    Pose.POINT: Action.NEXT_TRACK,
}


def _post_key(keycode: int) -> None:
    CGEventPost(kCGHIDEventTap, CGEventCreateKeyboardEvent(None, keycode, True))
    CGEventPost(kCGHIDEventTap, CGEventCreateKeyboardEvent(None, keycode, False))


def _post_media_key(key: int) -> None:
    """Media keys are not normal keystrokes -- they ride on NSSystemDefined."""
    for is_down in (True, False):
        data1 = (key << 16) | ((0xA if is_down else 0xB) << 8)
        event = NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
            NSSystemDefined, (0, 0), 0xA00 if is_down else 0xB00, 0, 0, None, 8, data1, -1
        )
        CGEventPost(kCGHIDEventTap, event.CGEvent())


_ACTION_IMPLS: dict[Action, Callable[[], None]] = {
    Action.APPROVE: lambda: _post_key(KEY_RETURN),
    Action.REJECT: lambda: _post_key(KEY_ESCAPE),
    Action.NEXT_TRACK: lambda: _post_media_key(NX_KEYTYPE_NEXT),
    Action.VOLUME_UP: lambda: _post_media_key(NX_KEYTYPE_SOUND_UP),
    Action.VOLUME_DOWN: lambda: _post_media_key(NX_KEYTYPE_SOUND_DOWN),
}


class Executor:
    """Posts events, and enforces the refractory period on discrete actions."""

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self._last_discrete_at = 0.0
        self._last_pose: Optional[Pose] = None

    def scroll(self, pixels: float) -> None:
        """Continuous -- no refractory, no debounce. It should feel like glass."""
        if pixels == 0:
            return
        if self.dry_run:
            return
        event = CGEventCreateScrollWheelEvent(
            None, kCGScrollEventUnitPixel, 1, int(round(pixels))
        )
        CGEventPost(kCGHIDEventTap, event)

    def try_discrete(self, pose: Pose, now: Optional[float] = None) -> Optional[Action]:
        """Fire the action bound to `pose`, if one is bound and we're not cooling down.

        Two guards, and both are load-bearing:

          edge trigger -- fire on the transition into a pose, not every frame
                          it is held. Otherwise holding a thumbs-up sends
                          Return thirty times a second.
          refractory   -- a stability window still lets a pose flicker out and
                          back within a few frames. The cooldown absorbs that.

        Returns the Action if it fired, else None.
        """
        now = now if now is not None else time.monotonic()

        # Edge detection: only the first frame of a new pose is a candidate.
        is_new_pose = pose is not self._last_pose
        self._last_pose = pose

        action = DISCRETE_BINDINGS.get(pose)
        if action is None or not is_new_pose:
            return None

        if now - self._last_discrete_at < config.DISCRETE_REFRACTORY_SECONDS:
            return None

        self._last_discrete_at = now
        if not self.dry_run:
            _ACTION_IMPLS[action]()
        return action

    def reset(self) -> None:
        """Clear edge-detection state when the gate closes.

        Without this, disarming while holding thumbs-up and then re-arming into
        the same pose would not re-fire -- the pose never "changed".
        """
        self._last_pose = None
