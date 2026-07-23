import codecs

from libc.stddef cimport size_t

cdef extern from *:
    ctypedef char* const_char_ptr "const char*"

# Upstream freedesktop uchardet (>= 0.1.0) multi-candidate API. uchardet returns
# an ordered list of candidate encodings; we take the first (best) one.
cdef extern from "uchardet.h":
    ctypedef void* uchardet_t
    cdef uchardet_t uchardet_new()
    cdef void uchardet_delete(uchardet_t ud)
    cdef int uchardet_handle_data(uchardet_t ud, const_char_ptr data, size_t length)
    cdef void uchardet_data_end(uchardet_t ud)
    cdef void uchardet_reset(uchardet_t ud)
    cdef size_t uchardet_get_n_candidates(uchardet_t ud)
    cdef const_char_ptr uchardet_get_encoding(uchardet_t ud, size_t candidate)
    cdef float uchardet_get_confidence(uchardet_t ud, size_t candidate)


DEF UCHARDET_SAFE_CHUNK_SIZE = 1024


cdef int handle_data_chunked(uchardet_t ud, const_char_ptr data, size_t length):
    """Keep freedesktop uchardet's internal code-point buffer in bounds."""
    cdef size_t offset = 0
    cdef size_t chunk_length
    cdef int result

    while offset < length:
        chunk_length = length - offset
        if chunk_length > UCHARDET_SAFE_CHUNK_SIZE:
            chunk_length = UCHARDET_SAFE_CHUNK_SIZE
        result = uchardet_handle_data(ud, data + offset, chunk_length)
        if result != 0:
            return result
        offset += chunk_length

    return 0


# uchardet's multibyte probers. Without uchardet's language pass to multiply
# their confidence down, a weak one (e.g. Big5 at ~0.4 on a near-ASCII
# Windows-1252 file, issue #33) can win; require strong standalone evidence.
DEF MULTIBYTE_FLOOR = 0.5
_MULTIBYTE_STRICT = frozenset(
    (b"SHIFT_JIS", b"SJIS", b"EUC-JP", b"GB18030", b"GBK",
     b"EUC-KR", b"UHC", b"BIG5", b"EUC-TW", b"JOHAB")
)


cdef _select_candidate(uchardet_t ud, bint reject_utf8):
    """Return (charset, confidence) for the best candidate.

    This reproduces, from the public candidate list, what cChardet's C++ overlay
    did inside the engine:

    * When reject_utf8 is set -- the payload is known not to be valid UTF-8 --
      skip UTF-8 candidates. uchardet's UTF-8 prober does not reject invalid
      byte sequences itself and clears the candidate threshold on its confidence
      floor, so it otherwise mislabels single-byte non-UTF-8 text (ISO-8859-15)
      as UTF-8.
    * Skip a multibyte candidate below MULTIBYTE_FLOOR so a weak false positive
      (Big5 on near-ASCII text, issue #33) cannot win.

    If nothing clears the bars, fall back to the UTF-8 candidate as a penalized
    last resort -- never a weak multibyte -- matching the overlay.
    """
    cdef size_t n = uchardet_get_n_candidates(ud)
    cdef size_t i
    cdef bytes name
    cdef bytes upper
    cdef float conf
    cdef bytes top_name = b""
    cdef float top_conf = 0.0
    cdef bytes utf8_name = b""
    cdef float utf8_conf = 0.0

    for i in range(n):
        name = uchardet_get_encoding(ud, i)
        conf = uchardet_get_confidence(ud, i)
        upper = name.upper()
        if i == 0:
            top_name = name
            top_conf = conf
        if upper == b"UTF-8" or upper == b"UTF8":
            if not utf8_name:
                utf8_name = name
                utf8_conf = conf
            if reject_utf8:
                continue
            return name, conf
        if upper in _MULTIBYTE_STRICT and conf < MULTIBYTE_FLOOR:
            continue
        return name, conf

    if utf8_name:
        return utf8_name, utf8_conf
    return top_name, top_conf


