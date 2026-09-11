"""AT Phase 1 demo: microphone -> audio stream -> VAD -> speech segment.

This is the first end-to-end proof of the pipeline described in the AT
architecture doc, running on an ordinary workstation with no ASR/MT/TTS yet.
It opens the default microphone, runs streaming VAD over the incoming audio,
and for every detected speech segment prints its timing and writes it to a
WAV file for manual inspection.

Usage:
    python -m tools.mic_vad_demo --duration 15 --out-dir /tmp/at_segments
    python -m tools.mic_vad_demo --duration 15 --vad-aggressiveness 3
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import numpy as np

from core.audio.capture import MicrophoneCapture
from core.audio.wav_io import write_wav
from core.common.config import load_config
from core.common.logging_setup import configure_logging
from core.vad.segmenter import SpeechSegmenter
from core.vad.webrtc_vad import WebRtcVAD

logger = logging.getLogger("tools.mic_vad_demo")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=15.0, help="seconds to listen")
    parser.add_argument("--out-dir", type=Path, default=Path("/tmp/at_segments"))
    parser.add_argument("--sample-rate", type=int, default=None, help="override config sample rate")
    parser.add_argument("--vad-aggressiveness", type=int, default=None, choices=[0, 1, 2, 3])
    parser.add_argument("--device", type=str, default=None, help="PortAudio input device name/index")
    parser.add_argument("--json-logs", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = load_config()
    configure_logging(level=cfg.log_level, json_output=args.json_logs)

    sample_rate_hz = args.sample_rate or cfg.audio.sample_rate_hz
    frame_samples = int(sample_rate_hz * cfg.vad.frame_ms / 1000)
    aggressiveness = (
        args.vad_aggressiveness if args.vad_aggressiveness is not None else cfg.vad.aggressiveness
    )
    device = args.device or cfg.audio.device

    vad = WebRtcVAD(aggressiveness=aggressiveness)
    segmenter = SpeechSegmenter(
        vad=vad,
        sample_rate_hz=sample_rate_hz,
        frame_ms=cfg.vad.frame_ms,
        min_speech_ms=cfg.vad.min_speech_ms,
        hangover_ms=cfg.vad.hangover_ms,
        max_segment_ms=cfg.vad.max_segment_ms,
    )

    segments_found = []
    leftover = bytearray()

    def on_frames(pcm) -> None:
        # pcm arrives in whatever blocksize PortAudio delivers; re-chunk to
        # the VAD's fixed frame size using a small leftover buffer.
        nonlocal leftover
        leftover.extend(pcm.tobytes())
        frame_bytes = frame_samples * 2  # int16 = 2 bytes/sample
        while len(leftover) >= frame_bytes:
            chunk = leftover[:frame_bytes]
            del leftover[:frame_bytes]
            frame = np.frombuffer(bytes(chunk), dtype=np.int16)
            segment = segmenter.push(frame)
            if segment is not None:
                segments_found.append(segment)
                idx = len(segments_found)
                out_path = args.out_dir / f"segment_{idx:03d}.wav"
                write_wav(out_path, segment.audio, sample_rate_hz)
                logger.info(
                    "speech segment #%d: %.2fs - %.2fs (%.2fs) forced_close=%s -> %s",
                    idx,
                    segment.start_time_s,
                    segment.end_time_s,
                    segment.duration_s,
                    segment.forced_close,
                    out_path,
                )

    capture = MicrophoneCapture(
        sample_rate_hz=sample_rate_hz,
        channels=cfg.audio.channels,
        blocksize_samples=cfg.audio.blocksize_samples,
        device=device,
        ring_buffer_seconds=cfg.audio.ring_buffer_seconds,
        on_frames=on_frames,
    )

    logger.info("listening for %.1fs (aggressiveness=%d, sample_rate=%d)...",
                args.duration, aggressiveness, sample_rate_hz)
    with capture:
        time.sleep(args.duration)

    final_segment = segmenter.flush()
    if final_segment is not None:
        segments_found.append(final_segment)
        idx = len(segments_found)
        out_path = args.out_dir / f"segment_{idx:03d}.wav"
        write_wav(out_path, final_segment.audio, sample_rate_hz)
        logger.info("final in-progress segment flushed -> %s", out_path)

    diag = capture.diagnostics.snapshot()
    logger.info("diagnostics: %s", diag)
    logger.info("total speech segments detected: %d", len(segments_found))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
