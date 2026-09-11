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
    # TTS (Phase 7) hasn't landed yet, so nothing should claim "production"
    # (which requires ASR+translation+TTS all benchmarked) until it does.
    reg = LanguageRegistry.load()
    assert reg.with_status("production") == []


def test_status_reflects_actually_tested_phases():
    # As of Phase 6: ASR+LID tested for all 9 (en is the ASR/LID target,
    # not yet a translation source); translation tested for the 8 non-
    # English source languages (see tools/translation_benchmark.py).
    reg = LanguageRegistry.load()
    assert reg.get("en").status == "asr_ready"
    for code in EXPECTED_V1_LANGUAGES - {"en"}:
        assert reg.get(code).status == "translation_ready", code
