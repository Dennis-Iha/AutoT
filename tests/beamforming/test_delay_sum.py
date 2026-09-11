"""Measures that correct time-alignment actually improves SNR relative to
naive (unaligned) averaging, and that delay estimation recovers a known
injected delay - not just that the code runs without crashing.
"""

import numpy as np
import pytest

from core.beamforming.delay_sum import DelaySumBeamformer, estimate_delay_samples

SR = 16000


def _db(power: float) -> float:
    return 10 * np.log10(max(power, 1e-12))


def _snr_proxy(out: np.ndarray, reference: np.ndarray) -> float:
    """Correlate `out` against the known clean `reference`, scale-align it,
    and report the ratio of aligned-reference power to residual power - an
    SNR proxy that doesn't require the exact per-channel noise realizations."""
    m = min(len(out), len(reference))
    a, b = out[:m].astype(np.float64), reference[:m].astype(np.float64)
    scale = np.dot(a, b) / np.dot(b, b)
    residual = a - scale * b
    return _db(np.mean((scale * b) ** 2)) - _db(np.mean(residual ** 2))


def _make_two_mic_scenario(seed=42, n=8000, d_true=7):
    rng = np.random.default_rng(seed)
    source = rng.normal(0, 1000, n)
    ch0 = source + rng.normal(0, 800, n)
    ch1_clean = np.concatenate([np.zeros(d_true), source])[:n]
    ch1 = ch1_clean + rng.normal(0, 800, n)
    multi = np.stack([ch0, ch1], axis=1).astype(np.int16)
    return multi, source, d_true


def test_delay_estimation_recovers_known_delay():
    multi, _, d_true = _make_two_mic_scenario()
    estimated = estimate_delay_samples(multi[:, 0], multi[:, 1], max_delay_samples=20)
    assert estimated == d_true


def test_aligned_beamforming_beats_naive_averaging():
    multi, source, d_true = _make_two_mic_scenario()

    aligned = DelaySumBeamformer(channel_delays_samples=[0, d_true]).process(multi, SR)
    naive = DelaySumBeamformer(channel_delays_samples=[0, 0]).process(multi, SR)

    aligned_snr = _snr_proxy(aligned.astype(np.float64), source)
    naive_snr = _snr_proxy(naive.astype(np.float64), source)

    # Measured ~4.85dB aligned vs ~-3.45dB naive (an ~8.3dB gap); require at
    # least a 4dB advantage for correct alignment over no alignment.
    assert aligned_snr - naive_snr >= 4.0


def test_single_channel_is_passthrough():
    n = 100
    audio = np.arange(n, dtype=np.int16).reshape(-1, 1)
    out = DelaySumBeamformer(channel_delays_samples=[0]).process(audio, SR)
    np.testing.assert_array_equal(out, audio[:, 0])


def test_wrong_channel_count_raises():
    multi, _, _ = _make_two_mic_scenario()
    with pytest.raises(ValueError):
        DelaySumBeamformer(channel_delays_samples=[0, 0, 0]).process(multi, SR)


def test_wrong_shape_raises():
    with pytest.raises(ValueError):
        DelaySumBeamformer(channel_delays_samples=[0]).process(np.zeros(10), SR)


def test_zero_delays_is_naive_average():
    n = 50
    ch0 = np.full(n, 100, dtype=np.int16)
    ch1 = np.full(n, 200, dtype=np.int16)
    multi = np.stack([ch0, ch1], axis=1)
    out = DelaySumBeamformer(channel_delays_samples=[0, 0]).process(multi, SR)
    np.testing.assert_array_equal(out, np.full(n, 150, dtype=np.int16))
