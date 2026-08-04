cChardet
========

[![PyPI version](https://badge.fury.io/py/faust-cchardet.svg)](https://badge.fury.io/py/faust-cchardet)
[![Run tests](https://github.com/faust-streaming/cChardet/actions/workflows/test.yml/badge.svg)](https://github.com/faust-streaming/cChardet/actions/workflows/test.yml)
[![Build Wheels](https://github.com/faust-streaming/cChardet/actions/workflows/build-and-upload-to-pypi.yml/badge.svg)](https://github.com/faust-streaming/cChardet/actions/workflows/build-and-upload-to-pypi.yml)

cChardet is high speed universal character encoding detector. - binding to [uchardet](https://github.com/PyYoshi/uchardet).

## This fork (`faust-cchardet`) vs [`PyYoshi/cChardet`](https://github.com/PyYoshi/cChardet)

This is the [faust-streaming](https://github.com/faust-streaming/cChardet) maintained fork of
upstream [`PyYoshi/cChardet`](https://github.com/PyYoshi/cChardet). It exists mainly to keep the
project building on current Python and Windows toolchains and to publish up-to-date prebuilt
wheels across platforms. **The public Python API is unchanged from upstream.**

The distribution is renamed on PyPI; the import name is not:

```bash
pip install faust-cchardet
```

```python
import cchardet   # same import name as upstream
```

**Key differences**

- **Prebuilt wheels** built with `cibuildwheel`, so most users install without a C++ compiler:
  - Linux: `x86_64`, `i686`, `aarch64` (CPython and PyPy)
  - macOS: `x86_64`, `arm64`
  - Windows: `x86_64` / AMD64
- **Windows / MSVC support** — pinned to an MSVC-compatible `uchardet` (`bdb8a0…`) so the C++
  extension compiles under Microsoft Visual C++. Upstream's newer `uchardet` header does not
  build under MSVC.
- **Modern build** — uses the [meson-python](https://mesonbuild.com/meson-python/) build backend
  (`distutils` is removed in Python 3.12+); Meson builds the Cython output as C++ and links the
  matching C++ runtime automatically.
- **Versioning** — the version lives in `src/cchardet/version.py` and is exposed as
  `cchardet.__version__` (upstream uses `setuptools_scm`).
- **Python support** — requires Python **>= 3.10** (3.6–3.9 are dropped).

**Detection differences** (a consequence of the pinned `uchardet`)

- A UTF-8 byte-order mark is reported as `UTF-8-SIG` (upstream reports `UTF-8`).
- On 32-bit (`i686`) builds a few near-equivalent labels differ — e.g. Thai `TIS-620` is
  detected as `ISO-8859-11`.

## Building against a system `uchardet`

By default cChardet builds a **bundled** copy of `uchardet` (vendored as a git
submodule), which is what the published wheels ship. Distributions and source
builds can instead link the **system** `uchardet` through the `system-uchardet`
Meson [feature option](https://mesonbuild.com/Build-options.html#features):

| `-Dsystem-uchardet=` | Behaviour |
| --- | --- |
| `disabled` (default) | Always build the bundled copy (used by the wheels). |
| `enabled` | Require the system library; the build **fails** if it is missing or too old. Recommended for distro packaging. |
| `auto` | Use the system library if it is new enough, otherwise fall back to the bundled copy. |

Pass the option through your build front-end. With `pip` / `build` the
meson-python backend reads it from `setup-args`:

```bash
pip install . --config-settings=setup-args=-Dsystem-uchardet=enabled
```

> **Requirement:** the system `uchardet` must be recent enough to expose
> `uchardet_get_n_candidates`. That symbol currently ships only in the git
> version (<https://gitlab.freedesktop.org/uchardet/uchardet.git>) — no tagged
> release provides it yet — so `enabled`/`auto` probe for it and reject an
> older library.

## Supported Languages/Encodings

- International (Unicode)
  - UTF-8
  - UTF-16BE / UTF-16LE
  - UTF-32BE / UTF-32LE / X-ISO-10646-UCS-4-34121 / X-ISO-10646-UCS-4-21431
- Arabic
  - ISO-8859-6
  - WINDOWS-1256
- Bulgarian
  - ISO-8859-5
  - WINDOWS-1251
- Chinese
  - ISO-2022-CN
  - BIG5
  - EUC-TW
  - GB18030
  - HZ-GB-2312
- Croatian:
  - ISO-8859-2
  - ISO-8859-13
  - ISO-8859-16
  - Windows-1250
  - IBM852
  - MAC-CENTRALEUROPE
- Czech
  - Windows-1250
  - ISO-8859-2
  - IBM852
  - MAC-CENTRALEUROPE
- Danish
  - ISO-8859-1
  - ISO-8859-15
  - WINDOWS-1252
- English
  - ASCII
- Esperanto
  - ISO-8859-3
- Estonian
  - ISO-8859-4
  - ISO-8859-13
  - ISO-8859-13
  - Windows-1252
  - Windows-1257
- Finnish
  - ISO-8859-1
  - ISO-8859-4
  - ISO-8859-9
  - ISO-8859-13
  - ISO-8859-15
  - WINDOWS-1252
- French
  - ISO-8859-1
  - ISO-8859-15
  - WINDOWS-1252
- German
  - ISO-8859-1
  - WINDOWS-1252
- Greek
  - ISO-8859-7
  - WINDOWS-1253
- Hebrew
  - ISO-8859-8
  - WINDOWS-1255
- Hungarian:
  - ISO-8859-2
  - WINDOWS-1250
- Irish Gaelic
  - ISO-8859-1
  - ISO-8859-9
  - ISO-8859-15
  - WINDOWS-1252
- Italian
  - ISO-8859-1
  - ISO-8859-3
  - ISO-8859-9
  - ISO-8859-15
  - WINDOWS-1252
- Japanese
  - ISO-2022-JP
  - SHIFT_JIS
  - EUC-JP
- Korean
  - ISO-2022-KR
  - EUC-KR / UHC
- Lithuanian
  - ISO-8859-4
  - ISO-8859-10
  - ISO-8859-13
- Latvian
  - ISO-8859-4
  - ISO-8859-10
  - ISO-8859-13
- Maltese
  - ISO-8859-3
- Polish:
  - ISO-8859-2
  - ISO-8859-13
  - ISO-8859-16
  - Windows-1250
  - IBM852
  - MAC-CENTRALEUROPE
- Portuguese
  - ISO-8859-1
  - ISO-8859-9
  - ISO-8859-15
  - WINDOWS-1252
- Romanian:
  - ISO-8859-2
  - ISO-8859-16
  - Windows-1250
  - IBM852
- Russian
  - ISO-8859-5
  - KOI8-R
  - WINDOWS-1251
  - MAC-CYRILLIC
  - IBM866
  - IBM855
- Slovak
  - Windows-1250
  - ISO-8859-2
  - IBM852
  - MAC-CENTRALEUROPE
- Slovene
  - ISO-8859-2
  - ISO-8859-16
  - Windows-1250
  - IBM852
  - MAC-CENTRALEUROPE

## Example

### One-shot detection

```python
import cchardet as chardet

with open(r"src/tests/samples/wikipediaJa_One_Thousand_and_One_Nights_SJIS.txt", "rb") as f:
    msg = f.read()
    result = chardet.detect(msg)
    print(result)
```

### Streaming detection

```python
import cchardet

detector = cchardet.UniversalDetector()
with open("bigfile.txt", "rb") as f:
    for line in f:
        detector.feed(line)
        if detector.done:
            break
detector.close()
print(detector.result)
```

## Command line

A `cchardetect` console script is installed with the package:

```bash
$ cchardetect src/tests/samples/wikipediaJa_One_Thousand_and_One_Nights_SJIS.txt
src/tests/samples/wikipediaJa_One_Thousand_and_One_Nights_SJIS.txt: SHIFT_JIS with confidence 0.99

$ cat somefile.txt | cchardetect        # also reads from stdin
```

## Benchmark

```bash
$ pip install -e .
$ python src/tests/bench.py
```

### Results

CPU: AMD Ryzen 9 7950X3D

RAM: DDR5-5600MT/s 96GB

Platform: Ubuntu 24.04 amd64

#### Python 3.12.3

|                   | Request (call/s) |
|-------------------|------------------|
| chardet v5.2.0    | 1.1              |
| cchardet v2.2.0a1 | 2263.6           |

## LICENSE

See **COPYING** file.

## Contact

- [Issues](https://github.com/faust-streaming/cChardet/issues?page=1&state=open)

## Support Platforms

Prebuilt wheels are published for:

- Windows x86_64 (AMD64)
- Linux x86_64, i686, aarch64
- macOS x86_64, arm64
