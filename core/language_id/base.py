"""Spoken language identification interface.

Returns ``{language, confidence, timestamp}`` per the master architecture
spec, with an explicit low-confidence marker so callers can implement the
required fallback behavior ("do not immediately translate if confidence is
too low") instead of silently trusting every detection.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from core.asr.base import LanguageDetectionResult

#: Below this confidence, callers should treat the detection as unreliable
#: (prompt the user, retry with more audio, or fall back to a default
#: language) rather than routing straight into ASR/translation for it.
LOW_CONFIDENCE_THRESHOLD = 0.5


class LanguageIdentifier(ABC):
    @abstractmethod
    def identify(self, audio: np.ndarray, sample_rate_hz: int) -> LanguageDetectionResult:
        raise NotImplementedError

    def is_confident(self, result: LanguageDetectionResult) -> bool:
        return result.confidence >= LOW_CONFIDENCE_THRESHOLD
