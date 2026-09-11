"""Shared pytest fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.common.config import REPO_ROOT, load_config
from core.translation.model_registry import TranslationModelRegistry

FIXTURES_SPEECH_DIR = REPO_ROOT / "tests" / "fixtures" / "speech"


@pytest.fixture(scope="session")
def speech_fixtures() -> dict:
    """Loads tests/fixtures/speech/manifest.json plus each language's WAV path."""
    with open(FIXTURES_SPEECH_DIR / "manifest.json") as f:
        manifest = json.load(f)
    result = {}
    for lang, entry in manifest.items():
        if not isinstance(entry, dict):  # skips top-level metadata like sample_rate_hz, channels
            continue
        result[lang] = {**entry, "wav_path": FIXTURES_SPEECH_DIR / f"{lang}.wav"}
    return result


def _resolve_path(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else REPO_ROOT / path


@pytest.fixture(scope="session")
def whisper_cpp_available() -> tuple[Path, Path] | None:
    """Returns (binary_path, model_path) if whisper.cpp has been built and a
    model downloaded via tools/setup_whisper_cpp.sh, else None."""
    cfg = load_config().asr
    binary_path = _resolve_path(cfg.binary_path)
    model_path = _resolve_path(cfg.model_path)
    if binary_path.exists() and model_path.exists():
        return binary_path, model_path
    return None


@pytest.fixture(scope="session")
def translation_registry() -> TranslationModelRegistry | None:
    """Returns a loaded TranslationModelRegistry if at least one model is
    ready (tools/setup_translation_models.sh has been run), else None."""
    registry = TranslationModelRegistry.load()
    if any(registry.get(s, t).is_ready() for s, t in registry.pairs()):
        return registry
    return None
