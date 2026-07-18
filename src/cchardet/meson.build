# uchardet (vendored via the src/ext/uchardet git submodule). Meson does not
# support globbing sources, so the C++ files are listed explicitly.
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
  '../ext/uchardet/src/nsLatin1Prober.cpp',
  '../ext/uchardet/src/nsMBCSGroupProber.cpp',
  '../ext/uchardet/src/nsMBCSSM.cpp',
  '../ext/uchardet/src/nsSBCSGroupProber.cpp',
  '../ext/uchardet/src/nsSBCharSetProber.cpp',
  '../ext/uchardet/src/nsSJISProber.cpp',
  '../ext/uchardet/src/nsUTF8Prober.cpp',
  '../ext/uchardet/src/nsUniversalDetector.cpp',
  '../ext/uchardet/src/uchardet.cpp',
  '../ext/uchardet/src/LangModels/LangArabicModel.cpp',
  '../ext/uchardet/src/LangModels/LangBulgarianModel.cpp',
  '../ext/uchardet/src/LangModels/LangCroatianModel.cpp',
  '../ext/uchardet/src/LangModels/LangCzechModel.cpp',
  '../ext/uchardet/src/LangModels/LangDanishModel.cpp',
  '../ext/uchardet/src/LangModels/LangEsperantoModel.cpp',
  '../ext/uchardet/src/LangModels/LangEstonianModel.cpp',
  '../ext/uchardet/src/LangModels/LangFinnishModel.cpp',
  '../ext/uchardet/src/LangModels/LangFrenchModel.cpp',
  '../ext/uchardet/src/LangModels/LangGermanModel.cpp',
  '../ext/uchardet/src/LangModels/LangGreekModel.cpp',
  '../ext/uchardet/src/LangModels/LangHebrewModel.cpp',
  '../ext/uchardet/src/LangModels/LangHungarianModel.cpp',
  '../ext/uchardet/src/LangModels/LangIrishModel.cpp',
  '../ext/uchardet/src/LangModels/LangItalianModel.cpp',
  '../ext/uchardet/src/LangModels/LangLatvianModel.cpp',
  '../ext/uchardet/src/LangModels/LangLithuanianModel.cpp',
  '../ext/uchardet/src/LangModels/LangMalteseModel.cpp',
  '../ext/uchardet/src/LangModels/LangPolishModel.cpp',
  '../ext/uchardet/src/LangModels/LangPortugueseModel.cpp',
  '../ext/uchardet/src/LangModels/LangRomanianModel.cpp',
  '../ext/uchardet/src/LangModels/LangRussianModel.cpp',
  '../ext/uchardet/src/LangModels/LangSlovakModel.cpp',
  '../ext/uchardet/src/LangModels/LangSloveneModel.cpp',
  '../ext/uchardet/src/LangModels/LangSpanishModel.cpp',
  '../ext/uchardet/src/LangModels/LangSwedishModel.cpp',
  '../ext/uchardet/src/LangModels/LangThaiModel.cpp',
  '../ext/uchardet/src/LangModels/LangTurkishModel.cpp',
  '../ext/uchardet/src/LangModels/LangVietnameseModel.cpp',
)

uchardet_inc = include_directories('../ext/uchardet/src')

py.extension_module(
  '_cchardet',
  '_cchardet.pyx',
  uchardet_sources,
  # Build the Cython output as C++ (the module wraps a C++ library). Meson then
  # links the C++ runtime that matches the active compiler (libstdc++ or
  # libc++), so no manual `-lstdc++` is needed.
  override_options: ['cython_language=cpp'],
  include_directories: uchardet_inc,
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
