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


def main() -> None:
    args = parse_args()
    if args.runs < 1:
        raise SystemExit("--runs must be at least 1")

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


if __name__ == "__main__":
    main()
