"""Phase 9: decouples real-time audio capture from pipeline processing.

This exists to fix a real bug found while building it, not a hypothetical
one: ``core/audio/capture.py``'s ``MicrophoneCapture`` invokes its
``on_frames`` callback directly on PortAudio's real-time audio thread.
Phase 8's ``tools/at_translate.py`` called ``TranslationPipeline.process()``
(measured 17-40+ seconds per segment, see docs/roadmap.md's Phase 9 notes)
and blocking audio playback synchronously from inside that callback - which
blocks the real-time audio thread for the full duration, meaning the
microphone stops being read (segmented, even) while a previous utterance is
still being translated and spoken. This directly contradicts the master
spec's "the program must continuously listen, translate and speak." It was
never caught by Phase 8's tests because the only live-mode smoke test used
3 seconds of silence, so no segment ever reached the blocking code path.

``StreamingSession`` fixes this with a producer/consumer queue: the audio
callback thread calls ``submit()`` (an O(1) queue push, safe to call from a
real-time callback) instead of processing inline; a single background
worker thread drains the queue and runs the (slow) pipeline + playback,
so capture keeps running uninterrupted while a previous segment is still
being processed. This does NOT reduce single-utterance latency (see the
Phase 9 profiling notes in docs/roadmap.md for why: whisper.cpp's own
auto-language-detect implementation pays a full second encoder pass
internally, independent of how this Python layer calls it - not a problem
overlap-driven architecture can fix) - it only prevents lost/unsegmented
speech while a previous segment plays out, and gives the caller visibility
into a growing backlog via ``pending_count``.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable

import numpy as np

from core.orchestration.pipeline import PipelineResult, TranslationPipeline

logger = logging.getLogger(__name__)


class StreamingSession:
    def __init__(
        self,
        pipeline: TranslationPipeline,
        sample_rate_hz: int,
        on_result: Callable[[PipelineResult], None],
    ):
        self.pipeline = pipeline
        self.sample_rate_hz = sample_rate_hz
        self.on_result = on_result
        self._queue: queue.Queue[np.ndarray] = queue.Queue()
        self._stop_event = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True, name="StreamingSessionWorker")
        self._worker.start()

    def submit(self, audio: np.ndarray) -> None:
        """Enqueue a completed speech segment for processing. Non-blocking
        (O(1) queue push) - safe to call from a real-time audio callback."""
        self._queue.put(audio)

    @property
    def pending_count(self) -> int:
        """Segments queued but not yet processed - a growing number means
        the pipeline can't keep up with incoming speech in real time."""
        return self._queue.qsize()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                audio = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if self.pending_count > 0:
                logger.warning(
                    "processing backlog: %d segment(s) still queued behind this one",
                    self.pending_count,
                )
            try:
                result = self.pipeline.process(audio, self.sample_rate_hz)
            except Exception:
                logger.exception("unhandled exception processing streamed segment")
                continue
            try:
                self.on_result(result)
            except Exception:
                logger.exception("on_result callback raised")

    def stop(self, wait: bool = True, timeout_s: float = 5.0) -> None:
        self._stop_event.set()
        if wait:
            self._worker.join(timeout=timeout_s)
