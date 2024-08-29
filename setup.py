#!/usr/bin/env python
# coding: utf-8

import os
import codecs
import re
from setuptools.command.build_ext import build_ext

try:
    import sysconfig
except ImportError:
    from distutils import sysconfig

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


# Remove the "-Wstrict-prototypes" compiler option, which isn't valid for C++.
cfg_vars = sysconfig.get_config_vars()
for key, value in cfg_vars.items():
    if type(value) == str:
        cfg_vars[key] = value.replace("-Wstrict-prototypes", "")
        # O3を指定したところで速度が向上するかは疑問である
        # cfg_vars[key] = value.replace("-O2", "-O3")


cchardet_module = Extension("cchardet._cchardet", sources, language="c++", extra_compile_args=['-std=c++11'], **ext_args,)


def read(f):
    return open(os.path.join(os.path.dirname(__file__), f)).read().strip()


setup(
    name="faust-cchardet",
    author="PyYoshi",
    author_email="myoshi321go@gmail.com",
    url=r"https://github.com/faust-streaming/cChardet",
    description="cChardet is high speed universal character encoding detector.",
    long_description="\n\n".join((read("README.md"), read("CHANGES.md"))),
    license="Mozilla Public License",
    classifiers=[
        "Development Status :: 6 - Mature",
        "License :: OSI Approved :: Mozilla Public License 1.1 (MPL 1.1)",
        "License :: OSI Approved :: GNU General Public License (GPL)",
        "License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)",
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
    scripts=["src/cchardet/cli/cchardetect.py"],
    ext_modules=cythonize(
        [
            cchardet_module,
        ],
        cplus=True,
        compiler_directives={"language_level": "3"},  # Python 3
    ),
)
