import glob
import os
import platform

import cchardet
import pytest
import sys

SKIP_LIST = [
    # ja/utf-16{le,be}: BOM-less UTF-16 is detected as UTF-8 (a known upstream
    # limitation -- freedesktop uchardet #45, "UTF16/32 detection is useless").
    os.path.join("src", "tests", "testdata", "ja", "utf-16le.txt"),
    os.path.join("src", "tests", "testdata", "ja", "utf-16be.txt"),
    # es/iso-8859-15: detected as ISO-8859-1, which is genuinely wrong here --
    # the sample uses a character that differs between the two (not decode-
    # equivalent, unlike the da/he cases below).
    os.path.join("src", "tests", "testdata", "es", "iso-8859-15.txt"),
]

if sys.maxsize <= 2**32:
    # Fails on i686 only, original cchardet test fails too
    SKIP_LIST.append(os.path.join("src", "tests", "testdata", "th", "tis-620.txt"))
    SKIP_LIST.append(os.path.join("src", "tests", "testdata", "fi", "iso-8859-1.txt"))
    SKIP_LIST.append(os.path.join("src", "tests", "testdata", "ga", "iso-8859-1.txt"))

# Genuine detection changes under upstream freedesktop uchardet where the new
# label is *wrong* for the sample -- verified by decoding the sample bytes
# against the canonical Unicode Consortium mapping tables
# (https://www.unicode.org/Public/MAPPINGS/). Kept skipped pending issue #46:
#   * mt/iso-8859-3 -- Maltese (needs ISO-8859-3's ċ/ġ/ħ/ż) mis-detected as
#                      ISO-8859-15 @ ~0.49. Instance of the known upstream
#                      "language-awareness for encoding ties" problem: both
#                      encodings decode the bytes, confidence sits near 0.5 (and
#                      is fixed regardless of input length), so the pick is
#                      essentially chance. Tracked upstream at
#                      https://gitlab.freedesktop.org/uchardet/uchardet/-/issues/2
#                      (same single-byte class as freedesktop uchardet #6 and
#                      #28). Not fixable in this binding.
#   * da/iso-8859-15 -- the manylinux wheel relabels this WINDOWS-1252, but the
#                      file contains € (byte 0xA4 = U+20AC in ISO-8859-15 vs
#                      ¤ U+00A4 in windows-1252), so the Windows label is wrong.
# (ru/maccyrillic is no longer skipped: detect() normalizes the MAC-CYRILLIC
# label to maccyrillic -- see src/cchardet/__init__.py. zh/gb18030 is no longer
# skipped either: its sample was a degenerate 88-byte repeat of one phrase that
# uchardet mis-ranked; it is now a realistic Chinese paragraph, which detects as
# GB18030 correctly.)
# See https://github.com/faust-streaming/cChardet/issues/46.
SKIP_LIST += [
    os.path.join("src", "tests", "testdata", "mt", "iso-8859-3.txt"),
    os.path.join("src", "tests", "testdata", "da", "iso-8859-15.txt"),
]

# Samples where freedesktop uchardet reports a superset/near-equivalent label
# instead of the exact one, but the two encodings decode to *identical* text for
# the bytes actually present -- so instead of asserting a build-dependent name,
# test_detect asserts decode-equivalence.
#   * fr/pt/es iso-8859-1, hu iso-8859-2 -> Windows-125x: no bytes in 0x80-0x9F
#     and no 0xA4 (the only positions where ISO-8859-1/-2 and windows-1252/-1250
#     disagree), so they decode identically; the exact label is build-dependent.
#   * da iso-8859-1 -> ISO-8859-15: no distinguishing bytes, decodes identically.
#   * he iso-8859-8 -> WINDOWS-1255 (a superset of ISO-8859-8), identical over
#     the bytes present. (da and he were previously skipped outright; the
#     freedesktop engine detects them as decode-equivalent labels, so they are
#     now real assertions rather than silent skips.)
# Byte tables: https://www.unicode.org/Public/MAPPINGS/ (ISO8859/*.TXT,
# VENDORS/MICSFT/WINDOWS/CP125x.TXT, VENDORS/MICSFT/WINDOWS/CP1255.TXT).
DECODE_EQUIVALENT = {
    os.path.join("src", "tests", "testdata", "fr", "iso-8859-1.txt"),
    os.path.join("src", "tests", "testdata", "pt", "iso-8859-1.txt"),
    os.path.join("src", "tests", "testdata", "es", "iso-8859-1.txt"),
    os.path.join("src", "tests", "testdata", "hu", "iso-8859-2.txt"),
    os.path.join("src", "tests", "testdata", "da", "iso-8859-1.txt"),
    os.path.join("src", "tests", "testdata", "he", "iso-8859-8.txt"),
}

