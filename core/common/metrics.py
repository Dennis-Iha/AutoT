"""Minimal in-process metrics system for AT-CORE.

Not a Prometheus/OpenTelemetry integration yet — that belongs to Phase 31
(product metrics dashboards) once there is a backend to ship metrics to. For
now this gives every pipeline stage (audio capture, VAD, and later ASR/MT/TTS)
a consistent, dependency-free way to record counters and latency timers, and
a way to dump a snapshot to JSON for benchmark scripts (Phase 9's
``latency_benchmark.py`` and friends).
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass
class TimerStats:
    count: int = 0
    total_ms: float = 0.0
    min_ms: float = float("inf")
    max_ms: float = 0.0

    def record(self, elapsed_ms: float) -> None:
        self.count += 1
        self.total_ms += elapsed_ms
        self.min_ms = min(self.min_ms, elapsed_ms)
        self.max_ms = max(self.max_ms, elapsed_ms)

    @property
    def avg_ms(self) -> float:
        return self.total_ms / self.count if self.count else 0.0

    def to_dict(self) -> dict:
        return {
            "count": self.count,
            "avg_ms": round(self.avg_ms, 3),
            "min_ms": round(self.min_ms, 3) if self.count else None,
            "max_ms": round(self.max_ms, 3),
            "total_ms": round(self.total_ms, 3),
        }


class Metrics:
    """A named collection of counters and timers.

    Thread-safety note: this class is intentionally not locked. Audio
    callbacks run on a dedicated PortAudio thread; each pipeline stage should
    own its own ``Metrics`` instance rather than sharing one across threads
    without synchronization.
    """

    def __init__(self, namespace: str = ""):
        self.namespace = namespace
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = {}
        self._timers: dict[str, TimerStats] = defaultdict(TimerStats)

    def incr(self, name: str, value: int = 1) -> None:
        self._counters[name] += value

    def gauge(self, name: str, value: float) -> None:
        self._gauges[name] = value

    @contextmanager
    def timer(self, name: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            self._timers[name].record(elapsed_ms)

    def record_ms(self, name: str, elapsed_ms: float) -> None:
        self._timers[name].record(elapsed_ms)

    def snapshot(self) -> dict:
        return {
            "namespace": self.namespace,
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "timers": {name: stats.to_dict() for name, stats in self._timers.items()},
        }
