"""Phase 11 benchmark: real measured size/RAM/latency/accuracy across
quantization levels of the base ASR model, per the master spec's explicit
requirement ("For each model record: model size, RAM, latency, accuracy,
power estimate").

Power is deliberately NOT estimated here: this workstation has no
accessible power measurement (Intel RAPL's energy_uj is root-only on this
machine, and no `perf` binary is installed) - reporting a guessed number
would violate this project's own "never fabricate benchmark numbers"
principle. Real power measurement needs either root RAPL access or
dedicated hardware instrumentation (expected once Phase 12 embedded dev
boards are in the picture, several of which expose power rails directly).

Usage:
    python -m tools.quantization_benchmark [--languages en es] [--out results.json]
    tools/quantize_asr_models.sh base q4_0 q5_0 q8_0   # run first if not already done
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
QUANTIZED_DIR = REPO_ROOT / "models" / "asr" / "whisper" / "quantized"


def _resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else REPO_ROOT / path


def _peak_rss_mb(binary_path: Path, args: list[str], poll_interval_s: float = 0.01) -> float:
    """Sampled peak RSS (same approach as tools/asr_benchmark.py) - a
    poll_interval_s gap could miss a brief true peak, not claimed exact."""
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


def discover_models() -> list[tuple[str, Path]]:
    """Returns [(label, path), ...]: the unquantized base model plus every
    quantized variant found in models/asr/whisper/quantized/."""
    cfg = load_config().asr
    base_path = _resolve(cfg.model_path)
    models = [("base (unquantized, f16)", base_path)] if base_path.exists() else []
    if QUANTIZED_DIR.exists():
        for path in sorted(QUANTIZED_DIR.glob("ggml-base-*.bin")):
            quant_type = path.stem.replace("ggml-base-", "")
            models.append((quant_type, path))
    return models


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--languages", nargs="+", default=["en", "es", "ar"])
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    cfg = load_config().asr
    binary_path = _resolve(cfg.binary_path)
    if not binary_path.exists():
        print("whisper.cpp binary not found. Run tools/setup_whisper_cpp.sh first.")
        return 1

    models = discover_models()
    if len(models) <= 1:
        print("No quantized models found. Run tools/quantize_asr_models.sh first.")
        return 1

    with open(FIXTURES_DIR / "manifest.json") as f:
        manifest = json.load(f)

    report = {}
    for label, model_path in models:
        print(f"\n=== {label} ({model_path.stat().st_size / 1e6:.1f}MB) ===")
        asr = WhisperCppASR(binary_path=binary_path, model_path=model_path)
        rows = []
        for lang in args.languages:
            if lang not in manifest:
                continue
            audio, sr = read_wav(FIXTURES_DIR / f"{lang}.wav")
            reference = manifest[lang]["text"]

            start = time.perf_counter()
            result = asr.transcribe(audio, sr, language=lang)  # forced: isolate from LID accuracy
            latency_ms = (time.perf_counter() - start) * 1000.0

            wer = word_error_rate(reference, result.text)
            cer = character_error_rate(reference, result.text)
            rows.append({"language": lang, "wer": round(wer, 3), "cer": round(cer, 3),
                         "latency_ms": round(latency_ms, 1)})
            print(f"  {lang}: wer={wer:.2f} cer={cer:.2f} {latency_ms:6.0f}ms")

        peak_rss_mb = _peak_rss_mb(
            binary_path,
            ["-m", str(model_path), "-f", str(FIXTURES_DIR / "en.wav"), "-l", "en", "-nt"],
        )
        avg_wer = sum(r["wer"] for r in rows) / len(rows) if rows else float("nan")
        avg_cer = sum(r["cer"] for r in rows) / len(rows) if rows else float("nan")
        avg_latency = sum(r["latency_ms"] for r in rows) / len(rows) if rows else float("nan")
        print(f"  avg: wer={avg_wer:.2f} cer={avg_cer:.2f} latency={avg_latency:.0f}ms "
              f"peak_rss={peak_rss_mb:.0f}MB")

        report[label] = {
            "size_mb": round(model_path.stat().st_size / 1e6, 1),
            "peak_rss_mb": round(peak_rss_mb, 1),
            "avg_wer": round(avg_wer, 3),
            "avg_cer": round(avg_cer, 3),
            "avg_latency_ms": round(avg_latency, 1),
            "power_watts": None,  # not measured - see module docstring
            "rows": rows,
        }

    if args.out:
        args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
