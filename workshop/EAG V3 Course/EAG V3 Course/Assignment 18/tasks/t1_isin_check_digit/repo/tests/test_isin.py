import unittest

from isin import is_valid_isin


class TestIsin(unittest.TestCase):
    def test_reliance(self):
        self.assertTrue(is_valid_isin("INE002A01018"))

    def test_infosys(self):
        self.assertTrue(is_valid_isin("INE009A01021"))

    def test_apple(self):
        self.assertTrue(is_valid_isin("US0378331005"))

    def test_wrong_check_digit(self):
        self.assertFalse(is_valid_isin("INE002A01019"))

    def test_too_short(self):
        self.assertFalse(is_valid_isin("INE002A0101"))


if __name__ == "__main__":
    unittest.main()
