project(
  'faust-cchardet',
  'cpp',
  'cython',
  version: '3.2.0',
  meson_version: '>=1.2.0',
  default_options: [
    'cpp_std=c++11',
    'warning_level=1',
  ],
)

py = import('python').find_installation(pure: false)

# The `freethreading_compatible` directive in src/cchardet/_cchardet.pyx is
# silently ignored by Cython < 3.1 -- the build still succeeds, but the module
# does not declare Py_MOD_GIL_NOT_USED and re-enables the GIL process-wide on
# free-threaded CPython. pyproject.toml pins the floor for isolated builds;
# this check covers the paths that bypass it (--no-build-isolation, distro
# packaging, -Dsystem-uchardet=enabled).
cython = meson.get_compiler('cython')
if not cython.version().version_compare('>=3.1.0')
  error(
    'Cython >= 3.1.0 is required (got ' + cython.version() + '): the ' +
    'freethreading_compatible directive in src/cchardet/_cchardet.pyx is ' +
    'silently ignored by older Cython, producing a module that re-enables ' +
    'the GIL on free-threaded CPython.'
  )
endif

# Compile the .pyx as Python 3 (the module has no explicit language_level).
add_project_arguments('-3', language: 'cython')

subdir('src/cchardet')

# The `cchardetect` command-line tool is installed as a console entry point
# (see [project.scripts] in pyproject.toml), which meson-python turns into a
# wrapper script. The old standalone bin/cchardetect script it replaced has
# been removed.
