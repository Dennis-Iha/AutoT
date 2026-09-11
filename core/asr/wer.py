"""Word/character error rate computation for ASR accuracy benchmarking.

Word-level WER assumes whitespace-delimited words, which is meaningful for
most of AT's v1 languages (en/es/fr/pt/ru/hi/bn/ar all use spaces between
words) but NOT for Mandarin, which has no whitespace word boundaries - WER
on unsegmented Chinese text is not a meaningful metric without a proper word
segmenter (out of scope here). Character error rate (CER) is script-agnostic
and is the metric to trust for cross-language comparison; report both, but
prefer CER for zh.
"""

from __future__ import annotations

import re
import unicodedata

_PUNCTUATION_RE = re.compile(r"[.,!?¿¡؟،…\"'()\[\]{}:;]")


def normalize_text(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace. Unicode-aware so
    this behaves sensibly on non-Latin scripts (Arabic, Devanagari, Bengali,
    Cyrillic, CJK) too, not just ASCII."""
    text = unicodedata.normalize("NFKC", text)
    text = text.lower()
    text = _PUNCTUATION_RE.sub("", text)
    return " ".join(text.split())


def edit_distance(ref: list[str], hyp: list[str]) -> int:
    """Levenshtein distance between two token sequences."""
    n, m = len(ref), len(hyp)
    dp = list(range(m + 1))
    for i in range(1, n + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, m + 1):
            temp = dp[j]
            if ref[i - 1] == hyp[j - 1]:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j - 1])
            prev = temp
    return dp[m]


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref_words = normalize_text(reference).split()
    hyp_words = normalize_text(hypothesis).split()
    if not ref_words:
        return 0.0 if not hyp_words else 1.0
    return edit_distance(ref_words, hyp_words) / len(ref_words)


def character_error_rate(reference: str, hypothesis: str) -> float:
    ref_chars = list(normalize_text(reference).replace(" ", ""))
    hyp_chars = list(normalize_text(hypothesis).replace(" ", ""))
    if not ref_chars:
        return 0.0 if not hyp_chars else 1.0
    return edit_distance(ref_chars, hyp_chars) / len(ref_chars)
