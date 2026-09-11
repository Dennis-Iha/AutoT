"""Phase 4 benchmark: per-language identification accuracy and latency on
the espeak-ng-synthesized speech fixtures (tests/fixtures/speech/).

This measures accuracy on SYNTHESIZED speech, not natural human speech -
documented as a real limitation, not glossed over (see
tests/fixtures/speech/manifest.json's "_provenance" field). Treat these
numbers as "does the integration work and roughly how confident is it",
not as a production accuracy claim; Phase 30 (dedicated performance
testing across real environments) is where that claim would need to be
earned with real recordings.

Usage:
    python -m tools.language_id_benchmark [--out results.json]
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from core.audio.wav_io import read_wav
from core.common.config import REPO_ROOT, load_config
from core.language_id.whisper_lid import WhisperLanguageIdentifier

FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "speech"


def _resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else REPO_ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    cfg = load_config().asr
    binary_path = _resolve(cfg.binary_path)
    model_path = _resolve(cfg.model_path)
    if not binary_path.exists() or not model_path.exists():
        print(f"whisper.cpp not set up: binary={binary_path} model={model_path}")
        print("Run tools/setup_whisper_cpp.sh first.")
        return 1

    with open(FIXTURES_DIR / "manifest.json") as f:
        manifest = json.load(f)
    languages = [lang for lang, entry in manifest.items() if isinstance(entry, dict)]

    identifier = WhisperLanguageIdentifier(binary_path=binary_path, model_path=model_path)

    rows = []
    correct = 0
    for lang in languages:
        audio, sr = read_wav(FIXTURES_DIR / f"{lang}.wav")
        start = time.perf_counter()
        result = identifier.identify(audio, sr)
        latency_ms = (time.perf_counter() - start) * 1000.0
        is_correct = result.language == lang
        correct += is_correct
        rows.append({
            "true_language": lang,
            "detected_language": result.language,
            "confidence": round(result.confidence, 4),
            "correct": is_correct,
            "latency_ms": round(latency_ms, 1),
        })
        print(f"  {lang:3s} -> {result.language:3s} (conf={result.confidence:.3f}, "
              f"{'OK' if is_correct else 'WRONG'}, {latency_ms:.0f}ms)")

    accuracy = correct / len(languages)
    print(f"\nAccuracy on synthesized-speech fixtures: {correct}/{len(languages)} ({accuracy:.0%})")
    print(f"Model: {model_path.name}")

    report = {
        "model": model_path.name,
        "accuracy": accuracy,
        "n_languages": len(languages),
        "rows": rows,
        "caveat": "measured on espeak-ng synthesized speech, not natural human speech",
    }
    if args.out:
        args.out.write_text(json.dumps(report, indent=2))
        print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
