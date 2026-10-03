"""Behavioral and cross-language tests that exercise the actual command-line apps.

Run from the repository root with: python -m unittest discover -s tests -v
Set CPP_EXECUTABLE to test a C++ executable at a nondefault location.
"""

import csv
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HEADER = ["id", "date", "amount_cents", "category", "description"]
LIST_HEADER = "ID | Date | Amount (USD) | Category | Description\n"
SUMMARY_HEADER = "Category | Total (USD)\n"
PYTHON_COMMAND = [sys.executable, str(ROOT / "python" / "main.py")]


def cpp_command():
    """Missing optional builds skip; an incorrect explicit override is an error."""
    configured = os.environ.get("CPP_EXECUTABLE")
    path = Path(configured).expanduser() if configured else ROOT / "build" / (
        "expense_tracker.exe" if os.name == "nt" else "expense_tracker"
    )
    if not path.is_absolute():
        path = ROOT / path
    if path.is_file():
        return [str(path.resolve())]
    if configured:
        raise RuntimeError(f"CPP_EXECUTABLE does not exist: {path}")
    return None


class FixtureMixin:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="expense-tracker-test-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.data = self.directory / "expenses.csv"

    def invoke(self, *args, command=None, expected=0, default_data=False):
        argv = list(command or self.command)
        if not default_data:
            argv.extend(["--data", str(self.data)])
        argv.extend(args)
        result = subprocess.run(
            argv, cwd=self.directory, capture_output=True, text=True,
            encoding="utf-8", timeout=20, check=False,
        )
        self.assertEqual(
            result.returncode, expected,
            f"Command: {argv!r}\nstdout: {result.stdout}\nstderr: {result.stderr}",
        )
        if expected == 0:
            self.assertEqual(result.stderr, "", result.stderr)
        else:
            self.assertTrue(result.stderr.startswith("Error:"), result.stderr)
        return result

    def add(self, date="2026-10-02", amount="12.34", category="Food",
            description="Lunch", command=None, expected=0):
        return self.invoke(
            "add", "--date", date, "--amount", amount, "--category", category,
            "--description", description, command=command, expected=expected,
        )

    def write_rows(self, rows):
        with self.data.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(HEADER)
            writer.writerows(rows)

    def read_rows(self):
        with self.data.open(encoding="utf-8", newline="") as stream:
            return list(csv.DictReader(stream))

    def seed(self):
        self.add("2026-10-01", "0.10", "Food", "Coffee")
        self.add("2026-10-02", "0.20", "Food", "Lunch")
        self.add("2026-10-03", "15.00", "Transport", "Bus ticket")