# Python can't decode encoding
SKIP_LIST_02 = [
    os.path.join("src", "tests", "testdata", "vi", "viscii.txt"),
    os.path.join("src", "tests", "testdata", "zh", "euc-tw.txt"),
]

SKIP_LIST_02.extend(SKIP_LIST)


def test_ascii():
    detected_encoding = cchardet.detect(b"abcdefghijklmnopqrstuvwxyz")
    assert "ascii" == detected_encoding["encoding"].lower()


@pytest.mark.parametrize(
    ("sample", "expected_encoding"),
    [
        (("é" * 1200).encode("utf-8"), "utf-8"),
        (("é" * 1200).encode("utf-8") + b"\xff", None),
    ],
)
def test_long_multibyte_input_does_not_overflow_uchardet_buffer(sample, expected_encoding):
    # freedesktop uchardet keeps a 1024-entry internal code-point buffer. A
    # single HandleData call containing more than 1024 multi-byte characters
    # writes past that allocation and eventually aborts in free(). This also
    # covers the same shape as the Assamese documents that crash issue #57's
    # benchmark corpus.
    detected = cchardet.detect(sample)

    assert detected["encoding"] is not None
    if expected_encoding is not None:
        assert detected["encoding"].lower() == expected_encoding

    detector = cchardet.UniversalDetector()
    detector.feed(sample)
    detector.close()
    assert detector.result["encoding"] is not None


@pytest.mark.parametrize(
    "testfile", glob.glob(os.path.join("src", "tests", "testdata", "*", "*.txt"))
)
def test_detect(testfile):
    key = testfile.replace("\\", "/")
    if key in SKIP_LIST:
        return

    base = os.path.basename(testfile)
    expected_charset = os.path.splitext(base)[0]
    with open(testfile, "rb") as f:
        msg = f.read()
    detected_encoding = cchardet.detect(msg)["encoding"]

    if key in DECODE_EQUIVALENT:
        # The exact label is build-dependent, but it must decode identically to
        # the filename-declared encoding over the bytes present (see
        # DECODE_EQUIVALENT above).
        assert detected_encoding is not None
        assert msg.decode(detected_encoding) == msg.decode(expected_charset)
        return

    assert expected_charset.lower() == detected_encoding.lower()


@pytest.mark.skipif(
    platform.system() == "Windows",
    reason="FIXME: Cannot find test file on Windows for some reason",
)
def test_detector():
    detector = cchardet.UniversalDetector()
    with open(
        os.path.join(
            "src",
            "tests",
            "samples",
            "wikipediaJa_One_Thousand_and_One_Nights_SJIS.txt",
        ),
        "rb",
    ) as f:
        line = f.readline()
        while line:
            detector.feed(line)
            if detector.done:
                break
            line = f.readline()
    detector.close()
    detected_encoding = detector.result
    assert "shift_jis" == detected_encoding["encoding"].lower()


def test_github_issue_20():
    """
    https://github.com/PyYoshi/cChardet/issues/20
    """
    msg = b"\x8f"

    cchardet.detect(msg)

    detector = cchardet.UniversalDetector()
    detector.feed(msg)
    detector.close()


def test_universaldetector_result_without_close():
    """
    Regression test for https://github.com/faust-streaming/cChardet/issues/35

    Feeding a multi-byte encoding (UHC / CP949) line by line and then reading
    .result -- without an explicit close() -- must return the detected charset
    rather than None. uchardet only decides at DataEnd(), so .result finalizes
    detection on read.
    """
    data = "한국어 인코딩 테스트입니다.\n".encode(
        "cp949"
    ) * 60

    detector = cchardet.UniversalDetector()
    for line in data.split(b"\n"):
        detector.feed(line + b"\n")
        if detector.done:
            break

    encoding = detector.result["encoding"]
    assert encoding is not None
    assert encoding.lower() == "uhc"


def test_universaldetector_done_implies_result():
    """
    Regression test for https://github.com/faust-streaming/cChardet/issues/35

    Upstream freedesktop uchardet only resolves detection at DataEnd(), so
    `done` does not flip mid-feed (unlike the old fork, which set it on a BOM).
    Reading .result finalizes detection: it returns the charset (UTF-8 for a
    BOM) and .done becomes True -- without an explicit close().
    """
    detector = cchardet.UniversalDetector()
    detector.feed(b"\xEF\xBB\xBF" + b"hello world " * 20)

    # .result finalizes on read (freedesktop publishes candidates at DataEnd).
    assert detector.result["encoding"] is not None
    assert detector.done


