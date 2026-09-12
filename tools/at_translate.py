"""AT Phase 8: the complete software pipeline as a command-line program.

    microphone -> VAD -> language ID -> ASR -> translation -> TTS -> speaker

This is the first point in the project where a user can plausibly experience
"speak a foreign language, hear English back" - proven on a workstation,
per the master architecture decision to prove the pipeline before shrinking
it into embedded hardware (Phases 12+).

Usage:
    python -m tools.at_translate --duration 30
    python -m tools.at_translate --input-file some_speech.wav
    python -m tools.at_translate --asr-model tiny   # faster, less accurate
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from core.asr.whisper_cpp_asr import WhisperCppASR
from core.audio.capture import MicrophoneCapture
from core.audio.playback import AudioPlayback
from core.audio.wav_io import read_wav, write_wav
from core.common.config import REPO_ROOT, load_config
from core.common.logging_setup import configure_logging
from core.language_id.whisper_lid import WhisperLanguageIdentifier
from core.orchestration.pipeline import PipelineStatus, TranslationPipeline
from core.streaming.session import StreamingSession
from core.translation.ctranslate2_translator import CTranslate2TranslationEngine
from core.translation.model_registry import TranslationModelRegistry
from core.tts.piper_tts import PiperTTSEngine
from core.tts.voice_registry import VoiceRegistry
from core.vad.segmenter import SpeechSegmenter
from core.vad.webrtc_vad import WebRtcVAD

logger = logging.getLogger("tools.at_translate")


def _resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else REPO_ROOT / path


def build_pipeline(target_language: str, asr_model: str | None, threads: int) -> TranslationPipeline:
    cfg = load_config().asr
    binary_path = _resolve(cfg.binary_path)
    model_path = (
        _resolve(cfg.model_path).parent / f"ggml-{asr_model}.bin"
        if asr_model else _resolve(cfg.model_path)
    )
    if not binary_path.exists() or not model_path.exists():
        raise SystemExit(
            f"ASR model/binary not found ({binary_path}, {model_path}). "
            "Run tools/setup_whisper_cpp.sh first."
        )

    translation_registry = TranslationModelRegistry.load()
    tts_registry = VoiceRegistry.load()

    return TranslationPipeline(
        language_identifier=WhisperLanguageIdentifier(binary_path, model_path, threads=threads),
        asr_engine=WhisperCppASR(binary_path, model_path, threads=threads),
        translation_engine=CTranslate2TranslationEngine(translation_registry),
        tts_engine=PiperTTSEngine(tts_registry),
        target_language=target_language,
    )


def handle_result(
    result,
    playback: AudioPlayback | None,
    out_dir: Path | None,
    segment_index: int,
) -> None:
    """Logs/saves/plays an already-computed PipelineResult. Deliberately
    does NOT call pipeline.process() itself - see core/streaming/session.py
    for why that must happen off the real-time audio thread in live mode."""
    if result.status == PipelineStatus.LOW_CONFIDENCE:
        assert result.detected_language is not None  # guaranteed by this status
        logger.info(
            "segment %d: low-confidence language (%s, %.2f) - skipped",
            segment_index, result.detected_language.language, result.detected_language.confidence,
        )
        return
    if result.status == PipelineStatus.UNSUPPORTED_LANGUAGE:
        assert result.detected_language is not None  # guaranteed by this status
        logger.info(
            "segment %d: no translation model for %s - skipped",
            segment_index, result.detected_language.language,
        )
        return
    if result.status == PipelineStatus.EMPTY_TRANSCRIPTION:
        logger.info("segment %d: empty transcription - skipped", segment_index)
        return
    if result.status == PipelineStatus.ERROR:
        logger.error("segment %d: pipeline error: %s", segment_index, result.error)
        return

    # Only PipelineStatus.OK reaches here, which guarantees every field below is set.
    assert result.detected_language is not None
    assert result.transcription is not None
    assert result.synthesis is not None

    total_ms = sum(result.stage_latencies_ms.values())
    logger.info(
        "segment %d [%s, conf=%.2f]: %r -> %r (total=%.0fms: %s)",
        segment_index, result.detected_language.language, result.detected_language.confidence,
        result.transcription.text,
        result.translation.text if result.translation else result.transcription.text,
        total_ms,
        ", ".join(f"{k}={v:.0f}ms" for k, v in result.stage_latencies_ms.items()),
    )

    if out_dir is not None:
        out_path = out_dir / f"segment_{segment_index:03d}.wav"
        write_wav(out_path, result.synthesis.audio, result.synthesis.sample_rate_hz)
        logger.info("segment %d: wrote %s", segment_index, out_path)

    if playback is not None:
        playback.play(result.synthesis.audio, result.synthesis.sample_rate_hz, blocking=True)


def run_file_mode(args, pipeline: TranslationPipeline) -> None:
    """File mode processes sequentially in the main thread - there is no
    real-time audio callback to protect here, unlike live mode (see
    core/streaming/session.py), so a direct process()-then-handle() call is
    fine."""
    audio, sample_rate_hz = read_wav(args.input_file)
    vad = WebRtcVAD(aggressiveness=2)
    segmenter = SpeechSegmenter(vad=vad, sample_rate_hz=sample_rate_hz)

    frame_samples = segmenter.frame_samples
    playback = None if args.no_play else AudioPlayback()
    segment_index = 0

    def process_and_handle(segment_audio) -> None:
        nonlocal segment_index
        segment_index += 1
        result = pipeline.process(segment_audio, sample_rate_hz)
        handle_result(result, playback, args.out_dir, segment_index)

    for start in range(0, len(audio) - frame_samples + 1, frame_samples):
        frame = audio[start:start + frame_samples]
        segment = segmenter.push(frame)
        if segment is not None:
            process_and_handle(segment.audio)
    final = segmenter.flush()
    if final is not None:
        process_and_handle(final.audio)

    logger.info("processed %d segment(s) from %s", segment_index, args.input_file)


def run_live_mode(args, pipeline: TranslationPipeline) -> None:
    """Live mode MUST keep the microphone's real-time callback thread free
    of slow work (pipeline.process() + blocking playback can take tens of
    seconds - see core/streaming/session.py's docstring for the bug this
    fixes), so segment processing runs on StreamingSession's background
    worker thread; on_frames only does cheap VAD/segmentation + a
    non-blocking queue push."""
    cfg = load_config()
    vad = WebRtcVAD(aggressiveness=cfg.vad.aggressiveness)
    segmenter = SpeechSegmenter(
        vad=vad, sample_rate_hz=cfg.audio.sample_rate_hz, frame_ms=cfg.vad.frame_ms,
        min_speech_ms=cfg.vad.min_speech_ms, hangover_ms=cfg.vad.hangover_ms,
        max_segment_ms=cfg.vad.max_segment_ms,
    )
    playback = None if args.no_play else AudioPlayback()
    submitted_count = [0]
    result_count = [0]
    leftover = bytearray()
    frame_samples = segmenter.frame_samples

    def on_result(result) -> None:
        result_count[0] += 1
        handle_result(result, playback, args.out_dir, result_count[0])

    session = StreamingSession(pipeline, cfg.audio.sample_rate_hz, on_result=on_result)

    def on_frames(pcm) -> None:
        # Runs on PortAudio's real-time thread - must stay fast. VAD/segment
        # assembly is cheap (a webrtcvad call + array ops); session.submit()
        # is an O(1) queue push. Never call pipeline.process() or block here.
        nonlocal leftover
        import numpy as np

        leftover.extend(pcm.tobytes())
        frame_bytes = frame_samples * 2
        while len(leftover) >= frame_bytes:
            chunk = leftover[:frame_bytes]
            del leftover[:frame_bytes]
            frame = np.frombuffer(bytes(chunk), dtype=np.int16)
            segment = segmenter.push(frame)
            if segment is not None:
                submitted_count[0] += 1
                if session.pending_count > 0:
                    logger.info(
                        "segment %d captured while %d earlier segment(s) still processing",
                        submitted_count[0], session.pending_count,
                    )
                session.submit(segment.audio)

    capture = MicrophoneCapture(
        sample_rate_hz=cfg.audio.sample_rate_hz, channels=cfg.audio.channels,
        blocksize_samples=cfg.audio.blocksize_samples, device=args.device,
        ring_buffer_seconds=cfg.audio.ring_buffer_seconds, on_frames=on_frames,
    )
    if args.duration is None:
        logger.info("listening indefinitely (target=%s)... speak now, Ctrl+C to stop", args.target)
    else:
        logger.info("listening for %.0fs (target=%s)... speak now", args.duration, args.target)
    with capture:
        try:
            if args.duration is None:
                while True:
                    time.sleep(0.2)
            else:
                time.sleep(args.duration)
        except KeyboardInterrupt:
            logger.info("stopping (Ctrl+C)...")
    final = segmenter.flush()
    if final is not None:
        submitted_count[0] += 1
        session.submit(final.audio)

    if session.pending_count > 0:
        logger.info("draining %d remaining segment(s)...", session.pending_count)
    drain_deadline = time.perf_counter() + 300.0  # generous: base-model ASR can take ~90s/segment
    while result_count[0] < submitted_count[0] and time.perf_counter() < drain_deadline:
        time.sleep(0.2)
    session.stop()

    logger.info("done: captured %d segment(s), processed %d", submitted_count[0], result_count[0])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="auto", help="currently always auto-detected")
    parser.add_argument("--target", default="en")
    parser.add_argument("--duration", type=float, default=30.0, help="live mode: seconds to listen")
    parser.add_argument("--input-file", type=Path, default=None, help="process a WAV file instead of the mic")
    parser.add_argument("--asr-model", default=None, help="e.g. tiny, base (default: config)")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--device", default=None, help="mic device (live mode only)")
    parser.add_argument("--out-dir", type=Path, default=None, help="save each segment's synthesized WAV")
    parser.add_argument("--no-play", action="store_true", help="don't play audio out loud")
    parser.add_argument("--json-logs", action="store_true")
    args = parser.parse_args()

    configure_logging(level="INFO", json_output=args.json_logs)
    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)

    pipeline = build_pipeline(args.target, args.asr_model, args.threads)

    if args.input_file:
        run_file_mode(args, pipeline)
    else:
        run_live_mode(args, pipeline)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
