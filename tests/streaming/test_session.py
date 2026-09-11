"""Tests StreamingSession's core property: submit() must never block, even
while the worker is deep inside a slow pipeline.process() call - this is
the actual bug (real-time audio callback blocked for tens of seconds) that
motivated building this module. Uses a controllable fake pipeline
(threading.Event-gated) rather than sleep()-based timing races.
"""

from __future__ import annotations

import threading
import time

import numpy as np

from core.streaming.session import StreamingSession

SR = 16000


class GatedFakePipeline:
    """process() blocks until release() is called, then returns a marker
    tied to the input so call order can be verified."""

    def __init__(self):
        self._gate = threading.Event()
        self.call_order: list[bytes] = []
        self.call_started = threading.Event()

    def release(self) -> None:
        self._gate.set()

    def process(self, audio: np.ndarray, sample_rate_hz: int):
        self.call_started.set()
        self._gate.wait(timeout=5)
        self._gate.clear()
        marker = audio.tobytes()
        self.call_order.append(marker)
        return marker  # StreamingSession doesn't care about the exact type


def make_audio(value: int) -> np.ndarray:
    return np.full(10, value, dtype=np.int16)


def test_submit_does_not_block_while_worker_is_busy():
    pipeline = GatedFakePipeline()
    results = []
    session = StreamingSession(pipeline, SR, on_result=results.append)
    try:
        session.submit(make_audio(1))
        assert pipeline.call_started.wait(timeout=2), "worker never picked up first item"

        # Worker is now blocked inside process() for item 1. submit() must
        # return immediately regardless - this is the property that fixes
        # the real-time audio callback deadlock bug.
        start = time.perf_counter()
        session.submit(make_audio(2))
        elapsed = time.perf_counter() - start
        assert elapsed < 0.1, f"submit() blocked for {elapsed:.2f}s - this is the bug being tested for"
    finally:
        pipeline.release()
        pipeline.release()
        session.stop()


def test_results_delivered_in_submission_order():
    pipeline = GatedFakePipeline()
    results = []
    session = StreamingSession(pipeline, SR, on_result=results.append)
    try:
        session.submit(make_audio(1))
        assert pipeline.call_started.wait(timeout=2)
        pipeline.call_started.clear()
        session.submit(make_audio(2))

        pipeline.release()  # let item 1 finish
        assert pipeline.call_started.wait(timeout=2)  # item 2 has started
        pipeline.release()  # let item 2 finish

        deadline = time.perf_counter() + 2
        while len(results) < 2 and time.perf_counter() < deadline:
            time.sleep(0.01)

        assert results == [make_audio(1).tobytes(), make_audio(2).tobytes()]
    finally:
        session.stop()


def test_pending_count_reflects_queue_depth():
    pipeline = GatedFakePipeline()
    session = StreamingSession(pipeline, SR, on_result=lambda r: None)
    try:
        session.submit(make_audio(1))
        assert pipeline.call_started.wait(timeout=2)  # item 1 now being processed, queue empty
        assert session.pending_count == 0

        session.submit(make_audio(2))
        session.submit(make_audio(3))
        deadline = time.perf_counter() + 1
        while session.pending_count < 2 and time.perf_counter() < deadline:
            time.sleep(0.01)
        assert session.pending_count == 2
    finally:
        pipeline.release()
        pipeline.release()
        pipeline.release()
        session.stop()


def test_exception_in_process_does_not_kill_worker():
    class BrokenThenFixedPipeline:
        def __init__(self):
            self.calls = 0

        def process(self, audio, sample_rate_hz):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("boom")
            return "ok"

    pipeline = BrokenThenFixedPipeline()
    results = []
    session = StreamingSession(pipeline, SR, on_result=results.append)
    try:
        session.submit(make_audio(1))  # raises inside worker, should be caught+logged
        session.submit(make_audio(2))  # worker must still be alive to process this
        deadline = time.perf_counter() + 2
        while not results and time.perf_counter() < deadline:
            time.sleep(0.01)
        assert results == ["ok"]
    finally:
        session.stop()


def test_exception_in_on_result_does_not_kill_worker():
    class InstantPipeline:
        def process(self, audio, sample_rate_hz):
            return "result"

    calls = []

    def flaky_on_result(result):
        calls.append(result)
        if len(calls) == 1:
            raise RuntimeError("callback boom")

    session = StreamingSession(InstantPipeline(), SR, on_result=flaky_on_result)
    try:
        session.submit(make_audio(1))
        session.submit(make_audio(2))
        deadline = time.perf_counter() + 2
        while len(calls) < 2 and time.perf_counter() < deadline:
            time.sleep(0.01)
        assert calls == ["result", "result"]
    finally:
        session.stop()


def test_stop_joins_worker_thread():
    class InstantPipeline:
        def process(self, audio, sample_rate_hz):
            return "result"

    session = StreamingSession(InstantPipeline(), SR, on_result=lambda r: None)
    session.stop(wait=True, timeout_s=2)
    assert not session._worker.is_alive()
