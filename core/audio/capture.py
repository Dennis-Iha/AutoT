"""Microphone capture via PortAudio (sounddevice).

``MicrophoneCapture`` opens an input stream on a background PortAudio thread
and pushes every incoming block into an ``AudioRingBuffer``. It records
timing diagnostics (callback latency, over/underflow flags reported by
PortAudio) into an ``AudioDiagnostics`` instance so Phase 1's latency/CPU
measurement requirement is met from the start, not bolted on later.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Self

import numpy as np
import sounddevice as sd

from core.audio.diagnostics import AudioDiagnostics
from core.audio.ring_buffer import AudioRingBuffer

logger = logging.getLogger(__name__)

FrameCallback = Callable[[np.ndarray], None]


class MicrophoneCapture:
    def __init__(
        self,
        sample_rate_hz: int = 16000,
        channels: int = 1,
        blocksize_samples: int = 320,
        device: str | int | None = None,
        ring_buffer_seconds: float = 10.0,
        on_frames: FrameCallback | None = None,
    ):
        self.sample_rate_hz = sample_rate_hz
        self.channels = channels
        self.blocksize_samples = blocksize_samples
        self.device = device
        self.on_frames = on_frames

        self.ring_buffer = AudioRingBuffer(
            capacity_samples=int(ring_buffer_seconds * sample_rate_hz),
            channels=channels,
        )
        self.diagnostics = AudioDiagnostics()
        self._stream: sd.InputStream | None = None
        self._last_callback_time: float | None = None

    def _callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        now = time.perf_counter()
        if status:
            self.diagnostics.record_stream_status(str(status))
        if self._last_callback_time is not None:
            inter_callback_ms = (now - self._last_callback_time) * 1000.0
            self.diagnostics.record_inter_callback_ms(inter_callback_ms)
        self._last_callback_time = now

        pcm = (indata * 32767.0).astype(np.int16) if indata.dtype != np.int16 else indata
        self.diagnostics.record_frames_captured(frames)
        self.ring_buffer.write(pcm)
        if self.on_frames is not None:
            self.on_frames(pcm)

    def start(self) -> None:
        if self._stream is not None:
            raise RuntimeError("MicrophoneCapture already started")
        self._stream = sd.InputStream(
            samplerate=self.sample_rate_hz,
            channels=self.channels,
            blocksize=self.blocksize_samples,
            dtype="float32",
            device=self.device,
            callback=self._callback,
        )
        self._stream.start()
        logger.info(
            "microphone stream started sample_rate=%d channels=%d blocksize=%d device=%r",
            self.sample_rate_hz,
            self.channels,
            self.blocksize_samples,
            self.device,
        )

    def stop(self) -> None:
        if self._stream is None:
            return
        self._stream.stop()
        self._stream.close()
        self._stream = None
        logger.info("microphone stream stopped")

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
