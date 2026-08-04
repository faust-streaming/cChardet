# cython: freethreading_compatible = True
cimport cython

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

    cdef bytes detected_charset = b""
    cdef float detected_confidence = 0.0
    if uchardet_get_n_candidates(ud) > 0:
        detected_charset = uchardet_get_encoding(ud, 0)
        detected_confidence = uchardet_get_confidence(ud, 0)
    uchardet_delete(ud)

    if detected_charset:
        return detected_charset, detected_confidence

    return None, None


cdef class UniversalDetector:
    # Every method that touches the instance state is wrapped in a per-instance
    # critical section. On a free-threaded build the module no longer runs under
    # the GIL (see the freethreading_compatible directive at the top), so the
    # check-then-act in close() -- and in the result property, which finalizes
    # as a side effect -- would otherwise let two threads reach
    # uchardet_delete(self._ud) for the same handle and corrupt the heap.
    # Sharing one detector across threads is still a caller error that yields
    # meaningless results (see the README), but it must not be able to segfault
    # the interpreter. This costs nothing on ordinary GIL builds: Cython
    # compiles __Pyx_PyCriticalSection_Begin down to `(void)(cs)` unless
    # CYTHON_COMPILING_IN_CPYTHON_FREETHREADING is set.
    cdef uchardet_t _ud
    cdef int _done
    cdef int _finalized
    cdef int _closed
    cdef bytes _detected_charset
    cdef float _detected_confidence

    def __init__(self):
        self._ud = uchardet_new()
        self._done = 0
        self._finalized = 0
        self._closed = 0
        self._detected_charset = b""
        self._detected_confidence = 0.0

    @cython.critical_section
    def reset(self):
        if not self._closed:
            self._done = 0
            self._finalized = 0
            self._detected_charset = b""
            self._detected_confidence = 0.0
            uchardet_reset(self._ud)

    @cython.critical_section
    def feed(self, bytes msg):
        cdef size_t length
        cdef const_char_ptr data
        cdef int result

        if self._closed or self._finalized:
            return

        length = len(msg)
        if length > 0:
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
            uchardet_data_end(self._ud)
            self._read_candidate()
            self._finalized = 1
            self._done = 1

    @cython.critical_section
    def close(self):
        if not self._closed:
            self._finalize()
            uchardet_delete(self._ud)
            self._closed = 1

    cdef void _read_candidate(self):
        if uchardet_get_n_candidates(self._ud) > 0:
            self._detected_charset = uchardet_get_encoding(self._ud, 0)
            self._detected_confidence = uchardet_get_confidence(self._ud, 0)
        else:
            self._detected_charset = b""
            self._detected_confidence = 0.0

    @property
    @cython.critical_section
    def done(self):
        return bool(self._done)

    @property
    @cython.critical_section
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
