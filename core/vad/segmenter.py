"""Speech segmentation on top of a frame-level VAD engine.

This closes the loop that Phase 1/2 asks for: microphone -> audio stream ->
VAD -> speech segment. A ``VADEngine`` only classifies individual fixed-size
frames; ``SpeechSegmenter`` turns that frame-level stream into discrete
speech segments by debouncing onset/offset over configurable windows (so a
single stray voiced or silent frame doesn't start/stop a segment) and
force-closing segments that run past ``max_segment_ms`` so a streaming
pipeline never buffers unbounded audio waiting for silence.

Algorithm (classic "ratio of voiced frames in a sliding window" VAD
collector, as used in the reference webrtcvad examples):

  * While not in a segment: keep a ring of the last ``onset_window_frames``
    (frame, is_speech) pairs. Once more than ``onset_ratio`` of them are
    speech, a segment starts, seeded with that whole window's audio (so the
    speech that triggered detection isn't lost).
  * While in a segment: every frame is appended to the segment. Keep a
    second ring of the last ``offset_window_frames`` pairs; once more than
    ``offset_ratio`` of them are silence, or the segment has run for
    ``max_segment_ms``, the segment ends.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from core.vad.base import VADEngine

ONSET_RATIO = 0.9
OFFSET_RATIO = 0.9


@dataclass
class SpeechSegment:
    audio: np.ndarray  # (n, channels) or (n,) int16 PCM
    start_time_s: float
    end_time_s: float
    forced_close: bool = False  # True if closed by max_segment_ms, not silence

    @property
    def duration_s(self) -> float:
        return self.end_time_s - self.start_time_s


class SpeechSegmenter:
    def __init__(
        self,
        vad: VADEngine,
        sample_rate_hz: int = 16000,
        frame_ms: int = 20,
        min_speech_ms: int = 200,
        hangover_ms: int = 300,
        max_segment_ms: int = 20000,
    ):
        self.vad = vad
        self.sample_rate_hz = sample_rate_hz
        self.frame_ms = frame_ms
        self.frame_samples = round(sample_rate_hz * frame_ms / 1000)

        self.onset_window_frames = max(1, round(min_speech_ms / frame_ms))
        self.offset_window_frames = max(1, round(hangover_ms / frame_ms))
        self.max_segment_frames = max(1, round(max_segment_ms / frame_ms))

        self._onset_ring: deque[tuple[np.ndarray, bool]] = deque(maxlen=self.onset_window_frames)
        self._offset_ring: deque[bool] = deque(maxlen=self.offset_window_frames)
        self._triggered = False
        self._voiced_frames: list[np.ndarray] = []
        self._segment_start_frame_idx = 0
        self._frame_idx = 0

    def reset(self) -> None:
        self._onset_ring.clear()
        self._offset_ring.clear()
        self._triggered = False
        self._voiced_frames = []
        self._frame_idx = 0
        self.vad.reset()

    def push(self, frame: np.ndarray) -> SpeechSegment | None:
        """Feed one frame of exactly ``frame_samples`` samples.

        Returns a completed ``SpeechSegment`` if this frame closed one,
        otherwise None. Call repeatedly as frames arrive from the ring
        buffer/microphone.
        """
        if len(frame) != self.frame_samples:
            raise ValueError(
                f"expected frame of {self.frame_samples} samples "
                f"({self.frame_ms}ms @ {self.sample_rate_hz}Hz), got {len(frame)}"
            )

        is_speech = self.vad.is_speech(frame, self.sample_rate_hz)
        result: SpeechSegment | None = None

        if not self._triggered:
            self._onset_ring.append((frame, is_speech))
            ring_full = len(self._onset_ring) == self.onset_window_frames
            voiced_count = sum(1 for _, s in self._onset_ring if s)
            if ring_full and voiced_count > ONSET_RATIO * self.onset_window_frames:
                self._triggered = True
                self._segment_start_frame_idx = self._frame_idx - self.onset_window_frames + 1
                self._voiced_frames = [f for f, _ in self._onset_ring]
                self._onset_ring.clear()
                self._offset_ring.clear()
        else:
            self._voiced_frames.append(frame)
            self._offset_ring.append(is_speech)
            ring_full = len(self._offset_ring) == self.offset_window_frames
            silent_count = sum(1 for s in self._offset_ring if not s)
            timed_out = len(self._voiced_frames) >= self.max_segment_frames
            should_close = timed_out or (
                ring_full and silent_count > OFFSET_RATIO * self.offset_window_frames
            )
            if should_close:
                result = self._close_segment(forced_close=timed_out)

        self._frame_idx += 1
        return result

    def flush(self) -> SpeechSegment | None:
        """Force-close an in-progress segment (e.g. on stream stop)."""
        if not self._triggered:
            return None
        return self._close_segment(forced_close=True)

    def _close_segment(self, forced_close: bool) -> SpeechSegment:
        audio = np.concatenate(self._voiced_frames, axis=0)
        start_s = self._segment_start_frame_idx * self.frame_ms / 1000.0
        end_s = (self._frame_idx + 1) * self.frame_ms / 1000.0
        segment = SpeechSegment(
            audio=audio, start_time_s=start_s, end_time_s=end_s, forced_close=forced_close
        )
        self._triggered = False
        self._voiced_frames = []
        self._onset_ring.clear()
        self._offset_ring.clear()
        return segment
