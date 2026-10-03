"""Focused core tests: python -m unittest discover -s python -v."""

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from tracker import (
    MAX_ID, TrackerError, add_expense, delete_expense, filter_expenses,
    load_expenses, parse_amount, parse_date, save_expenses, summarize,
)


class ValidationTests(unittest.TestCase):
    def test_exact_decimal_currency_and_boundaries(self):
        for value, expected in [
            ("0.01", 1), ("0.1", 10), ("12", 1200), ("12.34", 1234),
            ("999999999.99", 99_999_999_999), ("00012.30", 1230),
        ]:
            with self.subTest(value=value):
                self.assertEqual(parse_amount(value), expected)
        for value in ["0", "0.00", "-1", "+1", "1e3", "NaN", "1.",
                      ".01", "1.001", "1000000000", " 1", "1 "]:
            with self.subTest(value=value):
                with self.assertRaises(TrackerError):
                    parse_amount(value)

    def test_calendar_validation(self):
        self.assertEqual(parse_date("2024-02-29"), date(2024, 2, 29))
        self.assertEqual(parse_date("0001-01-01"), date(1, 1, 1))
        for value in ["2025-02-29", "2026-04-31", "0000-01-01", "2026-1-01"]:
            with self.subTest(value=value):
                with self.assertRaises(TrackerError):
                    parse_date(value)

    def test_dictionary_records_filters_and_integer_totals(self):
        expenses = []
        add_expense(expenses, "2026-10-02", "0.10", " Food ", " Lunch ")
        add_expense(expenses, "2026-10-02", "0.20", "Food", "Coffee")
        add_expense(expenses, "2026-10-03", "5.00", "Travel", "Bus ticket")
        self.assertIsInstance(expenses[0], dict)
        self.assertEqual(summarize(filter_expenses(expenses, category="Food")),
                         ({"Food": 30}, 30))
        self.assertEqual(len(filter_expenses(expenses, end="2026-10-02")), 2)
        self.assertEqual(len(filter_expenses(expenses, query="COFFEE")), 1)
        self.assertEqual(filter_expenses(expenses, category="food"), [])
        with self.assertRaises(TrackerError):
            filter_expenses(expenses, start="2026-10-03", end="2026-10-02")

    def test_invalid_text_and_exhausted_ids_do_not_mutate(self):
        expenses = []
        for category in ["", " ", "F\tood", "Food\n", "Caf\u00e9", "F" * 41]:
            with self.subTest(category=category):
                with self.assertRaises(TrackerError):
                    add_expense(expenses, "2026-10-02", "1", category, "Lunch")
                self.assertEqual(expenses, [])
        add_expense(expenses, "2026-10-02", "1", "Food", "Lunch")
        expenses[0]["id"] = MAX_ID
        with self.assertRaises(TrackerError):
            add_expense(expenses, "2026-10-02", "1", "Food", "Lunch")
        with self.assertRaises(TrackerError):
            delete_expense(expenses, "2")
        self.assertEqual(len(expenses), 1)


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "nested" / "expenses.csv"

    def test_missing_file_and_quoted_round_trip(self):
        self.assertEqual(load_expenses(self.path), [])
        expenses = []
        add_expense(expenses, "2026-10-02", "12.34", "Food, meals", 'Lunch "special"')
        save_expenses(self.path, expenses)
        self.assertEqual(load_expenses(self.path), expenses)
        self.assertIn('"Food, meals"', self.path.read_text(encoding="utf-8"))
        delete_expense(expenses, "1")
        save_expenses(self.path, expenses)
        self.assertEqual(load_expenses(self.path), [])

    def test_corrupt_storage_is_rejected_without_changes(self):
        self.path.parent.mkdir()
        header = "id,date,amount_cents,category,description\n"
        for content in [
            "", "wrong,header\n", header + "1,2026-02-30,100,Food,Lunch\n",
            header + "1,2026-10-02,100,Food,Lunch\n1,2026-10-02,100,Food,Coffee\n",
            header + "1,2026-10-02,100, Food,Lunch\n",
            header + '1,2026-10-02,100,Foo"d,Lunch\n',
            header + '1,2026-10-02,100,Food,"two\nlines"\n',
        ]:
            with self.subTest(content=content):
                self.path.write_text(content, encoding="utf-8")
                before = self.path.read_bytes()
                with self.assertRaises(TrackerError):
                    load_expenses(self.path)
                self.assertEqual(self.path.read_bytes(), before)

    def test_failed_replacement_keeps_original_and_cleans_temporary(self):
        expenses = []
        add_expense(expenses, "2026-10-02", "1", "Food", "Lunch")
        save_expenses(self.path, expenses)
        original = self.path.read_bytes()
        add_expense(expenses, "2026-10-02", "2", "Food", "Coffee")
        with patch("tracker.os.replace", side_effect=OSError("simulated failure")):
            with self.assertRaises(TrackerError):
                save_expenses(self.path, expenses)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])


if __name__ == "__main__":
    unittest.main()
