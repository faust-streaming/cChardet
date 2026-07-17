project(
  'faust-cchardet',
  'cpp',
  'cython',
  version: '2.1.20',
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

# Preserve the existing `cchardetect` command-line tool. It is a plain script
# (not a package entry point), so install it into the wheel's scripts dir.
install_data(
  'bin/cchardetect',
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
)
