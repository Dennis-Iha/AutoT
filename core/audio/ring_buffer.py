"""Thread-safe ring buffer for streaming PCM audio.

The microphone capture callback (``core/audio/capture.py``) runs on a
dedicated PortAudio callback thread and must never block. It writes into this
ring buffer; consumers (VAD, later ASR streaming) read from it on a separate
thread. Overflow (consumer too slow) drops the oldest samples and is counted,
never raises or blocks the writer.
"""

from __future__ import annotations

import threading

import numpy as np


class AudioRingBuffer:
    """Fixed-capacity ring buffer of mono/interleaved int16 PCM samples."""

    def __init__(self, capacity_samples: int, channels: int = 1):
        if capacity_samples <= 0:
            raise ValueError("capacity_samples must be positive")
        if channels <= 0:
            raise ValueError("channels must be positive")
        self.capacity_samples = capacity_samples
        self.channels = channels
        self._buf = np.zeros((capacity_samples, channels), dtype=np.int16)
        self._write_pos = 0
        self._available = 0
        self._lock = threading.Lock()
        self.dropped_samples = 0

    def write(self, frames: np.ndarray) -> None:
        """Write frames (shape (n, channels) or (n,) for mono). Never blocks."""
        if frames.ndim == 1:
            frames = frames.reshape(-1, 1)
        n = frames.shape[0]
        if n == 0:
            return
        with self._lock:
            if n > self.capacity_samples:
                # Only the most recent capacity_samples matter.
                self.dropped_samples += n - self.capacity_samples
                frames = frames[-self.capacity_samples:]
                n = frames.shape[0]

            end = self._write_pos + n
            if end <= self.capacity_samples:
                self._buf[self._write_pos:end] = frames
            else:
                first_part = self.capacity_samples - self._write_pos
                self._buf[self._write_pos:] = frames[:first_part]
                self._buf[: end - self.capacity_samples] = frames[first_part:]
            self._write_pos = end % self.capacity_samples

            overflow = self._available + n - self.capacity_samples
            if overflow > 0:
                self.dropped_samples += overflow
            self._available = min(self._available + n, self.capacity_samples)

    def read_available(self, max_samples: int | None = None) -> np.ndarray:
        """Drain up to max_samples (default: all available) oldest-first."""
        with self._lock:
            n = self._available if max_samples is None else min(max_samples, self._available)
            if n == 0:
                return np.zeros((0, self.channels), dtype=np.int16)
            start = (self._write_pos - self._available) % self.capacity_samples
            end = start + n
            if end <= self.capacity_samples:
                out = self._buf[start:end].copy()
            else:
                out = np.concatenate([self._buf[start:], self._buf[: end - self.capacity_samples]])
            self._available -= n
            return out

    @property
    def available_samples(self) -> int:
        with self._lock:
            return self._available
