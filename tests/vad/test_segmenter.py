"""Segmenter state-machine tests.

Uses a scripted fake VAD (returns a pre-programmed sequence of speech/silence
decisions) instead of the real WebRTC VAD, so segmentation timing logic is
tested deterministically and independently of actual speech-detection
accuracy on synthetic audio.
"""

import numpy as np
import pytest

from core.vad.base import VADEngine
from core.vad.segmenter import SpeechSegmenter

SAMPLE_RATE_HZ = 16000
FRAME_MS = 20
FRAME_SAMPLES = SAMPLE_RATE_HZ * FRAME_MS // 1000


class ScriptedVAD(VADEngine):
    """Replays a fixed list of booleans, one per call to is_speech()."""

    def __init__(self, script: list[bool]):
        self.script = list(script)
        self.calls = 0

    def is_speech(self, frame: np.ndarray, sample_rate_hz: int) -> bool:
        value = self.script[self.calls]
        self.calls += 1
        return value

    def reset(self) -> None:
        self.calls = 0


def make_frame(value: int = 0) -> np.ndarray:
    return np.full(FRAME_SAMPLES, value, dtype=np.int16)


def make_segmenter(script: list[bool], min_speech_ms=100, hangover_ms=100, max_segment_ms=2000):
    vad = ScriptedVAD(script)
    return SpeechSegmenter(
        vad=vad,
        sample_rate_hz=SAMPLE_RATE_HZ,
        frame_ms=FRAME_MS,
        min_speech_ms=min_speech_ms,
        hangover_ms=hangover_ms,
        max_segment_ms=max_segment_ms,
    ), vad


def run(segmenter: SpeechSegmenter, script: list[bool]):
    events = []
    for i in range(len(script)):
        seg = segmenter.push(make_frame(value=i + 1))
        if seg is not None:
            events.append(seg)
    return events


def test_pure_silence_produces_no_segments():
    # min_speech_ms=100 -> onset window = 5 frames at 20ms/frame.
    segmenter, _ = make_segmenter(script=[False] * 20)
    events = run(segmenter, [False] * 20)
    assert events == []


def test_sustained_speech_then_silence_produces_one_segment():
    # onset window = 5 frames, offset window = 5 frames (100ms/20ms).
    script = [True] * 10 + [False] * 10
    segmenter, _ = make_segmenter(script=script)
    events = run(segmenter, script)
    assert len(events) == 1
    seg = events[0]
    assert seg.forced_close is False
    assert seg.duration_s > 0
    # Segment audio should include the onset window plus frames while triggered.
    assert seg.audio.shape[0] >= FRAME_SAMPLES * 10


def test_brief_speech_blip_does_not_trigger_segment():
    # Only 2 voiced frames out of a 5-frame onset window -> never crosses
    # the 90% onset ratio, so no segment should start.
    script = [True, True, False, False, False] * 4
    segmenter, _ = make_segmenter(script=script)
    events = run(segmenter, script)
    assert events == []


def test_brief_silence_gap_does_not_split_segment():
    # A single silent frame inside sustained speech should not be enough to
    # cross the 90% offset ratio over a 5-frame window, so this should stay
    # one continuous segment rather than splitting into two.
    script = [True] * 8 + [False] + [True] * 8 + [False] * 10
    segmenter, _ = make_segmenter(script=script)
    events = run(segmenter, script)
    assert len(events) == 1


def test_two_separate_utterances_produce_two_segments():
    script = [True] * 10 + [False] * 10 + [True] * 10 + [False] * 10
    segmenter, _ = make_segmenter(script=script)
    events = run(segmenter, script)
    assert len(events) == 2
    assert events[1].start_time_s > events[0].end_time_s


def test_max_segment_ms_force_closes_long_segment():
    # max_segment_ms=200 -> 10 frames at 20ms; speech never stops.
    script = [True] * 30
    segmenter, _ = make_segmenter(script=script, max_segment_ms=200)
    events = run(segmenter, script)
    assert len(events) >= 1
    assert events[0].forced_close is True


def test_flush_closes_in_progress_segment():
    script = [True] * 10  # never reaches silence naturally
    segmenter, _ = make_segmenter(script=script)
    events = run(segmenter, script)
    assert events == []  # no segment closed yet
    final = segmenter.flush()
    assert final is not None
    assert final.forced_close is True


def test_flush_with_no_active_segment_returns_none():
    segmenter, _ = make_segmenter(script=[False] * 5)
    run(segmenter, [False] * 5)
    assert segmenter.flush() is None


def test_wrong_frame_size_raises():
    segmenter, _ = make_segmenter(script=[False])
    with pytest.raises(ValueError):
        segmenter.push(np.zeros(100, dtype=np.int16))


def test_reset_clears_state():
    script = [True] * 10 + [False] * 10
    segmenter, vad = make_segmenter(script=script)
    run(segmenter, script)
    segmenter.reset()
    assert segmenter.flush() is None
    assert vad.calls == 0


def test_in_segment_reflects_trigger_state():
    # onset/offset windows are 5 frames each (100ms/20ms), ratio 0.9 -> needs
    # 5/5 matching frames to flip. 10 True frames trigger onset at frame
    # index 4 (the 5th); 10 False frames then close it at index 14 (5th
    # consecutive False after the onset window was cleared).
    script = [True] * 10 + [False] * 10
    segmenter, _ = make_segmenter(script=script)
    assert segmenter.in_segment is False
    for i in range(len(script)):
        segmenter.push(make_frame(value=i + 1))
        if i < 4:
            assert segmenter.in_segment is False, f"triggered too early at frame {i}"
        elif i < 14:
            assert segmenter.in_segment is True, f"not triggered at frame {i}"
        else:
            assert segmenter.in_segment is False, f"should have closed by frame {i}"
