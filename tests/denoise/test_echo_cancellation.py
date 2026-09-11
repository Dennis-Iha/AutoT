"""Measures ERLE (echo return loss enhancement) on a synthetic, known echo
path rather than just checking the code runs. See
core/denoise/echo_cancellation.py for the algorithm and
tools/audio_cleanup_benchmark.py for the standalone benchmark this mirrors.
"""

import numpy as np
import pytest

from core.denoise.echo_cancellation import NLMSEchoCanceller, PassthroughEchoCanceller

SR = 16000


def _db(power: float) -> float:
    return 10 * np.log10(max(power, 1e-12))


def _make_echo_scenario(seed=42, n=8000, filter_length=64):
    rng = np.random.default_rng(seed)
    far = rng.normal(0, 1000, n)
    true_path = np.zeros(filter_length)
    true_path[5] = 0.6
    true_path[20] = 0.3
    echo = np.convolve(far, true_path)[:n]
    near_noise = rng.normal(0, 20, n)
    near = echo + near_noise
    return near.astype(np.int16), far.astype(np.int16)


def test_passthrough_is_identity():
    near, far = _make_echo_scenario()
    out = PassthroughEchoCanceller().process(near, far, SR)
    np.testing.assert_array_equal(out, near)


def test_length_mismatch_raises():
    near, far = _make_echo_scenario()
    with pytest.raises(ValueError):
        NLMSEchoCanceller().process(near, far[:-10], SR)


def test_converges_and_cancels_echo():
    near, far = _make_echo_scenario()
    aec = NLMSEchoCanceller(filter_length=64, step_size=0.5)
    out = aec.process(near, far, SR).astype(np.float64)

    # Measure ERLE only over the tail (after the adaptive filter has had
    # time to converge), not the whole signal - convergence transient at
    # the start is expected and not part of the claim being tested.
    tail = slice(int(len(near) * 0.75), len(near))
    pre_power = np.mean(near[tail].astype(np.float64) ** 2)
    post_power = np.mean(out[tail] ** 2)
    erle_db = _db(pre_power) - _db(post_power)

    # Measured ~29dB on this scenario; require at least 15dB.
    assert erle_db >= 15.0


def test_reset_clears_adapted_filter():
    near, far = _make_echo_scenario()
    aec = NLMSEchoCanceller(filter_length=64)
    aec.process(near, far, SR)
    assert np.any(aec._w != 0)
    aec.reset()
    assert np.all(aec._w == 0)


def test_output_same_length_and_dtype():
    near, far = _make_echo_scenario()
    out = NLMSEchoCanceller(filter_length=64).process(near, far, SR)
    assert out.shape == near.shape
    assert out.dtype == near.dtype
