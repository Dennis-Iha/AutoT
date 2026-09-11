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
    # Phase 0/1 has no ASR/MT/TTS integrated yet; nothing should claim to be
    # further along than "initial" until later phases actually benchmark it.
    reg = LanguageRegistry.load()
    assert reg.with_status("production") == []
    assert all(lang.status == "initial" for lang in reg)
