from dataclasses import replace

from core.tts.voice_registry import VoiceRegistry


def test_registry_loads_voices():
    registry = VoiceRegistry.load()
    assert "en_US-amy-medium" in registry.voice_ids()


def test_get_known_voice():
    registry = VoiceRegistry.load()
    entry = registry.get("en_US-amy-medium")
    assert entry is not None
    assert entry.language == "en"
    assert entry.engine == "piper"


def test_get_unknown_voice_returns_none():
    registry = VoiceRegistry.load()
    assert registry.get("nonexistent-voice") is None


def test_default_for_language():
    registry = VoiceRegistry.load()
    entry = registry.default_for_language("en")
    assert entry is not None
    assert entry.language == "en"


def test_default_for_unknown_language_returns_none():
    registry = VoiceRegistry.load()
    assert registry.default_for_language("xx") is None


def test_registry_entries_have_checksums():
    registry = VoiceRegistry.load()
    for voice_id in registry.voice_ids():
        entry = registry.get(voice_id)
        assert entry is not None
        assert entry.sha256 is not None
        assert len(entry.sha256) == 64


def test_is_valid_true_when_installed_and_checksum_matches():
    registry = VoiceRegistry.load()
    entry = registry.get("en_US-amy-medium")
    assert entry is not None
    if entry.is_ready():  # skip if tools/setup_tts_models.sh hasn't run
        assert entry.is_valid() is True


def test_is_valid_false_for_wrong_checksum():
    registry = VoiceRegistry.load()
    entry = registry.get("en_US-amy-medium")
    assert entry is not None
    if entry.is_ready():
        corrupted = replace(entry, sha256="0" * 64)
        assert corrupted.is_valid() is False


def test_is_valid_falls_back_to_is_ready_when_no_checksum_recorded():
    registry = VoiceRegistry.load()
    entry = registry.get("en_US-amy-medium")
    assert entry is not None
    no_checksum = replace(entry, sha256=None)
    assert no_checksum.is_valid() == no_checksum.is_ready()
