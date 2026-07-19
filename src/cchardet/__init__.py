from cchardet import _cchardet
from .version import __version__


def detect(msg):
    """
    Args:
        msg: str
    Returns:
        {
            "encoding": str,
            "confidence": float
        }
    """
    encoding, confidence = _cchardet.detect_with_confidence(msg)
    if isinstance(encoding, bytes):
        encoding = encoding.decode()

    # Upstream freedesktop uchardet emits a few Mac charset labels with a
    # hyphen (e.g. "MAC-CENTRALEUROPE", "MAC-CYRILLIC") that Python's codec
    # registry cannot resolve as-is, even though they name the same byte->char
    # mapping as Python's hyphen-normalized aliases. Normalize them so consumers
    # can pass the result straight to open(encoding=...) / bytes.decode(), as
    # the previous uchardet did.
    #
    # These are pure label-format differences: the byte tables are identical.
    # Verifiable against the canonical Unicode Consortium mapping files
    # (https://www.unicode.org/Public/MAPPINGS/VENDORS/APPLE/ -> CENTEURO.TXT,
    # CYRILLIC.TXT), which are also what Python's codecs are generated from --
    # e.g. codecs.lookup("mac-cyrillic") and codecs.lookup("maccyrillic")
    # resolve to the same codec.
    _MAC_LABEL_ALIASES = {
        "MAC-CENTRALEUROPE": "maccentraleurope",
        "MAC-CYRILLIC": "maccyrillic",
    }
    if encoding in _MAC_LABEL_ALIASES:
        encoding = _MAC_LABEL_ALIASES[encoding]

    return {"encoding": encoding, "confidence": confidence}


class UniversalDetector(object):
    def __init__(self):
        self._detector = _cchardet.UniversalDetector()

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        self.close()
        return False

    def reset(self):
        self._detector.reset()

    def feed(self, data):
        self._detector.feed(data)

    def close(self):
        self._detector.close()

    @property
    def done(self):
        return self._detector.done

    @property
    def result(self):
        encoding, confidence = self._detector.result
        if isinstance(encoding, bytes):
            encoding = encoding.decode()
        return {"encoding": encoding, "confidence": confidence}
