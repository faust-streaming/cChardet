CHANGES
=======

3.2.0 (unreleased)
------------------

- declare the ``_cchardet`` extension free-threading compatible (`#55`_), so
  importing ``cchardet`` no longer re-enables the GIL process-wide on
  free-threaded CPython (3.13t / 3.14t). Building now requires Cython >= 3.1,
  which is checked at configure time; older Cython ignores the declaration
  silently. ``UniversalDetector`` instance methods additionally take a
  per-instance critical section, so sharing one detector across threads can no
  longer corrupt the heap on a free-threaded build (it still produces
  meaningless results). This is free on ordinary GIL builds.

  Note that the published 3.1.0 and 3.0.1 ``cp314t`` wheels predate this and
  do re-enable the GIL on import; 3.2.0 is the first release that carries the
  declaration.

- fix a memory leak in ``UniversalDetector``: the underlying ``uchardet_t``
  handle was only released by an explicit ``close()``, so every detector that
  was simply dropped -- the documented pattern, since reading ``result``
  finalizes detection on its own -- leaked roughly 19 KB. ``__dealloc__`` now
  releases it, and ``close()`` and ``feed()``'s error path clear the handle so
  it cannot be released twice. Allocation moved from ``__init__`` to
  ``__cinit__``, which also fixes a segfault when a detector was built without
  running ``__init__`` (via ``__new__``, or a subclass that does not call
  ``super().__init__()``); ``__init__`` still resets the stream, so calling it
  again on a live detector starts fresh as before. ``detect()`` no longer
  leaks its detector if building the result string raises, and a failed
  ``uchardet_new()`` now raises ``MemoryError`` instead of dereferencing NULL.

- document threading expectations for the Python API (`#55`_). ``detect()`` is
  safe to call concurrently from multiple threads, while a
  ``UniversalDetector`` instance holds the state of a single stream and must
  not be shared across threads without external synchronization -- use one
  detector per thread. See the README.

- ship type information (`#71`_). The package now carries a PEP 561 ``py.typed``
  marker, a ``_cchardet.pyi`` stub for the compiled extension, and annotations
  across the public API, so ``detect()`` and ``UniversalDetector.result`` type
  check as ``DetectionResult`` instead of ``Any`` downstream. Both members of
  that result are ``str | None`` / ``float | None``, which type checkers now
  require callers to handle. Also corrects ``detect()``'s docstring, which
  claimed it took ``str`` when it has always required ``bytes``.

.. _#55: https://github.com/faust-streaming/cChardet/issues/55
.. _#71: https://github.com/faust-streaming/cChardet/pull/71

3.1.0 (2026-08-04)
------------------

- add a ``system-uchardet`` Meson feature option, so distributions and source
  builds can link the system ``uchardet`` instead of the vendored copy
  (`#56`_ by `@mgorny`_, `#64`_). ``disabled`` (the default, and what the
  published wheels use) always builds the bundled copy, ``enabled`` requires
  the system library and fails if it is missing or too old, and ``auto``
  falls back to the bundled copy. The system library must be recent enough to
  expose ``uchardet_get_n_candidates``.

  Note that a system build currently detects non-UTF-8 input less accurately
  than the bundled one, because the encoding-only multibyte prober added in
  3.0.1 is part of the vendored copy. See the README for measurements and
  guidance for packagers.

.. _#56: https://github.com/faust-streaming/cChardet/pull/56
.. _#64: https://github.com/faust-streaming/cChardet/pull/64
.. _@mgorny: https://github.com/mgorny

3.0.1 (2026-08-04)
------------------

- fix the severe detection slowdown introduced in 3.0.0 (`#57`_). freedesktop
  uchardet 0.0.8 decodes every candidate to Unicode and fans the code points
  through its generic language models -- work cChardet never exposes, since it
  returns only encoding and confidence. Valid UTF-8 now short-circuits that
  path, and the vendored uchardet is built with an encoding-only multibyte
  group prober. Measured on the reporter's CC-News corpus: ~595 MB/s, against
  ~350 MB/s for 2.2.1 on the same runner.
- fix non-UTF-8 input being reported as UTF-8. Without uchardet's language
  pass, ``nsUTF8Prober`` never rejects invalid byte sequences on its own; the
  overlay validates the candidate instead. On the project's non-UTF-8
  benchmark corpus this drops the mislabel rate from 16.2% to 0%.
- fix heap corruption (``SIGABRT``, ``free(): invalid next size``) on long
  multibyte input by feeding uchardet in bounded chunks, keeping its internal
  1024-entry code-point buffer in range.