def test_github_issue_33_not_big5():
    """
    https://github.com/faust-streaming/cChardet/issues/33

    A near-ASCII, pipe-delimited CSV whose only non-ASCII bytes are a handful
    of Windows-1252 characters (0xB0 degree sign, 0x96 en-dash) was detected as
    BIG5 with 0.99 confidence by the previous (PyYoshi-fork) uchardet: some of
    the stray high bytes form valid Big5 lead+trail pairs and the fork's
    confidence model over-committed. Upstream freedesktop uchardet no longer
    makes that confident misdetection; guard against regressing back to Big5.
    """
    sample = (
        b'A|B|C|D|E|F|G|H|Date<30\xb0|Time\n'
        b'1|2|3|4d|5|6|7|8|2022-01-22|13:41\n'
        b'9|10|11|12|5|6|7|8|2022-01-22|13:41\n'
        b'10|2|3|4|5|6|7|8|2022-01-22|13:41\n'
        b'11|2|3|4|5|6|7|8|2022-01-22|13:41\n'
        b'11|2|3|4|5|6|7|8|2022-01-22|13:41\n'
        b'11|2|3|4|5|6|7|8|2022-01-22|13:41\n'
        b'11|2|3|4|5|6|7|8|2022-01-22|13:41\n'
        b'11|2|3|4|5|6|7|8|2022-01-22|13:41\n'
        b'11|2|3|4|5|6|7|8|2022-01-22<30\xb0|13:41\n'
        b'11|2|3|4|5|6|7|8|2022-01-22<30\xb0|13:41\n'
        b'11|2|3|4|5|6|7|8|2022-01-22<30\xb0|13:41\n'
        b'11|2|3|4|5|6|7|8|2022-01-22<30\xb0|13:41\n'
        b'11|2|3|4|5|6|7|8|2022-01-22|13:41\n'
        b'11|2|3|4|5|6|7|8|2022-01-22|13:41\n'
        b'|||||||||\n'
        b'""|""|""|""|""|""|""|""||\n'
        b'someVal|2|3|4|5|6|7|8|2022-01-22|13:41\n'
        b'\x1a\n'
        b'\x96'
    )
    detected = cchardet.detect(sample)
    assert (detected["encoding"] or "").upper() != "BIG5"


def test_decode():
    testfiles = glob.glob(os.path.join("src", "tests", "testdata", "*", "*.txt"))
    for testfile in testfiles:
        if testfile.replace("\\", "/") in SKIP_LIST_02:
            continue

        base = os.path.basename(testfile)
        expected_charset = os.path.splitext(base)[0]
        with open(testfile, "rb") as f:
            msg = f.read()
        detected_encoding = cchardet.detect(msg)
        try:
            msg.decode(detected_encoding["encoding"])
        except LookupError as e:
            print(
                "LookupError: { file=%s, encoding=%s }"
                % (testfile, detected_encoding["encoding"]),
            )
            raise e


def test_utf8_with_bom():
    sample = b"\xEF\xBB\xBF"
    detected_encoding = cchardet.detect(sample)
    # Upstream freedesktop uchardet labels a UTF-8 BOM as plain "UTF-8"; detect()
    # normalizes it back to "UTF-8-SIG" (matching chardet and the previous
    # uchardet) so decoding with the detected label strips the BOM. See the
    # BOM normalization in src/cchardet/__init__.py.
    assert "utf-8-sig" == detected_encoding["encoding"].lower()


def test_universaldetector_bom_normalization():
    # UniversalDetector must apply the same UTF-8 BOM normalization as detect()
    # so the streaming API is consistent for consumers that decode with the
    # detected label. Non-BOM UTF-8 must stay "UTF-8".
    detector = cchardet.UniversalDetector()
    detector.feed(b"\xEF\xBB\xBF" + "Some UTF-8 text.".encode("utf-8") * 3)
    detector.close()
    assert "utf-8-sig" == detector.result["encoding"].lower()

    detector = cchardet.UniversalDetector()
    detector.feed("これは日本語のテキストです。".encode("utf-8") * 4)
    detector.close()
    assert "utf-8" == detector.result["encoding"].lower()


@pytest.mark.skip(
    reason="upstream freedesktop uchardet detects IBM862 for this input rather "
    "than returning None; see issue #46",
)
def test_null_bytes():
    sample = b"ABC\x00\x80\x81"
    detected_encoding = cchardet.detect(sample)

    assert detected_encoding["encoding"] is None


# def test_iso8859_2_csv(self):
#     testfile = 'tests/samples/iso8859-2.csv'
#     with open(testfile, 'rb') as f:
#         msg = f.read()
#         detected_encoding = cchardet.detect(msg)
#         eq_(
#             "iso8859-2",
#             detected_encoding['encoding'].lower(),
#             'Expected %s, but got %s' % (
#                 "iso8859-2",
#                 detected_encoding['encoding'].lower()
#             )
#         )
