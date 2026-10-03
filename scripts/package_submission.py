"""Package tracked source/deliverables and the verified Windows executable."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--git", default="git")
    parser.add_argument("--output", type=Path, default=ROOT.parent / "Expense Tracker - All Deliverables.zip")
    args = parser.parse_args()
    result = subprocess.run(
        [args.git, "-c", f"safe.directory={ROOT.as_posix()}", "ls-files", "-z"],
        cwd=ROOT, check=True, stdout=subprocess.PIPE,
    )
    relative_paths = [Path(name.decode("utf-8")) for name in result.stdout.split(b"\0") if name]
    executable = Path("build/expense_tracker.exe")
    if (ROOT / executable).is_file():
        relative_paths.append(executable)
    relative_paths.append(Path(__file__).relative_to(ROOT))
    relative_paths = sorted(set(relative_paths))
    with ZipFile(args.output, "w", compression=ZIP_DEFLATED) as archive:
        for relative in relative_paths:
            path = (ROOT / relative).resolve()
            if not path.is_relative_to(ROOT) or ".git" in relative.parts:
                raise ValueError(f"Unexpected package path: {relative}")
            archive.write(path, Path(ROOT.name, relative).as_posix())
    with ZipFile(args.output, "r") as archive:
        if archive.testzip() is not None:
            raise ValueError("Submission ZIP integrity check failed.")
        if len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError("Submission ZIP contains duplicate entries.")
    print(f"Submission ZIP: {args.output}")
    print(f"{len(relative_paths)} files; {args.output.stat().st_size} bytes; integrity verified.")


if __name__ == "__main__":
    main()
