"""Delay-and-sum beamforming: the simplest real spatial-filtering algorithm,
and the standard first step before more advanced techniques (MVDR, GSC)
that need per-deployment calibration data AT doesn't have without real
hardware. Time-aligns each microphone channel to a reference using a known
(or estimated) per-channel sample delay, then averages - coherent averaging
boosts SNR for a source arriving from the steered direction while
incoherent noise on each channel partially cancels.
"""

from __future__ import annotations

import numpy as np

from core.beamforming.base import Beamformer


def estimate_delay_samples(reference: np.ndarray, other: np.ndarray, max_delay_samples: int) -> int:
    """Estimate the integer-sample delay of ``other`` relative to ``reference``
    via cross-correlation peak search (a plain, single-channel building
    block for calibrating DelaySumBeamformer; not full GCC-PHAT).

    Returns d such that ``other`` is best aligned to ``reference`` by
    shifting it left by d samples (d may be negative).
    """
    reference = reference.astype(np.float64)
    other = other.astype(np.float64)
    correlation = np.correlate(other, reference, mode="full")
    lags = np.arange(-len(reference) + 1, len(other))
    window = (lags >= -max_delay_samples) & (lags <= max_delay_samples)
    best_idx = np.argmax(np.abs(correlation[window]))
    return int(lags[window][best_idx])


def _shift(signal: np.ndarray, delay_samples: int) -> np.ndarray:
    """Shift signal so that output[n] = signal[n + delay_samples], zero-filling
    the exposed edge (i.e. advance the signal by delay_samples)."""
    if delay_samples == 0:
        return signal.copy()
    out = np.zeros_like(signal)
    if delay_samples > 0:
        out[: len(signal) - delay_samples] = signal[delay_samples:]
    else:
        out[-delay_samples:] = signal[: len(signal) + delay_samples]
    return out


class DelaySumBeamformer(Beamformer):
    def __init__(self, channel_delays_samples: list[int]):
        if len(channel_delays_samples) < 1:
            raise ValueError("need at least one channel delay")
        self.channel_delays_samples = list(channel_delays_samples)

    def process(self, multi_channel: np.ndarray, sample_rate_hz: int) -> np.ndarray:
        if multi_channel.ndim != 2:
            raise ValueError(f"expected shape (n_samples, n_channels), got {multi_channel.shape}")
        n_samples, n_channels = multi_channel.shape
        if n_channels != len(self.channel_delays_samples):
            raise ValueError(
                f"multi_channel has {n_channels} channels but "
                f"{len(self.channel_delays_samples)} delays were configured"
            )

        input_dtype = multi_channel.dtype
        aligned = np.zeros((n_samples, n_channels), dtype=np.float64)
        for ch, delay in enumerate(self.channel_delays_samples):
            aligned[:, ch] = _shift(multi_channel[:, ch].astype(np.float64), delay)

        out = aligned.mean(axis=1)
        if np.issubdtype(input_dtype, np.integer):
            info = np.iinfo(input_dtype)
            out = np.clip(np.round(out), info.min, info.max)
        return out.astype(input_dtype)
