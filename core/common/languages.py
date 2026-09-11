"""Language registry loader.

AT does not hard-code translation logic around the initial nine languages.
Everything downstream (ASR model selection, translation model selection, TTS
voice selection) should look languages up through this registry instead of
switching on language codes directly, so adding language #10 is a data change
(``models/registry/languages.json``) plus new model files, not a code change.

``status`` values (a loose progression, not a strict linear one - v1's
pipeline is asymmetric: <source language> speech -> ASR -> translate ->
*English* TTS, so English's own path skips "translation_ready" and goes
straight from ASR to TTS):
    "initial"       — part of the v1 target set, no models integrated yet.
    "asr_ready"      — an ASR model is registered and benchmarked for this language.
    "translation_ready" — a <this language>->en translation model is registered
                          and benchmarked (only meaningful for non-English v1
                          source languages).
    "tts_ready"      — a TTS voice is registered and benchmarked (only
                       meaningful for English today, the only TTS target).
    "production"     — reserved for Phase 30's defined, explicit quality
                       gates (WER/latency/etc. thresholds) actually passing,
                       not just "the pieces exist and produced correct
                       output in development" - no language is there yet.

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
