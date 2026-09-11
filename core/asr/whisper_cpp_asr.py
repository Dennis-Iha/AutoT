"""ASREngine backed by whisper.cpp (see whisper_cpp_runner.py for the exact
CLI contract this relies on)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import numpy as np

from core.asr.base import ASREngine, LanguageDetectionResult, TranscriptionResult, TranscriptSegment
from core.asr.whisper_cpp_runner import WhisperCppConfig, WhisperCppRunner


class WhisperCppASR(ASREngine):
    def __init__(self, binary_path: Path, model_path: Path, threads: int = 4):
        self._runner = WhisperCppRunner(
            WhisperCppConfig(binary_path=binary_path, model_path=model_path, threads=threads)
        )

    def detect_language(self, audio: np.ndarray, sample_rate_hz: int) -> LanguageDetectionResult:
        language, confidence = self._runner.detect_language(audio, sample_rate_hz)
        return LanguageDetectionResult(language=language, confidence=confidence)

    def transcribe(
        self, audio: np.ndarray, sample_rate_hz: int, language: str | None = None
    ) -> TranscriptionResult:
        data = self._runner.transcribe(audio, sample_rate_hz, language)
        detected_language = data["result"]["language"]
        segments = [
            TranscriptSegment(
                text=seg["text"].strip(),
                start_s=seg["offsets"]["from"] / 1000.0,
                end_s=seg["offsets"]["to"] / 1000.0,
            )
            for seg in data["transcription"]
        ]
        full_text = " ".join(seg.text for seg in segments).strip()
        return TranscriptionResult(text=full_text, language=detected_language, segments=segments)

    def transcribe_stream(
        self, audio_chunks: Iterator[np.ndarray], sample_rate_hz: int, language: str | None = None
    ) -> Iterator[TranscriptionResult]:
        for chunk in audio_chunks:
            yield self.transcribe(chunk, sample_rate_hz, language)
