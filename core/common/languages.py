"""Language registry loader.

AT does not hard-code translation logic around the initial nine languages.
Everything downstream (ASR model selection, translation model selection, TTS
voice selection) should look languages up through this registry instead of
switching on language codes directly, so adding language #10 is a data change
(``models/registry/languages.json``) plus new model files, not a code change.

``status`` values:
    "initial"       — part of the v1 target set, no models integrated yet.
    "asr_ready"      — an ASR model is registered and benchmarked for this language.
    "translation_ready" — a translation model is registered and benchmarked.
    "tts_ready"      — a TTS voice is registered and benchmarked.
    "production"     — asr+translation+tts all benchmarked and passing quality gates.

Do not report a language as supported to end users until it reaches
"production" — see docs/architecture.md, "Language coverage is a claim, not
an assumption."
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = REPO_ROOT / "models" / "registry" / "languages.json"


@dataclass(frozen=True)
class Language:
    code: str
    name: str
    status: str


class LanguageRegistry:
    def __init__(self, languages: dict[str, Language]):
        self._languages = languages

    @classmethod
    def load(cls, path: Path | None = None) -> LanguageRegistry:
        path = path or DEFAULT_REGISTRY_PATH
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        languages = {
            code: Language(code=code, name=entry["name"], status=entry.get("status", "initial"))
            for code, entry in raw.items()
        }
        return cls(languages)

    def get(self, code: str) -> Language | None:
        return self._languages.get(code)

    def __contains__(self, code: str) -> bool:
        return code in self._languages

    def __iter__(self):
        return iter(self._languages.values())

    def codes(self) -> list[str]:
        return list(self._languages.keys())

    def with_status(self, status: str) -> list[Language]:
        return [lang for lang in self._languages.values() if lang.status == status]
