# cython: freethreading_compatible = True
cimport cython

from libc.stddef cimport size_t

cdef extern from *:
    ctypedef char* const_char_ptr "const char*"

# Upstream freedesktop uchardet (>= 0.1.0) multi-candidate API. uchardet returns
# an ordered list of candidate encodings; we take the first (best) one.
#
# Every entry point that allocates is declared `except +`. uchardet is C++ and
# allocates with plain `new` -- uchardet_new() is `new HandleUniversalDetector`,
# HandleData() news the group probers, Reset() news nsMBCSGroupProber's
# code-point buffers, DataEnd() reports candidates into a std::vector. On a
# conforming compiler those throw std::bad_alloc rather than returning NULL, so
# uchardet's own `if (nsnull == ...) return NS_ERROR_OUT_OF_MEMORY` checks are
# dead code. This module is built as C++ (cython_language=cpp), but the frames
# above it are CPython's C ones: letting the exception unwind through them is
# undefined behaviour, in practice std::terminate(). `except +` makes Cython
# wrap the call and translate std::bad_alloc into MemoryError instead. The NULL
# checks below are kept as well -- they cost nothing and still cover any
# implementation that does return NULL, including a system libuchardet built
# with -fno-exceptions.
#
# uchardet_delete() is deliberately left alone: it runs the destructor, which
# is implicitly noexcept, and it is called from __dealloc__ where an exception
# could not be propagated anyway. The getters only index a std::vector.
cdef extern from "uchardet.h":
    ctypedef void* uchardet_t
    cdef uchardet_t uchardet_new() except +
    cdef void uchardet_delete(uchardet_t ud)
    cdef int uchardet_handle_data(uchardet_t ud, const_char_ptr data, size_t length) except +
    cdef void uchardet_data_end(uchardet_t ud) except +
    cdef void uchardet_reset(uchardet_t ud) except +
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
    cdef uchardet_t ud
    cdef int result
    cdef bytes detected_charset = b""
    cdef float detected_confidence = 0.0

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

    ud = uchardet_new()
    if ud == NULL:
        raise MemoryError("uchardet_new() failed")

    # try/finally rather than a uchardet_delete() before each exit: assigning
    # uchardet_get_encoding() to a `bytes` is a PyBytes_FromString, which can
    # raise MemoryError and jump straight to Cython's error label. That skipped
    # the delete underneath it and leaked the detector.
    try:
        result = handle_data_chunked(ud, data, length)
        if result != 0:
            raise Exception("Handle data error")

        uchardet_data_end(ud)

        if uchardet_get_n_candidates(ud) > 0:
            detected_charset = uchardet_get_encoding(ud, 0)
            detected_confidence = uchardet_get_confidence(ud, 0)
    finally:
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

    # Handle lifecycle: `_ud` is non-NULL for exactly as long as the handle is
    # owned, and NULL once released. Every uchardet_* call site below is
    # guarded on that, so operating on a released detector is a silent no-op
    # rather than an error -- close() has to stay idempotent, and feed()/reset()
    # were already no-ops once _closed was set, so raising would be a behaviour
    # change. A NULL in _finalize()/_read_candidate() degrades to "no
    # candidates". Note that being `cdef void` does not make those two
    # noexcept: since Cython 3 they propagate exceptions like any other cdef
    # function, via a PyErr_Occurred() check at the call site. close() relies
    # on that being true (see the try/finally there).
    def __cinit__(self):
        # Allocation lives here rather than in __init__ because __cinit__ runs
        # exactly once, before the object is reachable from Python, and cannot
        # be re-entered. Allocating in __init__ meant a second __init__() call
        # overwrote the live handle and leaked it. It also left _ud NULL for an
        # object built via __new__ or by a subclass that skips
        # super().__init__(), so the first feed() dereferenced NULL.
        self._ud = uchardet_new()
        if self._ud == NULL:
            raise MemoryError("uchardet_new() failed")
        self._done = 0
        self._finalized = 0
        self._closed = 0
        self._detected_charset = b""
        self._detected_confidence = 0.0

    @cython.critical_section
    def __init__(self):
        # Re-initialising in place has to start a genuinely fresh stream:
        # `d.__init__()` used to install a brand new handle, and callers who
        # rely on that must keep getting a clean detector rather than one that
        # silently concatenates the next feed() onto the previous stream.
        # Allocation still cannot leak -- the live handle is reset, and only a
        # released one is replaced.
        if self._ud == NULL:
            self._ud = uchardet_new()
            if self._ud == NULL:
                raise MemoryError("uchardet_new() failed")
        else:
            uchardet_reset(self._ud)
        self._done = 0
        self._finalized = 0
        self._closed = 0
        self._detected_charset = b""
        self._detected_confidence = 0.0

    def __dealloc__(self):
        # Deliberately not decorated with @cython.critical_section: the object
        # is being destroyed and is no longer reachable, so there is nothing to
        # serialise against, and taking a lock on a dying object is unsound.
        if self._ud != NULL:
            uchardet_delete(self._ud)
            self._ud = NULL

    @cython.critical_section
    def reset(self):
        if not self._closed and self._ud != NULL:
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

        if self._closed or self._finalized or self._ud == NULL:
            return

        length = len(msg)
        if length > 0:
            data = msg
            result = handle_data_chunked(self._ud, data, length)

            if result != 0:
                self._closed = 1
                uchardet_delete(self._ud)
                self._ud = NULL
                raise Exception("Handle data error")
    cdef void _finalize(self):
        # freedesktop uchardet only publishes candidates from DataEnd(); before
        # that uchardet_get_n_candidates() is 0. For multi-byte encodings (UHC,
        # Shift_JIS, Big5, ...) detection never resolves mid-stream, so this is
        # the only point at which a result exists. Idempotent -- safe to call
        # from both result and close(). See issue #35.
        if not self._finalized:
            if self._ud != NULL:
                uchardet_data_end(self._ud)
            self._read_candidate()
            self._finalized = 1
            self._done = 1

    @cython.critical_section
    def close(self):
        if not self._closed:
            # try/finally for exactly the reason detect_with_confidence() uses
            # one. _finalize() can raise: uchardet_data_end() is `except +`, and
            # _read_candidate() assigns uchardet_get_encoding() to a `bytes`,
            # which is a PyBytes_FromString that can raise MemoryError. Being
            # `cdef void` does not swallow that -- Cython 3 propagates out of a
            # void cdef function via a PyErr_Occurred() check at the call site,
            # so the generated code jumped straight past the uchardet_delete()
            # below. An explicit close() could then return having released
            # nothing, with _closed still unset. Releasing the handle is the one
            # thing close() must do even when it cannot build a result.
            try:
                self._finalize()
            finally:
                if self._ud != NULL:
                    # Clearing _ud is inseparable from having a __dealloc__:
                    # tp_dealloc still runs for this object afterwards, so
                    # without it every explicitly closed detector is a double
                    # free.
                    uchardet_delete(self._ud)
                    self._ud = NULL
                self._closed = 1

    cdef void _read_candidate(self):
        if self._ud != NULL and uchardet_get_n_candidates(self._ud) > 0:
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
