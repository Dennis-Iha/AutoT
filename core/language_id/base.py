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
#:
#: Raised from 0.5 to 0.65 after Phase 30's tools/performance_sweep.py found
#: a real, worse failure mode at 0.5: three languages (bn 0.55, hi 0.59,
#: zh 0.51 on the synthesized fixtures) cleared the old threshold while
#: being misdetected AS English specifically - which skips translation
#: entirely (source==target) rather than triggering this safeguard, and
#: produces fluent-sounding garbage presented as a valid response. 0.65
#: cleanly separates all 7 currently-unreliable languages (<=0.59) from the
#: 2 verified-working ones (es 0.94, en 0.91) on that same fixture set.
#: Honest limitation: this is a targeted fix for an n=9 synthesized-speech
#: sample, not a calibrated threshold from a precision/recall study - it
#: should be re-validated (and likely re-tuned) once real human-speech data
#: exists, not assumed to generalize. See docs/roadmap.md's Phase 30 section
#: and docs/troubleshooting.md's incident #10.
LOW_CONFIDENCE_THRESHOLD = 0.65


class LanguageIdentifier(ABC):
    @abstractmethod
    def identify(self, audio: np.ndarray, sample_rate_hz: int) -> LanguageDetectionResult:
        raise NotImplementedError

    def is_confident(self, result: LanguageDetectionResult) -> bool:
        return result.confidence >= LOW_CONFIDENCE_THRESHOLD
