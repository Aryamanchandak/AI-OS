import sqlite3
import tempfile
import unittest
from pathlib import Path

from advisor_gateway import IterationUsage, SQLiteIterationStore, TokenUsage


class AccountingTests(unittest.TestCase):
    def test_persists_model_tagged_iterations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteIterationStore(Path(directory) / "usage.sqlite")
            store.record("r1", IterationUsage(1, "executor", "cheap", TokenUsage(3, 2)))
            store.record("r1", IterationUsage(2, "advisor", "strong", TokenUsage(9, 4, 1, 2)))

            rows = store.fetch("r1")
            self.assertEqual([(row.role, row.model) for row in rows], [("executor", "cheap"), ("advisor", "strong")])
            self.assertEqual(rows[1].usage.cache_write_tokens, 2)
            with sqlite3.connect(store.path) as connection:
                columns = [row[1] for row in connection.execute("PRAGMA table_info(advisor_iterations)")]
            self.assertIn("model", columns)
