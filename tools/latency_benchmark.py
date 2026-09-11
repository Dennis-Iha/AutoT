"""Phase 9 benchmark: end-to-end latency breakdown per the master spec's
explicit requirement - audio capture, VAD, ASR, translation, TTS, playback,
and total latency, measured, not estimated.

Uses forced language (not auto-detection) for the ASR stage, deliberately:
this benchmark measures LATENCY, and conflating it with Phase 4/8's known
LID accuracy gap (see docs/roadmap.md) would make the numbers harder to
interpret. Language ID's own latency (dominated by a full encoder pass, see
docs/roadmap.md's Phase 9 profiling notes) is reported separately.

Usage:
    python -m tools.latency_benchmark [--out results.json]
    python -m tools.latency_benchmark --live-capture-test  # also measures
        one real mic-open -> first-callback latency number
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from core.asr.whisper_cpp_asr import WhisperCppASR
from core.audio.playback import AudioPlayback
from core.audio.wav_io import read_wav
from core.common.config import REPO_ROOT, load_config
from core.language_id.whisper_lid import WhisperLanguageIdentifier
from core.translation.ctranslate2_translator import CTranslate2TranslationEngine
from core.translation.model_registry import TranslationModelRegistry
from core.tts.piper_tts import PiperTTSEngine
from core.tts.voice_registry import VoiceRegistry
from core.vad.segmenter import SpeechSegmenter
from core.vad.webrtc_vad import WebRtcVAD

FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "speech"


def _resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else REPO_ROOT / path


def measure_vad_segmentation_latency(audio, sample_rate_hz: int) -> float:
    """Wall-clock time to push every frame of a pre-recorded clip through
    the segmenter - cheap (webrtcvad + array ops), included for
    completeness per the spec's explicit list, not because it's expected
    to be significant next to ASR's multi-second encoder cost."""
    vad = WebRtcVAD(aggressiveness=2)
    segmenter = SpeechSegmenter(vad=vad, sample_rate_hz=sample_rate_hz)
    frame_samples = segmenter.frame_samples

    start = time.perf_counter()
    for i in range(0, len(audio) - frame_samples + 1, frame_samples):
        segmenter.push(audio[i:i + frame_samples])
    segmenter.flush()
    return (time.perf_counter() - start) * 1000.0


def measure_playback_latency(audio, sample_rate_hz: int) -> tuple[float, float]:
    """Returns (wall_clock_ms, audio_duration_ms). The gap between them is
    playback overhead (device open/start latency) beyond the audio's own
    duration - blocking playback necessarily takes at least as long as the
    audio itself, so wall_clock >= duration is expected, not a bug."""
    playback = AudioPlayback()
    duration_ms = len(audio) / sample_rate_hz * 1000.0
    start = time.perf_counter()
    playback.play(audio, sample_rate_hz, blocking=True)
    wall_ms = (time.perf_counter() - start) * 1000.0
    return wall_ms, duration_ms


def measure_capture_open_latency() -> float:
    """Real hardware: wall-clock from requesting a mic stream to the first
    audio callback actually firing - the "how long before we're listening"
    number, not the steady-state per-frame latency (already measured in
    Phase 1's AudioDiagnostics)."""
    import threading

    from core.audio.capture import MicrophoneCapture

    first_callback_time: list[float] = []
    got_callback = threading.Event()

    def on_frames(pcm):
        if not first_callback_time:
            first_callback_time.append(time.perf_counter())
            got_callback.set()

    capture = MicrophoneCapture(on_frames=on_frames)
    start = time.perf_counter()
    capture.start()
    got_callback.wait(timeout=5)
    capture.stop()
    if not first_callback_time:
        return float("nan")
    return (first_callback_time[0] - start) * 1000.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--languages", nargs="+", default=["en", "es"])
    parser.add_argument("--live-capture-test", action="store_true")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    asr_cfg = load_config().asr
    binary_path = _resolve(asr_cfg.binary_path)
    model_path = _resolve(asr_cfg.model_path)
    if not binary_path.exists() or not model_path.exists():
        print("whisper.cpp not set up. Run tools/setup_whisper_cpp.sh first.")
        return 1

    translation_registry = TranslationModelRegistry.load()
    tts_registry = VoiceRegistry.load()

    lid = WhisperLanguageIdentifier(binary_path, model_path)
    asr = WhisperCppASR(binary_path, model_path)
    translator = CTranslate2TranslationEngine(translation_registry)
    tts = PiperTTSEngine(tts_registry)

    with open(FIXTURES_DIR / "manifest.json") as f:
        manifest = json.load(f)

    rows = []
    for lang in args.languages:
        if lang not in manifest:
            continue
        audio, sr = read_wav(FIXTURES_DIR / f"{lang}.wav")

        vad_ms = measure_vad_segmentation_latency(audio, sr)

        start = time.perf_counter()
        lid_result = lid.identify(audio, sr)
        lid_ms = (time.perf_counter() - start) * 1000.0

        start = time.perf_counter()
        transcription = asr.transcribe(audio, sr, language=lang)  # forced: isolate from LID accuracy
        asr_ms = (time.perf_counter() - start) * 1000.0

        translation_ms = 0.0
        target_text = transcription.text
        if lang != "en" and translator.supports_pair(lang, "en"):
            start = time.perf_counter()
            translation = translator.translate(transcription.text, lang, "en")
            translation_ms = (time.perf_counter() - start) * 1000.0
            target_text = translation.text

        start = time.perf_counter()
        synthesis = tts.synthesize(target_text)
        tts_ms = (time.perf_counter() - start) * 1000.0

        playback_wall_ms, playback_audio_ms = measure_playback_latency(
            synthesis.audio, synthesis.sample_rate_hz
        )

        total_ms = vad_ms + lid_ms + asr_ms + translation_ms + tts_ms + playback_wall_ms
        row = {
            "language": lang,
            "lid_confidence": round(lid_result.confidence, 3),
            "vad_ms": round(vad_ms, 1),
            "language_id_ms": round(lid_ms, 1),
            "asr_ms": round(asr_ms, 1),
            "translation_ms": round(translation_ms, 1),
            "tts_ms": round(tts_ms, 1),
            "playback_wall_ms": round(playback_wall_ms, 1),
            "playback_audio_duration_ms": round(playback_audio_ms, 1),
            "total_ms": round(total_ms, 1),
        }
        rows.append(row)
        print(f"  {lang}: vad={vad_ms:.0f}ms lid={lid_ms:.0f}ms asr={asr_ms:.0f}ms "
              f"translation={translation_ms:.0f}ms tts={tts_ms:.0f}ms "
              f"playback={playback_wall_ms:.0f}ms  TOTAL={total_ms:.0f}ms")

    capture_open_ms = None
    if args.live_capture_test:
        capture_open_ms = measure_capture_open_latency()
        print(f"\nmic open -> first callback: {capture_open_ms:.1f}ms")

    report = {"rows": rows, "capture_open_ms": capture_open_ms}
    if args.out:
        args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"\nWrote {args.out}")

    if rows:
        avg_total = sum(r["total_ms"] for r in rows) / len(rows)
        print(f"\naverage total latency across {len(rows)} language(s): {avg_total:.0f}ms")
        print("NOTE: this is per-utterance latency on this CPU with the base ASR model.")
        print("It is dominated by the ASR/LID encoder passes (see docs/roadmap.md's Phase 9")
        print("profiling notes) - not fixable by streaming architecture alone. See Phase 11")
        print("(quantization) and Phase 12 (embedded/NPU hardware) for the real fix.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
