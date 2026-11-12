"""The fast path: hand motion -> scroll magnitude. Never touches the agent.

This is the part the brief is right to insist on. Scroll is a motor task with a
tight feedback loop -- your eye sees the page move and your hand corrects, many
times a second. Routing that through a perceive-reason-act agent loop would put
hundreds of milliseconds inside a control loop that needs tens. Scroll is spinal
cord, not brain.

Everything here is frame-to-frame arithmetic on landmark positions. No model, no
training, no network.
"""

from __future__ import annotations

from typing import Optional

import config
from recognizer import Pose, Reading

SCROLL_POSE = Pose.TWO_FINGER


class ScrollController:
    """Turns anchor displacement into per-frame scroll deltas.

    Three things stand between a raw landmark and a scroll that feels good:

      smoothing  -- landmarks jitter by a pixel or two even on a still hand
      deadzone   -- a resting hand must produce exactly zero, not a slow drift
      curve      -- trackpads accelerate, so slow drags scrub and flicks travel
    """

    def __init__(self) -> None:
        self._smoothed_y: Optional[float] = None
        self._previous_y: Optional[float] = None
        self._engaged = False

    @property
    def is_engaged(self) -> bool:
        """True while actively scrolling -- the HUD shows this."""
        return self._engaged

    def reset(self) -> None:
        """Drop all motion state.

        Called whenever the gesture breaks: pose changed, hand left frame, gate
        closed. Without this, lifting your hand and putting it back somewhere
        else registers as one enormous flick.
        """
        self._smoothed_y = None
        self._previous_y = None
        self._engaged = False

    def update(self, reading: Reading) -> float:
        """Return scroll pixels for this frame. Positive scrolls content down.

        Zero means "emit nothing" -- callers should skip the event entirely
        rather than posting a zero-delta scroll.
        """
        anchor = reading.anchor()
        if reading.pose is not SCROLL_POSE or anchor is None:
            self.reset()
            return 0.0

        _, y = anchor

        if self._smoothed_y is None:
            # First frame of a new gesture: seed the filter and emit nothing.
            # Emitting on frame one would turn hand *placement* into motion.
            self._smoothed_y = y
            self._previous_y = y
            self._engaged = True
            return 0.0

        alpha = config.SCROLL_SMOOTHING
        self._smoothed_y = alpha * self._smoothed_y + (1.0 - alpha) * y

        delta = self._smoothed_y - (self._previous_y if self._previous_y is not None else self._smoothed_y)
        self._previous_y = self._smoothed_y
        self._engaged = True

        magnitude = abs(delta)
        if magnitude < config.SCROLL_DEADZONE:
            return 0.0

        # Subtract the deadzone rather than stepping over it, so motion enters
        # from zero instead of jumping to full deadzone-sized speed.
        effective = magnitude - config.SCROLL_DEADZONE
        curved = (effective ** config.SCROLL_EXPONENT) * config.SCROLL_GAIN
        curved = min(curved, float(config.SCROLL_MAX_PIXELS))

        # Intended: hand moves down -> content follows the hand, as with macOS
        # natural scrolling.
        #
        # UNVERIFIED as of writing -- no scroll event has ever actually landed
        # (the Accessibility grant was missing), so this sign comes from the
        # documented CGEvent convention, not from observation. If your first
        # live run scrolls backwards, swap the two branches below. That is the
        # whole fix.
        return curved if delta > 0 else -curved
