from core.common.languages import LanguageRegistry

EXPECTED_V1_LANGUAGES = {"en", "zh", "hi", "es", "ar", "fr", "bn", "pt", "ru"}


def test_registry_loads_all_v1_languages():
    reg = LanguageRegistry.load()
    assert set(reg.codes()) == EXPECTED_V1_LANGUAGES


def test_get_known_language():
    reg = LanguageRegistry.load()
    zh = reg.get("zh")
    assert zh is not None
    assert zh.name == "Mandarin Chinese"


def test_get_unknown_language_returns_none():
    reg = LanguageRegistry.load()
    assert reg.get("xx") is None


def test_contains():
    reg = LanguageRegistry.load()
    assert "en" in reg
    assert "xx" not in reg


def test_no_language_is_falsely_claimed_production_ready():
    # "production" is reserved for Phase 30's defined, explicit quality
    # gates actually passing - not claimed just because the pieces exist
    # and produced correct output during development.
    reg = LanguageRegistry.load()
    assert reg.with_status("production") == []


def test_status_reflects_actually_tested_phases():
    # As of Phase 7: English is the TTS target (+ tested as an ASR/LID
    # source too) so it skips "translation_ready" per the pipeline's
    # asymmetry (see core/common/languages.py); the 8 non-English v1
    # source languages have ASR+LID+translation-to-en all tested.
    reg = LanguageRegistry.load()
    assert reg.get("en").status == "tts_ready"
    for code in EXPECTED_V1_LANGUAGES - {"en"}:
        assert reg.get(code).status == "translation_ready", code
