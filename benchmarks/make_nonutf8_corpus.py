"""Generate a deterministic non-UTF-8 benchmark corpus.

The issue #57 CC-News corpus is almost entirely valid UTF-8, so cChardet's
UTF-8 fast path answers before uchardet is ever consulted. That leaves the
real detection engine -- the expensive path that regressed in freedesktop
uchardet (see work item #38) and the path most prone to mislabeling
non-UTF-8 bytes as UTF-8 -- completely unexercised by CI.

This module builds a labeled corpus of single- and multi-byte non-UTF-8
documents so both throughput (the #38 slowdown class) and accuracy (the
mislabel class) can be regression-gated. It is fully deterministic and needs
no network access, so the corpus never has to be downloaded or SHA-pinned.

The pickle it writes is a dict:

    {
        "documents": [bytes, ...],   # raw encoded document bytes
        "expected":  [str, ...],     # the source codec each document was
                                     # encoded with, parallel to "documents"
    }

Correctness is judged by decode-equivalence rather than exact label match:
a detection is counted correct when the detected codec decodes the document
to the same text the source codec produces. That tolerates benign aliasing
(GBK/GB18030, EUC-KR/UHC, ISO-8859-1/-15 on text without €-block
characters) while still rejecting a UTF-8 mislabel, whose bytes do not
decode as UTF-8 at all.
"""

from __future__ import annotations

import argparse
import pickle
import random
from pathlib import Path

# Short, public-domain-style snippets. The Latin samples deliberately avoid
# characters that differ between ISO-8859-1 and ISO-8859-15 (the € block:
# € Š š Ž ž Œ œ Ÿ) so either label is decode-equivalent for this text.
SAMPLES: dict[str, str] = {
    "fr": (
        "Le gouvernement a annoncé mardi que la mesure serait révisée avant "
        "la fin de l'année. Les élus locaux ont déclaré que des milliers "
        "d'habitants pourraient être touchés par cette décision inattendue. "
        "Un porte-parole a précisé que les négociations continueraient."
    ),
    "de": (
        "Die Regierung kündigte an, dass der Vorschlag vor Jahresende "
        "geprüft werde. Örtliche Beamte erklärten, die Maßnahme könnte "
        "Tausende Einwohner der größeren Städte betreffen. Fachleute wiesen "
        "darauf hin, dass die Änderungen für Verbraucher spürbar wären."
    ),
    "es": (
        "El gobierno anunció que la propuesta será revisada antes de fin de "
        "año. Funcionarios locales señalaron que la medida podría afectar a "
        "miles de residentes de la región montañosa. Un vocero indicó que "
        "las negociaciones seguirían durante las próximas semanas."
    ),
    "ru": (
        "Правительство объявило во вторник, что предложение будет "
        "рассмотрено до конца финансового года. Местные чиновники заявили, "
        "что эта мера может затронуть тысячи жителей региона. Аналитики "
        "отметили, что рынки оставались нестабильными весь квартал."
    ),
    "ja": (
        "政府は火曜日、会計年度末までに提案が検討されると発表した。地元当局者は、"
        "この措置が地域の何千人もの住民に影響を与える可能性があると述べた。"
        "アナリストは市場が四半期を通じて不安定なままだったと指摘している。"
    ),
    # Simplified Chinese, for GBK/GB18030.
    "zh": (
        "政府周二宣布，该提案将在本财政年度结束前进行审查。当地官员表示，"
        "这项措施可能影响该地区数千名居民的日常生活。分析人士指出，"
        "整个季度市场依然动荡，投资者密切关注利率的变化趋势。"
    ),
    # Traditional Chinese, for Big5 (which cannot encode simplified forms).
    "zh_tw": (
        "政府週二宣布，該提案將在本財政年度結束前進行審查。當地官員表示，"
        "這項措施可能影響該地區數千名居民的日常生活。分析人士指出，"
        "整個季度市場依然動盪，投資者密切關注利率的變化趨勢。"
    ),
    "ko": (
        "정부는 화요일 해당 제안이 회계연도 말 이전에 검토될 것이라고 발표했다. "
        "지역 관계자들은 이 조치가 지역 주민 수천 명에게 영향을 미칠 수 있다고 "
        "말했다. 분석가들은 시장이 분기 내내 불안정했다고 지적했다."
    ),
}

# Each category pairs a source codec with the languages whose text encodes
# cleanly in it. Only non-UTF-8 codecs appear -- that is the whole point.
CATEGORIES: tuple[tuple[str, tuple[str, ...], int], ...] = (
    ("iso-8859-15", ("fr", "de", "es"), 300),
    ("windows-1251", ("ru",), 250),
    ("shift_jis", ("ja",), 200),
    ("euc-jp", ("ja",), 200),
    ("gbk", ("zh",), 250),
    ("big5", ("zh_tw",), 200),
    ("euc-kr", ("ko",), 250),
)

_TARGET_BYTES = 2048


def _make_text(rng: random.Random, langs: tuple[str, ...]) -> str:
    """Build a document of roughly _TARGET_BYTES from the given languages."""
    parts: list[str] = []
    size = 0
    while size < _TARGET_BYTES:
        base = SAMPLES[rng.choice(langs)]
        # Sentence-ish slice so documents are not identical copies.
        start = rng.randint(0, max(0, len(base) - 60))
        chunk = base[start:start + rng.randint(40, 80)]
        parts.append(chunk)
        size += len(chunk.encode("utf-8"))
    return " ".join(parts)


def build_corpus(seed: int = 57) -> dict[str, list]:
    rng = random.Random(seed)
    documents: list[bytes] = []
    expected: list[str] = []
    for codec, langs, count in CATEGORIES:
        for _ in range(count):
            text = _make_text(rng, langs)
            documents.append(text.encode(codec))
            expected.append(codec)
    return {"documents": documents, "expected": expected}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="destination .pkl path")
    parser.add_argument("--seed", type=int, default=57)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    corpus = build_corpus(args.seed)
    args.output.write_bytes(pickle.dumps(corpus))
    total = sum(map(len, corpus["documents"]))
    print(
        f"wrote {len(corpus['documents'])} documents "
        f"({total / 1_000_000:.2f} MB) across "
        f"{len(CATEGORIES)} non-UTF-8 encodings to {args.output}"
    )


if __name__ == "__main__":
    main()
