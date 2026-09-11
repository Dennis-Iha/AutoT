"""LanguageIdentifier backed by whisper.cpp's encoder-only detect-language
path (see core/asr/whisper_cpp_runner.py). A separate, smaller model
dedicated purely to LID (e.g. VoxLingua107) would use less compute per call,
but would mean loading and running two different models for what a
multilingual Whisper model already does from one encoder pass - not
justified until benchmarking (Phase 11) shows the shared-model latency is a
real problem."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.asr.base import LanguageDetectionResult
from core.asr.whisper_cpp_runner import WhisperCppConfig, WhisperCppRunner
from core.language_id.base import LanguageIdentifier


class WhisperLanguageIdentifier(LanguageIdentifier):
    def __init__(self, binary_path: Path, model_path: Path, threads: int = 4):
        self._runner = WhisperCppRunner(
            WhisperCppConfig(binary_path=binary_path, model_path=model_path, threads=threads)
        )

    def identify(self, audio: np.ndarray, sample_rate_hz: int) -> LanguageDetectionResult:
        language, confidence = self._runner.detect_language(audio, sample_rate_hz)
        return LanguageDetectionResult(language=language, confidence=confidence)
