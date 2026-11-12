"""Wires the three boxes together and runs the loop.

    camera -> recognizer -> GATE -> { fast path | discrete } -> executor

Run:
    .venv/bin/python main.py           # dry run: shows everything, posts nothing
    .venv/bin/python main.py --live    # actually drives the machine

Keys (HUD window focused):
    q / esc   quit
    space     force-disarm
    d         toggle dry run
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Optional

import cv2
import numpy as np

import config
from actions import DISCRETE_BINDINGS, Executor
from fastpath import SCROLL_POSE, ScrollController
from gate import Gate, GateEvent, SLEEP_POSE, WAKE_POSE
from recognizer import Pose, Reading, Recognizer

# Skeleton for the HUD overlay: (start, end) landmark index pairs.
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),            # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),            # index
    (5, 9), (9, 10), (10, 11), (11, 12),       # middle
    (9, 13), (13, 14), (14, 15), (15, 16),     # ring
    (13, 17), (17, 18), (18, 19), (19, 20),    # pinky
    (0, 17),                                   # palm base
]

COLOR_ARMED = (80, 220, 120)
COLOR_ASLEEP = (110, 110, 110)
COLOR_WAKING = (60, 190, 255)
COLOR_TEXT = (240, 240, 240)
COLOR_DIM = (150, 150, 150)
COLOR_ALERT = (80, 120, 255)


class FrameClock:
    """Monotonic millisecond timestamps.

    detect_for_video rejects a timestamp that does not strictly increase, and
    wall-clock time can repeat across two fast frames. Counting from a fixed
    origin sidesteps that entirely.
    """

    def __init__(self) -> None:
        self._origin = time.monotonic()
        self._last_ms = -1

    def next_ms(self) -> int:
        ms = int((time.monotonic() - self._origin) * 1000)
        if ms <= self._last_ms:
            ms = self._last_ms + 1
        self._last_ms = ms
        return ms


class Banner:
    """Transient message shown on the HUD (last action, gate transitions)."""

    def __init__(self, hold_seconds: float = 1.6) -> None:
        self._text = ""
        self._until = 0.0
        self._hold = hold_seconds

    def show(self, text: str) -> None:
        self._text = text
        self._until = time.monotonic() + self._hold

    def current(self) -> str:
        return self._text if time.monotonic() < self._until else ""


def draw_hand(frame: np.ndarray, landmarks: np.ndarray, color) -> None:
    height, width = frame.shape[:2]
    points = [(int(x * width), int(y * height)) for x, y, _ in landmarks]

    for start, end in HAND_CONNECTIONS:
        cv2.line(frame, points[start], points[end], color, 2, cv2.LINE_AA)
    for point in points:
        cv2.circle(frame, point, 3, color, -1, cv2.LINE_AA)


def draw_hud(
    frame: np.ndarray,
    gate: Gate,
    reading: Reading,
    scroll: ScrollController,
    executor: Executor,
    banner: Banner,
    fps: float,
) -> None:
    height, width = frame.shape[:2]
    armed = gate.is_armed
    progress = gate.wake_progress()

    if armed:
        accent = COLOR_ARMED
    elif progress > 0:
        accent = COLOR_WAKING
    else:
        accent = COLOR_ASLEEP

    # A border you cannot miss. This is the privacy indicator -- if it is not
    # obvious at a glance whether the system is listening, the gate has failed
    # at its job even if the state machine is perfect.
    thickness = 8 if armed else 3
    cv2.rectangle(frame, (0, 0), (width - 1, height - 1), accent, thickness)

    # Status strip.
    cv2.rectangle(frame, (0, 0), (width, 46), (24, 24, 28), -1)
    label = "ARMED" if armed else "asleep"
    cv2.putText(frame, label, (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.85, accent, 2, cv2.LINE_AA)

    if executor.dry_run:
        cv2.putText(frame, "DRY RUN", (width - 130, 30), cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, COLOR_ALERT, 2, cv2.LINE_AA)

    # Wake dwell meter -- shows the gate filling up rather than snapping open.
    if progress > 0:
        bar_width = int((width - 32) * progress)
        cv2.rectangle(frame, (16, 52), (16 + bar_width, 60), COLOR_WAKING, -1)
        cv2.putText(frame, "waking...", (16, 80), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, COLOR_WAKING, 1, cv2.LINE_AA)

    pose_text = reading.pose.value if reading.has_hand else "no hand"
    cv2.putText(frame, f"pose: {pose_text}", (16, height - 52),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_TEXT, 1, cv2.LINE_AA)

    if armed and scroll.is_engaged:
        cv2.putText(frame, "SCROLLING", (16, height - 76), cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, COLOR_ARMED, 2, cv2.LINE_AA)

    hint = (
        f"hold {WAKE_POSE.value} to wake"
        if not armed
        else f"{SLEEP_POSE.value} to sleep  |  {SCROLL_POSE.value} to scroll"
    )
    cv2.putText(frame, hint, (16, height - 28), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, COLOR_DIM, 1, cv2.LINE_AA)

    message = banner.current()
    if message:
        cv2.putText(frame, message, (16, height - 100), cv2.FONT_HERSHEY_SIMPLEX,
                    0.75, COLOR_ARMED, 2, cv2.LINE_AA)

    cv2.putText(frame, f"{fps:4.1f} fps", (width - 110, height - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_DIM, 1, cv2.LINE_AA)


def open_camera() -> Optional[cv2.VideoCapture]:
    cap = cv2.VideoCapture(config.CAMERA_INDEX)
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
    return cap


def run(dry_run: bool, show_preview: bool) -> int:
    cap = open_camera()
    if cap is None:
        print("Could not open the camera. Run preflight.py -- this is almost")
        print("always the Camera privacy grant, not the code.", file=sys.stderr)
        return 1

    gate = Gate()
    scroll = ScrollController()
    executor = Executor(dry_run=dry_run)
    clock = FrameClock()
    banner = Banner()

    fps = 0.0
    last_frame_at = time.monotonic()

    print(f"running{' (DRY RUN -- no events posted)' if dry_run else ' LIVE'}")
    print(f"hold {WAKE_POSE.value} to arm, {SLEEP_POSE.value} to disarm, q to quit")

    try:
        with Recognizer() as recognizer:
            while True:
                got_frame, frame = cap.read()
                if not got_frame:
                    print("camera returned no frame; stopping", file=sys.stderr)
                    return 1

                if config.MIRROR_PREVIEW:
                    frame = cv2.flip(frame, 1)

                reading = recognizer.process(frame, clock.next_ms())
                event = gate.update(reading.pose)

                if event is GateEvent.WOKE:
                    banner.show("armed")
                elif event in (GateEvent.SLEPT, GateEvent.KILLED):
                    banner.show("disarmed")
                elif event is GateEvent.IDLE_TIMEOUT:
                    banner.show("disarmed (idle)")

                # ---- THE GATE ----------------------------------------------
                # Everything that can affect the machine lives inside this
                # branch. Not an `if` inside each handler -- one boundary, so
                # a new action cannot forget to check it.
                if gate.is_armed:
                    pixels = scroll.update(reading)
                    if pixels:
                        executor.scroll(pixels)

                    fired = executor.try_discrete(reading.pose)
                    if fired is not None:
                        banner.show(fired.value)
                        print(f"  -> {fired.value}"
                              f"{' (dry run)' if executor.dry_run else ''}")
                else:
                    scroll.reset()
                    executor.reset()
                # ------------------------------------------------------------

                now = time.monotonic()
                elapsed = now - last_frame_at
                last_frame_at = now
                if elapsed > 0:
                    fps = 0.9 * fps + 0.1 * (1.0 / elapsed) if fps else 1.0 / elapsed

                if show_preview:
                    if reading.has_hand:
                        draw_hand(frame, reading.landmarks,
                                  COLOR_ARMED if gate.is_armed else COLOR_ASLEEP)
                    draw_hud(frame, gate, reading, scroll, executor, banner, fps)
                    cv2.imshow(config.HUD_WINDOW_NAME, frame)

                    key = cv2.waitKey(1) & 0xFF
                    if key in (ord("q"), 27):
                        return 0
                    if key == ord(" "):
                        gate.kill()
                    if key == ord("d"):
                        executor.dry_run = not executor.dry_run
                        banner.show("dry run" if executor.dry_run else "LIVE")
    except KeyboardInterrupt:
        return 0
    finally:
        cap.release()
        cv2.destroyAllWindows()


def main() -> int:
    parser = argparse.ArgumentParser(description="gesture control POC")
    parser.add_argument("--live", action="store_true",
                        help="actually post OS events (default is a dry run)")
    parser.add_argument("--no-preview", action="store_true",
                        help="hide the HUD window (you lose the armed indicator)")
    args = parser.parse_args()

    dry_run = config.DRY_RUN and not args.live
    show_preview = config.SHOW_PREVIEW and not args.no_preview

    if not show_preview and not dry_run:
        print("Refusing to run live with no HUD: there would be no visible")
        print("indication that the system is armed. Drop --no-preview.",
              file=sys.stderr)
        return 2

    return run(dry_run=dry_run, show_preview=show_preview)


if __name__ == "__main__":
    sys.exit(main())
