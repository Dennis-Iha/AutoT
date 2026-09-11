"""Acoustic echo cancellation.

Relevant to AT because the device's own TTS playback can leak back into its
own microphone(s) (speaker-to-mic coupling in a headphone/earbud enclosure).
Unlike noise suppression, this needs a *reference* signal: the far-end audio
that was actually sent to the speaker, which AT always has (it generated
that audio itself), so this is a solvable problem rather than blind source
separation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view


class EchoCanceller(ABC):
    @abstractmethod
    def process(
        self, near_end: np.ndarray, far_end_reference: np.ndarray, sample_rate_hz: int
    ) -> np.ndarray:
        """Remove the far-end echo from the near-end (microphone) signal.

        Args:
            near_end: mic signal - desired near-end speech plus an acoustic
                echo of far_end_reference plus mic noise.
            far_end_reference: the signal that was sent to the speaker, same
                length and sample rate as near_end, time-aligned to it (no
                unknown bulk delay - if the playback path has a known fixed
                delay, align before calling this).

        Returns:
            Echo-cancelled signal, same length/dtype as near_end.
        """
        raise NotImplementedError

    def reset(self) -> None:
        return None


class PassthroughEchoCanceller(EchoCanceller):
    """Explicit identity - e.g. for a build with no speaker/mic coupling."""

    def process(self, near_end, far_end_reference, sample_rate_hz):
        return near_end.copy()


class NLMSEchoCanceller(EchoCanceller):
    """Normalized least-mean-squares adaptive echo canceller.

    Models the acoustic echo path (speaker -> enclosure -> mic) as an
    unknown FIR filter of length ``filter_length`` and adapts an estimate of
    it sample-by-sample from far_end_reference, using NLMS - the same family
    of algorithm real AEC systems (e.g. WebRTC's AEC3) build on, though this
    from-scratch implementation is a baseline for validating the interface
    and measuring ERLE (echo return loss enhancement), not a production
    system: it assumes a linear, time-invariant, single echo path and no
    double-talk handling (near-end speech during echo is not specially
    protected from being partially cancelled too).
    """

    def __init__(self, filter_length: int = 256, step_size: float = 0.5, regularization: float = 1e-6):
        self.filter_length = filter_length
        self.step_size = step_size
        self.regularization = regularization
        self._w = np.zeros(filter_length)

    def reset(self) -> None:
        self._w = np.zeros(self.filter_length)

    def process(
        self, near_end: np.ndarray, far_end_reference: np.ndarray, sample_rate_hz: int
    ) -> np.ndarray:
        if len(near_end) != len(far_end_reference):
            raise ValueError("near_end and far_end_reference must be the same length")

        input_dtype = near_end.dtype
        d = near_end.astype(np.float64)
        x = far_end_reference.astype(np.float64)
        length = self.filter_length

        x_padded = np.concatenate([np.zeros(length - 1), x])
        # windows[n] = [x[n], x[n-1], ..., x[n-L+1]]
        windows = sliding_window_view(x_padded, length)[:, ::-1]

        w = self._w
        mu = self.step_size
        eps = self.regularization
        out = np.empty(len(d))

        for n in range(len(d)):
            x_n = windows[n]
            y_n = w @ x_n
            e_n = d[n] - y_n
            out[n] = e_n
            norm = x_n @ x_n + eps
            w = w + (mu / norm) * e_n * x_n

        self._w = w
        if np.issubdtype(input_dtype, np.integer):
            info = np.iinfo(input_dtype)
            out = np.clip(np.round(out), info.min, info.max)
        return out.astype(input_dtype)
