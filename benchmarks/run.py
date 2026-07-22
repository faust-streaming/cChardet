"""Run a benchmark in a subprocess and record native-process failures."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import signal
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=3)
    return parser.parse_args()


def package_version() -> str:
    try:
        return importlib.metadata.version("faust-cchardet")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def main() -> None:
    args = parse_args()
    command = [
        sys.executable,
        str(Path(__file__).with_name("benchmark.py")),
        str(args.corpus),
        "--label",
        args.label,
        "--output",
        str(args.output),
        "--runs",
        str(args.runs),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    if completed.returncode == 0:
        return

    signal_name = None
    if completed.returncode < 0:
        try:
            signal_name = signal.Signals(-completed.returncode).name
        except ValueError:
            signal_name = f"SIG{-completed.returncode}"

    diagnostic = (completed.stderr or completed.stdout).strip()
    result = {
        "label": args.label,
        "status": "crashed" if signal_name else "failed",
        "version": package_version(),
        "exit_code": completed.returncode,
        "signal": signal_name,
        "diagnostic": diagnostic[-4000:],
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
