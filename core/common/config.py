"""Configuration system for AT-CORE.

Loads defaults from ``config/default.yaml`` (repo root), then overlays a
user-supplied YAML file (if given), then overlays environment variables
prefixed with ``AT_`` (e.g. ``AT_AUDIO__SAMPLE_RATE_HZ=16000`` overrides
``audio.sample_rate_hz``). Kept deliberately small: a nested dict + a few
typed accessor dataclasses, not a full settings framework, since AT does not
yet have configuration complex enough to justify one.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, get_type_hints

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "default.yaml"
ENV_PREFIX = "AT_"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    result = dict(data)
    for env_key, raw_value in os.environ.items():
        if not env_key.startswith(ENV_PREFIX):
            continue
        path = env_key[len(ENV_PREFIX):].lower().split("__")
        node = result
        for part in path[:-1]:
            node = node.setdefault(part, {})
        node[path[-1]] = yaml.safe_load(raw_value)
    return result


def load_raw_config(user_config_path: Path | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if DEFAULT_CONFIG_PATH.exists():
        with open(DEFAULT_CONFIG_PATH) as f:
            data = yaml.safe_load(f) or {}
    if user_config_path and user_config_path.exists():
        with open(user_config_path) as f:
            data = _deep_merge(data, yaml.safe_load(f) or {})
    return _apply_env_overrides(data)


@dataclass
class AudioConfig:
    sample_rate_hz: int = 16000
    channels: int = 1
    blocksize_samples: int = 320  # 20ms @ 16kHz
    device: str | None = None  # None = system default input device
    ring_buffer_seconds: float = 10.0


@dataclass
class VADConfig:
    aggressiveness: int = 2  # webrtcvad 0-3, higher = more aggressive filtering
    frame_ms: int = 20  # must be 10, 20, or 30 for webrtcvad
    min_speech_ms: int = 200  # ignore blips shorter than this
    hangover_ms: int = 300  # trailing silence required to close a segment
    max_segment_ms: int = 20000  # force-close very long segments


@dataclass
class AppConfig:
    log_level: str = "INFO"
    json_logs: bool = False
    audio: AudioConfig = field(default_factory=AudioConfig)
    vad: VADConfig = field(default_factory=VADConfig)


def _build_dataclass(cls: type, data: dict[str, Any]) -> Any:
    resolved_types = get_type_hints(cls)
    kwargs: dict[str, Any] = {}
    for f in cls.__dataclass_fields__.values():  # type: ignore[attr-defined]
        if f.name not in data:
            continue
        value = data[f.name]
        field_type = resolved_types.get(f.name, f.type)
        if hasattr(field_type, "__dataclass_fields__") and isinstance(value, dict):
            value = _build_dataclass(field_type, value)
        kwargs[f.name] = value
    return cls(**kwargs)


def load_config(user_config_path: Path | None = None) -> AppConfig:
    raw = load_raw_config(user_config_path)
    return _build_dataclass(AppConfig, raw)
