"""Audio pipeline diagnostics: latency, buffer health, CPU/memory usage.

Phase 1 explicitly requires measuring input latency, buffer latency, CPU
usage and memory usage rather than assuming the audio path is fine. This
module is the single place those numbers are collected so every tool
(``tools/mic_vad_demo.py``, later benchmark scripts) reports them the same
way.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

import psutil

from core.common.metrics import Metrics


@dataclass
class AudioDiagnostics:
    metrics: Metrics = field(default_factory=lambda: Metrics(namespace="audio"))
    stream_status_events: list[str] = field(default_factory=list)
    frames_captured: int = 0
    _process: psutil.Process = field(default_factory=lambda: psutil.Process(os.getpid()))
    _start_time: float = field(default_factory=time.perf_counter)

    def record_frames_captured(self, n: int) -> None:
        self.frames_captured += n
        self.metrics.incr("frames_captured", n)

    def record_inter_callback_ms(self, elapsed_ms: float) -> None:
        # A healthy callback cadence should track the configured blocksize
        # duration closely; large deviations indicate scheduling jitter or
        # buffer under/overrun risk.
        self.metrics.record_ms("inter_callback", elapsed_ms)

    def record_stream_status(self, status: str) -> None:
        self.stream_status_events.append(status)
        self.metrics.incr(f"stream_status.{status}")

    def resource_usage(self) -> dict:
        with self._process.oneshot():
            cpu_percent = self._process.cpu_percent(interval=None)
            mem_info = self._process.memory_info()
        return {
            "cpu_percent": cpu_percent,
            "rss_mb": round(mem_info.rss / (1024 * 1024), 2),
            "elapsed_s": round(time.perf_counter() - self._start_time, 3),
        }

    def snapshot(self) -> dict:
        return {
            "frames_captured": self.frames_captured,
            "stream_status_events": list(self.stream_status_events),
            "resource_usage": self.resource_usage(),
            "metrics": self.metrics.snapshot(),
        }
