from types import TracebackType
from typing import Literal, TypedDict, TypeVar

from cchardet import _cchardet
from .version import __version__

__all__ = ["DetectionResult", "UniversalDetector", "__version__", "detect"]

# typing.Self is 3.11+, and this package supports 3.10, so __enter__ is typed
# with a bound TypeVar instead -- subclasses still get their own type back.
_SelfT = TypeVar("_SelfT", bound="UniversalDetector")


class DetectionResult(TypedDict):
    """What :func:`detect` and :attr:`UniversalDetector.result` return.

    Both values are ``None`` when nothing could be detected, so callers have to
    handle that before using the encoding -- which is exactly what a type
    checker enforces once this package ships its ``py.typed`` marker.
    """

    encoding: str | None
    confidence: float | None


# Upstream freedesktop uchardet emits a few Mac charset labels with a hyphen
# (e.g. "MAC-CENTRALEUROPE", "MAC-CYRILLIC") that Python's codec registry cannot
# resolve as-is, even though they name the same byte->char mapping as Python's
# hyphen-normalized aliases. These are pure label-format differences: the byte
# tables are identical. Verifiable against the canonical Unicode Consortium
# mapping files (https://www.unicode.org/Public/MAPPINGS/VENDORS/APPLE/ ->
# CENTEURO.TXT, CYRILLIC.TXT), which are also what Python's codecs are generated
# from -- e.g. codecs.lookup("mac-cyrillic") and codecs.lookup("maccyrillic")
# resolve to the same codec.
_MAC_LABEL_ALIASES = {
    "MAC-CENTRALEUROPE": "maccentraleurope",
    "MAC-CYRILLIC": "maccyrillic",
}

_UTF8_BOM = b"\xef\xbb\xbf"


def _normalize_encoding(encoding: str | None, leading_bytes: bytes) -> str | None:
    """Normalize freedesktop uchardet labels to match the previous uchardet
    (and Python's ``chardet``) so results stay usable with open(encoding=...)
    / bytes.decode().

    ``leading_bytes`` is the first few bytes of the input (used to detect a
    UTF-8 BOM); pass ``b""`` when unavailable.
    """
    if encoding in _MAC_LABEL_ALIASES:
        return _MAC_LABEL_ALIASES[encoding]

    # freedesktop uchardet reports a UTF-8 byte-order mark as plain "UTF-8",
    # whereas the previous uchardet (and chardet) report "UTF-8-SIG". The
    # distinction matters downstream: decoding with "utf-8-sig" strips the BOM,
    # while "utf-8" leaves a leading U+FEFF in the text. Restore "UTF-8-SIG"
    # only when the input actually begins with a UTF-8 BOM; non-BOM UTF-8 stays
    # "UTF-8".
    if encoding == "UTF-8" and leading_bytes[:3] == _UTF8_BOM:
        return "UTF-8-SIG"

    return encoding


def detect(msg: bytes) -> DetectionResult:
    """Detect the character encoding of ``msg``.

    Args:
        msg: the raw bytes to inspect. Must be ``bytes`` -- the extension
            rejects ``str``, ``bytearray`` and ``memoryview``.
    Returns:
        A :class:`DetectionResult`. Both members are ``None`` when nothing
        could be detected.
    """
    raw_encoding, confidence = _cchardet.detect_with_confidence(msg)
    encoding = raw_encoding.decode() if raw_encoding is not None else None

    # detect_with_confidence above rejects anything that is not bytes, so the
    # old isinstance() guard on msg here could never take its fallback branch.
    encoding = _normalize_encoding(encoding, msg[:3])

    return {"encoding": encoding, "confidence": confidence}


class UniversalDetector(object):
    def __init__(self) -> None:
        self._detector = _cchardet.UniversalDetector()
        self._leading = b""

    def __enter__(self: _SelfT) -> _SelfT:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        # Literal[False] rather than bool: it tells the checker this context
        # manager never swallows an exception.
        self.close()
        return False

    def reset(self) -> None:
        self._detector.reset()
        self._leading = b""

    def feed(self, data: bytes) -> None:
        # Remember the first bytes so result can spot a UTF-8 BOM (uchardet only
        # exposes the label, not the raw bytes). The BOM is 3 bytes and is
        # virtually always delivered in the first chunk.
        if not self._leading and data:
            self._leading = bytes(data[:3])
        self._detector.feed(data)

    def close(self) -> None:
        self._detector.close()

    @property
    def done(self) -> bool:
        return self._detector.done

    @property
    def result(self) -> DetectionResult:
        raw_encoding, confidence = self._detector.result
        encoding = raw_encoding.decode() if raw_encoding is not None else None
        if encoding is not None:
            encoding = _normalize_encoding(encoding, self._leading)
        return {"encoding": encoding, "confidence": confidence}
