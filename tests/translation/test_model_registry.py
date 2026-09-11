from core.translation.model_registry import TranslationModelRegistry

EXPECTED_PAIRS = {("ar", "en"), ("bn", "en"), ("zh", "en"), ("fr", "en"),
                  ("hi", "en"), ("pt", "en"), ("ru", "en"), ("es", "en")}


def test_registry_loads_all_v1_pairs():
    registry = TranslationModelRegistry.load()
    assert set(registry.pairs()) == EXPECTED_PAIRS


def test_get_known_pair():
    registry = TranslationModelRegistry.load()
    entry = registry.get("ar", "en")
    assert entry is not None
    assert entry.model_id == "argos-ar-en-1.0"
    assert entry.engine == "ctranslate2"


def test_get_unknown_pair_returns_none():
    registry = TranslationModelRegistry.load()
    assert registry.get("en", "xx") is None


def test_ctranslate2_model_dir_is_model_subdirectory():
    registry = TranslationModelRegistry.load()
    entry = registry.get("ar", "en")
    assert entry.ctranslate2_model_dir == entry.model_dir / "model"


def test_supports_pair_false_for_unknown():
    registry = TranslationModelRegistry.load()
    assert registry.supports_pair("xx", "en") is False
