import glob
import os
import platform

import cchardet
import pytest

SKIP_LIST = [
    os.path.join('src','tests','testdata','ja','utf-16le.txt'),
    os.path.join('src','tests','testdata','ja','utf-16be.txt'),
    os.path.join('src','tests','testdata','es','iso-8859-15.txt'),
    os.path.join('src','tests','testdata','da','iso-8859-1.txt'),
    os.path.join('src','tests','testdata','he','iso-8859-8.txt'),
]

# Python can't decode encoding
SKIP_LIST_02 = [
    os.path.join('src','tests','testdata','vi','viscii.txt'),
    os.path.join('src','tests','testdata','zh','euc-tw.txt'),
]
SKIP_LIST_02.extend(SKIP_LIST)


def test_ascii():
    detected_encoding = cchardet.detect(b'abcdefghijklmnopqrstuvwxyz')
    assert 'ascii' == detected_encoding['encoding'].lower()


def test_detect():
    testfiles = glob.glob(os.path.join('src','tests','testdata','*','*.txt'))
    for testfile in testfiles:
        if testfile.replace("\\", "/") in SKIP_LIST:
            continue

        base = os.path.basename(testfile)
        expected_charset = os.path.splitext(base)[0]
        with open(testfile, 'rb') as f:
            msg = f.read()
            detected_encoding = cchardet.detect(msg)
            assert expected_charset.lower() == detected_encoding['encoding'].lower()


@pytest.mark.skipif(platform.system() == 'Windows', reason="FIXME: Cannot find test file on Windows for some reason")
def test_detector():
    detector = cchardet.UniversalDetector()
    with open(os.path.join('src','tests','samples','wikipediaJa_One_Thousand_and_One_Nights_SJIS.txt'), 'rb') as f:
        line = f.readline()
        while line:
            detector.feed(line)
            if detector.done:
                break
            line = f.readline()
    detector.close()
    detected_encoding = detector.result
    assert "shift_jis" == detected_encoding['encoding'].lower()


def test_github_issue_20():
    """
    https://github.com/PyYoshi/cChardet/issues/20
    """
    msg = b'\x8f'

    cchardet.detect(msg)

    detector = cchardet.UniversalDetector()
    detector.feed(msg)
    detector.close()


def test_decode():
    testfiles = glob.glob(os.path.join('src','tests','testdata','*','*.txt'))
    for testfile in testfiles:
        if testfile.replace("\\", "/") in SKIP_LIST_02:
            continue

        base = os.path.basename(testfile)
        expected_charset = os.path.splitext(base)[0]
        with open(testfile, 'rb') as f:
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
    assert "utf-8-sig" == detected_encoding["encoding"].lower()


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
