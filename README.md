# Cross-Language Expense Tracker

University of the Cumberlands • MSCS632-M30 Advanced Programming Languages • Fall 2026 residency

**Team:** Prateek Sahay and Venkata Sai Makani  
**Languages:** Python 3.10+ and C++17  
**Repository:** https://github.com/psahay101/cross-language-expense-tracker

Two independent command-line applications implement the same expense tracker. They share a validated CSV format, identical functional output, and a behavioral test suite. The project emphasizes language comparison through actual source code rather than different feature sets.

## Features

- Record an expense with date, amount, category, description, and a generated ID.
- List all expenses or filter by an inclusive date range and exact category.
- Search category and description with an ASCII case-insensitive substring.
- Summarize total expenses by category and overall, including filtered summaries.
- Delete an expense by ID as an additional convenience feature.
- Save and reload data between executions, including files written by the other implementation.
- Reject invalid input or corrupted storage without overwriting the original file.

Currency is **USD only**, stored as integer cents. The applications never use binary floating-point numbers for money. Both are single-user, single-writer applications; concurrent processes writing the same file are not supported.

## Project structure

```text
python/main.py             Python command-line interface
python/tracker.py          Dictionary records, validation, queries, atomic CSV storage
python/test_tracker.py     Focused Python core and storage tests
cpp/main.cpp               C++ command-line interface
cpp/tracker.hpp            Expense, Filters, Summary, and Tracker declarations
cpp/tracker.cpp            Typed records, validation, queries, RAII CSV storage
cpp/CMakeLists.txt         Optional CMake build
tests/test_tracker.py      Behavioral tests for both programs and interoperability
data/sample.csv            Demonstration expenses; real user data is ignored by Git
scripts/                   Demonstration and submission helper scripts
docs/                      Deliverable reports, slides, evidence, and screenshots
.github/workflows/ci.yml   Linux build and automated test workflow
```

## Run the Python application

