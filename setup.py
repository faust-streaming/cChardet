#!/usr/bin/env python
# coding: utf-8

import os
import sys
import glob
import codecs
import re
import pkgconfig
from distutils.command.build_ext import build_ext
from distutils import sysconfig

try:
    from setuptools import setup, Extension
except ImportError:
    from distutils.core import setup, Extension

from Cython.Build import cythonize

cchardet_dir = os.path.join("src", "cchardet") + os.path.sep

try:
    ext_args = pkgconfig.parse('uchardet')
except pkgconfig.PackageNotFoundError:
    include_path = os.environ.get('INCLUDE_PATH')
    library_path = os.environ.get('LIBRARY_PATH')

    ext_args = {
        'include_dirs': include_path.split(os.pathsep) if include_path else [],
        'library_dirs': library_path.split(os.pathsep) if library_path else [],
        'libraries': ['uchardet'],
    }

# Remove the "-Wstrict-prototypes" compiler option, which isn't valid for C++.
cfg_vars = sysconfig.get_config_vars()
for key, value in cfg_vars.items():
    if type(value) == str:
        cfg_vars[key] = value.replace("-Wstrict-prototypes", "")
        # O3を指定したところで速度が向上するかは疑問である
        # cfg_vars[key] = value.replace("-O2", "-O3")


cchardet_module = Extension(
    'cchardet._cchardet',
    [
        os.path.join('src', 'cchardet', '_cchardet.pyx')
    ],
    language='c++',
    **ext_args
)


def read(f):
    return open(os.path.join(os.path.dirname(__file__), f)).read().strip()


with codecs.open(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'src', 'cchardet', 'version.py'), 'r', 'latin1') as fp:
    try:
        version = re.findall(
            r"^__version__ = '([^']+)'\r?$", fp.read(), re.M)[0]
    except IndexError:
        raise RuntimeError('Unable to determine version.')

setup(
    name='faust-cchardet',
    author='PyYoshi',
    author_email='myoshi321go@gmail.com',
    url=r'https://github.com/faust-streaming/cChardet',
    description='cChardet is high speed universal character encoding detector.',
    long_description='\n\n'.join((read('README.rst'), read('CHANGES.rst'))),
    version=version,
    license='Mozilla Public License',
    classifiers=[
        'License :: OSI Approved :: Mozilla Public License 1.1 (MPL 1.1)',
        'License :: OSI Approved :: GNU General Public License (GPL)',
        'License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)',
        'Programming Language :: Cython',
        'Programming Language :: Python',
        'Topic :: Software Development :: Libraries',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10', 
        'Programming Language :: Python :: 3.11',
    ],
    keywords=[
        'cython',
        'chardet',
        'charsetdetect'
    ],
    cmdclass={'build_ext': build_ext},
    package_dir={'': 'src'},
    packages=['cchardet', ],
    scripts=['bin/cchardetect'],
    ext_modules=cythonize([
        cchardet_module,
    ]),
)
