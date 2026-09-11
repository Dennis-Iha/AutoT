import numpy as np
import pytest

from core.audio.ring_buffer import AudioRingBuffer


def test_write_read_roundtrip():
    buf = AudioRingBuffer(capacity_samples=100, channels=1)
    data = np.arange(10, dtype=np.int16).reshape(-1, 1)
    buf.write(data)
    assert buf.available_samples == 10
    out = buf.read_available()
    np.testing.assert_array_equal(out, data)
    assert buf.available_samples == 0


def test_mono_1d_input_is_accepted():
    buf = AudioRingBuffer(capacity_samples=100, channels=1)
    data = np.arange(5, dtype=np.int16)
    buf.write(data)
    out = buf.read_available()
    assert out.shape == (5, 1)
    np.testing.assert_array_equal(out[:, 0], data)


def test_wraparound():
    buf = AudioRingBuffer(capacity_samples=10, channels=1)
    buf.write(np.arange(7, dtype=np.int16).reshape(-1, 1))
    buf.read_available(max_samples=5)  # advance write/read pointers past the end
    buf.write(np.arange(100, 108, dtype=np.int16).reshape(-1, 1))  # wraps around
    out = buf.read_available()
    expected = np.concatenate(
        [np.arange(5, 7, dtype=np.int16), np.arange(100, 108, dtype=np.int16)]
    ).reshape(-1, 1)
    np.testing.assert_array_equal(out, expected)


def test_overflow_drops_oldest_and_is_counted():
    buf = AudioRingBuffer(capacity_samples=5, channels=1)
    buf.write(np.arange(5, dtype=np.int16).reshape(-1, 1))
    buf.write(np.arange(100, 103, dtype=np.int16).reshape(-1, 1))  # overflow by 3
    assert buf.dropped_samples == 3
    out = buf.read_available()
    # Oldest 3 samples (0,1,2) were dropped; buffer holds [3,4,100,101,102].
    expected = np.array([3, 4, 100, 101, 102], dtype=np.int16).reshape(-1, 1)
    np.testing.assert_array_equal(out, expected)


def test_write_larger_than_capacity_keeps_most_recent():
    buf = AudioRingBuffer(capacity_samples=4, channels=1)
    buf.write(np.arange(10, dtype=np.int16).reshape(-1, 1))
    assert buf.dropped_samples == 6
    out = buf.read_available()
    np.testing.assert_array_equal(out[:, 0], np.arange(6, 10, dtype=np.int16))


def test_partial_read():
    buf = AudioRingBuffer(capacity_samples=10, channels=1)
    buf.write(np.arange(8, dtype=np.int16).reshape(-1, 1))
    first = buf.read_available(max_samples=3)
    assert first.shape[0] == 3
    assert buf.available_samples == 5
    rest = buf.read_available()
    assert rest.shape[0] == 5


def test_read_empty_returns_empty_array():
    buf = AudioRingBuffer(capacity_samples=10, channels=2)
    out = buf.read_available()
    assert out.shape == (0, 2)


def test_invalid_capacity_raises():
    with pytest.raises(ValueError):
        AudioRingBuffer(capacity_samples=0)
    with pytest.raises(ValueError):
        AudioRingBuffer(capacity_samples=10, channels=0)


def test_stereo_shape_preserved():
    buf = AudioRingBuffer(capacity_samples=10, channels=2)
    data = np.array([[1, -1], [2, -2], [3, -3]], dtype=np.int16)
    buf.write(data)
    out = buf.read_available()
    np.testing.assert_array_equal(out, data)
