"""Measures real, objective effects of noise suppression on a synthetic
signal with independently known clean/noise components, rather than just
checking the code runs. Thresholds are set with margin below values
actually measured during development (see core/denoise/noise_suppression.py
docstring) - not guessed.
"""

import numpy as np
import pytest

from core.denoise.noise_suppression import (
    PassthroughNoiseSuppressor,
    SpectralSubtractionNoiseSuppressor,
)

SR = 16000


def _db(power: float) -> float:
    return 10 * np.log10(max(power, 1e-12))


def _make_noisy_signal(seed=42):
    rng = np.random.default_rng(seed)
    n = int(2.0 * SR)
    t = np.arange(n) / SR
    speech_region = (t >= 0.5) & (t < 1.5)
    tone = sum(np.sin(2 * np.pi * f * t) for f in (200, 400, 800)) * 3000 / 3
    speech = np.zeros(n)
    speech[speech_region] = tone[speech_region]
    noise = rng.normal(0, 500, n)
    mixture = np.clip(speech + noise, -32768, 32767).astype(np.int16)
    return mixture, speech_region


def test_passthrough_is_identity():
    mixture, _ = _make_noisy_signal()
    out = PassthroughNoiseSuppressor().process(mixture, SR)
    np.testing.assert_array_equal(out, mixture)


def test_reduces_noise_floor_energy():
    mixture, speech_region = _make_noisy_signal()
    cleaned = SpectralSubtractionNoiseSuppressor().process(mixture, SR).astype(np.float64)

    noise_only = ~speech_region
    in_rms = np.sqrt(np.mean(mixture[noise_only].astype(np.float64) ** 2))
    out_rms = np.sqrt(np.mean(cleaned[noise_only] ** 2))
    reduction_db = _db(in_rms ** 2) - _db(out_rms ** 2)

    # Measured ~5.8dB with default settings; require at least 3dB (factor ~2 in power).
    assert reduction_db >= 3.0


def test_retains_most_speech_energy():
    mixture, speech_region = _make_noisy_signal()
    cleaned = SpectralSubtractionNoiseSuppressor().process(mixture, SR).astype(np.float64)

    in_rms = np.sqrt(np.mean(mixture[speech_region].astype(np.float64) ** 2))
    out_rms = np.sqrt(np.mean(cleaned[speech_region] ** 2))
    retained_fraction = out_rms / in_rms

    # Measured ~0.72; a suppressor that destroys speech (e.g. retained < 0.3)
    # would defeat the purpose even if it kills all the noise.
    assert retained_fraction >= 0.5


def test_output_same_length_and_dtype():
    mixture, _ = _make_noisy_signal()
    cleaned = SpectralSubtractionNoiseSuppressor().process(mixture, SR)
    assert cleaned.shape == mixture.shape
    assert cleaned.dtype == mixture.dtype


def test_silence_in_silence_out():
    silence = np.zeros(8000, dtype=np.int16)
    cleaned = SpectralSubtractionNoiseSuppressor().process(silence, SR)
    assert np.max(np.abs(cleaned)) < 10


@pytest.mark.parametrize("n", [100, 4000, 32000])
def test_handles_various_lengths_without_crashing(n):
    rng = np.random.default_rng(1)
    audio = rng.integers(-5000, 5000, n).astype(np.int16)
    out = SpectralSubtractionNoiseSuppressor().process(audio, SR)
    assert out.shape == audio.shape
