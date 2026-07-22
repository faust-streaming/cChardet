"""Measure cchardet throughput over the corpus from GitHub issue #57."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import pickle
import statistics
import time
from pathlib import Path

import cchardet


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=3)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.runs < 1:
        raise SystemExit("--runs must be at least 1")

    # The CI workflow verifies the archive's SHA-256 before extracting this
    # pickle. Never use this script with an untrusted pickle.
    with args.corpus.open("rb") as corpus_file:
        documents = pickle.load(corpus_file)

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
        "version": importlib.metadata.version("faust-cchardet"),
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
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
