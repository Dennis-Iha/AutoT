"""Voice Activity Detection interface.

Kept deliberately narrow: a VAD engine classifies one fixed-size frame of PCM
audio as speech or not-speech. All temporal logic (onset/offset debouncing,
hangover, segment assembly) lives in ``core/vad/segmenter.py`` on top of this,
so a different VAD backend (e.g. a future Silero-VAD or hardware VAD) can be
swapped in without touching segmentation logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class VADEngine(ABC):
    """Frame-level speech/non-speech classifier."""

    #: Sample rates the backend supports, in Hz.
    supported_sample_rates: tuple[int, ...] = (8000, 16000, 32000, 48000)
    #: Frame durations the backend supports, in milliseconds.
    supported_frame_ms: tuple[int, ...] = (10, 20, 30)

    @abstractmethod
    def is_speech(self, frame: np.ndarray, sample_rate_hz: int) -> bool:
        """Classify a single mono int16 PCM frame.

        Args:
            frame: 1-D int16 array of exactly ``sample_rate_hz * frame_ms / 1000``
                samples. Implementations must validate this and raise
                ``ValueError`` on a malformed frame rather than guessing.
            sample_rate_hz: Sample rate of ``frame``; must be one of
                ``supported_sample_rates``.

        Returns:
            True if the frame is classified as speech.
        """
        raise NotImplementedError

    def reset(self) -> None:
        """Clear any internal state. Default no-op for stateless backends."""
        return
