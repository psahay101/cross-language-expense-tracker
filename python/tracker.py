"""Expense records, validation, filtering, and atomic CSV persistence.

Python dictionaries hold each expense. Type hints document the expected values,
while runtime checks protect the boundary between user input and stored data.
All currency values are integer cents; floating-point arithmetic is never used.
"""

from __future__ import annotations

import csv
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Iterable, Iterator, TypedDict

HEADER = ["id", "date", "amount_cents", "category", "description"]
MAX_ID = 2_147_483_647
MAX_AMOUNT_CENTS = 99_999_999_999
MAX_ROWS = 100_000
MAX_CSV_LINE_LENGTH = 1_024
MAX_TOTAL_CENTS = 9_223_372_036_854_775_807


class TrackerError(Exception):
    """A recoverable input or storage problem that the CLI can explain."""


class Expense(TypedDict):
    id: int
    date: date
    amount_cents: int
    category: str
    description: str


def parse_date(value: str) -> date:
    """Require the unambiguous YYYY-MM-DD spelling and a real calendar date."""
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise TrackerError("Date must use YYYY-MM-DD.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise TrackerError("Date must be a valid calendar date.") from exc


def parse_amount(value: str) -> int:
    """Parse decimal currency exactly, without rounding or binary floats."""
    if re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", value) is None:
        raise TrackerError("Amount must be positive with at most two decimal places.")
    dollars, separator, fraction = value.partition(".")
    # Bound conversion size before int(); very long strings of leading zeros
    # remain valid, but cannot trigger Python's integer string conversion limit.
    significant = dollars.lstrip("0") or "0"
    if len(significant) > 9:
        raise TrackerError("Amount must be between $0.01 and $999999999.99.")
    cents = int(significant) * 100
    if separator:
        cents += int(fraction.ljust(2, "0"))
    if not 1 <= cents <= MAX_AMOUNT_CENTS:
        raise TrackerError("Amount must be between $0.01 and $999999999.99.")
    return cents


def parse_positive_integer(value: str, label: str, maximum: int) -> int:
    if re.fullmatch(r"[0-9]+", value) is None:
        raise TrackerError(f"{label} must be a positive integer.")
    significant = value.lstrip("0") or "0"
    if len(significant) > len(str(maximum)):
        raise TrackerError(f"{label} is outside the supported range.")
    result = int(significant)
    if not 1 <= result <= maximum:
        raise TrackerError(f"{label} is outside the supported range.")
    return result


def clean_text(value: str, label: str, maximum: int) -> str:
    """Keep the shared file format portable by accepting printable ASCII."""
    if any(ord(character) < 32 or ord(character) > 126 for character in value):
        raise TrackerError(f"{label} must contain printable ASCII characters only.")
    cleaned = value.strip(" ")
    if not cleaned:
        raise TrackerError(f"{label} must not be empty.")
    if len(cleaned) > maximum:
        raise TrackerError(f"{label} must be at most {maximum} characters.")
    return cleaned


def checked_total(expenses: Iterable[Expense]) -> int:
    total = 0
    for expense in expenses:
        amount = expense["amount_cents"]
        if total > MAX_TOTAL_CENTS - amount:
            raise TrackerError("Expense total exceeds the supported range.")
        total += amount
    return total


def checked_csv_lines(lines: Iterable[str]) -> Iterator[str]:
    """Reject nonstandard quoting and physical multiline records.

    The csv module does the actual decoding. This small lexical check closes
    its permissive acceptance of a quote inside an unquoted field and enforces
    the application's one-physical-line-per-record storage contract.
    """
    for line_number, line in enumerate(lines, start=1):
        if line.endswith("\r\n"):
            content = line[:-2]
        elif line.endswith(("\n", "\r")):
            content = line[:-1]
        else:
            content = line
        if len(content) > MAX_CSV_LINE_LENGTH:
            raise TrackerError(f"CSV line {line_number} exceeds the supported length.")
        state = "start"
        for character in content:
            if state == "quoted":
                if character == '"':
                    state = "after_quote"
            elif state == "after_quote":
                if character == '"':
                    state = "quoted"  # Escaped double quote within a field.
                elif character == ",":
                    state = "start"
                else:
                    raise TrackerError(f"CSV line {line_number} has invalid quoting.")
            elif character == ",":
                state = "start"
            elif character == '"':
                if state != "start":
                    raise TrackerError(f"CSV line {line_number} has invalid quoting.")
                state = "quoted"
            else:
                state = "unquoted"
        if state == "quoted":
            raise TrackerError(f"CSV line {line_number} has an unterminated quoted field.")
        yield line


def load_expenses(path: Path) -> list[Expense]:
    """Validate the whole existing file before any mutation can be saved."""
    records: list[Expense] = []
    seen_ids: set[int] = set()
    try:
        with path.open("r", encoding="utf-8", newline="") as source:
            reader = csv.reader(checked_csv_lines(source), strict=True)
            if next(reader, None) != HEADER:
                raise TrackerError("CSV header must be id,date,amount_cents,category,description.")
            for row_number, row in enumerate(reader, start=2):
                if len(records) >= MAX_ROWS:
                    raise TrackerError(f"CSV cannot contain more than {MAX_ROWS} expenses.")
                if len(row) != len(HEADER):
                    raise TrackerError(f"CSV row {row_number} must contain five fields.")
                try:
                    identifier = parse_positive_integer(row[0], "ID", MAX_ID)
                    if identifier in seen_ids:
                        raise TrackerError("Expense IDs must be unique.")
                    expense: Expense = {
                        "id": identifier,
                        "date": parse_date(row[1]),
                        "amount_cents": parse_positive_integer(
                            row[2], "Amount in cents", MAX_AMOUNT_CENTS
                        ),
                        "category": clean_text(row[3], "Category", 40),
                        "description": clean_text(row[4], "Description", 200),
                    }
                    if expense["category"] != row[3] or expense["description"] != row[4]:
                        raise TrackerError("Stored text must not have surrounding spaces.")
                except TrackerError as exc:
                    raise TrackerError(f"CSV row {row_number}: {exc}") from exc
                seen_ids.add(identifier)
                records.append(expense)
    except FileNotFoundError:
        # Only a nonexistent target is an empty database. Broken parent paths,
        # unreadable files, and existing empty files are reported as errors.
        if path.exists():
            raise TrackerError("Unable to open the expense file.")
        return []
    except (OSError, UnicodeError, csv.Error) as exc:
        raise TrackerError(f"Unable to read the expense file: {exc}") from exc
    checked_total(records)
    return records


def save_expenses(path: Path, expenses: list[Expense]) -> None:
    """Replace the target only after writing a complete file beside it.

    This provides atomic replacement for one writer. It is not a locking or
    multi-writer database, so do not run simultaneous writers on the same file.
    """
    temporary_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as target:
            temporary_path = Path(target.name)
            writer = csv.writer(target, lineterminator="\n")
            writer.writerow(HEADER)
            for expense in expenses:
                writer.writerow([
                    expense["id"], expense["date"].isoformat(),
                    expense["amount_cents"], expense["category"],
                    expense["description"],
                ])
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary_path, path)
    except OSError as exc:
        raise TrackerError(f"Unable to save the expense file: {exc}") from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass  # Preserve the original storage error if cleanup fails.


