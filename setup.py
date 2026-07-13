#!/usr/bin/env python
# coding: utf-8

import os
import sys
import codecs
import re
from setuptools.command.build_ext import build_ext
import sysconfig

try:
    from setuptools import setup, Extension
except ImportError:
    from distutils.core import setup, Extension

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
    if type(value) == str:
        cfg_vars[key] = value.replace("-Wstrict-prototypes", "")
        # O3を指定したところで速度が向上するかは疑問である
        # cfg_vars[key] = value.replace("-O2", "-O3")


cchardet_module = Extension("cchardet._cchardet", sources, language="c++", **ext_args)


def read(f):
    return open(os.path.join(os.path.dirname(__file__), f)).read().strip()


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
    name="faust-cchardet",
    author="PyYoshi",
    author_email="myoshi321go@gmail.com",
    url=r"https://github.com/faust-streaming/cChardet",
    description="cChardet is high speed universal character encoding detector.",
    long_description="\n\n".join((read("README.rst"), read("CHANGES.rst"))),
    version=version,
    license="MPL-1.1 OR GPL-2.0-or-later or LGPL-2.1-or-later",
    classifiers=[
        "Development Status :: 6 - Mature",
        "Programming Language :: Cython",
        "Programming Language :: Python",
        "Programming Language :: Python :: Implementation :: CPython",
        "Programming Language :: Python :: Implementation :: PyPy",
        "Topic :: Software Development :: Libraries",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    keywords=["cython", "chardet", "charsetdetect"],
    cmdclass={"build_ext": build_ext},
    package_dir={"": "src"},
    packages=[
        "cchardet",
    ],
    scripts=["bin/cchardetect"],
    ext_modules=cythonize(
        [
            cchardet_module,
        ],
        cplus=True,
        compiler_directives={"language_level": "3"},  # Python 3
    ),
)
