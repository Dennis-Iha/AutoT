"""WAV file I/O built on soundfile (libsndfile).

Used for: recording raw diagnostic captures, saving detected speech segments
for inspection, and loading fixture WAVs in tests.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf


def write_wav(path: str | Path, samples: np.ndarray, sample_rate_hz: int) -> None:
    """Write int16 PCM samples (shape (n,) or (n, channels)) to a WAV file."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), samples, sample_rate_hz, subtype="PCM_16")


def read_wav(path: str | Path) -> tuple[np.ndarray, int]:
    """Read a WAV file, returning (int16 samples, sample_rate_hz)."""
    samples, sample_rate_hz = sf.read(str(path), dtype="int16", always_2d=False)
    return samples, sample_rate_hz
