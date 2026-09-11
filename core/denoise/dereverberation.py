"""Single-channel dereverberation.

This is deliberately NOT full WPE (weighted prediction error) - real WPE
needs multiple synchronized microphones and cross-channel linear prediction,
which AT does not have until real multi-mic hardware exists (Phase 13+).
What is implemented here is a real, working, single-channel technique
(spectral-domain late-reverberation subtraction, in the spirit of Lebart et
al. 2001 / Habets 2007): model the reverberant "tail" energy per frequency
bin as an exponentially decaying function of recent frame energy, and
subtract the predicted tail from the current frame before reconstructing.
Labelled honestly as a simplified technique rather than presented as WPE.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from core.denoise.stft import istft, stft


class Dereverberator(ABC):
    @abstractmethod
    def process(self, audio: np.ndarray, sample_rate_hz: int) -> np.ndarray:
        """Reduce reverberant tail energy in a mono int16 PCM buffer."""
        raise NotImplementedError

    def reset(self) -> None:
        return None


class PassthroughDereverberator(Dereverberator):
    """Explicit identity - baseline for A/B benchmarking."""

    def process(self, audio: np.ndarray, sample_rate_hz: int) -> np.ndarray:
        return audio.copy()


class SpectralDereverberator(Dereverberator):
    """Exponential-decay spectral-tail subtraction.

    ``reverb_time_s`` is the assumed RT60 (time for reverberant energy to
    decay 60dB) of the room the recording was made in; it sets the per-hop
    decay factor ``alpha`` of the recursive tail-energy estimate:

        tail_power[i] = alpha * (power[i-1] + tail_power[i-1])
        cleaned_power[i] = max(power[i] - subtraction_factor * tail_power[i],
                                spectral_floor * power[i])

    where ``alpha`` is derived from RT60 so that, left unattenuated, the
    modeled tail decays by 60dB over ``reverb_time_s`` seconds.
    """

    def __init__(
        self,
        frame_size: int = 512,
        hop_size: int = 256,
        reverb_time_s: float = 0.4,
        subtraction_factor: float = 1.0,
        spectral_floor: float = 0.1,
    ):
        self.frame_size = frame_size
        self.hop_size = hop_size
        self.reverb_time_s = reverb_time_s
        self.subtraction_factor = subtraction_factor
        self.spectral_floor = spectral_floor

    def process(self, audio: np.ndarray, sample_rate_hz: int) -> np.ndarray:
        input_dtype = audio.dtype
        x = audio.astype(np.float64)

        spec = stft(x, self.frame_size, self.hop_size)
        mag = np.abs(spec)
        phase = np.angle(spec)
        power = mag ** 2

        hop_duration_s = self.hop_size / sample_rate_hz
        alpha = 10 ** (-6.0 * hop_duration_s / self.reverb_time_s)

        n_frames, n_bins = power.shape
        cleaned_power = np.empty_like(power)
        tail = np.zeros(n_bins)
        for i in range(n_frames):
            cleaned_power[i] = np.maximum(
                power[i] - self.subtraction_factor * tail,
                self.spectral_floor * power[i],
            )
            tail = alpha * (power[i] + tail)

        cleaned_mag = np.sqrt(cleaned_power)
        cleaned_spec = cleaned_mag * np.exp(1j * phase)

        out = istft(cleaned_spec, self.frame_size, self.hop_size, length=len(x))
        if np.issubdtype(input_dtype, np.integer):
            info = np.iinfo(input_dtype)
            out = np.clip(np.round(out), info.min, info.max)
        return out.astype(input_dtype)
