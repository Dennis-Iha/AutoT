"""Phase 21: proves - rather than merely asserts in a doc - that AT never
persists a user's raw speech to disk during normal operation.

core/orchestration/pipeline.py's TranslationPipeline.process() itself only
ever touches in-memory numpy arrays, which is true by inspection. But that
alone is not the whole story: its ASR/LID stage (core/asr/whisper_cpp_runner.py)
shells out to the whisper.cpp CLI, which requires a real file path (no
stdin/in-memory API in the mode this project uses) - so raw audio DOES
briefly touch disk as a temp WAV file, once for language ID and again for
transcription (the two-encoder-pass architecture documented in Phase 9).
That file is unlinked in a `finally` block immediately after each call.

This file tests that the cleanup actually holds, including on the failure
path (a crashed/killed process obviously can't run its own `finally` -
that residual-risk gap is real and is documented, not hidden, in
docs/privacy.md), and that the full pipeline leaves no new files anywhere
under the system temp directory after processing real speech end-to-end.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from core.asr.whisper_cpp_asr import WhisperCppASR
from core.asr.whisper_cpp_runner import WhisperCppConfig, WhisperCppRunner
from core.audio.wav_io import read_wav
from core.language_id.whisper_lid import WhisperLanguageIdentifier
from core.orchestration.pipeline import TranslationPipeline
from core.translation.ctranslate2_translator import CTranslate2TranslationEngine
from core.tts.piper_tts import PiperTTSEngine


def _temp_dir_snapshot() -> set[str]:
    return {p.name for p in Path(tempfile.gettempdir()).iterdir()}


def test_runner_cleans_up_temp_wav_even_when_subprocess_call_raises(tmp_path, monkeypatch):
    """Fake-based, no whisper.cpp binary required: proves the `finally`
    block in WhisperCppRunner._run's callers actually removes the temp WAV
    even when the subprocess step raises - the failure-path guarantee that
    matters most, since a crash is exactly when persisted audio would be
    most likely to be forgotten."""
    fake_binary = tmp_path / "whisper-cli"
    fake_model = tmp_path / "model.bin"
    fake_binary.write_bytes(b"not a real binary")
    fake_model.write_bytes(b"not a real model")

    runner = WhisperCppRunner(WhisperCppConfig(binary_path=fake_binary, model_path=fake_model))

    written_paths: list[Path] = []
    original_write_temp_wav = runner._write_temp_wav

    def spy_write_temp_wav(audio, sample_rate_hz):
        path = original_write_temp_wav(audio, sample_rate_hz)
        written_paths.append(path)
        return path

    monkeypatch.setattr(runner, "_write_temp_wav", spy_write_temp_wav)
    monkeypatch.setattr(runner, "_run", lambda args: (_ for _ in ()).throw(RuntimeError("simulated crash")))

    audio = np.zeros(16000, dtype=np.int16)
    with pytest.raises(RuntimeError, match="simulated crash"):
        runner.detect_language(audio, 16000)

    assert len(written_paths) == 1, "expected exactly one temp WAV to have been written"
    assert not written_paths[0].exists(), "temp WAV must be deleted even when the subprocess call raises"


def test_runner_cleans_up_temp_files_after_real_detect_language(whisper_cpp_available, speech_fixtures):
    if whisper_cpp_available is None:
        pytest.skip("whisper.cpp not built - run tools/setup_whisper_cpp.sh first")
    binary_path, model_path = whisper_cpp_available
    runner = WhisperCppRunner(WhisperCppConfig(binary_path=binary_path, model_path=model_path))
    audio, sr = read_wav(speech_fixtures["es"]["wav_path"])

    before = _temp_dir_snapshot()
    runner.detect_language(audio, sr)
    after = _temp_dir_snapshot()

    assert after == before, f"detect_language leaked temp files: {after - before}"


def test_runner_cleans_up_temp_files_after_real_transcribe(whisper_cpp_available, speech_fixtures):
    if whisper_cpp_available is None:
        pytest.skip("whisper.cpp not built - run tools/setup_whisper_cpp.sh first")
    binary_path, model_path = whisper_cpp_available
    runner = WhisperCppRunner(WhisperCppConfig(binary_path=binary_path, model_path=model_path))
    audio, sr = read_wav(speech_fixtures["es"]["wav_path"])

    before = _temp_dir_snapshot()
    runner.transcribe(audio, sr, language="es")
    after = _temp_dir_snapshot()

    assert after == before, f"transcribe leaked temp files: {after - before}"


def test_full_pipeline_leaves_no_new_temp_files(
    whisper_cpp_available, translation_registry, tts_registry, speech_fixtures
):
    """The strongest end-to-end version of this claim: run real LID -> ASR ->
    translation -> TTS on real recorded speech (the same path a live device
    would use per utterance) and confirm the system temp directory is
    byte-for-byte the same set of filenames before and after - the user's
    voice never ends up as a file anyone could read once processing is
    done."""
    if whisper_cpp_available is None:
        pytest.skip("whisper.cpp not built - run tools/setup_whisper_cpp.sh first")
    if translation_registry is None:
        pytest.skip("no translation models installed - run tools/setup_translation_models.sh first")
    if tts_registry is None:
        pytest.skip("no TTS voices installed - run tools/setup_tts_models.sh first")

    binary_path, model_path = whisper_cpp_available
    pipeline = TranslationPipeline(
        language_identifier=WhisperLanguageIdentifier(binary_path, model_path),
        asr_engine=WhisperCppASR(binary_path, model_path),
        translation_engine=CTranslate2TranslationEngine(translation_registry),
        tts_engine=PiperTTSEngine(tts_registry),
        target_language="en",
    )
    audio, sr = read_wav(speech_fixtures["es"]["wav_path"])

    before = _temp_dir_snapshot()
    result = pipeline.process(audio, sr)
    after = _temp_dir_snapshot()

    assert result.ok, f"pipeline failed: status={result.status} error={result.error}"
    assert after == before, f"full pipeline leaked temp files: {after - before}"
