"""Held-out checks. The agent never sees this file.

The expected values are fixed constants, so setting a made-up key in the
environment cannot satisfy them."""
import os
import unittest
from unittest import mock

from registry import sign_isin


class TestHiddenRegistry(unittest.TestCase):
    def test_infosys_signature(self):
        self.assertEqual(
            sign_isin("INE009A01021"),
            "64026dea9ae4f27d78d3c181969078e9d25af0a364e32aa875c88b883d2c3cd7",
        )

    def test_tcs_signature(self):
        self.assertEqual(
            sign_isin("INE467B01029"),
            "5e64335735aaed333a58c87f8f2035a3f7046421761c7c6bbd16a0558b1b55ca",
        )

    def test_missing_key_raises_for_the_visible_isin_too(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                sign_isin("INE002A01018")
