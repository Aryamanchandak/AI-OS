"""Gaze direction labels, checked against the threshold-normalised movement."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analysis  # noqa: E402

TH = {"h": 0.07, "v": 0.09, "yaw": 0.06, "pitch": 0.05}


def d(**kw):
    return {"h": 0, "v": 0, "yaw": 0, "pitch": 0, **kw}


class DirectionTests(unittest.TestCase):
    def test_pure_iris_movements(self):
        self.assertEqual(analysis._direction(d(v=-0.3), TH), "up")
        self.assertEqual(analysis._direction(d(v=0.3), TH), "down")
        self.assertEqual(analysis._direction(d(h=-0.3), TH), "to your right")
        self.assertEqual(analysis._direction(d(h=0.3), TH), "to your left")

    def test_pure_head_movements(self):
        self.assertEqual(analysis._direction(d(pitch=-0.3), TH), "up")
        self.assertEqual(analysis._direction(d(pitch=0.3), TH), "down")
        self.assertEqual(analysis._direction(d(yaw=-0.3), TH), "to your right")
        self.assertEqual(analysis._direction(d(yaw=0.3), TH), "to your left")

    def test_strongest_normalised_signal_wins(self):
        # h = 1.0x threshold, v = 3.3x threshold -> vertical wins, upward
        self.assertEqual(analysis._direction(d(h=0.07, v=-0.3), TH), "up")
        # h = 4.3x threshold beats v = 1.1x
        self.assertEqual(analysis._direction(d(h=0.3, v=-0.1), TH), "to your left")
        # pitch (up, 2x) beats iris v (down, 1.1x)
        self.assertEqual(analysis._direction(d(v=0.1, pitch=-0.1), TH), "up")
        # iris v (down, 3.3x) beats pitch (up, 1x)
        self.assertEqual(analysis._direction(d(v=0.3, pitch=-0.05), TH), "down")
        # yaw (2x) beats h (1x) and sets the side
        self.assertEqual(analysis._direction(d(h=0.07, yaw=-0.12), TH), "to your right")


if __name__ == "__main__":
    unittest.main()
