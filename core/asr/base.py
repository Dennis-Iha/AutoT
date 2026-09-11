"""Automatic speech recognition interface.

Deliberately narrow, matching the master architecture spec: ``detect_language``,
``transcribe``, ``transcribe_stream``. Language identification is exposed here
too (not only in ``core/language_id/``) because the realistic production
architecture for a Whisper-family model computes both from the same encoder
forward pass - see ``core/language_id/whisper_lid.py`` for why LID is a thin
wrapper around this same backend rather than a separate model.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field

import numpy as np


@dataclass
class LanguageDetectionResult:
    language: str  # ISO 639-1 code, e.g. "es"
    confidence: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class TranscriptSegment:
    text: str
    start_s: float
    end_s: float


@dataclass
class TranscriptionResult:
    text: str
    language: str
    segments: list[TranscriptSegment]
    timestamp: float = field(default_factory=time.time)


class ASREngine(ABC):
    @abstractmethod
    def detect_language(self, audio: np.ndarray, sample_rate_hz: int) -> LanguageDetectionResult:
        """Identify the spoken language of a mono int16 PCM buffer."""
        raise NotImplementedError

    @abstractmethod
    def transcribe(
        self, audio: np.ndarray, sample_rate_hz: int, language: str | None = None
    ) -> TranscriptionResult:
        """Transcribe a mono int16 PCM buffer.

        Args:
            language: ISO 639-1 code to force decoding in that language, or
                None to auto-detect (equivalent to calling detect_language()
                first and decoding with the result).
        """
        raise NotImplementedError

    @abstractmethod
    def transcribe_stream(
        self, audio_chunks: Iterator[np.ndarray], sample_rate_hz: int, language: str | None = None
    ) -> Iterator[TranscriptionResult]:
        """Transcribe a sequence of audio chunks, yielding a result per chunk.

        This is chunk-at-a-time transcription (each yielded result is a full,
        independent decode of the chunk it corresponds to), NOT true
        incremental/partial streaming with progressively refined hypotheses -
        that requires the real-time architecture built in Phase 9. Documented
        here rather than silently implied.
        """
        raise NotImplementedError
