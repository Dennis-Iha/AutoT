"""Real translation tests against the espeak-ng fixture text (all 8 source
languages -> English) - not mocked. Requires
tools/setup_translation_models.sh to have been run; skips gracefully if not
available, since that downloads ~1GB of models.
"""

from __future__ import annotations

import json

import pytest

from core.common.config import REPO_ROOT
from core.translation.ctranslate2_translator import CTranslate2TranslationEngine

LANGUAGES = ["ar", "bn", "zh", "fr", "hi", "pt", "ru", "es"]

# Content words a correct translation of "Where is the train station?"
# should contain in some inflection - NOT an exact-match assertion (MT
# output phrasing legitimately varies: "Where's" vs "Where is", "railway"
# vs "train"), but enough to catch a badly broken pipeline (wrong
# language's model loaded, garbled tokenization, empty output).
EXPECTED_SUBSTRINGS = ["where", "station"]


@pytest.fixture(scope="module")
def engine(translation_registry):
    if translation_registry is None:
        pytest.skip("no translation models installed - run tools/setup_translation_models.sh first")
    return CTranslate2TranslationEngine(translation_registry)


@pytest.fixture(scope="module")
def manifest():
    with open(REPO_ROOT / "tests" / "fixtures" / "speech" / "manifest.json") as f:
        return json.load(f)


@pytest.mark.parametrize("lang", LANGUAGES)
def test_translate_produces_plausible_english(engine, manifest, lang):
    text = manifest[lang]["text"]
    result = engine.translate(text, lang, "en")
    assert result.source_language == lang
    assert result.target_language == "en"
    lowered = result.text.lower()
    for expected in EXPECTED_SUBSTRINGS:
        assert expected in lowered, f"{lang}: {result.text!r} missing {expected!r}"


def test_no_leftover_sentencepiece_markers(engine, manifest):
    # Regression test for a real bug caught during development: sentencepiece
    # 0.2.2's decode() on a list of piece-strings inconsistently left "▁"
    # markers in the output for some languages (see
    # core/translation/ctranslate2_translator.py's _SentencePieceTokenizer).
    for lang in LANGUAGES:
        result = engine.translate(manifest[lang]["text"], lang, "en")
        assert "▁" not in result.text, f"{lang}: {result.text!r}"


def test_translate_stream_yields_one_result_per_input(engine, manifest):
    # translate_stream is one (source, target) pair applied to a sequence of
    # texts, not mixed-language per item - matches translate()'s scope.
    texts = [manifest["ar"]["text"], "أين محطة الحافلات"]
    results = list(engine.translate_stream(iter(texts), "ar", "en"))
    assert len(results) == 2
    assert all(r.source_language == "ar" and r.target_language == "en" for r in results)


def test_unsupported_pair_raises(engine):
    with pytest.raises(ValueError, match="no ready translation model"):
        engine.translate("hello", "en", "xx")


def test_supports_pair(translation_registry):
    if translation_registry is None:
        pytest.skip("no translation models installed")
    engine = CTranslate2TranslationEngine(translation_registry)
    assert engine.supports_pair("ar", "en") is True
    assert engine.supports_pair("xx", "en") is False


def test_unload_frees_cached_backend(engine, manifest):
    engine.translate(manifest["ar"]["text"], "ar", "en")
    assert ("ar", "en") in engine._translators
    engine.unload("ar", "en")
    assert ("ar", "en") not in engine._translators
