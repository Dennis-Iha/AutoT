"""ASR model registry (Phase 10) - the same manifest/checksum pattern as
core/translation/model_registry.py and core/tts/voice_registry.py, applied
to whisper.cpp's ggml model files, which previously only lived as raw
config paths (core/common/config.py's ASRConfig) with no version/checksum
tracking at all.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from core.common.model_manifest import verify_checksum

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = REPO_ROOT / "models" / "registry" / "asr_models.json"


@dataclass(frozen=True)
class ASRModelEntry:
    model_id: str
    size_class: str
    engine: str
    multilingual: bool
    path: Path
    sha256: str
    size_mb: float

    def is_ready(self) -> bool:
        """Fast existence check - use in hot paths."""
        return self.path.exists()

    def is_valid(self) -> bool:
        """Full checksum verification - use at startup / offline-readiness
        checks, not per-request (reads the whole file, see
        core/common/model_manifest.py)."""
        return verify_checksum(self.path, self.sha256)


class ASRModelRegistry:
    def __init__(self, entries: list[ASRModelEntry]):
        self._by_id = {e.model_id: e for e in entries}
        self._by_size_class = {e.size_class: e for e in entries}

    @classmethod
    def load(cls, path: Path | None = None) -> ASRModelRegistry:
        path = path or DEFAULT_REGISTRY_PATH
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        entries = [
            ASRModelEntry(
                model_id=row["model_id"],
                size_class=row["size_class"],
                engine=row["engine"],
                multilingual=row["multilingual"],
                path=REPO_ROOT / row["path"],
                sha256=row["sha256"],
                size_mb=row["size_mb"],
            )
            for row in raw["models"]
        ]
        return cls(entries)

    def get(self, model_id: str) -> ASRModelEntry | None:
        return self._by_id.get(model_id)

    def get_by_size_class(self, size_class: str) -> ASRModelEntry | None:
        return self._by_size_class.get(size_class)

    def model_ids(self) -> list[str]:
        return list(self._by_id.keys())