def add_expense(
    expenses: list[Expense], expense_date: str, amount: str,
    category: str, description: str,
) -> Expense:
    """Validate and append one record; the caller controls persistence."""
    if len(expenses) >= MAX_ROWS:
        raise TrackerError(f"Cannot store more than {MAX_ROWS} expenses.")
    identifier = max((expense["id"] for expense in expenses), default=0) + 1
    if identifier > MAX_ID:
        raise TrackerError("No more expense IDs are available.")
    record: Expense = {
        "id": identifier,
        "date": parse_date(expense_date),
        "amount_cents": parse_amount(amount),
        "category": clean_text(category, "Category", 40),
        "description": clean_text(description, "Description", 200),
    }
    if checked_total(expenses) > MAX_TOTAL_CENTS - record["amount_cents"]:
        raise TrackerError("Expense total exceeds the supported range.")
    expenses.append(record)
    return record


def delete_expense(expenses: list[Expense], identifier: str) -> int:
    expense_id = parse_positive_integer(identifier, "ID", MAX_ID)
    for index, expense in enumerate(expenses):
        if expense["id"] == expense_id:
            del expenses[index]
            return expense_id
    raise TrackerError(f"Expense #{expense_id} does not exist.")


def filter_expenses(
    expenses: list[Expense], start: str | None = None,
    end: str | None = None, category: str | None = None,
    query: str | None = None,
) -> list[Expense]:
    start_date = parse_date(start) if start is not None else None
    end_date = parse_date(end) if end is not None else None
    if start_date is not None and end_date is not None and start_date > end_date:
        raise TrackerError("Start date must not be after end date.")
    selected_category = clean_text(category, "Category", 40) if category is not None else None
    selected_query = clean_text(query, "Query", 200).lower() if query is not None else None
    return [
        expense for expense in expenses
        if (start_date is None or expense["date"] >= start_date)
        and (end_date is None or expense["date"] <= end_date)
        and (selected_category is None or expense["category"] == selected_category)
        and (selected_query is None or selected_query in expense["category"].lower()
             or selected_query in expense["description"].lower())
    ]


def summarize(expenses: list[Expense]) -> tuple[dict[str, int], int]:
    totals: dict[str, int] = {}
    overall = checked_total(expenses)
    for expense in expenses:
        category = expense["category"]
        totals[category] = totals.get(category, 0) + expense["amount_cents"]
    return totals, overall


def format_amount(cents: int) -> str:
    return f"${cents // 100}.{cents % 100:02d}"
