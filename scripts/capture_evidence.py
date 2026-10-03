"""Record real CLI runs and test output without changing any user expense file.

Run from any directory with Python 3.10+: python scripts/capture_evidence.py
Compile the C++ application first, or provide its location with --cpp PATH.
Generated HTML is a view of captured output, suitable for browser screenshots.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import platform
import re
import shlex
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence"


def shell_command(argv: list[str]) -> str:
    return subprocess.list2cmdline(argv) if os.name == "nt" else shlex.join(argv)


def execute(argv: list[str], expected: int = 0, *, merge_streams: bool = False,
            environment: dict[str, str] | None = None) -> dict:
    started = time.perf_counter()
    result = subprocess.run(
        argv, cwd=ROOT, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT if merge_streams else subprocess.PIPE,
        text=True, encoding="utf-8", timeout=180, check=False, env=environment,
    )
    return {
        "argv": argv,
        "cwd": str(ROOT),
        "returncode": result.returncode,
        "expected_returncode": expected,
        "stdout": result.stdout,
        "stderr": result.stderr or "",
        "elapsed_seconds": round(time.perf_counter() - started, 6),
    }


def transcript_record(record: dict, display_argv: list[str] | None = None) -> str:
    text = "> " + shell_command(display_argv or record["argv"]) + "\n"
    if record["stdout"]:
        text += record["stdout"]
        if not text.endswith("\n"):
            text += "\n"
    if record["stderr"]:
        text += record["stderr"]
        if not text.endswith("\n"):
            text += "\n"
    return text + f"[exit {record['returncode']}]\n"


def write_terminal_html(filename: str, title: str, subtitle: str, captured_text: str,
                        footer: str) -> None:
    document = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
* {{ box-sizing: border-box; }}
body {{ margin: 0; padding: 28px; color: #e2e8f0; background: #e8edf3;
        font-family: Arial, sans-serif; }}
main {{ width: 100%; max-width: 1100px; margin: 0 auto; background: #101827;
        border-radius: 14px; overflow: hidden; box-shadow: 0 8px 28px #23364a30; }}
header {{ padding: 22px 26px; background: #182438; border-bottom: 1px solid #314258; }}
h1 {{ margin: 0 0 8px; font-size: 23px; font-weight: 700; color: #ffffff; }}
p {{ margin: 0; color: #b9c9dd; font-size: 13px; line-height: 1.5; }}
pre {{ margin: 0; padding: 22px 26px; white-space: pre-wrap; overflow-wrap: anywhere;
       font-family: Consolas, "Liberation Mono", monospace; font-size: 14px;
       line-height: 1.48; color: #def3e7; }}
footer {{ border-top: 1px solid #314258; padding: 15px 26px; color: #a9bbd1;
          font-size: 12px; line-height: 1.5; }}
</style></head><body><main><header><h1>{title}</h1><p>{subtitle}</p></header>
<pre>{captured}</pre><footer>{footer}</footer></main></body></html>
""".format(
        title=html.escape(title), subtitle=html.escape(subtitle),
        captured=html.escape(captured_text), footer=html.escape(footer),
    )
    (EVIDENCE / filename).write_text(document, encoding="utf-8")


def display_demo_argv(record: dict, language: str) -> list[str]:
    """Clearly labeled display aliases shorten only paths, never CLI arguments."""
    argv = record["argv"]
    prefix_length = 2 if language == "Python" else 1
    display = ["python", "python/main.py"] if language == "Python" else ["build/expense_tracker"]
    remainder = list(argv[prefix_length:])
    if remainder and remainder[0] == "--data":
        remainder[1] = "<temporary-demo.csv>"
    return display + remainder


