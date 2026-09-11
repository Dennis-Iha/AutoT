"""Text translation interface.

``translate(text, source_language, target_language)`` is deliberately
generic - never hard-code per-language branches against this interface.
Which model actually serves a given (source, target) pair is resolved
through the model registry (``core/translation/model_registry.py``), not
baked into this class, so swapping today's per-language-pair CTranslate2
models for a single shared multilingual model later (e.g. NLLB-200) is a
registry/config change, not an interface change.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field


@dataclass
class TranslationResult:
    text: str
    source_language: str
    target_language: str
    timestamp: float = field(default_factory=time.time)


class TranslationEngine(ABC):
    @abstractmethod
    def translate(self, text: str, source_language: str, target_language: str) -> TranslationResult:
        raise NotImplementedError

    @abstractmethod
    def translate_stream(
        self, texts: Iterator[str], source_language: str, target_language: str
    ) -> Iterator[TranslationResult]:
        """Translate a sequence of independent text chunks (e.g. one per
        ASR segment), one result per input. Not incremental/partial
        translation of a single growing utterance - that is Phase 9 scope."""
        raise NotImplementedError

    @abstractmethod
    def supports_pair(self, source_language: str, target_language: str) -> bool:
        raise NotImplementedError
