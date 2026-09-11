"""Real TTS tests. Requires tools/setup_tts_models.sh to have been run;
skips gracefully if not available.

The round-trip test is the strongest evidence this module has that Piper's
output is genuinely intelligible speech rather than just "non-silent audio"
- an independent ASR system (whisper.cpp) transcribing the synthesized
audio back to the original text, exactly, is a much stronger signal than
checking peak amplitude or duration.
"""

from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

from core.tts.piper_tts import PiperTTSEngine

ROUND_TRIP_SENTENCES = [
    "Have you eaten today?",
    "Where is the train station?",
    "The weather is very nice this morning.",
]


@pytest.fixture(scope="module")
def engine(tts_registry):
    if tts_registry is None:
        pytest.skip("no TTS voices installed - run tools/setup_tts_models.sh first")
    return PiperTTSEngine(tts_registry)


def test_synthesize_produces_nonempty_nonsilent_audio(engine):
    result = engine.synthesize("Have you eaten today?")
    assert result.audio.dtype == np.int16
    assert len(result.audio) > 0
    assert np.max(np.abs(result.audio)) > 1000  # not silence


def test_synthesize_duration_is_plausible_for_text_length(engine):
    short = engine.synthesize("Hi.")
    long = engine.synthesize("This is a considerably longer sentence than the short one.")
    short_s = len(short.audio) / short.sample_rate_hz
    long_s = len(long.audio) / long.sample_rate_hz
    assert long_s > short_s


def test_speed_multiplier_changes_duration(engine):
    normal = engine.synthesize("Have you eaten today?", speed=1.0)
    fast = engine.synthesize("Have you eaten today?", speed=1.5)
    slow = engine.synthesize("Have you eaten today?", speed=0.7)
    normal_s = len(normal.audio) / normal.sample_rate_hz
    fast_s = len(fast.audio) / fast.sample_rate_hz
    slow_s = len(slow.audio) / slow.sample_rate_hz
    assert fast_s < normal_s < slow_s


def test_available_voices_nonempty(engine):
    assert len(engine.available_voices()) >= 1


def test_unknown_voice_raises(engine):
    with pytest.raises(ValueError, match="voice not ready"):
        engine.synthesize("hello", voice="nonexistent-voice")


def test_unload_frees_cached_voice(engine):
    engine.synthesize("Have you eaten today?")
    assert "en_US-amy-medium" in engine._loaded
    engine.unload("en_US-amy-medium")
    assert "en_US-amy-medium" not in engine._loaded


def test_synthesize_stream_yields_one_result_per_input(engine):
    texts = ["Hello.", "Goodbye."]
    results = list(engine.synthesize_stream(iter(texts)))
    assert len(results) == 2
    assert results[0].text == "Hello."
    assert results[1].text == "Goodbye."


@pytest.mark.parametrize("text", ROUND_TRIP_SENTENCES)
def test_tts_asr_round_trip_matches_original_text(engine, whisper_cpp_available, tmp_path, text):
    """The real quality bar: synthesize with Piper, transcribe back with
    whisper.cpp, and confirm the ASR output matches the original text."""
    if whisper_cpp_available is None:
        pytest.skip("whisper.cpp not built - run tools/setup_whisper_cpp.sh first")
    import subprocess

    from core.asr.wer import word_error_rate
    from core.asr.whisper_cpp_asr import WhisperCppASR
    from core.audio.wav_io import write_wav

    binary_path, model_path = whisper_cpp_available
    asr = WhisperCppASR(binary_path=binary_path, model_path=model_path)

    result = engine.synthesize(text)
    raw_wav = tmp_path / "tts_out.wav"
    write_wav(raw_wav, result.audio, result.sample_rate_hz)

    # whisper.cpp requires 16kHz input; Piper outputs 22050Hz.
    resampled_wav = tmp_path / "tts_out_16k.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw_wav),
         "-ar", "16000", "-ac", "1", str(resampled_wav)],
        check=True,
    )
    audio16, sr16 = sf.read(resampled_wav, dtype="int16")

    transcription = asr.transcribe(audio16, sr16, language="en")
    wer = word_error_rate(text, transcription.text)
    assert wer == 0.0, f"expected exact match, got {transcription.text!r} (wer={wer})"