- add a benchmark CI job that compares each change against the two most recent
  releases and fails on a throughput regression or a UTF-8 mislabel rate above
  the configured ceiling.

  Known limitation: on genuinely non-UTF-8 input, throughput is still about
  0.6x of 2.2.1. The remaining cost is the single-byte prober's language
  models inside freedesktop uchardet, tracked upstream as `uchardet#38`_.

.. _#57: https://github.com/faust-streaming/cChardet/issues/57
.. _uchardet#38: https://gitlab.freedesktop.org/uchardet/uchardet/-/issues/38

3.0.0 (2026-07-20) -- yanked
----------------------------

Yanked from PyPI: this release is orders of magnitude slower than 2.2.1
(`#57`_), mislabels non-UTF-8 input as UTF-8, and can abort on long multibyte
input. Use 3.0.1 or later.

- switch to upstream freedesktop uchardet and its multi-candidate API (`#50`_)
- normalize the UTF-8 BOM label to ``UTF-8-SIG`` for downstream compatibility
- normalize the ``MAC-CENTRALEUROPE`` label to protect downstream
  ``open()`` / ``decode()``

.. _#50: https://github.com/faust-streaming/cChardet/pull/50

2.2.1 (2026-07-19)
------------------

- fix ``UniversalDetector.result`` returning nothing without an explicit
  ``close()`` (`#35`_)

.. _#35: https://github.com/faust-streaming/cChardet/issues/35

2.2.0 (2026-07-19)
------------------

- convert the build system to meson-python
- add the ``cchardetect`` CLI entry point, a markdown README, and dev lockfiles
- build Linux aarch64 and both macOS architectures on native runners
- force the MSVC toolchain on Windows so wheels do not depend on MinGW runtime
  DLLs
- drop Python 3.9; require the test suite to pass on 3.13 and 3.14

2.1.7 (2020-10-27)
------------------

- support Python 3.9
- drop support for Python 3.5

2.1.6 (2020-03-17)
------------------

- drop support for Python 2.7
- support Github Actions
- update dev-dependencies

2.1.5 (2019-09-27)
------------------

- update language models (uchardet)
- add iso8859-2 test but disabled it
- support Python 3.8
- drop support for Python 3.4

2.1.4 (2018-09-27)
------------------

- disable LTO because become poor performance

2.1.3 (2018-09-26)
------------------

- support Python 3.7

2.1.2 (2018-09-26)
------------------

- enable `LTO`_ for wheel builds
- update Cython

.. _LTO: https://gcc.gnu.org/wiki/LinkTimeOptimization

2.1.1 (2017-07-01)
------------------

- fix that different results with different chuck sizes
- fix that assignments to nsSMState in nsCodingStateMachine result in unspecified behavior
- include COPYING in package

2.1.0 (2017-05-15)
------------------

- add cchardetect CLI script (`#30`_) `@craigds`_

.. _#30: https://github.com/PyYoshi/cChardet/pull/30
.. _@craigds: https://github.com/craigds

2.0.1 (2017-04-25)
------------------

- fix an issue where UTF-8 with a BOM would not be detected as UTF-8-SIG (fix `#28`_)
- pass NULL Byte to feed() / detect() (fix `#27`_)

.. _#28: https://github.com/PyYoshi/cChardet/issues/28
.. _#27: https://github.com/PyYoshi/cChardet/issues/27

2.0.0 (2017-04-06)
------------------

- Improve tests

2.0a4 (2017-04-05)
------------------

- Update uchardet repo (Fix buffer overflow)

2.0a3 (2017-03-29)
------------------

- Implement UniversalDetector (like chardet)

2.0a2 (2017-03-28)
------------------

- Update uchardet repo (Fix memory leak)

2.0a1 (2017-03-28)
------------------

- Replace `uchardet-enhanced`_ to `uchardet`_
- Remove Detector class

.. _uchardet-enhanced: https://bitbucket.org/medoc/uchardet-enhanced/overview
.. _uchardet: https://github.com/PyYoshi/uchardet

1.1.3 (2017-02-26)
------------------

- Support AArch64

1.1.2 (2017-01-08)
------------------

- Support Python 3.6

1.1.1 (2016-11-05)
------------------

- Use len() function (9e61cb9e96b138b0d18e5f9e013e144202ae4067)

- Remove detect function in _cchardet.pyx (25b581294fc0ae8f686ac9972c8549666766f695)

- Support manylinux1 wheel

1.1.0 (2016-10-17)
------------------

- Add Detector class

- Improve unit tests
