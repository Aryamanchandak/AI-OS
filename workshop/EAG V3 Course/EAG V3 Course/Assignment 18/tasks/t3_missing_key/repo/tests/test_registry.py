import os
import unittest
from unittest import mock

from registry import sign_isin


class TestRegistry(unittest.TestCase):
    def test_reliance_signature(self):
        self.assertEqual(
            sign_isin("INE002A01018"),
            "2576ae94f664075dc231bb8d0e2f018a12ce8c1e42ab31ce08b1c703d9fef15d",
        )

    def test_missing_key_raises(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                sign_isin("INE009A01021")


if __name__ == "__main__":
    unittest.main()
