"""Measures reduction of reverberant tail energy on a synthetically
reverberated signal (dry signal convolved with a synthetic decaying-noise
room impulse response), not just that the code runs.
"""

import numpy as np

from core.denoise.dereverberation import PassthroughDereverberator, SpectralDereverberator

SR = 16000


def _db(power: float) -> float:
    return 10 * np.log10(max(power, 1e-12))


def _make_reverberant_signal(seed=42):
    rng = np.random.default_rng(seed)
    n = int(1.0 * SR)
    dry_len = int(0.3 * SR)
    t = np.arange(n) / SR
    tone = sum(np.sin(2 * np.pi * f * t) for f in (200, 400, 800)) * 3000 / 3
    dry = np.zeros(n)
    dry[:dry_len] = tone[:dry_len]

    rir_len = int(0.5 * SR)
    tau = 0.15 * SR
    rir = rng.normal(0, 1, rir_len) * np.exp(-np.arange(rir_len) / tau)
    rir[0] = 3.0  # dominant direct path

    wet = np.convolve(dry, rir)[:n]
    wet = np.clip(wet / np.max(np.abs(wet)) * 20000, -32768, 32767).astype(np.int16)
    # Reverberant tail region: after the dry signal has stopped (0.3s) but
    # before the RIR's energy has fully decayed away.
    tail_region = slice(int(0.5 * SR), int(0.9 * SR))
    return wet, tail_region


def test_passthrough_is_identity():
    wet, _ = _make_reverberant_signal()
    out = PassthroughDereverberator().process(wet, SR)
    np.testing.assert_array_equal(out, wet)


def test_reduces_reverberant_tail_energy():
    wet, tail_region = _make_reverberant_signal()
    dewet = SpectralDereverberator(reverb_time_s=0.4).process(wet, SR).astype(np.float64)

    pre_rms = np.sqrt(np.mean(wet[tail_region].astype(np.float64) ** 2))
    post_rms = np.sqrt(np.mean(dewet[tail_region] ** 2))
    reduction_db = _db(pre_rms ** 2) - _db(post_rms ** 2)

    # Measured ~9.8dB on this scenario; require at least 4dB.
    assert reduction_db >= 4.0


def test_output_same_length_and_dtype():
    wet, _ = _make_reverberant_signal()
    out = SpectralDereverberator().process(wet, SR)
    assert out.shape == wet.shape
    assert out.dtype == wet.dtype


def test_silence_stays_silent():
    silence = np.zeros(8000, dtype=np.int16)
    out = SpectralDereverberator().process(silence, SR)
    assert np.max(np.abs(out)) < 10
