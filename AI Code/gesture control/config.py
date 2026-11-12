"""Every tunable in one place.

These numbers are the entire feel of the system. Expect to change them while
sitting at the desk with the HUD open -- that is the intended workflow, not a
sign anything is wrong.
"""

from pathlib import Path

MODEL_PATH = Path(__file__).parent / "models" / "hand_landmarker.task"

# ---------------------------------------------------------------- camera ----
CAMERA_INDEX = 0
FRAME_WIDTH = 960
FRAME_HEIGHT = 540
# Mirror the preview so moving your hand right moves it right on screen.
MIRROR_PREVIEW = True

# ------------------------------------------------------------ recognizer ----
MIN_HAND_DETECTION_CONFIDENCE = 0.6
MIN_HAND_PRESENCE_CONFIDENCE = 0.6
MIN_TRACKING_CONFIDENCE = 0.6

# A pose must hold for this many consecutive frames before it counts as real.
# This is the answer to "how do I tell an intentional flick from incidental
# motion": intent has dwell, noise does not.
POSE_STABILITY_FRAMES = 4

# ------------------------------------------------------------------ gate ----
# Wake and sleep are deliberately ASYMMETRIC, because their costs are.
#
# A false wake arms a system that can approve a deploy -- expensive. So waking
# demands a deliberate, sustained, unusual pose.
#
# A false sleep just disarms you -- cheap, and you notice immediately. So
# sleeping should be as fast as possible, because when you want out, you want
# out NOW.
WAKE_DWELL_SECONDS = 0.6   # open palm must be held this long
SLEEP_DWELL_SECONDS = 0.0  # fist disarms on the first stable frame

# Auto-disarm after this long with no recognized gesture. A gate you can forget
# to close is not a privacy story.
IDLE_DISARM_SECONDS = 20.0

# ------------------------------------------------------------- fast path ----
# Hand displacement -> scroll distance.
#
# Trackpads accelerate: slow drags scrub precisely, fast flicks travel far. We
# reproduce that with a deadzone (kills jitter) and a mild power curve.
SCROLL_DEADZONE = 0.004    # normalised frame units; below this, no scroll
SCROLL_GAIN = 2600.0       # pixels of scroll per unit of normalised motion
SCROLL_EXPONENT = 1.35     # >1 accelerates; 1.0 is linear
SCROLL_MAX_PIXELS = 120    # per-frame clamp, stops one bad frame launching you
# Exponential smoothing on the hand position. Cuts landmark jitter without
# adding perceptible lag.
SCROLL_SMOOTHING = 0.45    # 0 = no smoothing, 1 = frozen

# ------------------------------------------------------------- executor ----
# Recognise and display everything, but post no real events. Start here.
# APPROVE sends Return into the focused window; you want to watch the HUD fire
# correctly a few dozen times before you let it do that for real.
# Override at runtime with:  --live
DRY_RUN = True

# -------------------------------------------------------------- discrete ----
# After a discrete action fires, ignore further discrete actions for this long.
# Without it, a 30fps camera fires "approve" thirty times a second.
DISCRETE_REFRACTORY_SECONDS = 1.0

# ------------------------------------------------------------------- HUD ----
SHOW_PREVIEW = True        # the armed indicator IS the privacy story -- keep it
HUD_WINDOW_NAME = "gesture control"