class BehaviorMixin(FixtureMixin):
    """The same contract is independently applied to each real implementation."""

    def test_empty_list_and_summary(self):
        self.assertEqual(self.invoke("list").stdout, LIST_HEADER + "(no expenses)\n")
        self.assertEqual(
            self.invoke("summary").stdout, SUMMARY_HEADER + "Overall | $0.00\n",
        )

    def test_add_persists_and_new_process_reads(self):
        self.assertEqual(self.add().stdout, "Added expense #1.\n")
        self.assertEqual(
            self.invoke("list").stdout,
            LIST_HEADER + "1 | 2026-10-02 | $12.34 | Food | Lunch\n",
        )
        self.assertEqual(self.read_rows(), [{
            "id": "1", "date": "2026-10-02", "amount_cents": "1234",
            "category": "Food", "description": "Lunch",
        }])

    def test_default_data_location(self):
        self.invoke(
            "add", "--date", "2026-10-02", "--amount", "1",
            "--category", "Food", "--description", "Snack", default_data=True,
        )
        self.assertTrue((self.directory / "data" / "expenses.csv").is_file())
        self.assertIn("Snack", self.invoke("list", default_data=True).stdout)

    def test_decimal_amounts_are_exact(self):
        self.add(amount="0.10")
        self.add(amount="0.20")
        self.assertEqual(
            self.invoke("summary").stdout,
            SUMMARY_HEADER + "Food | $0.30\nOverall | $0.30\n",
        )
        self.assertEqual([r["amount_cents"] for r in self.read_rows()], ["10", "20"])

    def test_integer_and_one_decimal_amounts(self):
        self.add(amount="2")
        self.add(amount="3.4")
        self.assertIn("$5.40", self.invoke("summary").stdout)

    def test_maximum_amount_and_wide_summary(self):
        self.add(amount="999999999.99")
        self.add(amount="999999999.99")
        self.assertIn("Overall | $1999999999.98", self.invoke("summary").stdout)

    def test_quoted_csv_and_trimmed_text_round_trip(self):
        self.add(category='  Food, groceries  ', description='  Lunch at "Joe\'s", cafe  ')
        self.assertEqual(self.read_rows()[0]["category"], "Food, groceries")
        self.assertEqual(self.read_rows()[0]["description"], 'Lunch at "Joe\'s", cafe')
        self.assertIn('Food, groceries | Lunch at "Joe\'s", cafe', self.invoke("list").stdout)

    def test_insertion_order_not_date_order(self):
        self.add("2026-10-03", description="Later date first")
        self.add("2026-10-01", description="Earlier date second")
        lines = self.invoke("list").stdout.splitlines()
        self.assertTrue(lines[1].startswith("1 | 2026-10-03"))
        self.assertTrue(lines[2].startswith("2 | 2026-10-01"))

    def test_inclusive_date_range_and_combined_filter(self):
        self.seed()
        output = self.invoke("list", "--start", "2026-10-01", "--end", "2026-10-02").stdout
        self.assertIn("Coffee", output)
        self.assertIn("Lunch", output)
        self.assertNotIn("Bus ticket", output)
        output = self.invoke(
            "list", "--start", "2026-10-02", "--end", "2026-10-03", "--category", "Food",
        ).stdout
        self.assertIn("Lunch", output)
        self.assertNotIn("Coffee", output)
        self.assertNotIn("Bus ticket", output)

    def test_one_sided_filters_and_exact_category(self):
        self.seed()
        self.assertNotIn("Coffee", self.invoke("list", "--start", "2026-10-02").stdout)
        self.assertNotIn("Bus ticket", self.invoke("list", "--end", "2026-10-02").stdout)
        self.assertEqual(
            self.invoke("list", "--category", "food").stdout, LIST_HEADER + "(no expenses)\n",
        )

    def test_category_summary_is_sorted_and_filtered(self):
        self.add(category="Transport", amount="1")
        self.add(category="Food", amount="2")
        self.add(category="Food", amount="3")
        self.assertEqual(
            self.invoke("summary").stdout,
            SUMMARY_HEADER + "Food | $5.00\nTransport | $1.00\nOverall | $6.00\n",
        )
        self.assertEqual(
            self.invoke("summary", "--category", "Food").stdout,
            SUMMARY_HEADER + "Food | $5.00\nOverall | $5.00\n",
        )

    def test_summary_applies_date_filter(self):
        self.seed()
        self.assertEqual(
            self.invoke("summary", "--start", "2026-10-02", "--end", "2026-10-02").stdout,
            SUMMARY_HEADER + "Food | $0.20\nOverall | $0.20\n",
        )

    def test_search_matches_description_and_category_case_insensitively(self):
        self.seed()
        self.assertIn("Lunch", self.invoke("search", "--query", "LUNCH").stdout)
        self.assertNotIn("Coffee", self.invoke("search", "--query", "LUNCH").stdout)
        output = self.invoke("search", "--query", "fOoD", "--start", "2026-10-02").stdout
        self.assertIn("Lunch", output)
        self.assertNotIn("Coffee", output)
        self.assertNotIn("Bus ticket", output)
        self.assertEqual(
            self.invoke("search", "--query", "no matching text").stdout,
            LIST_HEADER + "(no expenses)\n",
        )

    def test_delete_persists_and_missing_id_does_not_rewrite(self):
        self.seed()
        self.assertEqual(self.invoke("delete", "--id", "2").stdout, "Deleted expense #2.\n")
        output = self.invoke("list").stdout
        self.assertIn("Coffee", output)
        self.assertNotIn("Lunch", output)
        self.assertIn("Bus ticket", output)
        before = self.data.read_bytes()
        self.invoke("delete", "--id", "999", expected=2)
        self.assertEqual(self.data.read_bytes(), before)

    def test_invalid_search_queries_do_not_rewrite(self):
        self.add()
        before = self.data.read_bytes()
        for query in ("", " ", "Q" * 201, "line\nbreak", "caf\u00e9"):
            with self.subTest(query=query):
                self.invoke("search", "--query", query, expected=2)
                self.assertEqual(self.data.read_bytes(), before)

    def test_valid_calendar_boundaries(self):
        for date in ("0001-01-01", "2000-02-29", "2024-02-29", "9999-12-31"):
            with self.subTest(date=date):
                self.add(date=date)
                self.assertIn(date, self.invoke("list", "--start", date, "--end", date).stdout)

    def test_invalid_calendar_dates_do_not_rewrite(self):
        self.add()
        before = self.data.read_bytes()
        for date in (
            "2026-02-29", "1900-02-29", "2026-04-31", "0000-01-01", "10000-01-01",
            "2026-13-01", "2026-00-01", "2026-01-00", "2026-1-01", "2026/10/02",
        ):
            with self.subTest(date=date):
                self.add(date=date, expected=2)
                self.assertEqual(self.data.read_bytes(), before)

    def test_invalid_amounts_do_not_rewrite(self):
        self.add()
        before = self.data.read_bytes()
        for amount in (
            "0", "0.00", "-1", "+1", "1e2", "NaN", "inf", ".50", "1.", "1.001",
            "1,000", "1000000000", "999999999.999", "999999999999999999999999", "",
        ):
            with self.subTest(amount=amount):
                self.add(amount=amount, expected=2)
                self.assertEqual(self.data.read_bytes(), before)

    def test_text_limits_and_ascii_validation(self):
        self.add(category="C" * 40, description="D" * 200)
        before = self.data.read_bytes()
        for field, value in (
            ("category", " "), ("category", "C" * 41), ("description", ""),
            ("description", "D" * 201), ("description", "line\nbreak"),
            ("category", "tab\tinside"), ("description", "caf\u00e9"),
            ("category", "\tFood\t"), ("description", "\nLunch\n"),
        ):
            with self.subTest(field=field, value=value):
                self.add(**{field: value}, expected=2)
                self.assertEqual(self.data.read_bytes(), before)

    def test_invalid_filters_and_arguments(self):
        self.add()
        before = self.data.read_bytes()
        invalid_commands = [
            ["list", "--start", "2026-10-03", "--end", "2026-10-01"],
            ["summary", "--start", "2026-02-29"],
            ["search", "--query", "Food", "--start", "2026-10-03", "--end", "2026-10-01"],
            ["list", "--unknown", "value"], ["list", "unexpected"], ["add"], ["search"],
            ["list", "--cat", "Food"],
            ["list", "--category", "Food", "--category", "Transport"],
            ["search", "--query", "Food", "--query", "Coffee"],
            ["add", "--date", "2026-10-02", "--amount", "1", "--amount", "2",
             "--category", "Food", "--description", "Lunch"],
            ["delete", "--id", "0"], ["delete", "--id", "-1"],
            ["delete", "--id", "2147483648"], ["delete", "--id", "1.0"],
            ["nonsense"],
        ]
        for args in invalid_commands:
            with self.subTest(args=args):
                self.invoke(*args, expected=2)
                self.assertEqual(self.data.read_bytes(), before)

    def test_malformed_csv_is_rejected_without_rewriting(self):
        malformed_files = [
            "wrong,header\n1,2026-10-02,100,Food,Lunch\n",
            "id,date,amount_cents,category,description\n1,2026-10-02,100,Food\n",
            'id,date,amount_cents,category,description\n1,2026-10-02,100,Food,"unterminated\n',
            "id,date,amount_cents,category,description\n1,2026-10-02,100,Food,Lunch,extra\n",
            'id,date,amount_cents,category,description\n1,2026-10-02,100,Food,Lun"ch\n',
            'id,date,amount_cents,category,description\n1,2026-10-02,100,Food,"Lunch"junk\n',
        ]
        for contents in malformed_files:
            with self.subTest(contents=contents):
                self.data.write_text(contents, encoding="utf-8")
                before = self.data.read_bytes()
                self.invoke("list", expected=2)
                self.add(expected=2)
                self.assertEqual(self.data.read_bytes(), before)

    def test_invalid_stored_values_are_rejected(self):
        invalid_rows = [
            [0, "2026-10-02", 100, "Food", "Lunch"],
            [2147483648, "2026-10-02", 100, "Food", "Lunch"],
            [1, "2026-02-29", 100, "Food", "Lunch"],
            [1, "2026-10-02", "one", "Food", "Lunch"],
            [1, "2026-10-02", 0, "Food", "Lunch"],
            [1, "2026-10-02", -100, "Food", "Lunch"],
            [1, "2026-10-02", 100000000000, "Food", "Lunch"],
            [1, "2026-10-02", 100, "", "Lunch"],
            [1, "2026-10-02", 100, "Food", ""],
            [1, "2026-10-02", 100, " Food ", "Lunch"],
            [1, "2026-10-02", 100, "Food", " Lunch "],
            [1, "2026-10-02", 100, "Food", "caf\u00e9"],
        ]
        for row in invalid_rows:
            with self.subTest(row=row):
                self.write_rows([row])
                before = self.data.read_bytes()
                self.invoke("list", expected=2)
                self.add(expected=2)
                self.assertEqual(self.data.read_bytes(), before)

    def test_duplicate_ids_are_rejected_without_rewriting(self):
        self.write_rows([
            [1, "2026-10-02", 100, "Food", "Lunch"],
            [1, "2026-10-03", 200, "Transport", "Bus"],
        ])
        before = self.data.read_bytes()
        self.invoke("summary", expected=2)
        self.add(expected=2)
        self.assertEqual(self.data.read_bytes(), before)

    def test_identifier_limit_remains_readable_but_cannot_add(self):
        self.write_rows([[2147483647, "2026-10-02", 100, "Food", "Lunch"]])
        self.assertIn("2147483647 |", self.invoke("list").stdout)
        before = self.data.read_bytes()
        self.add(expected=2)
        self.assertEqual(self.data.read_bytes(), before)

    def test_record_limit_is_enforced(self):
        self.write_rows(
            [i, "2026-10-02", 1, "Food", "Limit test"] for i in range(1, 100001)
        )
        self.assertIn("Overall | $1000.00", self.invoke("summary").stdout)
        before = self.data.read_bytes()
        self.add(expected=2)
        self.assertEqual(self.data.read_bytes(), before)
        with self.data.open("a", encoding="utf-8", newline="") as stream:
            csv.writer(stream).writerow([100001, "2026-10-02", 1, "Food", "Too many"])
        before = self.data.read_bytes()
        self.invoke("summary", expected=2)
        self.assertEqual(self.data.read_bytes(), before)


