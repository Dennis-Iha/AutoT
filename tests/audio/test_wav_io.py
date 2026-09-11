import numpy as np

from core.audio.wav_io import read_wav, write_wav


def test_wav_roundtrip_mono(tmp_path):
    sample_rate_hz = 16000
    t = np.linspace(0, 1.0, sample_rate_hz, endpoint=False)
    tone = (np.sin(2 * np.pi * 440 * t) * 10000).astype(np.int16)

    path = tmp_path / "tone.wav"
    write_wav(path, tone, sample_rate_hz)
    assert path.exists()

    out, sr = read_wav(path)
    assert sr == sample_rate_hz
    assert out.shape == tone.shape
    assert out.dtype == np.int16
    # PCM_16 WAV round trip should be exact for int16 input.
    np.testing.assert_array_equal(out, tone)


def test_wav_roundtrip_stereo(tmp_path):
    sample_rate_hz = 8000
    left = np.full(100, 1000, dtype=np.int16)
    right = np.full(100, -1000, dtype=np.int16)
    stereo = np.stack([left, right], axis=1)

    path = tmp_path / "stereo.wav"
    write_wav(path, stereo, sample_rate_hz)
    out, sr = read_wav(path)

    assert sr == sample_rate_hz
    assert out.shape == (100, 2)
    np.testing.assert_array_equal(out, stereo)


def test_write_creates_parent_dirs(tmp_path):
    nested = tmp_path / "a" / "b" / "c.wav"
    write_wav(nested, np.zeros(10, dtype=np.int16), 16000)
    assert nested.exists()
