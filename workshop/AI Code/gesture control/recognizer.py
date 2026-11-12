"""Camera frame -> 21 hand landmarks -> a pose label.

Deliberately rule-based, not learned. Finger-extension state is a 5-bit code and
the six poses in our dictionary are just six of those codes. A trained classifier
buys nothing here and costs a dataset, so it is not in the weekend build.

The one non-obvious choice: extension is measured as *distance from the wrist*,
not "is the tip above the knuckle". Distance is rotation-invariant, so poses
still read correctly with your hand resting at desk height and tilted -- which
section 9 of the brief makes a hard requirement, not a preference.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence

import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

import config


class Pose(Enum):
    """The gesture dictionary. Tag every entry continuous or discrete.

    They look similar on camera and behave completely differently downstream.
    """

    NONE = "none"
    OPEN_PALM = "open_palm"      # discrete   -- wake
    FIST = "fist"                # discrete   -- sleep
    TWO_FINGER = "two_finger"    # CONTINUOUS -- scroll
    THUMBS_UP = "thumbs_up"      # discrete   -- approve
    THUMBS_DOWN = "thumbs_down"  # discrete   -- reject
    POINT = "point"              # discrete   -- next track


CONTINUOUS_POSES = {Pose.TWO_FINGER}

# Landmark indices, per the MediaPipe hand model.
WRIST = 0
THUMB_IP, THUMB_TIP = 3, 4
INDEX_MCP, INDEX_PIP, INDEX_TIP = 5, 6, 8
MIDDLE_PIP, MIDDLE_TIP = 10, 12
RING_PIP, RING_TIP = 14, 16
PINKY_MCP, PINKY_PIP, PINKY_TIP = 17, 18, 20


@dataclass
class Reading:
    """One frame's worth of interpretation."""

    pose: Pose
    landmarks: Optional[np.ndarray]  # (21, 3) normalised, or None if no hand
    handedness: str                  # "Left" / "Right" / ""

    @property
    def has_hand(self) -> bool:
        return self.landmarks is not None

    def anchor(self) -> Optional[tuple[float, float]]:
        """The point we track for continuous motion.

        The index MCP knuckle, not the fingertip: knuckles barely move when you
        curl a finger, so the scroll signal stays clean even as the pose flexes.
        """
        if self.landmarks is None:
            return None
        return float(self.landmarks[INDEX_MCP][0]), float(self.landmarks[INDEX_MCP][1])


def _distance(a: Sequence[float], b: Sequence[float]) -> float:
    return math.dist((a[0], a[1]), (b[0], b[1]))


def _fingers_extended(lm: np.ndarray) -> tuple[bool, bool, bool, bool, bool]:
    """(thumb, index, middle, ring, pinky) extension flags.

    For the four fingers: a tip further from the wrist than its own PIP joint
    means the finger is straight. Curl it and the tip swings back toward the
    wrist. Works at any hand rotation.
    """
    wrist = lm[WRIST]

    def straight(tip_idx: int, pip_idx: int) -> bool:
        return _distance(lm[tip_idx], wrist) > _distance(lm[pip_idx], wrist)

    index = straight(INDEX_TIP, INDEX_PIP)
    middle = straight(MIDDLE_TIP, MIDDLE_PIP)
    ring = straight(RING_TIP, RING_PIP)
    pinky = straight(PINKY_TIP, PINKY_PIP)

    # The thumb needs its own rule -- it folds sideways across the palm rather
    # than curling toward the wrist, so the wrist-distance test misreads it.
    # Instead: a tucked thumb ends up nearer the pinky knuckle than its own
    # IP joint is.
    pinky_mcp = lm[PINKY_MCP]
    thumb = _distance(lm[THUMB_TIP], pinky_mcp) > _distance(lm[THUMB_IP], pinky_mcp)

    return thumb, index, middle, ring, pinky


def _classify(lm: np.ndarray) -> Pose:
    thumb, index, middle, ring, pinky = _fingers_extended(lm)
    curled_fingers = not (index or middle or ring or pinky)

    if thumb and index and middle and ring and pinky:
        return Pose.OPEN_PALM

    if curled_fingers and not thumb:
        return Pose.FIST

    if curled_fingers and thumb:
        # Thumb alone -- direction decides approve vs reject. Image coordinates
        # put y=0 at the top, so "up" is a smaller y than the wrist.
        return Pose.THUMBS_UP if lm[THUMB_TIP][1] < lm[WRIST][1] else Pose.THUMBS_DOWN

    if index and middle and not ring and not pinky:
        return Pose.TWO_FINGER

    if index and not middle and not ring and not pinky:
        return Pose.POINT

    return Pose.NONE


class Recognizer:
    """Wraps the MediaPipe task and adds temporal stability.

    A raw per-frame label flickers. Downstream code should never see that
    flicker, so we only report a pose once it has survived
    POSE_STABILITY_FRAMES consecutive frames.
    """

    def __init__(self) -> None:
        if not config.MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Missing model bundle at {config.MODEL_PATH}. "
                "See README -- it is a one-line curl."
            )

        options = vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(config.MODEL_PATH)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=config.MIN_HAND_DETECTION_CONFIDENCE,
            min_hand_presence_confidence=config.MIN_HAND_PRESENCE_CONFIDENCE,
            min_tracking_confidence=config.MIN_TRACKING_CONFIDENCE,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)

        self._candidate = Pose.NONE
        self._candidate_frames = 0
        self._stable = Pose.NONE

    def __enter__(self) -> "Recognizer":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def close(self) -> None:
        self._landmarker.close()

    def process(self, bgr_frame: np.ndarray, timestamp_ms: int) -> Reading:
        rgb = np.ascontiguousarray(bgr_frame[:, :, ::-1])
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(mp_image, timestamp_ms)

        if not result.hand_landmarks:
            self._settle(Pose.NONE)
            return Reading(pose=self._stable, landmarks=None, handedness="")

        points = np.array(
            [[p.x, p.y, p.z] for p in result.hand_landmarks[0]], dtype=np.float32
        )
        handedness = ""
        if result.handedness and result.handedness[0]:
            handedness = result.handedness[0][0].category_name

        self._settle(_classify(points))
        return Reading(pose=self._stable, landmarks=points, handedness=handedness)

    def _settle(self, raw: Pose) -> None:
        """Promote a raw label to stable only after it holds."""
        if raw == self._candidate:
            self._candidate_frames += 1
        else:
            self._candidate = raw
            self._candidate_frames = 1

        if self._candidate_frames >= config.POSE_STABILITY_FRAMES:
            self._stable = self._candidate
