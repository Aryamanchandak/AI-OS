"""Held-out checks. The agent never sees this file."""
import unittest

from isin import is_valid_isin

VALID = [
    "INE040A01034",  # HDFC Bank
    "INE467B01029",  # TCS
    "INE090A01021",  # ICICI Bank
    "US5949181045",  # Microsoft
    "GB0002634946",  # BAE Systems
    "DE0007164600",  # SAP
]


class TestHiddenIsin(unittest.TestCase):
    def test_other_valid_isins(self):
        for code in VALID:
            self.assertTrue(is_valid_isin(code), code)

    def test_any_single_digit_change_is_caught(self):
        for code in VALID:
            for i, ch in enumerate(code):
                if not ch.isdigit():
                    continue
                for other in "0123456789":
                    if other != ch:
                        changed = code[:i] + other + code[i + 1:]
                        self.assertFalse(is_valid_isin(changed), changed)

    def test_lowercase_is_invalid(self):
        self.assertFalse(is_valid_isin("ine002a01018"))

    def test_other_characters_are_invalid(self):
        self.assertFalse(is_valid_isin("IN-002A01018"))

    def test_check_character_must_be_a_digit(self):
        self.assertFalse(is_valid_isin("INE002A0101A"))

    def test_wrong_length_or_type_is_invalid(self):
        self.assertFalse(is_valid_isin("INE002A010180"))
        self.assertFalse(is_valid_isin(None))
        self.assertFalse(is_valid_isin(123456789012))
