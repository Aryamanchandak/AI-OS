"""Step 0: prove the boring things work before writing any gesture code.

Three things must be true or nothing downstream matters:
  1. This process may post synthetic events  (System Settings > Privacy > Accessibility)
  2. This process may open the camera        (System Settings > Privacy > Camera)
  3. The MediaPipe model bundle loads

Run this FIRST. If the scroll test doesn't move a window, the problem is a
permission grant, not your code.

    .venv/bin/python preflight.py
"""

import sys
import time
from pathlib import Path

MODEL = Path(__file__).parent / "models" / "hand_landmarker.task"

OK = "\033[32m  ok  \033[0m"
BAD = "\033[31m FAIL \033[0m"
WARN = "\033[33m warn \033[0m"


def check_accessibility() -> bool:
    """Synthetic events require the Accessibility grant.

    The grant attaches to the *host binary* -- Terminal, iTerm, VS Code --
    not to this script. Whichever app launched python is the one that needs
    the checkbox ticked.
    """
    try:
        from ApplicationServices import AXIsProcessTrusted
    except ImportError:
        print(f"[{BAD}] pyobjc-framework-Quartz not importable")
        return False

    trusted = AXIsProcessTrusted()
    if trusted:
        print(f"[{OK}] Accessibility: this process may post synthetic events")
        return True

    print(f"[{BAD}] Accessibility: NOT granted -- synthetic events will silently no-op")
    print()
    print("       Fix: System Settings > Privacy & Security > Accessibility")
    print(f"       Add and tick the app that launched python ({host_app()}).")
    print("       Then restart that app -- the grant is read at process start.")
    return False


def host_app() -> str:
    """Best guess at which binary owns the Accessibility grant."""
    import os

    for var in ("TERM_PROGRAM", "__CFBundleIdentifier"):
        if os.environ.get(var):
            return os.environ[var]
    return "your terminal"


def check_scroll() -> bool:
    """Actually post a scroll event and let the user confirm it landed.

    There is no API that reports 'the event was delivered', so this is a
    human-in-the-loop check by necessity.
    """
    try:
        from Quartz import (
            CGEventCreateScrollWheelEvent,
            CGEventPost,
            kCGHIDEventTap,
            kCGScrollEventUnitPixel,
        )
    except ImportError as exc:
        print(f"[{BAD}] Quartz import failed: {exc}")
        return False

    print()
    print("       Scroll test: click into a scrollable window (browser, long file)")
    print("       and leave it focused. Starting in 5s...")
    for remaining in range(5, 0, -1):
        print(f"       {remaining}...", end="\r", flush=True)
        time.sleep(1)
    print("       scrolling now      ")

    # Twelve small pixel-unit ticks reads as one smooth trackpad gesture
    # rather than one jarring jump.
    for _ in range(12):
        event = CGEventCreateScrollWheelEvent(None, kCGScrollEventUnitPixel, 1, -18)
        CGEventPost(kCGHIDEventTap, event)
        time.sleep(0.016)

    try:
        answer = input("       Did the window scroll down? [y/N] ").strip().lower()
    except EOFError:
        # Non-interactive stdin. The events were still posted, we just cannot
        # ask -- so report honestly rather than claiming a pass.
        print(f"[{WARN}] Scroll posted, but stdin is closed so nobody confirmed it.")
        print("       Re-run preflight interactively to verify.")
        return False

    if answer.startswith("y"):
        print(f"[{OK}] Synthetic scroll events land in the focused window")
        return True

    print(f"[{BAD}] Scroll did not land -- check the Accessibility grant above")
    print("       If it scrolled the WRONG WAY, that is not a failure: flip the")
    print("       sign in fastpath.py's return, one character.")
    return False


def check_camera() -> bool:
    import cv2

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print(f"[{BAD}] Camera: could not open device 0")
        print("       Fix: System Settings > Privacy & Security > Camera")
        return False

    got_frame, frame = cap.read()
    cap.release()

    if not got_frame:
        print(f"[{BAD}] Camera: opened but returned no frame")
        return False

    height, width = frame.shape[:2]
    print(f"[{OK}] Camera: device 0 delivers {width}x{height} frames")
    return True


def check_model() -> bool:
    if not MODEL.exists():
        print(f"[{BAD}] Model bundle missing at {MODEL}")
        print("       Fix: curl -sSL -o models/hand_landmarker.task \\")
        print("            https://storage.googleapis.com/mediapipe-models/"
              "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task")
        return False

    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    options = vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(MODEL)),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=1,
    )
    with vision.HandLandmarker.create_from_options(options):
        pass

    print(f"[{OK}] MediaPipe HandLandmarker loads ({MODEL.stat().st_size // 1024} KB)")
    return True


def main() -> int:
    print()
    print("  gesture-control preflight")
    print("  " + "-" * 44)

    results = {
        "accessibility": check_accessibility(),
        "camera": check_camera(),
        "model": check_model(),
    }

    # The scroll test is pointless (and confusing) without the grant.
    if results["accessibility"]:
        results["scroll"] = check_scroll()
    else:
        print(f"[{WARN}] Skipping scroll test -- grant Accessibility first")
        results["scroll"] = False

    print("  " + "-" * 44)
    if all(results.values()):
        print("  All clear. Run:  .venv/bin/python main.py")
        return 0

    failed = ", ".join(name for name, ok in results.items() if not ok)
    print(f"  Blocked on: {failed}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
