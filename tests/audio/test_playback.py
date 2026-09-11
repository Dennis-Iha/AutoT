"""Unit tests mocking sounddevice - real hardware playback was verified
manually (see docs/roadmap.md Phase 8 notes), but an automated test suite
shouldn't play audio out loud on every run."""

from unittest.mock import patch

import numpy as np

from core.audio.playback import AudioPlayback


def test_play_converts_int16_to_float32():
    audio = np.array([0, 16384, -32768, 32767], dtype=np.int16)
    with patch("core.audio.playback.sd") as mock_sd:
        AudioPlayback().play(audio, 16000, blocking=False)
        played_audio = mock_sd.play.call_args[0][0]
        assert played_audio.dtype == np.float32
        np.testing.assert_allclose(played_audio, audio.astype(np.float32) / 32768.0)


def test_play_passes_sample_rate_and_device():
    audio = np.zeros(100, dtype=np.int16)
    with patch("core.audio.playback.sd") as mock_sd:
        AudioPlayback(device="my-device").play(audio, 22050, blocking=False)
        _, kwargs = mock_sd.play.call_args
        assert kwargs["samplerate"] == 22050
        assert kwargs["device"] == "my-device"


def test_blocking_play_calls_wait():
    audio = np.zeros(100, dtype=np.int16)
    with patch("core.audio.playback.sd") as mock_sd:
        AudioPlayback().play(audio, 16000, blocking=True)
        mock_sd.wait.assert_called_once()


def test_nonblocking_play_does_not_call_wait():
    audio = np.zeros(100, dtype=np.int16)
    with patch("core.audio.playback.sd") as mock_sd:
        AudioPlayback().play(audio, 16000, blocking=False)
        mock_sd.wait.assert_not_called()


def test_float_audio_passed_through_unchanged():
    audio = np.array([0.0, 0.5, -0.5], dtype=np.float32)
    with patch("core.audio.playback.sd") as mock_sd:
        AudioPlayback().play(audio, 16000, blocking=False)
        played_audio = mock_sd.play.call_args[0][0]
        np.testing.assert_array_equal(played_audio, audio)


def test_stop_calls_sd_stop():
    with patch("core.audio.playback.sd") as mock_sd:
        AudioPlayback().stop()
        mock_sd.stop.assert_called_once()
