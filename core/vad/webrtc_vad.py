"""WebRTC VAD backend.

Wraps the ``webrtcvad`` library (Google's WebRTC voice activity detector,
packaged for Python as a small C extension). This is a real, shipped
implementation, not a placeholder: it is CPU-only, requires no model file,
and runs in well under a millisecond per 20ms frame, which is why it is the
right choice for Phase 1/2 gating before any ASR is involved. Its accuracy on
music/loud non-speech noise is limited (Phase 3's noise suppression /
beamforming work exists partly to make its job easier); that limitation is
tracked, not hidden.
"""

from __future__ import annotations

import numpy as np
import webrtcvad

from core.vad.base import VADEngine


class WebRtcVAD(VADEngine):
    supported_sample_rates: tuple[int, ...] = (8000, 16000, 32000, 48000)
    supported_frame_ms: tuple[int, ...] = (10, 20, 30)

    def __init__(self, aggressiveness: int = 2):
        if aggressiveness not in (0, 1, 2, 3):
            raise ValueError("aggressiveness must be 0-3")
        self._vad = webrtcvad.Vad(aggressiveness)
        self.aggressiveness = aggressiveness

    def is_speech(self, frame: np.ndarray, sample_rate_hz: int) -> bool:
        if sample_rate_hz not in self.supported_sample_rates:
            raise ValueError(
                f"unsupported sample rate {sample_rate_hz}, must be one of "
                f"{self.supported_sample_rates}"
            )
        if frame.ndim != 1:
            raise ValueError(f"frame must be 1-D mono, got shape {frame.shape}")
        if frame.dtype != np.int16:
            raise ValueError(f"frame must be int16 PCM, got dtype {frame.dtype}")

        frame_ms = round(len(frame) * 1000 / sample_rate_hz)
        if frame_ms not in self.supported_frame_ms:
            raise ValueError(
                f"frame length {len(frame)} samples ({frame_ms}ms @ {sample_rate_hz}Hz) "
                f"does not match a supported frame duration {self.supported_frame_ms}"
            )

        return self._vad.is_speech(frame.tobytes(), sample_rate_hz)
