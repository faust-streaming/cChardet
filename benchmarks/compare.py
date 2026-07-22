"""Render benchmark results and reject a material throughput regression."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", nargs="+", type=Path)
    parser.add_argument("--minimum-relative-throughput", type=float, default=0.8)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    results = [json.loads(path.read_text(encoding="utf-8")) for path in args.results]
    current = next((result for result in results if result["label"] == "current"), None)
    releases = [result for result in results if result["label"] != "current"]
    if current is None or len(releases) != 2:
        raise SystemExit("expected one current result and exactly two release results")

    fastest_release = max(releases, key=lambda result: result["megabytes_per_second"])
    required = fastest_release["megabytes_per_second"] * args.minimum_relative_throughput
    passed = current["megabytes_per_second"] >= required

    lines = [
        "## cChardet benchmark",
        "",
        "| Build | Package version | Seconds (median) | MB/s | OK | Error | Empty |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        lines.append(
            f"| {result['label']} | {result['version']} | {result['seconds']:.3f} | "
            f"{result['megabytes_per_second']:.1f} | {result['ok']} | "
            f"{result['errors']} | {result['empty']} |"
        )
    lines.extend(
        [
            "",
            f"Current must retain at least {args.minimum_relative_throughput:.0%} of the "
            f"fastest comparison release ({fastest_release['label']}: "
            f"{fastest_release['megabytes_per_second']:.1f} MB/s).",
            "",
            f"**Result: {'PASS' if passed else 'FAIL'}** — current measured "
            f"{current['megabytes_per_second']:.1f} MB/s; required {required:.1f} MB/s.",
        ]
    )
    summary = "\n".join(lines) + "\n"
    args.output.write_text(summary, encoding="utf-8")
    print(summary)

    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as summary_file:
            summary_file.write(summary)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
