"""Real language-identification tests against the espeak-ng-synthesized
speech fixtures (tests/fixtures/speech/) - not synthetic tones. Requires
whisper.cpp to be built and a model downloaded (tools/setup_whisper_cpp.sh);
skips gracefully if not available rather than failing, since that setup step
downloads ~75-150MB and isn't run automatically as part of `pytest`.
"""

from __future__ import annotations

import pytest

from core.audio.wav_io import read_wav
from core.language_id.whisper_lid import WhisperLanguageIdentifier

LANGUAGES = ["en", "zh", "hi", "es", "ar", "fr", "bn", "pt", "ru"]


@pytest.fixture(scope="module")
def identifier(whisper_cpp_available):
    if whisper_cpp_available is None:
        pytest.skip("whisper.cpp not built - run tools/setup_whisper_cpp.sh first")
    binary_path, model_path = whisper_cpp_available
    return WhisperLanguageIdentifier(binary_path=binary_path, model_path=model_path)


@pytest.mark.parametrize("lang", LANGUAGES)
def test_identify_returns_valid_result_shape(identifier, speech_fixtures, lang):
    audio, sr = read_wav(speech_fixtures[lang]["wav_path"])
    result = identifier.identify(audio, sr)
    assert isinstance(result.language, str) and len(result.language) > 0
    assert 0.0 <= result.confidence <= 1.0
    assert result.timestamp > 0


def test_identify_english_fixture_as_english(identifier, speech_fixtures):
    audio, sr = read_wav(speech_fixtures["en"]["wav_path"])
    result = identifier.identify(audio, sr)
    assert result.language == "en"


def test_is_confident_helper(identifier, speech_fixtures):
    audio, sr = read_wav(speech_fixtures["en"]["wav_path"])
    result = identifier.identify(audio, sr)
    assert identifier.is_confident(result) == (result.confidence >= 0.5)
