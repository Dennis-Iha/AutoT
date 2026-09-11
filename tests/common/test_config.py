

from core.common.config import AppConfig, load_config


def test_load_config_returns_defaults_from_yaml():
    cfg = load_config()
    assert isinstance(cfg, AppConfig)
    assert cfg.audio.sample_rate_hz == 16000
    assert cfg.vad.frame_ms == 20


def test_env_override(monkeypatch):
    monkeypatch.setenv("AT_AUDIO__SAMPLE_RATE_HZ", "48000")
    monkeypatch.setenv("AT_VAD__AGGRESSIVENESS", "3")
    cfg = load_config()
    assert cfg.audio.sample_rate_hz == 48000
    assert cfg.vad.aggressiveness == 3


def test_user_config_overlay(tmp_path):
    user_cfg = tmp_path / "user.yaml"
    user_cfg.write_text("audio:\n  channels: 2\n")
    cfg = load_config(user_cfg)
    assert cfg.audio.channels == 2
    # Unrelated defaults should be untouched.
    assert cfg.audio.sample_rate_hz == 16000