Install Python 3.10 or newer from [Python.org](https://www.python.org/downloads/). No third-party packages are required. From the repository root:

```shell
python python/main.py --help
python python/main.py --data data/sample.csv list
python python/main.py --data data/sample.csv summary
```

On Windows, `py` may replace `python`; on macOS/Linux, `python3` may replace it. A supplied portable runtime used for local verification lives outside this repository in `C:\cumberlands\.tools\python` and is not a project dependency.

## Build and run the C++ application

Use a compiler with C++17 and filesystem support (for example, GCC 9+, Clang with a C++17 standard library, or a current Visual Studio C++ toolchain).

### Windows PowerShell with GCC/MinGW

```powershell
New-Item -ItemType Directory -Force build | Out-Null
g++ -std=c++17 -O2 -Wall -Wextra -Wpedantic cpp/main.cpp cpp/tracker.cpp -o build/expense_tracker.exe
.\build\expense_tracker.exe --help
.\build\expense_tracker.exe --data data/sample.csv summary
```

### Linux or macOS

```shell
mkdir -p build
g++ -std=c++17 -O2 -Wall -Wextra -Wpedantic cpp/main.cpp cpp/tracker.cpp -o build/expense_tracker
./build/expense_tracker --help
./build/expense_tracker --data data/sample.csv summary
```

`clang++` can replace `g++`. Windows MinGW builds may require the compiler's runtime DLLs unless linked statically. The locally supplied Windows executable was built with LLVM-MinGW and `-static`, and imports only Windows system DLLs; its source remains the authoritative submission.

### Optional CMake build

```shell
cmake -S cpp -B build
cmake --build build --config Release
```

A Visual Studio CMake generator places the executable at `build/Release/expense_tracker.exe`; a single-configuration generator usually uses `build/expense_tracker` (or `.exe` on Windows).

## Shared command interface

Place the global `--data PATH` option **before** the command. The default path is `data/expenses.csv`, relative to the current working directory. A missing data file starts an empty tracker. `--help`, `help`, or no command displays usage.

Use a new file such as `data/my-expenses.csv` for experimentation, preserving the supplied sample:

```shell
python python/main.py --data data/my-expenses.csv add --date 2026-10-02 --amount 12.34 --category Food --description "Lunch, campus"
python python/main.py --data data/my-expenses.csv add --date 2026-10-03 --amount 5.00 --category Transport --description "Bus ticket"
python python/main.py --data data/my-expenses.csv list
python python/main.py --data data/my-expenses.csv list --start 2026-10-02 --end 2026-10-03 --category Food
python python/main.py --data data/my-expenses.csv search --query CAMPUS
python python/main.py --data data/my-expenses.csv summary
python python/main.py --data data/my-expenses.csv summary --category Food
python python/main.py --data data/my-expenses.csv delete --id 1
```

Replace `python python/main.py` with the C++ executable to perform exactly the same operations. Category matching is **case-sensitive** (`Food` differs from `food`); search is ASCII case-insensitive. Results retain insertion order. Summary categories sort lexicographically. Successful operations return exit code `0`; invalid input or storage errors return `2` and print `Error: ...` to standard error.

### Expected sample summary

```text
Category | Total (USD)
Food | $21.09
Supplies | $19.99
Transport | $20.00
Overall | $61.08
```

## Storage and validation contract

CSV header:

```csv
id,date,amount_cents,category,description
1,2026-10-02,1234,Food,"Lunch, campus"
```

- Dates must be actual calendar dates in `YYYY-MM-DD` format, years `0001`–`9999`.
- Monetary input accepts digits and an optional decimal point followed by one or two digits. Values must be `$0.01`–`$999999999.99`. Signs, exponents, NaN, and excess precision are rejected; no rounding occurs.
- IDs are unique integers from `1` to `2147483647`; the next ID is the current maximum plus one. After deleting the highest ID, a later record may reuse that ID. Exhaustion produces an error.
- Categories contain 1–40 printable ASCII characters; descriptions contain 1–200. Leading/trailing ASCII spaces are trimmed on entry, and control characters/non-ASCII input are rejected before trimming.
- Search queries contain 1–200 printable ASCII characters after trimming.
- Stored text must already be trimmed. Fields use standard CSV quoting, including doubled embedded quotes. Multiline records, malformed quotes, duplicate IDs, invalid fields, and wrong headers are rejected.
- Storage supports at most 100,000 records and 1,024 characters per physical CSV line. Summary totals are checked against a signed 64-bit bound in both languages.
- Files are fully validated before mutations. Saves use a temporary file in the destination directory and replacement after a successful write. Python uses `os.replace`; C++ uses `MoveFileExW` on Windows and filesystem rename on POSIX. Atomic replacement protects a completed save, but does not provide multi-writer locking or a guarantee against every power-loss scenario.

## Language features demonstrated

| Topic | Python | C++17 |
|---|---|---|
| Expense representation | Dictionaries documented by `TypedDict`; runtime validation | `Expense` struct with fixed field types |
| Containers | Lists, dictionaries, comprehensions | `std::vector`, `std::map`, `std::set` |
| Dates | `datetime.date` and calendar validation | Explicit Gregorian calendar and leap-year rules |
| Money | Arbitrary-precision integers with a shared explicit limit | `std::int64_t` and checked arithmetic |
| Resource management | Context managers, automatic object memory management, `try/finally` | Value ownership, RAII streams, temporary-file destructor |
| Errors | Custom `TrackerError`, standard exceptions, boundary handling | `std::runtime_error`, typed exceptions, boundary `catch` |
| Modularity | Modules and procedural core functions | Header/source separation and `Tracker` class |
| Paradigms | Procedural functions plus declarative comprehensions | Object-oriented encapsulation plus generic STL algorithms |
| Concurrency | Deliberately single-threaded | Deliberately single-threaded |

Type hints do not make Python statically enforced at runtime. C++ containers manage their own allocations; demonstrating memory management does not require manual `new`/`delete`. Concurrency is a comparison topic rather than an artificial feature requirement for this single-user tracker.

## Run tests

Build C++ first, then run from the root:

```shell
python -m unittest discover -s python -p test_tracker.py -v
python -m unittest discover -s tests -v
```

The behavioral suite runs the actual CLI programs, checks both implementations independently, and compares their outputs and shared-file behavior. It includes persistence, exact cents, inclusive filters, search, deletion, CSV quoting, invalid dates/amounts, duplicate flags/IDs, storage corruption without data loss, record limits, and interoperability.

For a non-default C++ executable:

```powershell
$env:CPP_EXECUTABLE = (Resolve-Path build/Release/expense_tracker.exe).Path
python -m unittest discover -s tests -v
```

```shell
CPP_EXECUTABLE=./build/expense_tracker python3 -m unittest discover -s tests -v
```

If the default binary is missing, C++ and parity tests are explicitly skipped; such a run is **not** full verification. An explicitly configured missing binary produces an error. GitHub Actions builds C++ before testing. The locally verified results are recorded under `docs/evidence`.

## Residency deliverables

| Day | Date | Submission |
|---|---|---|
| Friday | October 2, 2026 | Detailed initial design, proposed task allocation, and timeline |
| Saturday | October 3, 2026 | Core implementation report, screenshots, source, and README |
| Sunday | October 4, 2026 | APA 7 comparison report and 15–20 minute presentation |

Reports are supplied in Word and PDF. Slides are supplied in PowerPoint and PDF, with speaker assignments and a timed demonstration plan. The documentation distinguishes planned team ownership from observed implementation/test results. The verified public repository URL is included above and in the reports.

## Collaboration plan

Prateek leads Python implementation and integration coordination; Venkata Sai Makani leads C++ implementation. Both members review each other's code, check equivalent behavior, and share documentation and presentation preparation. These are proposed assignments to confirm against each person's strengths. Use short-lived feature branches, small commits, and peer-reviewed pull requests before merging into `main`.

## Sources for the language comparison

- [Python typing documentation](https://docs.python.org/3/library/typing.html)
- [Python CSV documentation](https://docs.python.org/3/library/csv.html)
- [C++ Core Guidelines](https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines)

These primary sources support the report's discussion of runtime type hints, CSV handling, and resource ownership. Application examples and verification results come from this repository.
