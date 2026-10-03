"""Command-line interface for the Python expense tracker (Python 3.10+)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tracker import (
    TrackerError, add_expense, delete_expense, filter_expenses,
    format_amount, load_expenses, save_expenses, summarize,
)


class StoreOnceAction(argparse.Action):
    """Reject duplicate flags instead of silently selecting the final value."""

    def __call__(self, parser, namespace, values, option_string=None):
        seen = getattr(namespace, "_seen_options", set())
        if self.dest in seen:
            raise TrackerError(f"Option {option_string} must not be repeated.")
        seen.add(self.dest)
        setattr(namespace, "_seen_options", seen)
        setattr(namespace, self.dest, values)


class ArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs["allow_abbrev"] = False
        super().__init__(*args, **kwargs)

    def add_argument(self, *args, **kwargs):
        if args and args[0].startswith("-") and "action" not in kwargs:
            kwargs["action"] = StoreOnceAction
        return super().add_argument(*args, **kwargs)

    def error(self, message: str) -> None:
        raise TrackerError(message)


def add_filter_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--start", help="Inclusive start date, YYYY-MM-DD")
    parser.add_argument("--end", help="Inclusive end date, YYYY-MM-DD")
    parser.add_argument("--category", help="Exact, case-sensitive category")


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        description="Record and analyze expenses using exact USD cents."
    )
    parser.add_argument(
        "--data", default="data/expenses.csv",
        help="CSV path (default: data/expenses.csv); place before the command",
    )
    commands = parser.add_subparsers(dest="command", title="commands")
    add = commands.add_parser("add", help="Record one expense")
    add.add_argument("--date", required=True, help="Expense date, YYYY-MM-DD")
    add.add_argument("--amount", required=True, help="Positive USD amount, e.g. 12.34")
    add.add_argument("--category", required=True)
    add.add_argument("--description", required=True)
    listing = commands.add_parser("list", help="List expenses, optionally filtered")
    add_filter_arguments(listing)
    search = commands.add_parser("search", help="Search category and description")
    search.add_argument("--query", required=True, help="Case-insensitive text to find")
    add_filter_arguments(search)
    summary = commands.add_parser("summary", help="Show totals by category and overall")
    add_filter_arguments(summary)
    delete = commands.add_parser("delete", help="Delete an expense by ID")
    delete.add_argument("--id", required=True, help="Positive expense ID")
    commands.add_parser("help", help="Show command usage")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if args.command is None or args.command == "help":
            parser.print_help()
            return 0
        path = Path(args.data)
        expenses = load_expenses(path)
        if args.command == "add":
            expense = add_expense(
                expenses, args.date, args.amount, args.category, args.description
            )
            save_expenses(path, expenses)
            print(f"Added expense #{expense['id']}.")
        elif args.command == "delete":
            identifier = delete_expense(expenses, args.id)
            save_expenses(path, expenses)
            print(f"Deleted expense #{identifier}.")
        else:
            selected = filter_expenses(
                expenses, args.start, args.end, args.category,
                args.query if args.command == "search" else None,
            )
            if args.command == "summary":
                totals, overall = summarize(selected)
                print("Category | Total (USD)")
                for category in sorted(totals):
                    print(f"{category} | {format_amount(totals[category])}")
                print(f"Overall | {format_amount(overall)}")
            else:
                print("ID | Date | Amount (USD) | Category | Description")
                if not selected:
                    print("(no expenses)")
                for expense in selected:
                    print(
                        f"{expense['id']} | {expense['date'].isoformat()} | "
                        f"{format_amount(expense['amount_cents'])} | "
                        f"{expense['category']} | {expense['description']}"
                    )
        return 0
    except TrackerError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
