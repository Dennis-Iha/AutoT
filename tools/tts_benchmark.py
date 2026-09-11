"""Phase 7 benchmark: TTS latency plus a TTS->ASR round-trip intelligibility
check (see tests/tts/test_piper_tts.py for why round-trip WER is a
meaningfully stronger signal than "audio is non-silent").

Usage:
    python -m tools.tts_benchmark [--out results.json]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

import soundfile as sf

from core.asr.wer import word_error_rate
from core.asr.whisper_cpp_asr import WhisperCppASR
from core.audio.wav_io import write_wav
from core.common.config import REPO_ROOT, load_config
from core.tts.piper_tts import PiperTTSEngine
from core.tts.voice_registry import VoiceRegistry

TEST_SENTENCES = [
    "Have you eaten today?",
    "Where is the train station?",
    "The weather is very nice this morning.",
]


def _resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else REPO_ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    tts_registry = VoiceRegistry.load()
    voice_ids = [
        v for v in tts_registry.voice_ids()
        if (entry := tts_registry.get(v)) is not None and entry.is_ready()
    ]
    if not voice_ids:
        print("No TTS voices installed. Run tools/setup_tts_models.sh first.")
        return 1

    asr_cfg = load_config().asr
    binary_path = _resolve(asr_cfg.binary_path)
    model_path = _resolve(asr_cfg.model_path)
    have_asr = binary_path.exists() and model_path.exists()
    asr = WhisperCppASR(binary_path=binary_path, model_path=model_path) if have_asr else None
    if not have_asr:
        print("whisper.cpp not built - round-trip WER will be skipped. Run tools/setup_whisper_cpp.sh.")

    tts = PiperTTSEngine(tts_registry)
    rows = []
    for voice_id in voice_ids:
        for text in TEST_SENTENCES:
            start = time.perf_counter()
            result = tts.synthesize(text, voice=voice_id)
            latency_ms = (time.perf_counter() - start) * 1000.0
            duration_s = len(result.audio) / result.sample_rate_hz

            row = {
                "voice": voice_id,
                "text": text,
                "latency_ms": round(latency_ms, 1),
                "audio_duration_s": round(duration_s, 2),
                "real_time_factor": round(latency_ms / 1000.0 / duration_s, 3),
            }

            if asr is not None:
                raw_wav = Path("/tmp") / "tts_benchmark_raw.wav"
                resampled_wav = Path("/tmp") / "tts_benchmark_16k.wav"
                write_wav(raw_wav, result.audio, result.sample_rate_hz)
                subprocess.run(
                    ["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw_wav),
                     "-ar", "16000", "-ac", "1", str(resampled_wav)],
                    check=True,
                )
                audio16, sr16 = sf.read(resampled_wav, dtype="int16")
                transcription = asr.transcribe(audio16, sr16, language="en")
                row["round_trip_wer"] = round(word_error_rate(text, transcription.text), 3)
                row["round_trip_text"] = transcription.text

            rows.append(row)
            print(f"  {voice_id}: {latency_ms:5.0f}ms (RTF={row['real_time_factor']:.2f}) "
                  f"{text!r} -> round_trip_wer={row.get('round_trip_wer', 'n/a')}")

    if args.out:
        args.out.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
        print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
