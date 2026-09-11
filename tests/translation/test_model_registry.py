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


def test_registry_entries_have_checksums():
    # Phase 10: every model entry should carry a sha256 for offline-
    # readiness verification (core/common/offline_runtime.py).
    registry = TranslationModelRegistry.load()
    for source, target in registry.pairs():
        entry = registry.get(source, target)
        assert entry is not None
        assert entry.sha256 is not None
        assert len(entry.sha256) == 64


def test_is_valid_true_when_installed_and_checksum_matches():
    registry = TranslationModelRegistry.load()
    entry = registry.get("ar", "en")
    assert entry is not None
    if entry.is_ready():  # skip if tools/setup_translation_models.sh hasn't run
        assert entry.is_valid() is True


def test_is_valid_false_for_wrong_checksum():
    from dataclasses import replace

    registry = TranslationModelRegistry.load()
    entry = registry.get("ar", "en")
    assert entry is not None
    if entry.is_ready():
        corrupted = replace(entry, sha256="0" * 64)
        assert corrupted.is_valid() is False


def test_is_valid_falls_back_to_is_ready_when_no_checksum_recorded():
    from dataclasses import replace

    registry = TranslationModelRegistry.load()
    entry = registry.get("ar", "en")
    assert entry is not None
    no_checksum = replace(entry, sha256=None)
    assert no_checksum.is_valid() == no_checksum.is_ready()
