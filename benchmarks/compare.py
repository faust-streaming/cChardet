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
    parser.add_argument(
        "--max-utf8-mislabel-rate",
        type=float,
        default=None,
        help=(
            "When the corpus is labeled, fail if the current build reports more "
            "than this fraction of non-UTF-8 documents as UTF-8. Only enforced "
            "if the current result carries a 'utf8_mislabel_rate' field."
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    results = [json.loads(path.read_text(encoding="utf-8")) for path in args.results]
    current = next((result for result in results if result["label"] == "current"), None)
    releases = [result for result in results if result["label"] != "current"]
    if current is None or len(releases) != 2:
        raise SystemExit("expected one current result and exactly two release results")

    successful_releases = [
        result
        for result in releases
        if result.get("status", "ok") == "ok"
        and result.get("megabytes_per_second") is not None
    ]
    fastest_release = (
        max(successful_releases, key=lambda result: result["megabytes_per_second"])
        if successful_releases
        else None
    )
    required = (
        fastest_release["megabytes_per_second"] * args.minimum_relative_throughput
        if fastest_release
        else None
    )
    throughput_passed = (
        current.get("status", "ok") == "ok"
        and current.get("megabytes_per_second") is not None
        and required is not None
        and current["megabytes_per_second"] >= required
    )

    # Accuracy is only present for a labeled corpus (see make_nonutf8_corpus.py).
    labeled = any(result.get("accuracy") is not None for result in results)
    mislabel_passed = True
    if (
        args.max_utf8_mislabel_rate is not None
        and current.get("utf8_mislabel_rate") is not None
    ):
        mislabel_passed = (
            current["utf8_mislabel_rate"] <= args.max_utf8_mislabel_rate
        )

    passed = throughput_passed and mislabel_passed

    accuracy_header = " Accuracy |" if labeled else ""
    accuracy_divider = " ---: |" if labeled else ""
    lines = [
        "## cChardet benchmark",
        "",
        "| Build | Package version | Status | Seconds (median) | MB/s | OK | "
        f"Error | Empty |{accuracy_header}",
        f"|---|---:|---|---:|---:|---:|---:|---:|{accuracy_divider}",
    ]
    for result in results:
        status = result.get("status", "ok")
        seconds = result.get("seconds")
        throughput = result.get("megabytes_per_second")
        details = status
        if result.get("signal"):
            details += f" ({result['signal']})"
        if labeled:
            accuracy = result.get("accuracy")
            accuracy_cell = f" {accuracy:.1%} |" if accuracy is not None else " — |"
        else:
            accuracy_cell = ""
        lines.append(
            f"| {result['label']} | {result['version']} | {details} | "
            f"{seconds:.3f} | {throughput:.1f} | {result['ok']} | "
            f"{result['errors']} | {result['empty']} |{accuracy_cell}"
            if status == "ok"
            else f"| {result['label']} | {result['version']} | {details} | — | — | — | — | — |{accuracy_cell}"
        )
    lines.append("")
    if (
        args.max_utf8_mislabel_rate is not None
        and current.get("utf8_mislabel_rate") is not None
    ):
        lines.extend(
            [
                f"Current must report no more than {args.max_utf8_mislabel_rate:.0%} "
                f"of non-UTF-8 documents as UTF-8; measured "
                f"{current['utf8_mislabel_rate']:.1%} "
                f"({current.get('utf8_mislabels', 0)}/{current.get('labeled', 0)}) — "
                f"{'PASS' if mislabel_passed else 'FAIL'}.",
                "",
            ]
        )
    if fastest_release:
        lines.extend(
            [
                (
                    f"Current must retain at least {args.minimum_relative_throughput:.0%} "
                    f"of the fastest successful comparison release "
                    f"({fastest_release['label']}: "
                    f"{fastest_release['megabytes_per_second']:.1f} MB/s); measured "
                    f"{current['megabytes_per_second']:.1f} MB/s, required "
                    f"{required:.1f} MB/s — {'PASS' if throughput_passed else 'FAIL'}."
                    if current.get("status", "ok") == "ok"
                    else f"Current benchmark {current.get('status', 'failed')}."
                ),
                "",
                f"**Result: {'PASS' if passed else 'FAIL'}**",
            ]
        )
    else:
        lines.extend(
            [
                "No successful comparison release produced a throughput measurement.",
                "",
                "**Result: FAIL** — benchmark comparison is unavailable.",
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
