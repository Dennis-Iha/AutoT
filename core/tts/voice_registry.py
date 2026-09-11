"""TTS voice registry: maps a language to its installed voice model(s), the
same registry pattern used for ASR/translation models."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from core.common.model_manifest import verify_checksum

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = REPO_ROOT / "models" / "registry" / "tts_voices.json"


@dataclass(frozen=True)
class VoiceEntry:
    voice_id: str
    language: str
    engine: str
    quality: str
    sample_rate_hz: int
    model_dir: Path
    sha256: str | None = None  # of onnx_path
    size_mb: float | None = None

    @property
    def onnx_path(self) -> Path:
        return self.model_dir / f"{self.voice_id}.onnx"

    @property
    def config_path(self) -> Path:
        return self.model_dir / f"{self.voice_id}.onnx.json"

    def is_ready(self) -> bool:
        """Fast existence check - use in hot paths."""
        return self.onnx_path.exists() and self.config_path.exists()

    def is_valid(self) -> bool:
        """Full checksum verification - use at startup / offline-readiness
        checks, not per-request (reads the whole model file)."""
        if self.sha256 is None:
            return self.is_ready()
        return self.is_ready() and verify_checksum(self.onnx_path, self.sha256)


class VoiceRegistry:
    def __init__(self, entries: list[VoiceEntry]):
        self._by_id = {e.voice_id: e for e in entries}
        self._by_language: dict[str, list[VoiceEntry]] = {}
        for e in entries:
            self._by_language.setdefault(e.language, []).append(e)

    @classmethod
    def load(cls, path: Path | None = None) -> VoiceRegistry:
        path = path or DEFAULT_REGISTRY_PATH
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        entries = [
            VoiceEntry(
                voice_id=row["voice_id"],
                language=row["language"],
                engine=row["engine"],
                quality=row["quality"],
                sample_rate_hz=row["sample_rate_hz"],
                model_dir=REPO_ROOT / row["model_dir"],
                sha256=row.get("sha256"),
                size_mb=row.get("size_mb"),
            )
            for row in raw["voices"]
        ]
        return cls(entries)

    def get(self, voice_id: str) -> VoiceEntry | None:
        return self._by_id.get(voice_id)

    def default_for_language(self, language: str) -> VoiceEntry | None:
        candidates = self._by_language.get(language, [])
        return candidates[0] if candidates else None

    def voice_ids(self) -> list[str]:
        return list(self._by_id.keys())
