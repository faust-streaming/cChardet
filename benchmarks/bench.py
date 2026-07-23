"""cChardet benchmark tool: run a corpus benchmark or compare results.

Subcommands:
  run      Measure cchardet throughput (and, for a labeled corpus, accuracy)
           over the corpus from GitHub issue #57. Pass --supervise to run the
           measurement in a subprocess and record native-process crashes.
  compare  Render benchmark results and reject a material throughput (or
           UTF-8 mislabel) regression against the compared releases.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import pickle
import signal
import statistics
import subprocess
import sys
import time
from pathlib import Path


def package_version() -> str:
    try:
        return importlib.metadata.version("faust-cchardet")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _decode_equivalent(data: bytes, detected: str, source_codec: str) -> bool:
    """Return True if `detected` decodes `data` to the same text as its source.

    Judging by round-tripped text rather than exact label tolerates benign
    aliasing (GBK/GB18030, EUC-KR/UHC, ISO-8859-1/-15) while still rejecting a
    UTF-8 mislabel, whose bytes fail to decode as UTF-8 in the first place.
    """
    try:
        return data.decode(detected) == data.decode(source_codec)
    except (LookupError, ValueError):
        return False


def _supervise(args: argparse.Namespace) -> None:
    """Run the benchmark in a subprocess and record native-process failures."""
    command = [
        sys.executable, str(Path(__file__).resolve()), "run",
        str(args.corpus), "--label", args.label,
        "--output", str(args.output), "--runs", str(args.runs),
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


def run(args: argparse.Namespace) -> None:
    if args.supervise:
        _supervise(args)
        return
    if args.runs < 1:
        raise SystemExit("--runs must be at least 1")

    import cchardet

    # The CI workflow verifies the archive's SHA-256 before extracting this
    # pickle. Never use this script with an untrusted pickle.
    with args.corpus.open("rb") as corpus_file:
        corpus = pickle.load(corpus_file)

    # Two corpus shapes are supported. A plain list of byte strings (the
    # issue #57 CC-News corpus) measures throughput only. A dict with
    # parallel "documents" and "expected" lists (see make_nonutf8_corpus.py)
    # additionally scores detection accuracy by decode-equivalence.
    if isinstance(corpus, dict):
        documents = corpus["documents"]
        expected = corpus.get("expected")
    else:
        documents = corpus
        expected = None

    for document in documents[:50]:
        cchardet.detect(document)

    total_bytes = sum(map(len, documents))
    elapsed_runs: list[float] = []
    success = errors = empty = 0
    for run_number in range(args.runs):
        run_success = run_errors = run_empty = 0
        start = time.perf_counter()
        for document in documents:
            try:
                encoding = cchardet.detect(document).get("encoding")
            except Exception:
                run_errors += 1
                continue
            run_empty += not encoding
            run_success += bool(encoding)
        elapsed_runs.append(time.perf_counter() - start)
        if run_number == 0:
            success, errors, empty = run_success, run_errors, run_empty
        elif (run_success, run_errors, run_empty) != (success, errors, empty):
            raise RuntimeError("detection results changed between benchmark runs")

    median_seconds = statistics.median(elapsed_runs)
    result = {
        "label": args.label,
        "status": "ok",
        "version": package_version(),
        "documents": len(documents),
        "megabytes": total_bytes / 1_000_000,
        "seconds": median_seconds,
        "megabytes_per_second": total_bytes / 1_000_000 / median_seconds,
        "ok": success,
        "errors": errors,
        "empty": empty,
        "runs": args.runs,
        "elapsed_runs": elapsed_runs,
    }

    if expected is not None:
        correct = 0
        # A UTF-8 mislabel is the specific, dangerous failure this corpus
        # guards against: non-UTF-8 bytes reported as UTF-8, which makes a
        # downstream open(encoding=...) mojibake or raise. None of these
        # documents are valid UTF-8, so any UTF-8 detection is a mislabel.
        utf8_mislabels = 0
        for document, source_codec in zip(documents, expected):
            detected = cchardet.detect(document).get("encoding")
            if detected and _decode_equivalent(document, detected, source_codec):
                correct += 1
            elif detected and detected.upper() in ("UTF-8", "UTF8"):
                utf8_mislabels += 1
        result["labeled"] = len(documents)
        result["correct"] = correct
        result["accuracy"] = correct / len(documents) if documents else 0.0
        result["utf8_mislabels"] = utf8_mislabels
        result["utf8_mislabel_rate"] = (
            utf8_mislabels / len(documents) if documents else 0.0
        )
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


def compare(args: argparse.Namespace) -> None:
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
    enforce_mislabel = (
        args.max_utf8_mislabel_rate is not None
        and current.get("utf8_mislabel_rate") is not None
    )
    mislabel_passed = (
        current["utf8_mislabel_rate"] <= args.max_utf8_mislabel_rate
        if enforce_mislabel
        else True
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
        details = status + (f" ({result['signal']})" if result.get("signal") else "")
        if status == "ok":
            cells = [
                f"{result['seconds']:.3f}", f"{result['megabytes_per_second']:.1f}",
                str(result["ok"]), str(result["errors"]), str(result["empty"]),
            ]
        else:
            cells = ["—"] * 5
        if labeled:
            accuracy = result.get("accuracy")
            cells.append(f"{accuracy:.1%}" if accuracy is not None else "—")
        lines.append(
            f"| {result['label']} | {result['version']} | {details} | "
            + " | ".join(cells) + " |"
        )
    lines.append("")
    if enforce_mislabel:
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="run a corpus benchmark")
    run_parser.add_argument("corpus", type=Path)
    run_parser.add_argument("--label", required=True)
    run_parser.add_argument("--output", type=Path, required=True)
    run_parser.add_argument("--runs", type=int, default=3)
    run_parser.add_argument(
        "--supervise",
        action="store_true",
        help="run the benchmark in a subprocess and record native crashes",
    )
    run_parser.set_defaults(func=run)

    compare_parser = subparsers.add_parser("compare", help="compare benchmark results")
    compare_parser.add_argument("results", nargs="+", type=Path)
    compare_parser.add_argument(
        "--minimum-relative-throughput", type=float, default=0.8
    )
    compare_parser.add_argument(
        "--max-utf8-mislabel-rate",
        type=float,
        default=None,
        help=(
            "When the corpus is labeled, fail if the current build reports more "
            "than this fraction of non-UTF-8 documents as UTF-8. Only enforced "
            "if the current result carries a 'utf8_mislabel_rate' field."
        ),
    )
    compare_parser.add_argument("--output", type=Path, required=True)
    compare_parser.set_defaults(func=compare)

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
