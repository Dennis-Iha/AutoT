"""Phase 8: the complete software pipeline, wiring together every stage
built in Phases 2-7 behind one call:

    speech segment (int16 PCM, 16kHz)
        -> language identification
        -> ASR (transcribe in the detected language)
        -> translation (detected language -> target language)
        -> TTS (synthesize target-language speech)

This operates on ONE already-segmented utterance at a time (the caller is
responsible for VAD segmentation, e.g. core/vad/segmenter.py) - it does not
do audio capture or playback itself, so it can be tested and reused
independently of any particular audio I/O backend (see tools/at_translate.py
for the live microphone/speaker wiring).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import numpy as np

from core.asr.base import ASREngine, LanguageDetectionResult, TranscriptionResult
from core.language_id.base import LanguageIdentifier
from core.translation.base import TranslationEngine, TranslationResult
from core.tts.base import SynthesisResult, TTSEngine

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    status: str  # see PipelineStatus below
    detected_language: LanguageDetectionResult | None = None
    transcription: TranscriptionResult | None = None
    translation: TranslationResult | None = None
    synthesis: SynthesisResult | None = None
    stage_latencies_ms: dict[str, float] = field(default_factory=dict)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == PipelineStatus.OK


class PipelineStatus:
    OK = "ok"
    LOW_CONFIDENCE = "low_confidence"
    UNSUPPORTED_LANGUAGE = "unsupported_language"
    EMPTY_TRANSCRIPTION = "empty_transcription"
    ERROR = "error"


class TranslationPipeline:
    def __init__(
        self,
        language_identifier: LanguageIdentifier,
        asr_engine: ASREngine,
        translation_engine: TranslationEngine,
        tts_engine: TTSEngine,
        target_language: str = "en",
        tts_voice: str | None = None,
    ):
        self.language_identifier = language_identifier
        self.asr_engine = asr_engine
        self.translation_engine = translation_engine
        self.tts_engine = tts_engine
        self.target_language = target_language
        self.tts_voice = tts_voice

    def process(self, audio: np.ndarray, sample_rate_hz: int) -> PipelineResult:
        latencies: dict[str, float] = {}

        def timed(name, fn, *args):
            start = time.perf_counter()
            result = fn(*args)
            latencies[name] = (time.perf_counter() - start) * 1000.0
            return result

        try:
            detected = timed(
                "language_id", self.language_identifier.identify, audio, sample_rate_hz
            )
        except Exception as e:
            logger.exception("language_id stage failed")
            return PipelineResult(status=PipelineStatus.ERROR, error=str(e), stage_latencies_ms=latencies)

        if not self.language_identifier.is_confident(detected):
            logger.warning(
                "low-confidence language detection: %s (%.2f) - skipping segment",
                detected.language, detected.confidence,
            )
            return PipelineResult(
                status=PipelineStatus.LOW_CONFIDENCE,
                detected_language=detected,
                stage_latencies_ms=latencies,
            )

        source_language = detected.language
        needs_translation = source_language != self.target_language
        if needs_translation and not self.translation_engine.supports_pair(
            source_language, self.target_language
        ):
            logger.warning(
                "no translation model for %s->%s - skipping segment",
                source_language, self.target_language,
            )
            return PipelineResult(
                status=PipelineStatus.UNSUPPORTED_LANGUAGE,
                detected_language=detected,
                stage_latencies_ms=latencies,
            )

        try:
            transcription = timed(
                "asr", self.asr_engine.transcribe, audio, sample_rate_hz, source_language
            )
        except Exception as e:
            logger.exception("ASR stage failed")
            return PipelineResult(
                status=PipelineStatus.ERROR, detected_language=detected, error=str(e),
                stage_latencies_ms=latencies,
            )

        if not transcription.text.strip():
            return PipelineResult(
                status=PipelineStatus.EMPTY_TRANSCRIPTION,
                detected_language=detected,
                transcription=transcription,
                stage_latencies_ms=latencies,
            )

        if needs_translation:
            try:
                translation = timed(
                    "translation", self.translation_engine.translate,
                    transcription.text, source_language, self.target_language,
                )
                target_text = translation.text
            except Exception as e:
                logger.exception("translation stage failed")
                return PipelineResult(
                    status=PipelineStatus.ERROR, detected_language=detected,
                    transcription=transcription, error=str(e), stage_latencies_ms=latencies,
                )
        else:
            # Source already matches the target language - nothing to
            # translate; speak the transcription back directly.
            translation = None
            target_text = transcription.text

        try:
            synthesis = timed(
                "tts", self.tts_engine.synthesize, target_text, self.tts_voice
            )
        except Exception as e:
            logger.exception("TTS stage failed")
            return PipelineResult(
                status=PipelineStatus.ERROR, detected_language=detected,
                transcription=transcription, translation=translation, error=str(e),
                stage_latencies_ms=latencies,
            )

        return PipelineResult(
            status=PipelineStatus.OK,
            detected_language=detected,
            transcription=transcription,
            translation=translation,
            synthesis=synthesis,
            stage_latencies_ms=latencies,
        )
