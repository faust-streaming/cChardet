"""Lifecycle of the C ``uchardet_t`` handle owned by ``UniversalDetector``.

The handle is a raw C++ allocation (``uchardet_new()`` -> ``new
nsUniversalDetector``). Python's garbage collector, ``sys.getrefcount()`` and
``tracemalloc`` are all blind to it -- they only see the ``PyObject`` wrapper,
which was never the thing that leaked. So the invariants are asserted two ways:

1. Deterministic behavioural tests, which are the CI gate. They cannot flake:
   losing a ``_ud = NULL`` assignment turns ``close()`` + drop into a double
   free, i.e. a SIGSEGV inside ``uchardet_delete``, not a soft assertion.
2. One resident-set-size test, run in a subprocess so the measurement is
   isolated, with a threshold far below the unpatched signal (~19 KB per
   detector).
"""

import gc
import os
import subprocess
import sys
import textwrap

import pytest

import cchardet
from cchardet import _cchardet

# Not ASCII and not valid UTF-8, so it takes the full uchardet path -- the
# module short-circuits pure UTF-8 input before allocating a detector.
SAMPLE = "한국어 감사합니다 안녕하세요".encode("euc-kr")
OTHER = "Привет мир как дела сегодня хорошо".encode("cp1251")


def test_close_then_drop_does_not_double_free():
    """``close()`` releases the handle; ``__dealloc__`` must not release it again.

    ``close()`` has to clear ``_ud`` after ``uchardet_delete()``, because
    ``tp_dealloc`` still runs for the same object afterwards. Adding
    ``__dealloc__`` without that assignment makes every explicitly closed
    detector a double free -- verified to segfault, not merely to warn.
    """
    for _ in range(100):
        detector = _cchardet.UniversalDetector()
        detector.feed(SAMPLE)
        detector.close()
        del detector
    gc.collect()


def test_close_is_idempotent():
    detector = _cchardet.UniversalDetector()
    detector.feed(SAMPLE)
    detector.close()
    detector.close()
    detector.close()


def test_methods_after_close_are_silent_no_ops():
    """Once the handle is released, every uchardet_* call site is skipped.

    ``reset()`` and ``feed()`` were already no-ops on a closed detector, so the
    NULL guards preserve that contract rather than starting to raise.
    """
    detector = _cchardet.UniversalDetector()
    detector.feed(SAMPLE)
    detector.close()
    closed_result = detector.result

    detector.reset()
    detector.feed(SAMPLE)

    assert detector.result == closed_result
    assert detector.done is True


def test_result_without_close_still_releases_the_handle():
    """The ``result`` property finalizes as a side effect precisely so callers
    can stop without closing -- which is what made the missing ``__dealloc__``
    so easy to hit."""
    detector = _cchardet.UniversalDetector()
    detector.feed(SAMPLE)
    encoding, confidence = detector.result
    assert encoding is not None and confidence > 0
    del detector
    gc.collect()


def test_drop_without_feeding_or_closing():
    for _ in range(100):
        _cchardet.UniversalDetector()
    gc.collect()


def test_reinit_starts_a_fresh_stream():
    """``d.__init__()`` must reset the stream, not concatenate onto it.

    Allocation lives in ``__cinit__`` so a repeat ``__init__()`` cannot leak
    the live handle -- but ``__init__`` still has to reset that handle.  A
    version that simply did nothing silently fed the next payload into the
    previous stream and reported a bogus mixed-encoding answer.
    """
    baseline = _cchardet.UniversalDetector()
    baseline.feed(OTHER)
    expected = baseline.result

    detector = _cchardet.UniversalDetector()
    detector.feed(SAMPLE)
    detector.__init__()
    assert detector.done is False
    detector.feed(OTHER)
    assert detector.result == expected

    # Same again, but after the first stream was finalized by reading result.
    detector = _cchardet.UniversalDetector()
    detector.feed(SAMPLE)
    _ = detector.result
    detector.__init__()
    detector.feed(OTHER)
    assert detector.result == expected


def test_reinit_after_close_revives_the_detector():
    """A closed detector gets a brand new handle, matching the behaviour from
    when ``uchardet_new()`` lived in ``__init__``."""
    baseline = _cchardet.UniversalDetector()
    baseline.feed(OTHER)
    expected = baseline.result

    detector = _cchardet.UniversalDetector()
    detector.feed(SAMPLE)
    detector.close()

    detector.__init__()
    assert detector.done is False
    detector.feed(OTHER)
    assert detector.result == expected


def test_uninitialized_instance_does_not_crash():
    """``__cinit__`` runs for every construction path, so the handle exists even
    when ``__init__`` never runs. Allocating in ``__init__`` left ``_ud`` NULL
    here and the first ``feed()`` dereferenced it."""
    detector = _cchardet.UniversalDetector.__new__(_cchardet.UniversalDetector)
    detector.feed(SAMPLE)
    assert detector.result[0] is not None

    class Subclass(_cchardet.UniversalDetector):
        def __init__(self):  # deliberately does not call super().__init__()
            pass

    detector = Subclass()
    detector.feed(SAMPLE)
    assert detector.result[0] is not None


def test_constructor_still_rejects_arguments():
    """A no-argument ``__cinit__`` would silently swallow extra constructor
    arguments; the explicit ``__init__`` keeps this a TypeError."""
    with pytest.raises(TypeError):
        _cchardet.UniversalDetector(1)


def test_public_wrapper_context_manager_round_trip():
    with cchardet.UniversalDetector() as detector:
        detector.feed(SAMPLE)
        assert detector.result["encoding"] is not None


# ru_maxrss is KB on Linux but bytes on macOS, and Windows has no resource
# module at all. The leak is platform-independent, so measuring it on Linux is
# enough and avoids encoding the per-platform unit quirks into a CI gate.
@pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="ru_maxrss units are platform-specific"
)
def test_handle_is_not_leaked():
    """Dropping detectors without close() must not grow the heap.

    Before ``__dealloc__`` existed this leaked ~19 KB per detector, so 5000 of
    them cost ~95 MB. The threshold sits well below that signal and well above
    interpreter noise.
    """
    program = textwrap.dedent(
        """
        import resource
        from cchardet import _cchardet

        SAMPLE = "한국어 감사합니다 안녕하세요".encode("euc-kr")

        def rss_kb():
            return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

        for _ in range(200):          # settle the allocator first
            d = _cchardet.UniversalDetector(); d.feed(SAMPLE); _ = d.result

        before = rss_kb()
        for _ in range(5000):         # note: no close()
            d = _cchardet.UniversalDetector(); d.feed(SAMPLE); _ = d.result
        print(rss_kb() - before)
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    growth_kb = int(completed.stdout.strip())
    assert growth_kb < 20_000, f"RSS grew by {growth_kb} KB; the handle is leaking"
