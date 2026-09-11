"""Deterministic tests of the orchestration logic using fake components -
no real models involved, so these run fast and test the STATE MACHINE
(fallback on low confidence, unsupported pairs, empty transcription, error
propagation, source==target short-circuit), not model accuracy. Real
end-to-end behavior with actual models is covered by
tests/orchestration/test_pipeline_live.py (skips if models aren't set up).
"""

from __future__ import annotations

import numpy as np
import pytest

from core.asr.base import ASREngine, LanguageDetectionResult, TranscriptionResult, TranscriptSegment
from core.language_id.base import LanguageIdentifier
from core.orchestration.pipeline import PipelineStatus, TranslationPipeline
from core.translation.base import TranslationEngine, TranslationResult
from core.tts.base import SynthesisResult, TTSEngine

SR = 16000


class FakeLanguageIdentifier(LanguageIdentifier):
    def __init__(self, language="es", confidence=0.9):
        self.language = language
        self.confidence = confidence

    def identify(self, audio, sample_rate_hz):
        return LanguageDetectionResult(language=self.language, confidence=self.confidence)


class FakeASR(ASREngine):
    def __init__(self, text="hola"):
        self.text = text

    def detect_language(self, audio, sample_rate_hz):
        raise NotImplementedError

    def transcribe(self, audio, sample_rate_hz, language=None):
        return TranscriptionResult(
            text=self.text, language=language or "es",
            segments=[TranscriptSegment(text=self.text, start_s=0.0, end_s=1.0)],
        )

    def transcribe_stream(self, audio_chunks, sample_rate_hz, language=None):
        raise NotImplementedError


class FakeTranslation(TranslationEngine):
    def __init__(self, supported_pairs=(("es", "en"),), output_text="hello"):
        self.supported_pairs = set(supported_pairs)
        self.output_text = output_text
        self.calls = []

    def supports_pair(self, source_language, target_language):
        return (source_language, target_language) in self.supported_pairs

    def translate(self, text, source_language, target_language):
        self.calls.append((text, source_language, target_language))
        return TranslationResult(
            text=self.output_text, source_language=source_language, target_language=target_language
        )

    def translate_stream(self, texts, source_language, target_language):
        raise NotImplementedError


class FakeTTS(TTSEngine):
    def __init__(self):
        self.calls = []

    def synthesize(self, text, voice=None, speed=1.0):
        self.calls.append(text)
        return SynthesisResult(
            audio=np.zeros(100, dtype=np.int16), sample_rate_hz=22050, text=text, voice=voice or "default"
        )

    def synthesize_stream(self, texts, voice=None, speed=1.0):
        raise NotImplementedError

    def available_voices(self):
        return ["default"]


def make_pipeline(**overrides):
    defaults = {
        "language_identifier": FakeLanguageIdentifier(),
        "asr_engine": FakeASR(),
        "translation_engine": FakeTranslation(),
        "tts_engine": FakeTTS(),
        "target_language": "en",
    }
    defaults.update(overrides)
    return TranslationPipeline(**defaults)


def make_audio():
    return np.zeros(SR, dtype=np.int16)


def test_happy_path_full_pipeline():
    pipeline = make_pipeline()
    result = pipeline.process(make_audio(), SR)
    assert result.ok
    assert result.status == PipelineStatus.OK
    assert result.detected_language.language == "es"
    assert result.transcription.text == "hola"
    assert result.translation.text == "hello"
    assert result.synthesis.text == "hello"
    assert set(result.stage_latencies_ms.keys()) == {"language_id", "asr", "translation", "tts"}


def test_low_confidence_skips_everything_downstream():
    pipeline = make_pipeline(language_identifier=FakeLanguageIdentifier(confidence=0.1))
    result = pipeline.process(make_audio(), SR)
    assert result.status == PipelineStatus.LOW_CONFIDENCE
    assert result.transcription is None
    assert result.synthesis is None


def test_unsupported_language_pair_skips_asr():
    asr = FakeASR()
    pipeline = make_pipeline(
        language_identifier=FakeLanguageIdentifier(language="xx"),
        asr_engine=asr,
        translation_engine=FakeTranslation(supported_pairs=(("es", "en"),)),
    )
    result = pipeline.process(make_audio(), SR)
    assert result.status == PipelineStatus.UNSUPPORTED_LANGUAGE
    assert result.transcription is None


def test_empty_transcription_skips_translation_and_tts():
    translation = FakeTranslation()
    pipeline = make_pipeline(asr_engine=FakeASR(text="   "), translation_engine=translation)
    result = pipeline.process(make_audio(), SR)
    assert result.status == PipelineStatus.EMPTY_TRANSCRIPTION
    assert result.translation is None
    assert translation.calls == []


def test_source_equals_target_skips_translation_but_still_speaks():
    translation = FakeTranslation()
    tts = FakeTTS()
    pipeline = make_pipeline(
        language_identifier=FakeLanguageIdentifier(language="en"),
        asr_engine=FakeASR(text="hello there"),
        translation_engine=translation,
        tts_engine=tts,
        target_language="en",
    )
    result = pipeline.process(make_audio(), SR)
    assert result.ok
    assert result.translation is None
    assert translation.calls == []
    assert tts.calls == ["hello there"]
    assert result.synthesis.text == "hello there"


def test_language_id_exception_reported_as_error():
    class BrokenLID(LanguageIdentifier):
        def identify(self, audio, sample_rate_hz):
            raise RuntimeError("boom")

    pipeline = make_pipeline(language_identifier=BrokenLID())
    result = pipeline.process(make_audio(), SR)
    assert result.status == PipelineStatus.ERROR
    assert "boom" in result.error


def test_asr_exception_reported_as_error_with_language_preserved():
    class BrokenASR(ASREngine):
        def detect_language(self, audio, sample_rate_hz):
            raise NotImplementedError

        def transcribe(self, audio, sample_rate_hz, language=None):
            raise RuntimeError("asr boom")

        def transcribe_stream(self, audio_chunks, sample_rate_hz, language=None):
            raise NotImplementedError

    pipeline = make_pipeline(asr_engine=BrokenASR())
    result = pipeline.process(make_audio(), SR)
    assert result.status == PipelineStatus.ERROR
    assert result.detected_language is not None
    assert "asr boom" in result.error


def test_tts_exception_reported_as_error_with_translation_preserved():
    class BrokenTTS(TTSEngine):
        def synthesize(self, text, voice=None, speed=1.0):
            raise RuntimeError("tts boom")

        def synthesize_stream(self, texts, voice=None, speed=1.0):
            raise NotImplementedError

        def available_voices(self):
            return []

    pipeline = make_pipeline(tts_engine=BrokenTTS())
    result = pipeline.process(make_audio(), SR)
    assert result.status == PipelineStatus.ERROR
    assert result.translation is not None
    assert "tts boom" in result.error


@pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0])
def test_confidence_boundary_matches_language_identifier_threshold(confidence):
    from core.language_id.base import LOW_CONFIDENCE_THRESHOLD

    pipeline = make_pipeline(language_identifier=FakeLanguageIdentifier(confidence=confidence))
    result = pipeline.process(make_audio(), SR)
    expected_ok = confidence >= LOW_CONFIDENCE_THRESHOLD
    assert result.ok == expected_ok
