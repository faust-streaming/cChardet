project(
  'faust-cchardet',
  'cpp',
  'cython',
  version: '3.0.0',
  meson_version: '>=1.2.0',
  default_options: [
    'cpp_std=c++11',
    'warning_level=1',
  ],
)

py = import('python').find_installation(pure: false)

# Compile the .pyx as Python 3 (the module has no explicit language_level).
add_project_arguments('-3', language: 'cython')

subdir('src/cchardet')

# The `cchardetect` command-line tool is installed as a console entry point
# (see [project.scripts] in pyproject.toml), which meson-python turns into a
# wrapper script. The old standalone bin/cchardetect script it replaced has
# been removed.