def demo(language: str, command: list[str], sample: list[dict], directory: Path) -> dict:
    database = directory / (language.lower() + "-demo.csv")
    records = []
    for row in sample:
        cents = int(row["amount_cents"])
        amount = f"{cents // 100}.{cents % 100:02d}"
        record = execute(command + [
            "--data", str(database), "add", "--date", row["date"], "--amount", amount,
            "--category", row["category"], "--description", row["description"],
        ])
        records.append(record)
    operations = [
        ("list", ["list"], 0),
        ("filtered_list", ["list", "--start", "2026-10-03", "--end", "2026-10-04",
                           "--category", "Food"], 0),
        ("filtered_summary", ["summary", "--start", "2026-10-03", "--end", "2026-10-04",
                              "--category", "Food"], 0),
        ("search", ["search", "--query", "CAMPUS"], 0),
        ("summary", ["summary"], 0),
        ("invalid_date", ["add", "--date", "2026-02-30", "--amount", "1.00",
                          "--category", "Food", "--description", "Invalid date test"], 2),
    ]
    by_name = {}
    before_invalid = b""
    for name, args, expected in operations:
        if name == "invalid_date" and database.exists():
            before_invalid = database.read_bytes()
        record = execute(command + ["--data", str(database)] + args, expected)
        record["operation"] = name
        records.append(record)
        by_name[name] = record

    actual_ids = [
        int(match.group(1)) for match in re.finditer(r"^(\d+) \|", by_name["search"]["stdout"], re.MULTILINE)
    ]
    actual_total = re.search(r"^Overall \| \$(\d+\.\d{2})$", by_name["summary"]["stdout"], re.MULTILINE)
    filtered_total = re.search(
        r"^Overall \| \$(\d+\.\d{2})$", by_name["filtered_summary"]["stdout"], re.MULTILINE,
    )
    checks = {
        "all_expected_exit_codes": all(r["returncode"] == r["expected_returncode"] for r in records),
        "seed_ids_match_sample": all(
            record["stdout"] == f"Added expense #{row['id']}.\n"
            for record, row in zip(records[:len(sample)], sample)
        ),
        "overall_total_is_61_08": bool(actual_total and actual_total.group(1) == "61.08"),
        "filtered_total_is_8_75": bool(filtered_total and filtered_total.group(1) == "8.75"),
        "campus_search_ids_are_1_and_5": actual_ids == [1, 5],
        "invalid_date_is_reported_as_error": by_name["invalid_date"]["stderr"].startswith("Error:"),
        "invalid_add_preserves_storage": database.exists() and database.read_bytes() == before_invalid,
    }
    full_text = (
        f"{language} expense tracker\n"
        "Recorded CLI demonstration — actual captured program output\n"
        f"Working directory: {ROOT}\n"
        "Data file: isolated temporary file, populated through actual add commands.\n\n"
        + "\n".join(transcript_record(record) for record in records)
    )
    stem = ("python" if language == "Python" else "cpp") + "_demo"
    (EVIDENCE / (stem + ".txt")).write_text(full_text, encoding="utf-8")

    # Keep the first actual add and all five actual success outputs visible.
    # The four remaining add command arrays and complete output remain in .txt/.json.
    screenshot_text = transcript_record(records[0], display_demo_argv(records[0], language))
    screenshot_text += "\nFour more seed add commands (full commands in companion .txt):\n"
    for record in records[1:len(sample)]:
        screenshot_text += record["stdout"] + f"[exit {record['returncode']}]\n"
    screenshot_text += "\n" + "\n".join(
        transcript_record(record, display_demo_argv(record, language))
        for record in records[len(sample):]
    )
    write_terminal_html(
        stem + ".html", f"{language} expense tracker — CLI demonstration",
        "Recorded CLI demonstration — actual captured program output",
        screenshot_text,
        "Executable paths use display aliases; <temporary-demo.csv> replaces the isolated temporary path. "
        "Every argument array and complete captured output is retained in the companion text and JSON files.",
    )
    return {
        "language": language, "commands": records, "checks": checks,
        "passed": all(checks.values()), "search_ids": actual_ids,
        "overall_total_usd": actual_total.group(1) if actual_total else None,
        "filtered_total_usd": filtered_total.group(1) if filtered_total else None,
    }


