"""Held-out checks. The agent never sees this file."""
import os
import tempfile
import unittest

from symbols import load_symbols


def load_text(text):
    fd, path = tempfile.mkstemp(suffix=".csv")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        return load_symbols(path)
    finally:
        os.remove(path)


class TestHiddenSymbols(unittest.TestCase):
    def test_blank_lines_before_the_header(self):
        self.assertEqual(
            load_text("\n   \nsymbol,isin\nHDFCBANK,INE040A01034\n"),
            {"HDFCBANK": "INE040A01034"},
        )

    def test_whitespace_only_lines_and_tabs(self):
        self.assertEqual(
            load_text("symbol,isin\n\t\n\ticicibank\t,\tINE090A01021\t\n   \n"),
            {"ICICIBANK": "INE090A01021"},
        )

    def test_header_only_file_is_empty(self):
        self.assertEqual(load_text("symbol,isin\n"), {})

    def test_row_with_one_field_raises(self):
        with self.assertRaises(ValueError):
            load_text("symbol,isin\nRELIANCE\n")

    def test_row_with_three_fields_raises(self):
        with self.assertRaises(ValueError):
            load_text("symbol,isin\nRELIANCE,INE002A01018,EQ\n")
