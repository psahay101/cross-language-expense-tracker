#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
python_command="${PYTHON_EXECUTABLE:-python3}"
cpp_command="${CPP_EXECUTABLE:-./build/expense_tracker}"
echo 'Python: list and summary'
"$python_command" python/main.py --data data/sample.csv list
"$python_command" python/main.py --data data/sample.csv summary
echo 'C++: equivalent list and summary'
"$cpp_command" --data data/sample.csv list
"$cpp_command" --data data/sample.csv summary
echo 'Combined filters: expected Food total $8.75'
"$python_command" python/main.py --data data/sample.csv summary --start 2026-10-03 --end 2026-10-04 --category Food
"$cpp_command" --data data/sample.csv summary --start 2026-10-03 --end 2026-10-04 --category Food
echo 'Case-insensitive search: expected records #1 and #5'
"$python_command" python/main.py --data data/sample.csv search --query CAMPUS
"$cpp_command" --data data/sample.csv search --query CAMPUS
