import numpy as np
import pytest

from core.denoise.stft import istft, stft


@pytest.mark.parametrize("n", [800, 4000, 16000, 16001, 8123])
def test_round_trip_reconstructs_original(n):
    rng = np.random.default_rng(0)
    x = rng.normal(0, 1.0, n)
    spec = stft(x, frame_size=512, hop_size=256)
    y = istft(spec, frame_size=512, hop_size=256, length=n)
    assert y.shape == x.shape
    # Measured max abs error is ~1e-15 (machine precision); generous margin below that.
    np.testing.assert_allclose(y, x, atol=1e-9)


def test_spectrogram_shape():
    x = np.zeros(4000)
    spec = stft(x, frame_size=512, hop_size=256)
    assert spec.shape[1] == 512 // 2 + 1
    assert spec.dtype == np.complex128


def test_short_signal_still_produces_one_frame():
    x = np.ones(10)
    spec = stft(x, frame_size=512, hop_size=256)
    assert spec.shape[0] >= 1
    y = istft(spec, frame_size=512, hop_size=256, length=10)
    assert y.shape == (10,)
