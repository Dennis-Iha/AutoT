import numpy as np
import pytest

from core.vad.webrtc_vad import WebRtcVAD


def test_silence_is_not_speech():
    vad = WebRtcVAD(aggressiveness=2)
    frame = np.zeros(320, dtype=np.int16)  # 20ms @ 16kHz
    assert vad.is_speech(frame, 16000) is False


def test_loud_pure_tone_is_misclassified_as_speech():
    # Measured, not assumed: webrtcvad's energy/sub-band features key on
    # strong periodic energy in the speech frequency range, so a loud pure
    # 440Hz sine tone IS classified as speech even at the strictest
    # aggressiveness setting. This is a real accuracy limitation (it will
    # false-trigger on tonal noise/music), not a bug in this wrapper -
    # documented here so Phase 3 (noise suppression/beamforming) has a
    # concrete regression case to improve on, and so nobody downstream
    # assumes WebRtcVAD alone is a robust noise filter.
    vad = WebRtcVAD(aggressiveness=3)
    sample_rate_hz = 16000
    t = np.linspace(0, 0.02, 320, endpoint=False)
    tone = (np.sin(2 * np.pi * 440 * t) * 5000).astype(np.int16)
    assert vad.is_speech(tone, sample_rate_hz) is True


def test_quiet_pure_tone_is_not_speech():
    # A much lower-amplitude tone (closer to background-noise level) is
    # correctly rejected, confirming this is an energy-threshold effect
    # rather than is_speech() being unconditionally True.
    vad = WebRtcVAD(aggressiveness=3)
    sample_rate_hz = 16000
    t = np.linspace(0, 0.02, 320, endpoint=False)
    tone = (np.sin(2 * np.pi * 440 * t) * 50).astype(np.int16)
    assert vad.is_speech(tone, sample_rate_hz) is False


def test_invalid_aggressiveness_raises():
    with pytest.raises(ValueError):
        WebRtcVAD(aggressiveness=4)
    with pytest.raises(ValueError):
        WebRtcVAD(aggressiveness=-1)


def test_unsupported_sample_rate_raises():
    vad = WebRtcVAD(aggressiveness=2)
    frame = np.zeros(320, dtype=np.int16)
    with pytest.raises(ValueError, match="unsupported sample rate"):
        vad.is_speech(frame, 44100)


def test_wrong_frame_length_raises():
    vad = WebRtcVAD(aggressiveness=2)
    frame = np.zeros(123, dtype=np.int16)  # not 10/20/30ms at 16kHz
    with pytest.raises(ValueError, match="frame length"):
        vad.is_speech(frame, 16000)


def test_non_mono_frame_raises():
    vad = WebRtcVAD(aggressiveness=2)
    frame = np.zeros((320, 2), dtype=np.int16)
    with pytest.raises(ValueError, match="mono"):
        vad.is_speech(frame, 16000)


def test_wrong_dtype_raises():
    vad = WebRtcVAD(aggressiveness=2)
    frame = np.zeros(320, dtype=np.float32)
    with pytest.raises(ValueError, match="int16"):
        vad.is_speech(frame, 16000)


@pytest.mark.parametrize("frame_ms,expected_samples", [(10, 160), (20, 320), (30, 480)])
def test_all_supported_frame_durations_at_16k(frame_ms, expected_samples):
    vad = WebRtcVAD(aggressiveness=2)
    frame = np.zeros(expected_samples, dtype=np.int16)
    # Should not raise for any of the three supported frame durations.
    vad.is_speech(frame, 16000)
