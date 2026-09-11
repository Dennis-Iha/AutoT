"""Tests the parts of tools/latency_benchmark.py that don't need real
hardware (mic/speaker) or downloaded models - those are validated manually,
see docs/roadmap.md's Phase 9 section for real measured numbers."""

import numpy as np

from tools.latency_benchmark import measure_vad_segmentation_latency

SR = 16000


def test_vad_segmentation_latency_is_positive_and_fast():
    audio = np.zeros(SR * 2, dtype=np.int16)  # 2s of silence
    latency_ms = measure_vad_segmentation_latency(audio, SR)
    assert latency_ms > 0
    # Segmenting 2s of audio should take well under 2s of wall clock on any
    # reasonable machine - this is a sanity bound, not a tight benchmark.
    assert latency_ms < 2000


def test_vad_segmentation_latency_scales_roughly_with_audio_length():
    short = np.zeros(SR, dtype=np.int16)
    long = np.zeros(SR * 5, dtype=np.int16)
    short_ms = measure_vad_segmentation_latency(short, SR)
    long_ms = measure_vad_segmentation_latency(long, SR)
    assert long_ms >= short_ms