def test_summary(record: dict) -> dict:
    output = record["stdout"]
    match = re.search(r"^Ran (\d+) tests? in ([\d.]+)s$", output, re.MULTILINE)
    count = int(match.group(1)) if match else 0
    skipped_match = re.search(r"skipped=(\d+)", output)
    failure_match = re.search(r"failures=(\d+)", output)
    error_match = re.search(r"errors=(\d+)", output)
    skipped = int(skipped_match.group(1)) if skipped_match else 0
    failed = int(failure_match.group(1)) if failure_match else 0
    errors = int(error_match.group(1)) if error_match else 0
    return {
        "tests_run": count, "skipped": skipped, "failures": failed, "errors": errors,
        "tests_passed": count - skipped - failed - errors,
        "reported_seconds": float(match.group(2)) if match else None,
        "successful": record["returncode"] == 0 and count > 0 and skipped == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpp", type=Path, help="Path to the compiled C++ executable")
    args = parser.parse_args()
    executable = args.cpp or ROOT / "build" / (
        "expense_tracker.exe" if os.name == "nt" else "expense_tracker"
    )
    if not executable.is_absolute():
        executable = ROOT / executable
    if not executable.is_file():
        parser.error(f"Compile C++ first; executable not found: {executable}")
    with (ROOT / "data" / "sample.csv").open(encoding="utf-8", newline="") as stream:
        sample = list(csv.DictReader(stream))
    if len(sample) != 5:
        parser.error("The demonstration requires the five rows in data/sample.csv.")

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    captured_at = datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix="expense-tracker-evidence-") as temp:
        directory = Path(temp)
        demos = [
            demo("Python", [sys.executable, str(ROOT / "python" / "main.py")], sample, directory),
            demo("C++", [str(executable.resolve())], sample, directory),
        ]
    test_environment = dict(os.environ)
    test_environment["CPP_EXECUTABLE"] = str(executable.resolve())
    test_records = [
        execute([sys.executable, "-m", "unittest", "discover", "-s", "python", "-p", "test_*.py", "-v"],
                merge_streams=True, environment=test_environment),
        execute([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                merge_streams=True, environment=test_environment),
    ]
    summaries = [test_summary(record) for record in test_records]
    total_passed = sum(item["tests_passed"] for item in summaries)
    all_tests_passed = all(item["successful"] for item in summaries)
    test_text = (
        "Actual captured unittest output\n"
        f"Capture started (UTC): {captured_at}\n\n"
        + "\n".join(transcript_record(record) for record in test_records)
    )
    (EVIDENCE / "test_results.txt").write_text(test_text, encoding="utf-8")
    selected = ""
    for label, record, summary in zip(
        ("Python core validation and persistence", "Both languages and cross-language parity"),
        test_records, summaries,
    ):
        selected += label + "\n> " + shell_command(["python"] + record["argv"][1:]) + "\n"
        selected += "\n".join(record["stdout"].splitlines()[-13:]) + "\n"
        selected += f"[exit {record['returncode']}]\n\n"
    title = f"{total_passed} tests passed" if all_tests_passed else "Test run requires review"
    write_terminal_html(
        "parity_tests.html", title,
        "Recorded automated test execution — actual captured unittest output",
        selected,
        "Selected actual tails from both test runs. Full command arrays and full captured output "
        "are stored in test_results.txt and evidence_results.json. Counts are parsed from unittest output.",
    )

    output_parity = all(
        left["stdout"] == right["stdout"] and left["returncode"] == right["returncode"]
        for left, right in zip(demos[0]["commands"], demos[1]["commands"])
    )
    result = {
        "captured_at_utc": captured_at,
        "versions": {"python": sys.version, "platform": platform.platform()},
        "cpp_executable": str(executable.resolve()),
        "cpp_executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "source_sha256": {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in ("python/main.py", "python/tracker.py", "cpp/main.cpp", "cpp/tracker.cpp", "cpp/tracker.hpp")
        },
        "demos": demos, "demo_stdout_parity": output_parity,
        "test_runs": [{"capture": record, "summary": summary}
                      for record, summary in zip(test_records, summaries)],
        "totals": {"tests_run": sum(item["tests_run"] for item in summaries),
                   "tests_passed": total_passed, "all_tests_passed": all_tests_passed},
    }
    result["success"] = all(item["passed"] for item in demos) and output_parity and all_tests_passed
    (EVIDENCE / "evidence_results.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    print(f"Evidence saved in {EVIDENCE}")
    print(f"Demonstration stdout parity: {output_parity}")
    print(f"Tests passed: {total_passed}; complete success: {result['success']}")
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
