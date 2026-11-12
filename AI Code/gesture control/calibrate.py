"""Live pose readout. Posts nothing, needs no Accessibility grant -- camera only.

Why this exists
---------------
test_logic.py builds synthetic hands using the same rule the classifier uses to
read them, so those tests prove the classifier agrees with itself. They say
nothing about whether it reads a *real* hand correctly.

This is the tool that closes that gap, and it needs your actual hand.

Hold each of the six poses AT DESK HEIGHT -- forearm resting, hand low and
tilted, small amplitude. That is the posture section 9 of the brief makes a hard
requirement, and it is the one most likely to break the thumb heuristic.

The check that matters most:

    does THUMBS_DOWN ever read as thumbs_up, fist, or none?

Those two are bound to reject and approve. A confusion there is the section 9
safety asymmetry, live.

    .venv/bin/python calibrate.py
    .venv/bin/python calibrate.py --preview     # with a video window
"""

from __future__ import annotations

import argparse
import sys
import time

import cv2

import config
from recognizer import Pose, Recognizer, _fingers_extended

FINGER_NAMES = ("thumb", "index", "middle", "ring", "pinky")

CHECKLIST = [
    (Pose.OPEN_PALM, "all five fingers spread"),
    (Pose.FIST, "closed fist, thumb tucked"),
    (Pose.TWO_FINGER, "index + middle only"),
    (Pose.POINT, "index only"),
    (Pose.THUMBS_UP, "thumb up, fingers curled"),
    (Pose.THUMBS_DOWN, "thumb down, fingers curled"),
]


def flag_string(landmarks) -> str:
    flags = _fingers_extended(landmarks)
    return " ".join(
        f"{name}:{'1' if flag else '0'}" for name, flag in zip(FINGER_NAMES, flags)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="live pose readout")
    parser.add_argument("--preview", action="store_true", help="show a video window")
    args = parser.parse_args()

    cap = cv2.VideoCapture(config.CAMERA_INDEX)
    if not cap.isOpened():
        print("Could not open camera -- see preflight.py", file=sys.stderr)
        return 1
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)

    print()
    print("  Hold each pose at DESK HEIGHT. Watch the label settle.")
    print("  Ctrl-C when done. Nothing is being posted to the OS.")
    print()
    for pose, description in CHECKLIST:
        print(f"    {pose.value:<12} {description}")
    print()
    print("  " + "-" * 58)

    seen: dict[str, int] = {}
    last_label = None
    origin = time.monotonic()
    last_ms = -1

    try:
        with Recognizer() as recognizer:
            while True:
                got_frame, frame = cap.read()
                if not got_frame:
                    break
                if config.MIRROR_PREVIEW:
                    frame = cv2.flip(frame, 1)

                ms = int((time.monotonic() - origin) * 1000)
                if ms <= last_ms:
                    ms = last_ms + 1
                last_ms = ms

                reading = recognizer.process(frame, ms)
                label = reading.pose.value if reading.has_hand else "no hand"
                seen[label] = seen.get(label, 0) + 1

                # Print only on change -- a scrolling wall of identical lines
                # tells you nothing about stability.
                if label != last_label:
                    detail = flag_string(reading.landmarks) if reading.has_hand else ""
                    print(f"  {label:<12} {detail}")
                    last_label = label

                if args.preview:
                    cv2.putText(frame, label, (16, 40), cv2.FONT_HERSHEY_SIMPLEX,
                                1.0, (80, 220, 120), 2, cv2.LINE_AA)
                    cv2.imshow("calibrate", frame)
                    if (cv2.waitKey(1) & 0xFF) in (ord("q"), 27):
                        break
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()

    print("  " + "-" * 58)
    print("  frames per label:")
    for label, count in sorted(seen.items(), key=lambda kv: -kv[1]):
        print(f"    {label:<12} {count}")

    missing = [p.value for p, _ in CHECKLIST if p.value not in seen]
    if missing:
        print()
        print(f"  never recognised: {', '.join(missing)}")
        print("  Those poses need a rule fix before you trust them live.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
