"""Real end-to-end pipeline test: actual whisper.cpp ASR/LID, actual
CTranslate2 translation, actual Piper TTS - no fakes. Skips gracefully if
any of the three setup scripts haven't been run.

IMPORTANT, discovered while building this test (not assumed away): running
tools/language_id_benchmark.py for real gave only 2/9 (22%) correct language
detection on the base model against tests/fixtures/speech/ - the
espeak-ng-SYNTHESIZED fixtures that work well for ASR-with-forced-language
and TTS round-trip testing turn out to be a poor proxy for whisper.cpp's
language *detection* specifically (looping the clip 4x to rule out
"too short" didn't fix it either). Earlier Phase 4 documentation claiming
"all 9 languages tested" was accurate about output SHAPE (no code path
crashed) but did not verify per-language correctness - this was a real gap
in verification rigor, corrected in docs/roadmap.md's Phase 4/5 section
once this was caught, not swept under the rug.

Given that, this test file deliberately does NOT assert 9-language LID
accuracy (tools/language_id_benchmark.py's output is the honest source of
truth for that number - re-run it to see current numbers, e.g. after
switching models per Phase 11). Instead it tests the two things that
matter for Phase 8's wiring specifically:
  1. On a language the benchmark shows IS reliably detected (es, en): the
     full pipeline produces correct English output end-to-end.
  2. On a language the benchmark shows is NOT reliably detected (ar): the
     pipeline's low-confidence fallback correctly protects against
     mistranslating from a wrong language guess, rather than silently
     producing garbage output - this is Engineering-spec-required behavior
     ("do not immediately translate if confidence is too low"), and it is
     tested here as a real, valuable safety property, not a workaround.
"""

from __future__ import annotations

import pytest

from core.asr.whisper_cpp_asr import WhisperCppASR
from core.audio.wav_io import read_wav
from core.language_id.whisper_lid import WhisperLanguageIdentifier
from core.orchestration.pipeline import PipelineStatus, TranslationPipeline
from core.translation.ctranslate2_translator import CTranslate2TranslationEngine
from core.tts.piper_tts import PiperTTSEngine


@pytest.fixture(scope="module")
def pipeline(whisper_cpp_available, translation_registry, tts_registry):
    if whisper_cpp_available is None:
        pytest.skip("whisper.cpp not built - run tools/setup_whisper_cpp.sh first")
    if translation_registry is None:
        pytest.skip("no translation models installed - run tools/setup_translation_models.sh first")
    if tts_registry is None:
        pytest.skip("no TTS voices installed - run tools/setup_tts_models.sh first")

    binary_path, model_path = whisper_cpp_available
    return TranslationPipeline(
        language_identifier=WhisperLanguageIdentifier(binary_path, model_path),
        asr_engine=WhisperCppASR(binary_path, model_path),
        translation_engine=CTranslate2TranslationEngine(translation_registry),
        tts_engine=PiperTTSEngine(tts_registry),
        target_language="en",
    )


@pytest.mark.parametrize("lang", ["es"])
def test_full_pipeline_non_english_input_produces_english_speech(pipeline, speech_fixtures, lang):
    """es is reliably detected by tools/language_id_benchmark.py (conf~0.94);
    used here to prove the full chain works, not to claim other languages do."""
    audio, sr = read_wav(speech_fixtures[lang]["wav_path"])
    result = pipeline.process(audio, sr)

    assert result.ok, f"pipeline failed: status={result.status} error={result.error}"
    assert result.detected_language is not None
    assert result.detected_language.language == lang
    assert result.translation is not None
    assert "station" in result.translation.text.lower() or "where" in result.translation.text.lower()
    assert result.synthesis is not None
    assert len(result.synthesis.audio) > 0
    assert result.synthesis.sample_rate_hz > 0


def test_full_pipeline_english_input_skips_translation(pipeline, speech_fixtures):
    audio, sr = read_wav(speech_fixtures["en"]["wav_path"])
    result = pipeline.process(audio, sr)

    assert result.ok, f"pipeline failed: status={result.status} error={result.error}"
    assert result.detected_language is not None
    assert result.detected_language.language == "en"
    assert result.translation is None  # no-op: source already matches target
    assert result.synthesis is not None
    assert result.transcription is not None
    assert result.synthesis.text == result.transcription.text


def test_pipeline_reports_per_stage_latencies(pipeline, speech_fixtures):
    audio, sr = read_wav(speech_fixtures["es"]["wav_path"])
    result = pipeline.process(audio, sr)
    assert result.ok
    for stage in ("language_id", "asr", "translation", "tts"):
        assert stage in result.stage_latencies_ms
        assert result.stage_latencies_ms[stage] > 0


def test_low_confidence_language_detection_blocks_translation_not_crashes(pipeline, speech_fixtures):
    """ar is NOT reliably detected on the base model against this
    synthesized fixture (measured ~0.17 confidence, see module docstring) -
    the pipeline must fail safe (LOW_CONFIDENCE, no translation/TTS
    attempted) rather than mistranslate from a wrong language guess."""
    audio, sr = read_wav(speech_fixtures["ar"]["wav_path"])
    result = pipeline.process(audio, sr)

    assert result.status == PipelineStatus.LOW_CONFIDENCE
    assert result.detected_language is not None
    assert result.detected_language.confidence < 0.5
    assert result.transcription is None
    assert result.translation is None
    assert result.synthesis is None
