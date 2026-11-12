"""
Keynote toolbar coordinate calibration tool.

Walks you through each position that needs calibrating in config.py.
For each step: move your mouse to the target spot, then wait — a live
countdown tells you exactly how long you have left.

Usage:
    cd paint_agent
    python tests/find_coords.py
"""
import pyautogui
import time

WAIT = 10  # seconds per position — adjust if you need more

TARGETS = [
    {
        "key":         "KEYNOTE_TOOLBAR['shape_button']",
        "instruction": "Open Keynote, then hover over the SHAPE button in the toolbar\n"
                       "  (the overlapping-shapes icon, usually 4th–6th button from the left).",
    },
    {
        "key":         "KEYNOTE_SHAPE_PICKER['oval']",
        "instruction": "Click the Shape button to open the picker panel, then hover over\n"
                       "  the OVAL (circle) shape — it is the 3rd shape in the first row.",
    },
]


def countdown(label: str, seconds: int):
    for remaining in range(seconds, 0, -1):
        print(f"\r  {label} — capturing in {remaining:2d}s ...  ", end="", flush=True)
        time.sleep(1)
    print()


def main():
    print("=" * 60)
    print(" Keynote coordinate calibration")
    print(f" Each step gives you {WAIT} seconds to position your mouse.")
    print("=" * 60)

    results = {}
    for i, target in enumerate(TARGETS, 1):
        print(f"\nStep {i}/{len(TARGETS)}")
        print(f"  {target['instruction']}")
        input("  Press ENTER when you are ready to start the countdown...")
        countdown(target["key"], WAIT)
        x, y = pyautogui.position()
        results[target["key"]] = (x, y)
        print(f"  Captured: ({x}, {y})")

    print("\n" + "=" * 60)
    print(" Done! Paste these values into mcp_server/config.py:")
    print("=" * 60)
    for key, pos in results.items():
        print(f"  {key} = {pos}")
    print()


if __name__ == "__main__":
    main()
