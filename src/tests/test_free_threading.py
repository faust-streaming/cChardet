"""Free-threaded (no-GIL) CPython support -- see issue #55.

The `_cchardet` extension declares `# cython: freethreading_compatible = True`,
which makes CPython leave the GIL disabled on a free-threaded build instead of
re-enabling it process-wide at import.

That declaration is an unchecked assertion: Cython emits a single `Py_mod_gil`
slot and no locking of its own, and it is ignored outright by Cython < 3.1.
Neither a missing directive nor a misspelled one fails the build -- both
compile at exit 0 with no diagnostic -- so the only reliable guard is the
runtime assertion below.
"""

import contextlib
import glob
import os
import sys
import sysconfig
import threading

import pytest

import cchardet

# Note: do NOT run these under PYTHON_GIL=0 / -Xgil=0. Those force the GIL off
# regardless of what the module declares, which would make a regressed build
# indistinguishable from a correct one.
FREE_THREADED = bool(sysconfig.get_config_var("Py_GIL_DISABLED"))

_TESTDATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testdata")


def _corpus():
    """The detection corpus, as bytes. Independent of the current directory."""
    blobs = []
    for path in sorted(glob.glob(os.path.join(_TESTDATA, "*", "*.txt"))):
        with open(path, "rb") as f:
            blobs.append(f.read())
    assert blobs, "testdata corpus is empty"
    return blobs


@pytest.mark.skipif(
    not FREE_THREADED, reason="requires a free-threaded (GIL-disabled) build"
)
def test_extension_does_not_re_enable_the_gil():
    # cchardet is imported at module scope, so by the time this body runs the
    # GIL would already be permanently back on if _cchardet were missing the
    # freethreading_compatible directive (or had been built with Cython < 3.1,
    # which ignores it silently).
    assert sys._is_gil_enabled() is False


def test_detect_is_safe_from_many_threads():
    """detect() allocates and frees its own detector per call, so concurrent
    callers must not interfere with each other."""
    corpus = _corpus()
    baseline = [cchardet.detect(blob)["encoding"] for blob in corpus]

    n = 8
    barrier = threading.Barrier(n)
    results = {}
    errors = []

    def worker(k):
        try:
            barrier.wait()
            results[k] = [cchardet.detect(blob)["encoding"] for blob in corpus]
        except BaseException as exc:  # noqa: BLE001 - reported via `errors`
            errors.append(repr(exc))

    threads = [threading.Thread(target=worker, args=(k,)) for k in range(n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, errors
    assert len(results) == n
    for k, got in results.items():
        assert got == baseline, f"thread {k} diverged from the serial baseline"


def test_each_thread_gets_its_own_detector():
    """The supported streaming pattern: one UniversalDetector per thread."""
    samples = _corpus()[:8]
    baseline = {}
    for i, blob in enumerate(samples):
        with cchardet.UniversalDetector() as detector:
            detector.feed(blob)
            baseline[i] = detector.result["encoding"]

    barrier = threading.Barrier(len(samples))
    results = {}
    errors = []

    def worker(i, blob):
        try:
            barrier.wait()
            with cchardet.UniversalDetector() as detector:
                detector.feed(blob)
                results[i] = detector.result["encoding"]
        except BaseException as exc:  # noqa: BLE001 - reported via `errors`
            errors.append(repr(exc))

    threads = [
        threading.Thread(target=worker, args=(i, blob))
        for i, blob in enumerate(samples)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, errors
    assert results == baseline


def test_sharing_one_detector_across_threads_does_not_crash():
    """Sharing an instance is a caller error that produces meaningless results,
    but it must not be able to corrupt the heap.

    Without the critical sections on UniversalDetector, this reliably segfaults
    on a free-threaded build: close() is a check-then-act on `_closed`, `_ud` is
    not cleared after uchardet_delete(), and `result` finalizes as a side
    effect -- so two threads can reach uchardet_delete() for the same handle.

    The failure is a hard crash (SIGSEGV, or glibc "double free or corruption"),
    so this takes the whole pytest process down rather than reporting a failed
    assertion. It is also probabilistic: 400 rounds detected an unlocked build
    8/8 on cp313t while costing ~0.7s, where 50 rounds caught it only 1/3.
    Lower the count and this stops being a useful guard.
    """
    data = ("こんにちは世界" * 40).encode("utf-8")

    for _ in range(400):
        detector = cchardet.UniversalDetector()
        barrier = threading.Barrier(6)

        # detector/barrier are bound as defaults so each round's threads close
        # over that round's objects rather than the loop variable.
        def worker(k, detector=detector, barrier=barrier):
            barrier.wait()
            for _ in range(30):
                # Racing callers may legitimately observe a closed detector and
                # raise; only memory safety is under test here.
                with contextlib.suppress(Exception):
                    if k % 3 == 0:
                        detector.feed(data)
                    elif k % 3 == 1:
                        _ = detector.result
                    else:
                        detector.close()

        threads = [threading.Thread(target=worker, args=(k,)) for k in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
