"""Lifecycle of the C ``uchardet_t`` handle owned by ``UniversalDetector``.

The handle is a raw C++ allocation (``uchardet_new()`` -> ``new
nsUniversalDetector``). Python's garbage collector, ``sys.getrefcount()`` and
``tracemalloc`` are all blind to it -- they only see the ``PyObject`` wrapper,
which was never the thing that leaked. So the invariants are asserted two ways:

1. Deterministic behavioural tests, which are the CI gate. They cannot flake:
   losing a ``_ud = NULL`` assignment turns ``close()`` + drop into a double
   free, i.e. a SIGSEGV inside ``uchardet_delete``, not a soft assertion.
2. Resident-set-size tests, run in a subprocess so the measurement is isolated,
   with thresholds far below the unpatched signal (~19 KB per detector).

The out-of-memory paths need the failure to be injected, and the two levers are
not interchangeable. Capping ``RLIMIT_AS`` and exhausting the address space is
what makes the *C++* ``new`` inside uchardet fail; it cannot be aimed at the
Python allocator, and it is too coarse to fail a small allocation on demand,
because the heap free list keeps serving those. ``_testcapi.set_nomemory()``
is the opposite: it fails ``PyMem_*``/``PyObject_*`` precisely and on demand,
and leaves C++ ``new`` alone. So each test uses the one that reaches its bug.
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


def _require_nomemory_hook():
    """``_testcapi.set_nomemory()`` makes the *Python* allocator fail on demand.

    That is the lever for the two tests below: they need finalization to raise
    part-way through ``close()``. Real memory pressure cannot do it -- the C++
    allocations inside ``uchardet_data_end()`` are small and get served from the
    heap free list long after the address space is exhausted (measured). The
    hook is precise instead, and it only touches ``PyMem_*``/``PyObject_*``, so
    ``uchardet_data_end()`` still succeeds and the failure lands exactly where
    the bug lives: the ``PyBytes_FromString`` in ``_read_candidate()``.

    It is a CPython-internal test module -- absent on PyPy, and strippable.
    """
    testcapi = pytest.importorskip(
        "_testcapi", reason="needs CPython's allocator-failure injection"
    )
    if not hasattr(testcapi, "set_nomemory"):
        pytest.skip("this build's _testcapi has no set_nomemory()")


# Installing the allocator hook is process-global and leaves the interpreter in
# a delicate state, so both tests run it in a subprocess rather than risk
# poisoning the rest of the session.
_FAILING_CLOSE_PREAMBLE = """
import _testcapi
from cchardet import _cchardet

SAMPLE = "한국어 감사합니다 안녕하세요".encode("euc-kr")

def failing_close(detector):
    "close() a detector with every Python allocation failing."
    try:
        _testcapi.set_nomemory(0)
        detector.close()
    except MemoryError:
        return "MemoryError"
    except BaseException as exc:
        return type(exc).__name__
    else:
        return "no-error"
    finally:
        _testcapi.remove_mem_hooks()
"""


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


# RLIMIT_AS is the lever that makes this deterministic, and it only means what
# we need it to mean on Linux. The bug is platform-independent, so testing it
# on one platform is enough.
@pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="RLIMIT_AS pressure is Linux-specific"
)
def test_allocation_failure_raises_instead_of_aborting(tmp_path):
    """An out-of-memory uchardet must raise ``MemoryError``, not kill the process.

    uchardet allocates with plain ``new``, so allocation failure throws
    ``std::bad_alloc``; its own ``if (nsnull == ...) return
    NS_ERROR_OUT_OF_MEMORY`` checks are dead code. Without ``except +`` on the
    allocating entry points that exception unwinds out of the extension into
    CPython's C frames, which is undefined behaviour -- and observably
    ``std::terminate()``: on an unpatched build this program dies with SIGABRT
    and ``terminate called after throwing an instance of 'std::bad_alloc'``,
    reproducibly, where the patched build reports ``MemoryError``.

    Run in a subprocess because it deliberately exhausts the address space.

    Deliberately biased towards skipping. Squeezing a process this hard makes
    it fragile in ways that have nothing to do with uchardet -- a runner can
    die in the dynamic loader ("cannot allocate memory for thread-local data")
    before the experiment even finishes. So the verdict is written to a file
    the instant it is known, rather than printed at the end where any later
    death would erase it, and only the specific ``std::bad_alloc`` signature is
    treated as failure. Anything else means the experiment did not run, not
    that the code is broken.
    """
    verdict = tmp_path / "verdict"
    verdict.touch()

    program = textwrap.dedent(
        """
        import os, sys, mmap, resource
        from cchardet import _cchardet

        SAMPLE = "한국어 감사합니다".encode("euc-kr")

        # Everything the post-squeeze section needs, prepared while allocation
        # still works: the open fd, the message bytes, and every code path.
        fd = os.open(sys.argv[1], os.O_WRONLY)
        VERDICT = b"MemoryError"
        d = _cchardet.UniversalDetector(); d.feed(SAMPLE); _ = d.result
        del d

        _soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        with open("/proc/self/statm") as fh:
            usage = int(fh.read().split()[0]) * 4096
        resource.setrlimit(resource.RLIMIT_AS, (usage + (8 << 20), hard))

        # Consume the remaining address space down to page granularity. mmap is
        # a direct syscall, so this is exact and does not disturb pymalloc.
        blocks = []
        size = 1 << 20
        while size >= 4096:
            try:
                blocks.append(mmap.mmap(-1, size))
            except (OSError, MemoryError, ValueError):
                size >>= 1

        # Hold every detector, so the C++ heap free list drains and uchardet's
        # `new` has to go to the OS -- otherwise it just recycles the warm-up
        # allocation and never fails.
        held = []
        try:
            for _ in range(100000):
                d = _cchardet.UniversalDetector()
                d.feed(SAMPLE)
                held.append(d)
        except MemoryError:
            # Record it here, still under pressure, using only objects that
            # already exist. Cleanup and interpreter shutdown come next and can
            # themselves die on a starved runner; the answer is already on disk.
            os.write(fd, VERDICT)

        resource.setrlimit(resource.RLIMIT_AS, (_soft, hard))
        for b in blocks:
            b.close()
        del held
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", program, str(verdict)],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )

    # The one true failure signature: the C++ exception reached CPython's C
    # frames and std::terminate ran.
    escaped = "std::bad_alloc" in completed.stderr or "terminate called" in completed.stderr
    assert not escaped, (
        f"std::bad_alloc escaped into CPython's C frames instead of being "
        f"translated (rc={completed.returncode}):\n{completed.stderr}"
    )

    if verdict.read_bytes() != b"MemoryError":
        pytest.skip(
            f"allocation pressure did not reach uchardet on this runner "
            f"(rc={completed.returncode}): {completed.stderr.strip()[:200]}"
        )


