"""Transport abstraction for earbud-to-earbud coordination (Phase 16).

No real BLE hardware exists in this environment to build/test a real
left-right radio link against (see hardware/hardware-selection.md - every
Phase 12 candidate needs a companion BT chip, none acquired). The
coordination PROTOCOL (master election, failure detection, state sync)
is hardware-agnostic distributed-systems logic and can be built and
genuinely tested today against a simulated channel; only the transport
underneath needs to change once real hardware exists (an
``EncryptedBLEChannel`` implementing this same interface).
"""

from __future__ import annotations

import queue
import random
import threading
from abc import ABC, abstractmethod
from typing import Any


class Channel(ABC):
    """One directional endpoint of a two-node link."""

    @abstractmethod
    def send(self, message: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def receive(self, timeout_s: float = 0.1) -> dict[str, Any] | None:
        """Returns None on timeout (no message available) rather than blocking
        indefinitely - callers poll this in a loop, matching how a real radio
        link's non-blocking receive would behave."""
        raise NotImplementedError


class InMemoryChannelPair:
    """Two connected in-process Channels for testing coordination logic
    without real hardware. Supports injecting packet loss and latency to
    exercise the failure-detection/promotion paths the master spec
    explicitly asks to be tested ("packet loss, interference")."""

    def __init__(self, drop_rate: float = 0.0, latency_s: float = 0.0, seed: int | None = None):
        self.drop_rate = drop_rate
        self.latency_s = latency_s
        self._rng = random.Random(seed)
        self._to_b: queue.Queue = queue.Queue()
        self._to_a: queue.Queue = queue.Queue()
        self.a = _QueueChannel(send_q=self._to_b, recv_q=self._to_a, pair=self)
        self.b = _QueueChannel(send_q=self._to_a, recv_q=self._to_b, pair=self)

    def _should_drop(self) -> bool:
        return self.drop_rate > 0 and self._rng.random() < self.drop_rate


class _QueueChannel(Channel):
    def __init__(self, send_q: queue.Queue, recv_q: queue.Queue, pair: InMemoryChannelPair):
        self._send_q = send_q
        self._recv_q = recv_q
        self._pair = pair

    def send(self, message: dict) -> None:
        if self._pair._should_drop():
            return
        if self._pair.latency_s > 0:
            timer = threading.Timer(self._pair.latency_s, self._send_q.put, args=(message,))
            timer.daemon = True
            timer.start()
        else:
            self._send_q.put(message)

    def receive(self, timeout_s: float = 0.1) -> dict | None:
        try:
            return self._recv_q.get(timeout=timeout_s)
        except queue.Empty:
            return None
