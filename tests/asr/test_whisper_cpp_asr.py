"""Real ASR tests against the espeak-ng-synthesized speech fixtures.
Requires whisper.cpp to be built (tools/setup_whisper_cpp.sh); skips
gracefully if not available. See tools/asr_benchmark.py for per-language
accuracy measurement - these tests check the integration works (valid
output shape, language routing, error handling), not WER thresholds.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.asr.whisper_cpp_asr import WhisperCppASR
from core.audio.wav_io import read_wav

LANGUAGES = ["en", "zh", "hi", "es", "ar", "fr", "bn", "pt", "ru"]


@pytest.fixture(scope="module")
def asr(whisper_cpp_available):
    if whisper_cpp_available is None:
        pytest.skip("whisper.cpp not built - run tools/setup_whisper_cpp.sh first")
    binary_path, model_path = whisper_cpp_available
    return WhisperCppASR(binary_path=binary_path, model_path=model_path)


@pytest.mark.parametrize("lang", LANGUAGES)
def test_transcribe_auto_language_returns_nonempty_text(asr, speech_fixtures, lang):
    audio, sr = read_wav(speech_fixtures[lang]["wav_path"])
    result = asr.transcribe(audio, sr)
    assert isinstance(result.text, str)
    assert len(result.text.strip()) > 0
    assert len(result.segments) >= 1


def test_forcing_language_is_honored(asr, speech_fixtures):
    audio, sr = read_wav(speech_fixtures["en"]["wav_path"])
    result = asr.transcribe(audio, sr, language="en")
    assert result.language == "en"


def test_detect_language_matches_transcribe_language(asr, speech_fixtures):
    audio, sr = read_wav(speech_fixtures["en"]["wav_path"])
    detected = asr.detect_language(audio, sr)
    transcribed = asr.transcribe(audio, sr)
    assert detected.language == transcribed.language


def test_segments_have_increasing_non_negative_times(asr, speech_fixtures):
    audio, sr = read_wav(speech_fixtures["en"]["wav_path"])
    result = asr.transcribe(audio, sr, language="en")
    prev_end = -1.0
    for seg in result.segments:
        assert seg.start_s >= 0
        assert seg.end_s >= seg.start_s
        assert seg.start_s >= prev_end - 0.01  # small tolerance for boundary rounding
        prev_end = seg.end_s


def test_wrong_sample_rate_raises(asr):
    audio = np.zeros(8000, dtype=np.int16)
    with pytest.raises(ValueError, match="16000Hz"):
        asr.transcribe(audio, sample_rate_hz=8000)


def test_transcribe_stream_yields_one_result_per_chunk(asr, speech_fixtures):
    audio, sr = read_wav(speech_fixtures["en"]["wav_path"])
    half = len(audio) // 2
    chunks = [audio[:half], audio[half:]]
    results = list(asr.transcribe_stream(iter(chunks), sr, language="en"))
    assert len(results) == 2
