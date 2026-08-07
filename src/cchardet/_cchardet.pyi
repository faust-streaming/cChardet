"""Type stubs for the Cython extension module.

Type checkers cannot see inside a compiled extension, so without this stub the
whole package degrades to ``Any`` even with a ``py.typed`` marker. Kept in sync
with ``_cchardet.pyx`` by hand -- it is a small, stable surface.

Note the ``bytes`` argument types: the Cython signatures are ``bytes msg``, so
``bytearray`` and ``memoryview`` raise ``TypeError`` at runtime rather than
being accepted as buffers.
"""

class UniversalDetector:
    def __init__(self) -> None: ...
    def reset(self) -> None: ...
    def feed(self, msg: bytes) -> None: ...
    def close(self) -> None: ...
    @property
    def done(self) -> bool: ...
    @property
    def result(self) -> tuple[bytes, float] | tuple[None, None]: ...

def detect_with_confidence(
    msg: bytes,
) -> tuple[bytes, float] | tuple[None, None]: ...
