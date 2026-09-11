"""Short-time Fourier transform utilities shared by spectral-domain audio
cleanup algorithms (noise suppression, dereverberation).

This is a block/offline implementation (centered padding, arbitrary-length
buffers in, same-length audio out) suitable for cleaning a whole captured
segment at a time, which is how Phase 3 is used today. A frame-synchronous
causal streaming variant belongs to Phase 9 once the rest of the pipeline is
streaming end-to-end - documented here rather than silently assumed.
"""

from __future__ import annotations

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view


def periodic_hann(frame_size: int) -> np.ndarray:
    """Periodic (DFT-even) Hann window - the correct variant for STFT/ISTFT,
    as opposed to numpy's default symmetric np.hanning()."""
    n = np.arange(frame_size)
    return 0.5 - 0.5 * np.cos(2 * np.pi * n / frame_size)


def stft(signal: np.ndarray, frame_size: int = 512, hop_size: int = 256) -> np.ndarray:
    """Compute a centered STFT of a 1-D real signal.

    Returns a complex array of shape (n_frames, frame_size // 2 + 1). The
    signal is zero-padded by frame_size // 2 samples on each side before
    framing (standard "centered" STFT), so that
    ``istft(stft(x, fs, hs), fs, hs, length=len(x))`` reconstructs ``x``.
    """
    signal = np.asarray(signal, dtype=np.float64)
    window = periodic_hann(frame_size)
    pad = frame_size // 2
    padded = np.pad(signal, (pad, pad))

    n_frames = max(1, 1 + (len(padded) - frame_size) // hop_size)
    needed = (n_frames - 1) * hop_size + frame_size
    if needed > len(padded):
        padded = np.pad(padded, (0, needed - len(padded)))

    frames = sliding_window_view(padded, frame_size)[::hop_size][:n_frames]
    windowed = frames * window
    return np.fft.rfft(windowed, axis=1)


def istft(spec: np.ndarray, frame_size: int = 512, hop_size: int = 256, length: int | None = None) -> np.ndarray:
    """Inverse of ``stft``: weighted overlap-add reconstruction.

    Applies the same analysis window at synthesis time (WOLA) and
    normalizes by the accumulated sum of squared windows, which gives exact
    reconstruction wherever frames overlap enough to keep that sum bounded
    away from zero (true in the interior for Hann + hop <= frame_size/2).
    """
    window = periodic_hann(frame_size)
    frames = np.fft.irfft(spec, n=frame_size, axis=1) * window
    n_frames = frames.shape[0]

    out_len = (n_frames - 1) * hop_size + frame_size
    out = np.zeros(out_len)
    norm = np.zeros(out_len)
    for i in range(n_frames):
        start = i * hop_size
        out[start:start + frame_size] += frames[i]
        norm[start:start + frame_size] += window ** 2
    norm = np.maximum(norm, 1e-8)
    out = out / norm

    pad = frame_size // 2
    out = out[pad:]
    if length is not None:
        out = out[:length]
    return out
