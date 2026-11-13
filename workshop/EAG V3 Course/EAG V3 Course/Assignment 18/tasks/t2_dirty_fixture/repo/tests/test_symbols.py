import os
import unittest

from symbols import load_symbols

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "nse_symbols.csv")


class TestSymbols(unittest.TestCase):
    def test_loads_all_three_rows(self):
        self.assertEqual(
            load_symbols(FIXTURE),
            {
                "RELIANCE": "INE002A01018",
                "INFY": "INE009A01021",
                "TCS": "INE467B01029",
            },
        )

    def test_symbols_are_upper_case(self):
        self.assertIn("INFY", load_symbols(FIXTURE))


if __name__ == "__main__":
    unittest.main()
