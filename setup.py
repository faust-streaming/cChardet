#!/usr/bin/env python
# coding: utf-8

import codecs
import os
import re
import sys
import sysconfig

from setuptools.command.build_ext import build_ext

try:
    import sysconfig
except ImportError:
    from distutils import sysconfig

try:
    from setuptools import Extension, setup
except ImportError:
    from distutils.core import Extension, setup

from Cython.Build import cythonize

join = os.path.join

cchardet_dir = join("src", "cchardet") + os.path.sep
uchardet_dir = join("src", "ext", "uchardet", "src")
uchardet_lang_models_dir = join(uchardet_dir, "LangModels")

cchardet_sources = [join("src", "cchardet", "_cchardet.pyx")]
uchardet_sources = [
    join(uchardet_dir, file)
    for file in os.listdir(uchardet_dir)
    if file.endswith(".cpp")
]
uchardet_lang_source = [
    join(uchardet_lang_models_dir, file)
    for file in os.listdir(uchardet_lang_models_dir)
    if file.endswith(".cpp")
]
sources = cchardet_sources + uchardet_sources + uchardet_lang_source

ext_args = {
    "include_dirs": uchardet_dir.split(os.pathsep),
    "library_dirs": uchardet_dir.split(os.pathsep),
}

if sys.platform.startswith("linux"):
    # Explicitly link libstdc++ on Linux for newer toolchains/Python versions.
    ext_args["libraries"] = ["stdc++"]


# Remove the "-Wstrict-prototypes" compiler option, which isn't valid for C++.
cfg_vars = sysconfig.get_config_vars()
for key, value in cfg_vars.items():
    if isinstance(value, str):
        cfg_vars[key] = value.replace("-Wstrict-prototypes", "")
        # O3を指定したところで速度が向上するかは疑問である
        # cfg_vars[key] = value.replace("-O2", "-O3")


cchardet_module = Extension(
    "cchardet._cchardet",
    sources,
    language="c++",
    extra_compile_args=['-std=c++11'],
    **ext_args
)


# Single source of truth for the version, also exposed at runtime as
# cchardet.__version__ (see src/cchardet/version.py).
with codecs.open(
    os.path.join(
        os.path.abspath(os.path.dirname(__file__)), "src", "cchardet", "version.py"
    ),
    "r",
    "latin1",
) as fp:
    try:
        version = re.findall(r"^__version__ = '([^']+)'\r?$", fp.read(), re.M)[0]
    except IndexError:
        raise RuntimeError("Unable to determine version.")


setup(
    version=version,
    cmdclass={"build_ext": build_ext},
    package_dir={"": "src"},
    packages=[
        "cchardet",
    ],
    ext_modules=cythonize(
        [
            cchardet_module,
        ],
        cplus=True,
        compiler_directives={"language_level": "3"},  # Python 3
    ),
)
