# uchardet (vendored via the src/ext/uchardet git submodule, upstream
# freedesktop). Meson does not support globbing sources, so the C++ files are
# listed explicitly. cChardet overlays the multibyte group prober to retain
# encoding detection without uchardet's generic Unicode language pass.
uchardet_sources = files(
  '../ext/uchardet/src/CharDistribution.cpp',
  '../ext/uchardet/src/JpCntx.cpp',
  '../ext/uchardet/src/nsBig5Prober.cpp',
  '../ext/uchardet/src/nsCharSetProber.cpp',
  '../ext/uchardet/src/nsEUCJPProber.cpp',
  '../ext/uchardet/src/nsEUCKRProber.cpp',
  '../ext/uchardet/src/nsEUCTWProber.cpp',
  '../ext/uchardet/src/nsEscCharsetProber.cpp',
  '../ext/uchardet/src/nsEscSM.cpp',
  '../ext/uchardet/src/nsGB2312Prober.cpp',
  '../ext/uchardet/src/nsHebrewProber.cpp',
  '../ext/uchardet/src/nsJohabProber.cpp',
  '../ext/uchardet/src/nsLatin1Prober.cpp',
  'uchardet-overlay/nsMBCSGroupProber.cpp',
  '../ext/uchardet/src/nsMBCSSM.cpp',
  '../ext/uchardet/src/nsSBCSGroupProber.cpp',
  '../ext/uchardet/src/nsSBCharSetProber.cpp',
  '../ext/uchardet/src/nsSJISProber.cpp',
  '../ext/uchardet/src/nsUTF8Prober.cpp',
  '../ext/uchardet/src/nsUniversalDetector.cpp',
  '../ext/uchardet/src/uchardet.cpp',
  '../ext/uchardet/src/LangModels/LangArabicModel.cpp',
  '../ext/uchardet/src/LangModels/LangBelarusianModel.cpp',
  '../ext/uchardet/src/LangModels/LangBulgarianModel.cpp',
  '../ext/uchardet/src/LangModels/LangCatalanModel.cpp',
  '../ext/uchardet/src/LangModels/LangCroatianModel.cpp',
  '../ext/uchardet/src/LangModels/LangCzechModel.cpp',
  '../ext/uchardet/src/LangModels/LangDanishModel.cpp',
  '../ext/uchardet/src/LangModels/LangEnglishModel.cpp',
  '../ext/uchardet/src/LangModels/LangEsperantoModel.cpp',
  '../ext/uchardet/src/LangModels/LangEstonianModel.cpp',
  '../ext/uchardet/src/LangModels/LangFinnishModel.cpp',
  '../ext/uchardet/src/LangModels/LangFrenchModel.cpp',
  '../ext/uchardet/src/LangModels/LangGeorgianModel.cpp',
  '../ext/uchardet/src/LangModels/LangGermanModel.cpp',
  '../ext/uchardet/src/LangModels/LangGreekModel.cpp',
  '../ext/uchardet/src/LangModels/LangHebrewModel.cpp',
  '../ext/uchardet/src/LangModels/LangHindiModel.cpp',
  '../ext/uchardet/src/LangModels/LangHungarianModel.cpp',
  '../ext/uchardet/src/LangModels/LangIrishModel.cpp',
  '../ext/uchardet/src/LangModels/LangItalianModel.cpp',
  '../ext/uchardet/src/LangModels/LangLatvianModel.cpp',
  '../ext/uchardet/src/LangModels/LangLithuanianModel.cpp',
  '../ext/uchardet/src/LangModels/LangMacedonianModel.cpp',
  '../ext/uchardet/src/LangModels/LangMalteseModel.cpp',
  '../ext/uchardet/src/LangModels/LangNorwegianModel.cpp',
  '../ext/uchardet/src/LangModels/LangPolishModel.cpp',
  '../ext/uchardet/src/LangModels/LangPortugueseModel.cpp',
  '../ext/uchardet/src/LangModels/LangRomanianModel.cpp',
  '../ext/uchardet/src/LangModels/LangRussianModel.cpp',
  '../ext/uchardet/src/LangModels/LangSerbianModel.cpp',
  '../ext/uchardet/src/LangModels/LangSlovakModel.cpp',
  '../ext/uchardet/src/LangModels/LangSloveneModel.cpp',
  '../ext/uchardet/src/LangModels/LangSpanishModel.cpp',
  '../ext/uchardet/src/LangModels/LangSwedishModel.cpp',
  '../ext/uchardet/src/LangModels/LangThaiModel.cpp',
  '../ext/uchardet/src/LangModels/LangTurkishModel.cpp',
  '../ext/uchardet/src/LangModels/LangUkrainianModel.cpp',
  '../ext/uchardet/src/LangModels/LangVietnameseModel.cpp',
)

uchardet_inc = include_directories('../ext/uchardet/src')

# Select the uchardet implementation to build against. `system-uchardet` is a
# feature option:
#   enabled  -> require the system library; hard fail if it is missing or too
#               old. This is what distro packaging wants.
#   disabled -> always build the bundled copy (the default, used by the wheels).
#   auto     -> use the system library if it is new enough, otherwise fall back
#               to the bundled copy (convenient for source installs).
system_uchardet = get_option('system-uchardet')

use_bundled = true
if not system_uchardet.disabled()
  # Passing the feature as `required:` makes meson hard fail for `enabled` when
  # no uchardet is installed, while `auto` continues quietly if it is absent.
  system_uchardet_dep = dependency('uchardet', required: system_uchardet)
  if system_uchardet_dep.found()
    # The candidate API (uchardet_get_n_candidates) only exists in uchardet
    # newer than the last tagged release, so a found-but-too-old system library
    # must still be rejected.
    # TODO: replace this has_function() probe with a `version: '>=X'` constraint
    # on the dependency() call above once upstream tags a release exposing it.
    cpp = meson.get_compiler('cpp')
    if cpp.has_function('uchardet_get_n_candidates', dependencies: [system_uchardet_dep])
      uchardet = system_uchardet_dep
      use_bundled = false
    elif system_uchardet.enabled()
      error(
        'system-uchardet is enabled but the installed uchardet is too old: ' +
        'it does not provide uchardet_get_n_candidates. Install the git ' +
        'version from https://gitlab.freedesktop.org/uchardet/uchardet.git, ' +
        'or set -Dsystem-uchardet=disabled to build the bundled copy.'
      )
    endif
    # auto + a too-old system library: fall through to the bundled copy below.
  endif
endif

if use_bundled
  uchardet = declare_dependency(
    sources: uchardet_sources,
    include_directories: uchardet_inc,
  )
endif

py.extension_module(
  '_cchardet',
  '_cchardet.pyx',
  dependencies: [uchardet],
  # Build the Cython output as C++ (the module wraps a C++ library). Meson then
  # links the C++ runtime that matches the active compiler (libstdc++ or
  # libc++), so no manual `-lstdc++` is needed.
  override_options: ['cython_language=cpp'],
  install: true,
  subdir: 'cchardet',
)

py.install_sources(
  '__init__.py',
  '__main__.py',
  'version.py',
  subdir: 'cchardet',
)

py.install_sources(
  'cli/__init__.py',
  'cli/cchardetect.py',
  subdir: 'cchardet/cli',
)
