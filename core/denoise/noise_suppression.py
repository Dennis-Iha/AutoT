"""Noise suppression.

Operates on an arbitrary-length audio buffer (e.g. a detected speech
segment from ``core/vad/segmenter.py``), not on fixed 20ms VAD frames -
spectral estimation needs more context than a single VAD frame provides.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from core.denoise.stft import istft, stft


class NoiseSuppressor(ABC):
    @abstractmethod
    def process(self, audio: np.ndarray, sample_rate_hz: int) -> np.ndarray:
        """Denoise a mono int16 PCM buffer. Returns an int16 buffer of the same length."""
        raise NotImplementedError

    def reset(self) -> None:
        return None


class PassthroughNoiseSuppressor(NoiseSuppressor):
    """Explicit identity. Used when a downstream hardware DSP/NPU (Phase 14)
    already performs noise suppression upstream of this pipeline stage, or
    as a baseline for A/B benchmarking against a real algorithm."""

    def process(self, audio: np.ndarray, sample_rate_hz: int) -> np.ndarray:
        return audio.copy()


class SpectralSubtractionNoiseSuppressor(NoiseSuppressor):
    """Spectral subtraction with a causal minimum-statistics noise floor.

    Classic Boll (1979) style spectral subtraction: subtract an estimate of
    the stationary noise magnitude spectrum from each frame's magnitude,
    keep the original (noisy) phase, and reconstruct. The noise estimate is
    NOT taken from a fixed "noise-only" lead-in (real captured segments
    often start right at speech onset, per the Phase 2 segmenter) - instead
    each frequency bin's noise floor is the running minimum of its
    magnitude over the last ``noise_window_frames`` frames, a simplified,
    single-channel version of Martin's (2001) minimum-statistics method.
    This works because stationary noise is present in every frame while
    speech energy in any given bin is intermittent, so the per-bin minimum
    over a long-enough window tracks the noise floor even without silence.

    An over-subtraction factor and spectral floor control the classic
    tradeoff between residual noise and "musical noise" artifacts. The
    default over_subtraction=4.0 is higher than the textbook "subtract the
    noise estimate once" value of 1.0 because the min-of-N-frames estimate
    above is a systematic *underestimate* of the true noise floor (the
    minimum of many random samples sits well below their mean); measured on
    a synthetic white-noise benchmark, over_subtraction=4.0 gave ~6dB noise
    reduction while retaining ~72% of in-band speech energy, consistent
    with the 3-6 range Berouti et al. (1979) recommend for stationary
    noise - see tests/denoise/test_noise_suppression.py for the measurement.
    """

    def __init__(
        self,
        frame_size: int = 512,
        hop_size: int = 256,
        over_subtraction: float = 4.0,
        spectral_floor: float = 0.05,
        noise_window_frames: int = 40,
    ):
        self.frame_size = frame_size
        self.hop_size = hop_size
        self.over_subtraction = over_subtraction
        self.spectral_floor = spectral_floor
        self.noise_window_frames = noise_window_frames

    def process(self, audio: np.ndarray, sample_rate_hz: int) -> np.ndarray:
        input_dtype = audio.dtype
        x = audio.astype(np.float64)

        spec = stft(x, self.frame_size, self.hop_size)
        mag = np.abs(spec)
        phase = np.angle(spec)

        n_frames = mag.shape[0]
        window = min(self.noise_window_frames, n_frames)
        padded_mag = np.pad(mag, ((window - 1, 0), (0, 0)), mode="edge")
        noise_mag = sliding_window_view(padded_mag, window, axis=0).min(axis=-1)

        cleaned_mag = np.maximum(
            mag - self.over_subtraction * noise_mag,
            self.spectral_floor * mag,
        )
        cleaned_spec = cleaned_mag * np.exp(1j * phase)

        out = istft(cleaned_spec, self.frame_size, self.hop_size, length=len(x))
        if np.issubdtype(input_dtype, np.integer):
            info = np.iinfo(input_dtype)
            out = np.clip(np.round(out), info.min, info.max)
        return out.astype(input_dtype)
