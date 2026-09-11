"""Audio playback via PortAudio (sounddevice) - the mirror of capture.py.
Needed by Phase 8's full pipeline to actually speak the TTS output.
"""

from __future__ import annotations

import logging

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)


class AudioPlayback:
    def __init__(self, device: str | int | None = None):
        self.device = device

    def play(self, audio: np.ndarray, sample_rate_hz: int, blocking: bool = True) -> None:
        """Play an int16 (or float) PCM buffer. PortAudio/the OS handles
        rate conversion if sample_rate_hz differs from the device's native
        rate, so callers don't need to resample first."""
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0
        sd.play(audio, samplerate=sample_rate_hz, device=self.device)
        if blocking:
            sd.wait()

    def stop(self) -> None:
        sd.stop()
