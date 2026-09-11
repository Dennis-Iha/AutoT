"""Translation model registry: maps (source_language, target_language) to
the on-disk model that serves it. This is the piece the master architecture
spec calls for explicitly - "Language Registry -> Model Registry ->
Language Pair Registry" - so TranslationEngine implementations never
hard-code per-language logic; they look here.

Today every entry is a separate bilingual CTranslate2 model (via
tools/setup_translation_models.sh, sourced from the Argos Translate model
index - see core/translation/ctranslate2_translator.py for why). A future
multilingual model (e.g. one NLLB-200 CTranslate2 conversion serving all
pairs) would replace these many rows with fewer rows or a single
`"target": "*"`-style wildcard entry - a registry change, not a code change
to anything that calls this registry.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from core.common.model_manifest import verify_checksum

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = REPO_ROOT / "models" / "registry" / "translation_models.json"


@dataclass(frozen=True)
class TranslationModelEntry:
    model_id: str
    source: str
    target: str
    version: str
    engine: str
    # model_dir is this language pair's resource directory: model_dir/model/
    # holds the CTranslate2 model (model.bin + a vocabulary file, name
    # varies by package version) and model_dir/ itself holds the tokenizer
    # file as a sibling - see ctranslate2_translator.py for how both are
    # loaded (ctranslate2.Translator wants the "model" subdirectory
    # specifically, not this parent).
    model_dir: Path
    tokenizer_model: Path  # sentencepiece.model or bpe.model
    sha256: str | None = None  # of ctranslate2_model_dir/model.bin
    size_mb: float | None = None

    @property
    def ctranslate2_model_dir(self) -> Path:
        return self.model_dir / "model"

    def is_ready(self) -> bool:
        """Fast existence check - use in hot paths (this is what
        TranslationEngine.supports_pair() calls per-request)."""
        return (self.ctranslate2_model_dir / "model.bin").exists() and self.tokenizer_model.exists()

    def is_valid(self) -> bool:
        """Full checksum verification - use at startup / offline-readiness
        checks, not per-request (reads the whole model file)."""
        if self.sha256 is None:
            return self.is_ready()
        return self.is_ready() and verify_checksum(self.ctranslate2_model_dir / "model.bin", self.sha256)


class TranslationModelRegistry:
    def __init__(self, entries: list[TranslationModelEntry]):
        self._by_pair: dict[tuple[str, str], TranslationModelEntry] = {
            (e.source, e.target): e for e in entries
        }

    @classmethod
    def load(cls, path: Path | None = None) -> TranslationModelRegistry:
        path = path or DEFAULT_REGISTRY_PATH
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        entries = []
        for row in raw["models"]:
            entries.append(
                TranslationModelEntry(
                    model_id=row["model_id"],
                    source=row["source"],
                    target=row["target"],
                    version=row["version"],
                    engine=row["engine"],
                    model_dir=REPO_ROOT / row["model_dir"],
                    tokenizer_model=REPO_ROOT / row["tokenizer_model"],
                    sha256=row.get("sha256"),
                    size_mb=row.get("size_mb"),
                )
            )
        return cls(entries)

    def get(self, source: str, target: str) -> TranslationModelEntry | None:
        return self._by_pair.get((source, target))

    def supports_pair(self, source: str, target: str) -> bool:
        entry = self.get(source, target)
        return entry is not None and entry.is_ready()

    def pairs(self) -> list[tuple[str, str]]:
        return list(self._by_pair.keys())
