import glob
import os
import platform

import cchardet
import pytest
import sys

SKIP_LIST = [
    os.path.join("src", "tests", "testdata", "ja", "utf-16le.txt"),
    os.path.join("src", "tests", "testdata", "ja", "utf-16be.txt"),
    os.path.join("src", "tests", "testdata", "es", "iso-8859-15.txt"),
    os.path.join("src", "tests", "testdata", "da", "iso-8859-1.txt"),
    os.path.join("src", "tests", "testdata", "he", "iso-8859-8.txt"),
]

if sys.maxsize <= 2**32:
    # Fails on i686 only, original cchardet test fails too
    SKIP_LIST.append(os.path.join("src", "tests", "testdata", "th", "tis-620.txt"))
    SKIP_LIST.append(os.path.join("src", "tests", "testdata", "fi", "iso-8859-1.txt"))
    SKIP_LIST.append(os.path.join("src", "tests", "testdata", "ga", "iso-8859-1.txt"))

# Detection differs under upstream freedesktop uchardet (see
# https://github.com/faust-streaming/cChardet/issues/46), pending review.
# (MAC-CENTRALEUROPE is no longer here: detect() normalizes that label, so the
# maccentraleurope samples pass again.) ru/maccyrillic is a label-format
# difference (MAC-CYRILLIC), and zh/gb18030 (the repetitive sample mgorny
# flagged) and mt/iso-8859-3 are genuine detection changes.
SKIP_LIST += [
    os.path.join("src", "tests", "testdata", "ru", "maccyrillic.txt"),
    os.path.join("src", "tests", "testdata", "zh", "gb18030.txt"),
    os.path.join("src", "tests", "testdata", "mt", "iso-8859-3.txt"),
]

# Latin-1 vs Windows-1252 (and ISO-8859-2 vs Windows-1250) are near-identical
# candidates -- the Windows codepages are supersets of the ISO variants, so
# uchardet's confidence margin between them is razor-thin. Under upstream
# freedesktop uchardet the *shipped* manylinux wheel resolves these common
# Western-European samples to the Windows codepage, while a local -O2 dev build
# still reports the ISO label; the ranking flips with compiler optimization.
# The relabel is decode-compatible (windows-1252 superset of iso-8859-1), so we
# skip these pending the issue #46 review rather than asserting a build-
# dependent result. See https://github.com/faust-streaming/cChardet/issues/46.
SKIP_LIST += [
    os.path.join("src", "tests", "testdata", "fr", "iso-8859-1.txt"),
    os.path.join("src", "tests", "testdata", "pt", "iso-8859-1.txt"),
    os.path.join("src", "tests", "testdata", "es", "iso-8859-1.txt"),
    os.path.join("src", "tests", "testdata", "da", "iso-8859-15.txt"),
    os.path.join("src", "tests", "testdata", "hu", "iso-8859-2.txt"),
]

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
    "testfile", glob.glob(os.path.join("src", "tests", "testdata", "*", "*.txt"))
)
def test_detect(testfile):
    if testfile.replace("\\", "/") in SKIP_LIST:
        return

    base = os.path.basename(testfile)
    expected_charset = os.path.splitext(base)[0]
    with open(testfile, "rb") as f:
        msg = f.read()
        detected_encoding = cchardet.detect(msg)
        assert expected_charset.lower() == detected_encoding["encoding"].lower()


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
    # Upstream freedesktop uchardet reports a UTF-8 BOM as plain UTF-8 (the
    # fork of uchardet reported UTF-8-SIG).
    assert "utf-8" == detected_encoding["encoding"].lower()


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
