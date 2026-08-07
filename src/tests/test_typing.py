"""PEP 561 packaging: the type information has to actually ship.

Annotating the source does nothing for downstream users on its own. A type
checker only looks at an installed package if it carries a ``py.typed`` marker,
and it cannot see into the compiled extension without ``_cchardet.pyi``. Both
are installed by ``py.install_sources`` in src/cchardet/meson.build, which is
easy to drop when that list is edited -- and dropping it fails silently,
degrading every downstream ``cchardet`` annotation to ``Any`` with no error
anywhere. Hence these tests.
"""

import pathlib

import cchardet

_PACKAGE_DIR = pathlib.Path(cchardet.__file__).parent


def test_py_typed_marker_is_installed():
    assert (_PACKAGE_DIR / "py.typed").is_file(), (
        "py.typed is missing from the installed package, so type checkers will "
        "ignore cchardet's annotations entirely (PEP 561)"
    )


def test_extension_stub_is_installed():
    assert (_PACKAGE_DIR / "_cchardet.pyi").is_file(), (
        "_cchardet.pyi is missing from the installed package, so the compiled "
        "extension is untyped and the public API degrades to Any"
    )


def test_detection_result_is_exported():
    """The TypedDict is part of the public API -- downstream code annotates
    against it, so removing or renaming it is a breaking change."""
    assert cchardet.DetectionResult in (cchardet.DetectionResult,)
    assert set(cchardet.DetectionResult.__annotations__) == {"encoding", "confidence"}
    assert "DetectionResult" in cchardet.__all__


def test_result_shape_matches_the_declared_type():
    """Guard against the annotations drifting from what is actually returned."""
    detected = cchardet.detect("こんにちは".encode("shift_jis"))
    assert set(detected) == {"encoding", "confidence"}
    assert isinstance(detected["encoding"], str)
    assert isinstance(detected["confidence"], float)

    with cchardet.UniversalDetector() as detector:
        detector.feed("こんにちは".encode("shift_jis"))
        streamed = detector.result
    assert set(streamed) == {"encoding", "confidence"}

    # The None case the annotation forces callers to handle.
    empty = cchardet.detect(b"")
    assert empty["encoding"] is None
    assert empty["confidence"] is None
