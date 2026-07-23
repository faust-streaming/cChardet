"""Regression guard for non-UTF-8 detection.

cChardet 3.x builds uchardet without its generic language pass. That pass is
what upstream relies on to (a) reject a UTF-8 candidate produced from
non-UTF-8 bytes and (b) suppress weak multibyte false positives. Removing it
without compensating -- as an earlier revision of the encoding-only overlay
did -- mislabels non-UTF-8 multibyte text (GBK, EUC-KR, ...) as UTF-8.

The issue #57 CC-News benchmark corpus cannot catch this: it is almost
entirely valid UTF-8, so cChardet's UTF-8 fast path answers before the
detection engine runs. These tests exercise the engine directly with a
deterministic, generated non-UTF-8 corpus (benchmarks/make_nonutf8_corpus.py)
and assert the specific failure never returns.
"""

import os
import sys

import pytest

# benchmarks/ is a sibling of src/ at the repository root, not an installed
# package. Add it to the path so the shared corpus generator can be imported.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BENCHMARKS_DIR = os.path.join(_REPO_ROOT, "benchmarks")
if _BENCHMARKS_DIR not in sys.path:
    sys.path.insert(0, _BENCHMARKS_DIR)

import cchardet

try:
    import make_nonutf8_corpus
except ImportError:  # pragma: no cover - benchmarks/ absent (e.g. sdist)
    make_nonutf8_corpus = None

pytestmark = pytest.mark.skipif(
    make_nonutf8_corpus is None,
    reason="benchmarks/make_nonutf8_corpus.py not available in this checkout",
)

# Multibyte codecs are the encoding-only overlay's direct responsibility and
# the ones the pre-fix overlay mislabeled as UTF-8.
_MULTIBYTE_CODECS = {"shift_jis", "euc-jp", "gbk", "big5", "euc-kr"}


def _decode_equivalent(data, detected, source_codec):
    try:
        return data.decode(detected) == data.decode(source_codec)
    except (LookupError, ValueError):
        return False


@pytest.fixture(scope="module")
def corpus():
    return make_nonutf8_corpus.build_corpus()


def test_no_multibyte_document_is_mislabeled_as_utf8(corpus):
    """No non-UTF-8 multibyte document may be reported as UTF-8 -- the exact
    overlay regression: a caller's open(encoding="utf-8") then mojibakes."""
    offenders = []
    for data, source_codec in zip(corpus["documents"], corpus["expected"]):
        if source_codec not in _MULTIBYTE_CODECS:
            continue
        detected = (cchardet.detect(data).get("encoding") or "")
        if detected.upper() in ("UTF-8", "UTF8"):
            offenders.append((source_codec, detected, data[:32]))
    assert not offenders, (
        f"{len(offenders)} multibyte document(s) mislabeled as UTF-8, e.g. "
        f"{offenders[0][0]} -> {offenders[0][1]}"
    )


def test_multibyte_detection_is_accurate(corpus):
    """Every multibyte document must decode-match its source codec. Genuine
    detections score well above the 0.5 threshold, so require >= 99% accuracy
    (headroom for an incidental ambiguous sample, not a real regression)."""
    total = correct = 0
    for data, source_codec in zip(corpus["documents"], corpus["expected"]):
        if source_codec not in _MULTIBYTE_CODECS:
            continue
        total += 1
        detected = cchardet.detect(data).get("encoding")
        if detected and _decode_equivalent(data, detected, source_codec):
            correct += 1
    assert total > 0
    accuracy = correct / total
    assert accuracy >= 0.99, f"multibyte accuracy {accuracy:.1%} ({correct}/{total})"


def test_issue_33_style_false_positive_is_suppressed(corpus):
    """No document may be confidently mislabeled Big5 (issue #33 class): a
    near-ASCII sample scored ~0.4 Big5 once the bogus UTF-8 candidate was
    removed, which the overlay's 0.5 multibyte threshold now suppresses."""
    for data, source_codec in zip(corpus["documents"], corpus["expected"]):
        if source_codec == "big5":
            continue
        result = cchardet.detect(data)
        detected = (result.get("encoding") or "").upper()
        if detected == "BIG5":
            assert _decode_equivalent(data, "big5", source_codec), (
                f"{source_codec} document mislabeled as Big5 "
                f"(confidence {result.get('confidence')})"
            )
