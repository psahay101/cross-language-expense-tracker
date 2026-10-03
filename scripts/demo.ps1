param(
    [string]$PythonExecutable = 'python',
    [string]$CppExecutable = '.\build\expense_tracker.exe'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

Write-Output 'Python: list and category totals from the supplied sample'
& $PythonExecutable python/main.py --data data/sample.csv list
& $PythonExecutable python/main.py --data data/sample.csv summary
Write-Output 'C++: identical list and totals'
& $CppExecutable --data data/sample.csv list
& $CppExecutable --data data/sample.csv summary
Write-Output 'Combined date/category filter: expected Food total $8.75'
& $PythonExecutable python/main.py --data data/sample.csv summary --start 2026-10-03 --end 2026-10-04 --category Food
& $CppExecutable --data data/sample.csv summary --start 2026-10-03 --end 2026-10-04 --category Food
Write-Output 'Case-insensitive search: expected records #1 and #5'
& $PythonExecutable python/main.py --data data/sample.csv search --query CAMPUS
& $CppExecutable --data data/sample.csv search --query CAMPUS
Write-Output 'Add/delete/persistence examples and failure cases are in scripts/capture_evidence.py.'
