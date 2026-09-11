"""Phase 6 benchmark: per-language-pair translation latency and output, on
the espeak-ng fixture text (tests/fixtures/speech/manifest.json).

No BLEU/chrF score is computed here - that needs a proper parallel
reference corpus with (ideally) multiple valid reference translations per
source sentence, which a single hand-picked sentence per language cannot
provide honestly. This benchmark reports latency and the actual output text
for manual inspection, and is a real integration smoke test across all 8
v1 source languages; formal MT quality scoring is deferred to Phase 30.

Usage:
    python -m tools.translation_benchmark [--out results.json]
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from core.common.config import REPO_ROOT
from core.translation.ctranslate2_translator import CTranslate2TranslationEngine
from core.translation.model_registry import TranslationModelRegistry

FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "speech"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    registry = TranslationModelRegistry.load()
    ready_pairs = [
        (s, t) for s, t in registry.pairs() if (e := registry.get(s, t)) is not None and e.is_ready()
    ]
    if not ready_pairs:
        print("No translation models installed. Run tools/setup_translation_models.sh first.")
        return 1

    with open(FIXTURES_DIR / "manifest.json") as f:
        manifest = json.load(f)

    engine = CTranslate2TranslationEngine(registry)
    rows = []
    for source, target in sorted(ready_pairs):
        if source not in manifest:
            continue
        text = manifest[source]["text"]

        # Include model load time in the first call, report it separately
        # from steady-state latency (an embedded device pays load cost once
        # per session, not per utterance).
        start = time.perf_counter()
        result = engine.translate(text, source, target)
        load_and_first_call_ms = (time.perf_counter() - start) * 1000.0

        start = time.perf_counter()
        engine.translate(text, source, target)
        warm_latency_ms = (time.perf_counter() - start) * 1000.0

        entry = registry.get(source, target)
        assert entry is not None  # guaranteed by ready_pairs filter above
        model_size_mb = sum(
            f.stat().st_size for f in entry.model_dir.rglob("*") if f.is_file()
        ) / 1e6

        row = {
            "source": source,
            "target": target,
            "input": text,
            "output": result.text,
            "model_size_mb": round(model_size_mb, 1),
            "first_call_ms": round(load_and_first_call_ms, 1),
            "warm_latency_ms": round(warm_latency_ms, 1),
        }
        rows.append(row)
        print(f"  {source}->{target}: {warm_latency_ms:6.0f}ms warm, "
              f"{model_size_mb:5.0f}MB  {text!r} -> {result.text!r}")
        engine.unload(source, target)

    if args.out:
        args.out.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
        print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
