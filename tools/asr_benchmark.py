"""Phase 5/11 benchmark: per-language WER/CER, latency, and peak RSS for
each installed whisper.cpp model, on the espeak-ng-synthesized speech
fixtures (tests/fixtures/speech/).

Measured on SYNTHESIZED speech, not natural human speech - real accuracy
validation against natural recordings is deferred to Phase 30. This
benchmark exists to compare model sizes against each other (tiny vs base
vs ...) on a controlled, reproducible input, per Engineering Principle #17:
"do not design the final earbud PCB before the AI workload has been
benchmarked" - this is that benchmarking, starting on a workstation.

Usage:
    python -m tools.asr_benchmark [--models tiny base] [--out results.json]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

import psutil

from core.asr.wer import character_error_rate, word_error_rate
from core.asr.whisper_cpp_asr import WhisperCppASR
from core.audio.wav_io import read_wav
from core.common.config import REPO_ROOT, load_config

FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "speech"


def _resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else REPO_ROOT / path


def _peak_rss_mb(binary_path: Path, args: list[str], poll_interval_s: float = 0.01) -> float:
    """Samples RSS of the running subprocess every poll_interval_s and
    reports the max seen. This is a SAMPLED peak, not an exact instrumented
    one (a poll_interval_s=10ms gap could miss a brief true peak) - honest
    about that rather than implying exact measurement precision."""
    env = {**os.environ, "LD_LIBRARY_PATH": str(binary_path.parent)}
    proc = subprocess.Popen(
        [str(binary_path), *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env
    )
    peak_bytes = 0
    try:
        ps_proc = psutil.Process(proc.pid)
        while proc.poll() is None:
            try:
                peak_bytes = max(peak_bytes, ps_proc.memory_info().rss)
            except psutil.NoSuchProcess:
                break
            time.sleep(poll_interval_s)
    finally:
        proc.wait(timeout=120)
    return peak_bytes / (1024 * 1024)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", default=None, help="model sizes, e.g. tiny base")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    cfg = load_config().asr
    binary_path = _resolve(cfg.binary_path)
    if not binary_path.exists():
        print(f"whisper.cpp binary not found: {binary_path}. Run tools/setup_whisper_cpp.sh first.")
        return 1

    models_dir = _resolve(cfg.model_path).parent
    if args.models:
        model_paths = [models_dir / f"ggml-{m}.bin" for m in args.models]
    else:
        model_paths = sorted(models_dir.glob("ggml-*.bin"))
    model_paths = [m for m in model_paths if m.exists()]
    if not model_paths:
        print(f"No models found in {models_dir}. Run tools/setup_whisper_cpp.sh first.")
        return 1

    with open(FIXTURES_DIR / "manifest.json") as f:
        manifest = json.load(f)
    languages = [lang for lang, entry in manifest.items() if isinstance(entry, dict)]

    report = {}
    for model_path in model_paths:
        print(f"\n=== {model_path.name} ===")
        asr = WhisperCppASR(binary_path=binary_path, model_path=model_path)
        rows = []
        for lang in languages:
            audio, sr = read_wav(FIXTURES_DIR / f"{lang}.wav")
            reference = manifest[lang]["text"]

            start = time.perf_counter()
            result = asr.transcribe(audio, sr, language=lang)
            latency_ms = (time.perf_counter() - start) * 1000.0

            wer = word_error_rate(reference, result.text)
            cer = character_error_rate(reference, result.text)
            rows.append({
                "language": lang,
                "reference": reference,
                "hypothesis": result.text,
                "wer": round(wer, 3),
                "cer": round(cer, 3),
                "latency_ms": round(latency_ms, 1),
            })
            print(f"  {lang:3s} wer={wer:.2f} cer={cer:.2f} {latency_ms:6.0f}ms  "
                  f"ref={reference!r} hyp={result.text!r}")

        peak_rss_mb = _peak_rss_mb(
            binary_path,
            ["-m", str(model_path), "-f", str(FIXTURES_DIR / "en.wav"), "-l", "en", "-nt"],
        )
        avg_wer = sum(r["wer"] for r in rows) / len(rows)
        avg_cer = sum(r["cer"] for r in rows) / len(rows)
        avg_latency = sum(r["latency_ms"] for r in rows) / len(rows)
        print(f"  avg: wer={avg_wer:.2f} cer={avg_cer:.2f} latency={avg_latency:.0f}ms "
              f"peak_rss={peak_rss_mb:.0f}MB size={model_path.stat().st_size/1e6:.0f}MB")

        report[model_path.name] = {
            "size_mb": round(model_path.stat().st_size / 1e6, 1),
            "peak_rss_mb": round(peak_rss_mb, 1),
            "avg_wer": round(avg_wer, 3),
            "avg_cer": round(avg_cer, 3),
            "avg_latency_ms": round(avg_latency, 1),
            "rows": rows,
        }

    if args.out:
        args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
