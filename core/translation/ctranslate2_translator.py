"""TranslationEngine backed by CTranslate2 + a per-language-pair tokenizer.

Chosen over the ``argostranslate`` Python package itself: argostranslate
pulls in ``stanza`` (for paragraph->sentence splitting) which transitively
requires PyTorch - a multi-hundred-MB dependency AT doesn't need, since
utterance segmentation is already done upstream by core/vad/segmenter.py
(Phase 2). This module uses the same underlying CTranslate2 model files
Argos Translate's ``.argosmodel`` packages ship (fetched by
``tools/setup_translation_models.sh``, which discards the stanza model)
directly via the lightweight ``ctranslate2`` package (no torch).

Tokenizer scheme is NOT uniform across languages - verified by inspection
while building this, not assumed:

  - Most v1 languages (ar/bn/zh/fr/hi/pt/ru) ship a ``sentencepiece.model``.
  - Spanish's package ships the older subword-nmt BPE format
    (``bpe.model``, classic ``word@@ pair`` merge rules) with Moses-style
    pre-tokenization and HTML-entity-escaped punctuation (``&apos;s``),
    requiring ``subword_nmt`` + ``sacremoses`` (both pure Python, no torch)
    instead of ``sentencepiece``.

Both were verified end-to-end during development to produce correct
translations before this module was written - see
tests/translation/test_ctranslate2_translator.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import ctranslate2
import sentencepiece as spm
from sacremoses import MosesDetokenizer, MosesTokenizer
from subword_nmt.apply_bpe import BPE

from core.translation.base import TranslationEngine, TranslationResult
from core.translation.model_registry import TranslationModelEntry, TranslationModelRegistry


class _SentencePieceTokenizer:
    #: SentencePiece's word-boundary marker (U+2581 LOWER ONE EIGHTH BLOCK).
    _SPACE_MARKER = "▁"

    def __init__(self, model_path: Path):
        self._sp = spm.SentencePieceProcessor()
        self._sp.load(str(model_path))

    def encode(self, text: str) -> list[str]:
        return self._sp.encode(text, out_type=str)

    def decode(self, tokens: list[str]) -> str:
        # sentencepiece 0.2.2's SentencePieceProcessor.decode() on a list of
        # piece-strings was observed (during development) to inconsistently
        # drop only SOME word-boundary markers depending on the token
        # sequence, e.g. "▁Where is the▁railway▁station?"
        # instead of "Where is the railway station?". The standard manual
        # SentencePiece detokenization - concatenate all pieces, then turn
        # the marker into a space - is simpler and was verified correct
        # across all 7 sentencepiece-based v1 languages; use it instead of
        # trusting decode()'s type-dispatch behavior.
        return "".join(tokens).replace(self._SPACE_MARKER, " ").strip()


class _BPETokenizer:
    def __init__(self, model_path: Path, source_lang: str, target_lang: str):
        with open(model_path, encoding="utf-8") as f:
            self._bpe = BPE(f)
        self._moses_tokenize = MosesTokenizer(lang=source_lang)
        self._moses_detokenize = MosesDetokenizer(lang=target_lang)

    def encode(self, text: str) -> list[str]:
        pre_tokenized = self._moses_tokenize.tokenize(text, return_str=True)
        return self._bpe.process_line(pre_tokenized).split()

    def decode(self, tokens: list[str]) -> str:
        merged = " ".join(tokens).replace("@@ ", "")
        return self._moses_detokenize.detokenize(merged.split())


def _load_tokenizer(entry: TranslationModelEntry):
    sentencepiece_path = entry.model_dir / "sentencepiece.model"
    bpe_path = entry.model_dir / "bpe.model"
    if sentencepiece_path.exists():
        return _SentencePieceTokenizer(sentencepiece_path)
    if bpe_path.exists():
        return _BPETokenizer(bpe_path, source_lang=entry.source, target_lang=entry.target)
    raise FileNotFoundError(
        f"no sentencepiece.model or bpe.model found under {entry.model_dir} "
        f"for {entry.source}->{entry.target}"
    )


class CTranslate2TranslationEngine(TranslationEngine):
    def __init__(self, registry: TranslationModelRegistry, device: str = "cpu"):
        self._registry = registry
        self._device = device
        self._translators: dict[tuple[str, str], ctranslate2.Translator] = {}
        self._tokenizers: dict[tuple[str, str], object] = {}

    def supports_pair(self, source_language: str, target_language: str) -> bool:
        return self._registry.supports_pair(source_language, target_language)

    def _get_backend(self, source: str, target: str):
        key = (source, target)
        if key not in self._translators:
            entry = self._registry.get(source, target)
            if entry is None or not entry.is_ready():
                raise ValueError(f"no ready translation model for {source}->{target}")
            self._translators[key] = ctranslate2.Translator(
                str(entry.ctranslate2_model_dir), device=self._device
            )
            self._tokenizers[key] = _load_tokenizer(entry)
        return self._translators[key], self._tokenizers[key]

    def translate(self, text: str, source_language: str, target_language: str) -> TranslationResult:
        translator, tokenizer = self._get_backend(source_language, target_language)
        source_tokens = tokenizer.encode(text)
        results = translator.translate_batch([source_tokens])
        target_tokens = results[0].hypotheses[0]
        translated_text = tokenizer.decode(target_tokens)
        return TranslationResult(
            text=translated_text, source_language=source_language, target_language=target_language
        )

    def translate_stream(
        self, texts: Iterator[str], source_language: str, target_language: str
    ) -> Iterator[TranslationResult]:
        for text in texts:
            yield self.translate(text, source_language, target_language)

    def unload(self, source_language: str, target_language: str) -> None:
        """Free the loaded model for a pair - Phase 10's RAM-management need
        (an embedded device cannot keep all 8 translation models resident)."""
        key = (source_language, target_language)
        self._translators.pop(key, None)
        self._tokenizers.pop(key, None)
