"""Text-to-speech interface."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field

import numpy as np


@dataclass
class SynthesisResult:
    audio: np.ndarray  # mono int16 PCM
    sample_rate_hz: int
    text: str
    voice: str
    timestamp: float = field(default_factory=time.time)


class TTSEngine(ABC):
    @abstractmethod
    def synthesize(self, text: str, voice: str | None = None, speed: float = 1.0) -> SynthesisResult:
        """Synthesize text to speech.

        Args:
            voice: engine-specific voice identifier, or None for the
                engine's default.
            speed: playback speed multiplier (1.0 = normal, >1.0 = faster).
        """
        raise NotImplementedError

    @abstractmethod
    def synthesize_stream(
        self, texts: Iterator[str], voice: str | None = None, speed: float = 1.0
    ) -> Iterator[SynthesisResult]:
        """Synthesize a sequence of independent text chunks (e.g. one per
        translated ASR segment), one result per input - not incremental
        synthesis of a single growing utterance (Phase 9 scope)."""
        raise NotImplementedError

    @abstractmethod
    def available_voices(self) -> list[str]:
        raise NotImplementedError