def test_close_still_releases_the_handle_when_finalizing_raises():
    """``close()`` must release the handle even if it cannot build the result.

    ``close()`` calls ``_finalize()`` first, and ``_finalize()`` can raise:
    ``_read_candidate()`` assigns ``uchardet_get_encoding()`` to a ``bytes``,
    which is a ``PyBytes_FromString``. Being ``cdef void`` does not make that
    safe -- since Cython 3 a void ``cdef`` function propagates exceptions via a
    ``PyErr_Occurred()`` check at the call site, so without a ``finally`` the
    generated code jumps straight past ``uchardet_delete()`` *and* past
    ``self._closed = 1``.

    The detector is then left wide open: not closed, handle still held. That is
    observable, and it is what this test pins. On a build without the
    ``finally`` the failed ``close()`` is simply undone -- reading ``result``
    afterwards silently re-finalizes the stream and hands back ``UHC`` -- where
    the fixed build reports a closed detector.
    """
    _require_nomemory_hook()

    program = _FAILING_CLOSE_PREAMBLE + textwrap.dedent(
        """
        # The same stream, closed normally: proves the sample still detects, so
        # a `None` from the victim below means "released", not "never worked".
        reference = _cchardet.UniversalDetector()
        reference.feed(SAMPLE)
        reference.close()
        print("reference", reference.result[0] is not None, flush=True)

        victim = _cchardet.UniversalDetector()
        victim.feed(SAMPLE)
        print("raised", failing_close(victim), flush=True)

        # A detector whose close() released the handle has nothing left to
        # finalize, so result stays empty. One that did not re-finalizes here
        # and answers as if close() had never been called.
        print("after", "closed" if victim.result[0] is None else "open", flush=True)

        victim.close()   # still idempotent
        del victim       # and not a double free
        print("survived", flush=True)
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert completed.returncode == 0, (
        f"subprocess died (rc={completed.returncode}):\n{completed.stderr}"
    )

    reported = dict(
        line.split(" ", 1) for line in completed.stdout.strip().splitlines() if " " in line
    )
    assert reported.get("reference") == "True", "the sample stopped detecting"
    assert reported.get("raised") == "MemoryError", (
        f"close() did not raise from finalization: {reported}\n{completed.stderr}"
    )
    assert reported.get("after") == "closed", (
        "close() raised and left the detector open -- the handle was not "
        "released; it needs to be freed in a finally"
    )
    assert "survived" in completed.stdout


@pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="ru_maxrss units are platform-specific"
)
def test_failed_close_does_not_leak_the_handle():
    """The direct measurement behind the test above: the handle is really gone.

    ``result`` reporting "closed" is a proxy -- it shows ``_closed`` was set,
    not that ``uchardet_delete()`` ran. So hold every detector whose ``close()``
    raised: nothing is dropped, ``__dealloc__`` never runs, and the only thing
    that can have released a handle is ``close()`` itself. Without the
    ``finally`` this leaks the full ~19 KB per detector, the same signature as
    the missing ``__dealloc__``.
    """
    _require_nomemory_hook()

    program = _FAILING_CLOSE_PREAMBLE + textwrap.dedent(
        """
        import resource

        N = 3000

        def rss_kb():
            return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

        held = []   # nothing is ever dropped, so __dealloc__ cannot help

        def closed_detector():
            detector = _cchardet.UniversalDetector()
            detector.feed(SAMPLE)
            failing_close(detector)
            held.append(detector)

        for _ in range(200):     # settle the allocator first
            closed_detector()

        before = rss_kb()
        for _ in range(N):
            closed_detector()
        print(len(held), (rss_kb() - before) * 1024 // N, flush=True)
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    held, per_detector = (int(field) for field in completed.stdout.split())

    assert held == 3200, "detectors were dropped; __dealloc__ could mask the leak"
    # Measured: ~87 B/detector (just the PyObject wrappers) with the finally,
    # ~19,500 B/detector without it. The threshold sits between the two, orders
    # of magnitude clear of both.
    assert per_detector < 1000, (
        f"a close() that raised leaked {per_detector} B/detector; the handle "
        f"is not being released in a finally"
    )