class TestPython(BehaviorMixin, unittest.TestCase):
    command = PYTHON_COMMAND


class TestCpp(BehaviorMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.command = cpp_command()
        if cls.command is None:
            raise unittest.SkipTest(
                "C++ behavioral tests skipped: compile build/expense_tracker first "
                "or set CPP_EXECUTABLE. Python tests still run."
            )


class TestCrossLanguage(FixtureMixin, unittest.TestCase):
    command = PYTHON_COMMAND

    @classmethod
    def setUpClass(cls):
        cls.cpp = cpp_command()
        if cls.cpp is None:
            raise unittest.SkipTest(
                "Cross-language parity tests skipped: C++ executable is absent. "
                "A Python-only run does not establish implementation parity."
            )

    def assert_parity(self, *args):
        python = self.invoke(*args)
        cpp = self.invoke(*args, command=self.cpp)
        self.assertEqual(python.stdout, cpp.stdout, f"Output mismatch for {args!r}")
        return python.stdout

    def test_python_cpp_python_csv_interoperability(self):
        self.add(amount="0.10", category="Food, cafe", description='Lunch at "Joe\'s"')
        self.assert_parity("list")
        self.assertEqual(
            self.add(amount="0.20", category="Food, cafe", description="Coffee", command=self.cpp).stdout,
            "Added expense #2.\n",
        )
        self.assert_parity("list")
        self.assertEqual(
            self.assert_parity("summary"),
            SUMMARY_HEADER + "Food, cafe | $0.30\nOverall | $0.30\n",
        )
        self.invoke("delete", "--id", "1", command=self.cpp)
        self.assert_parity("list")
        self.assertEqual([row["id"] for row in self.read_rows()], ["2"])

    def test_cpp_python_cpp_csv_interoperability(self):
        self.add(date="2000-02-29", amount="1.2", command=self.cpp)
        self.add(date="0001-01-01", amount="3.45", category="Books")
        self.assert_parity("list")
        self.assert_parity("summary")
        self.invoke("delete", "--id", "2")
        self.assert_parity("list")

    def test_filter_search_and_summary_output_parity(self):
        self.seed()
        for args in (
            ("list",), ("list", "--category", "Food"),
            ("list", "--start", "2026-10-02", "--end", "2026-10-03"),
            ("search", "--query", "COFFEE"),
            ("search", "--query", "FOOD", "--end", "2026-10-02"),
            ("summary",), ("summary", "--category", "Transport"),
            ("summary", "--start", "2026-10-02", "--end", "2026-10-02"),
            ("list", "--category", "Missing"),
        ):
            with self.subTest(args=args):
                self.assert_parity(*args)

    def test_empty_output_parity(self):
        self.assert_parity("list")
        self.assert_parity("summary")
        self.assert_parity("search", "--query", "Missing")

    def test_both_refuse_corrupted_shared_storage(self):
        self.data.write_text(
            "id,date,amount_cents,category,description\n1,2026-10-02,NaN,Food,Lunch\n",
            encoding="utf-8",
        )
        before = self.data.read_bytes()
        for command in (PYTHON_COMMAND, self.cpp):
            self.add(command=command, expected=2)
            self.assertEqual(self.data.read_bytes(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