def detect_with_confidence(bytes msg):
    cdef size_t length = len(msg)
    cdef const_char_ptr data = msg

    # Encoding-only callers do not need freedesktop uchardet's expensive
    # language-model pass when the entire payload is already valid UTF-8.
    # Keep ASCII on the normal path so its established label is preserved.
    if not msg.isascii():
        try:
            msg.decode("utf-8")
        except UnicodeDecodeError:
            pass
        else:
            return b"UTF-8", 0.99

    cdef uchardet_t ud = uchardet_new()

    cdef int result = handle_data_chunked(ud, data, length)
    if result != 0:
        uchardet_delete(ud)
        raise Exception("Handle data error")

    uchardet_data_end(ud)

    # Non-ASCII input that reached here failed the UTF-8 fast path above, so it
    # is not valid UTF-8; reject any UTF-8 candidate. ASCII input is valid
    # UTF-8, so leave it alone.
    detected = _select_candidate(ud, not msg.isascii())
    uchardet_delete(ud)

    if detected[0]:
        return detected[0], detected[1]

    return None, None


cdef class UniversalDetector:
    cdef uchardet_t _ud
    cdef int _done
    cdef int _finalized
    cdef int _closed
    cdef int _nonascii
    cdef int _utf8_invalid
    cdef object _utf8_decoder
    cdef bytes _detected_charset
    cdef float _detected_confidence

    def __init__(self):
        self._ud = uchardet_new()
        self._done = 0
        self._finalized = 0
        self._closed = 0
        self._reset_utf8_state()
        self._detected_charset = b""
        self._detected_confidence = 0.0

    cdef void _reset_utf8_state(self):
        # Track UTF-8 validity incrementally across feed() so the finalize step
        # can reject a UTF-8 mislabel the same way detect_with_confidence does.
        self._nonascii = 0
        self._utf8_invalid = 0
        self._utf8_decoder = codecs.getincrementaldecoder("utf-8")()

    def reset(self):
        if not self._closed:
            self._done = 0
            self._finalized = 0
            self._reset_utf8_state()
            self._detected_charset = b""
            self._detected_confidence = 0.0
            uchardet_reset(self._ud)

    def feed(self, bytes msg):
        cdef size_t length
        cdef const_char_ptr data
        cdef int result

        if self._closed or self._finalized:
            return

        length = len(msg)
        if length > 0:
            if not msg.isascii():
                self._nonascii = 1
            if not self._utf8_invalid:
                try:
                    self._utf8_decoder.decode(msg)
                except UnicodeDecodeError:
                    self._utf8_invalid = 1
            data = msg
            result = handle_data_chunked(self._ud, data, length)

            if result != 0:
                self._closed = 1
                uchardet_delete(self._ud)
                raise Exception("Handle data error")
    cdef void _finalize(self):
        # freedesktop uchardet only publishes candidates from DataEnd(); before
        # that uchardet_get_n_candidates() is 0. For multi-byte encodings (UHC,
        # Shift_JIS, Big5, ...) detection never resolves mid-stream, so this is
        # the only point at which a result exists. Idempotent -- safe to call
        # from both result and close(). See issue #35.
        if not self._finalized:
            # A truncated trailing multibyte sequence also means the stream is
            # not valid UTF-8.
            if not self._utf8_invalid:
                try:
                    self._utf8_decoder.decode(b"", True)
                except UnicodeDecodeError:
                    self._utf8_invalid = 1
            uchardet_data_end(self._ud)
            self._read_candidate()
            self._finalized = 1
            self._done = 1

    def close(self):
        if not self._closed:
            self._finalize()
            uchardet_delete(self._ud)
            self._closed = 1

    cdef void _read_candidate(self):
        detected = _select_candidate(
            self._ud, self._nonascii and self._utf8_invalid)
        self._detected_charset = detected[0]
        self._detected_confidence = detected[1]

    @property
    def done(self):
        return bool(self._done)

    @property
    def result(self):
        # Finalize on read so callers get the detected charset even when they
        # stop feeding without an explicit close() -- uchardet only decides at
        # DataEnd(), and for multi-byte encodings `done` never flips mid-stream.
        # This matches chardet's UniversalDetector, whose result is populated
        # once detection stops. See issue #35.
        if not self._finalized and not self._closed:
            self._finalize()

        if len(self._detected_charset):
            return self._detected_charset, self._detected_confidence
        else:
            return None, None
