from core.asr.model_registry import ASRModelRegistry

EXPECTED_MODEL_IDS = {"whisper-tiny", "whisper-base", "whisper-small"}


def test_registry_loads_all_models():
    registry = ASRModelRegistry.load()
    assert set(registry.model_ids()) == EXPECTED_MODEL_IDS


def test_get_known_model():
    registry = ASRModelRegistry.load()
    entry = registry.get("whisper-base")
    assert entry is not None
    assert entry.size_class == "base"
    assert entry.engine == "whisper_cpp"
    assert entry.multilingual is True


def test_get_unknown_model_returns_none():
    registry = ASRModelRegistry.load()
    assert registry.get("whisper-xl") is None


def test_get_by_size_class():
    registry = ASRModelRegistry.load()
    entry = registry.get_by_size_class("tiny")
    assert entry is not None
    assert entry.model_id == "whisper-tiny"


def test_get_by_unknown_size_class_returns_none():
    registry = ASRModelRegistry.load()
    assert registry.get_by_size_class("xl") is None


def test_is_ready_and_is_valid_false_for_missing_file(tmp_path):
    from core.asr.model_registry import ASRModelEntry

    entry = ASRModelEntry(
        model_id="fake", size_class="tiny", engine="whisper_cpp", multilingual=True,
        path=tmp_path / "does_not_exist.bin", sha256="0" * 64, size_mb=1.0,
    )
    assert entry.is_ready() is False
    assert entry.is_valid() is False


def test_is_valid_false_for_wrong_checksum(tmp_path):
    from core.asr.model_registry import ASRModelEntry

    path = tmp_path / "model.bin"
    path.write_bytes(b"some model data")
    entry = ASRModelEntry(
        model_id="fake", size_class="tiny", engine="whisper_cpp", multilingual=True,
        path=path, sha256="0" * 64, size_mb=1.0,
    )
    assert entry.is_ready() is True  # file exists
    assert entry.is_valid() is False  # but checksum doesn't match


def test_is_valid_true_for_correct_checksum(tmp_path):
    import hashlib

    from core.asr.model_registry import ASRModelEntry

    path = tmp_path / "model.bin"
    data = b"some model data"
    path.write_bytes(data)
    entry = ASRModelEntry(
        model_id="fake", size_class="tiny", engine="whisper_cpp", multilingual=True,
        path=path, sha256=hashlib.sha256(data).hexdigest(), size_mb=1.0,
    )
    assert entry.is_valid() is True
