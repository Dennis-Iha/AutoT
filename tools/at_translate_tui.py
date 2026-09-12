"""A live terminal UI for tools.at_translate's microphone live mode.

Same real pipeline, same Phase 9 StreamingSession architecture as
`tools.at_translate`'s live mode - this file adds no new pipeline logic,
only a richer view than log lines scrolling by: a mic-level meter (derived
from real captured audio, not simulated), the most recently completed
segment's detected language/confidence/transcription/translation/latency,
and a scrolling history table.

Workstation-only, by design: this is a visualization tool for proving and
demonstrating the pipeline while AT-CORE runs on a computer with a real
terminal, per the master architecture decision to prove the pipeline here
before shrinking it onto headphone/earbud hardware (Phase 12+). It is NOT
expected to survive onto the embedded target - there is no terminal to
render into there, and this file is not imported by anything in core/.

Requires the `tui` optional dependency group (rich):
    pip install -e ".[tui]"

Usage:
    python -m tools.at_translate_tui --duration 120
    python -m tools.at_translate_tui --asr-model tiny --no-play
"""

from __future__ import annotations

import argparse
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from core.audio.capture import MicrophoneCapture
from core.audio.playback import AudioPlayback
from core.audio.wav_io import write_wav
from core.common.config import load_config
from core.common.logging_setup import configure_logging
from core.orchestration.pipeline import PipelineResult, PipelineStatus, TranslationPipeline
from core.streaming.session import StreamingSession
from core.vad.segmenter import SpeechSegmenter
from core.vad.webrtc_vad import WebRtcVAD
from tools.at_translate import build_pipeline

MIC_LEVEL_REFERENCE = 3000.0  # int16 RMS that renders as a "full" meter - a
# relative loudness indicator for this display only, NOT a calibrated dB
# measurement; don't read anything quantitative into the exact number.
HISTORY_SIZE = 12


@dataclass
class LiveState:
    status: str = "starting"
    target_language: str = "en"
    duration_s: float | None = None  # None = run until Ctrl+C, not a fixed window
    started_at: float = field(default_factory=time.perf_counter)
    mic_level: float = 0.0
    speech_active: bool = False
    submitted: int = 0
    processed: int = 0
    current: PipelineResult | None = None
    current_index: int = 0
    history: deque[tuple[int, PipelineResult]] = field(
        default_factory=lambda: deque(maxlen=HISTORY_SIZE)
    )
    lock: threading.Lock = field(default_factory=threading.Lock)


def _status_text(result: PipelineResult) -> str:
    return {
        PipelineStatus.OK: "[bold green]ok[/bold green]",
        PipelineStatus.LOW_CONFIDENCE: "[yellow]low confidence[/yellow]",
        PipelineStatus.UNSUPPORTED_LANGUAGE: "[yellow]unsupported[/yellow]",
        PipelineStatus.EMPTY_TRANSCRIPTION: "[dim]empty[/dim]",
        PipelineStatus.ERROR: "[bold red]error[/bold red]",
    }.get(result.status, result.status)


def _truncate(text: str | None, width: int = 42) -> str:
    if not text:
        return "-"
    return text if len(text) <= width else text[: width - 1] + "…"


def render(state: LiveState) -> Group:
    with state.lock:
        elapsed = time.perf_counter() - state.started_at
        duration_s = state.duration_s
        status, submitted, processed = state.status, state.submitted, state.processed
        mic_level, speech_active = state.mic_level, state.speech_active
        current, current_index = state.current, state.current_index
        history = list(state.history)

    if duration_s is None:
        time_field = f"{elapsed:4.0f}s elapsed (Ctrl+C to stop)"
    else:
        time_field = f"{max(0.0, duration_s - elapsed):4.0f}s left"

    badge = {
        "listening": "[bold green]LISTENING[/bold green]",
        "draining": "[bold yellow]FINISHING UP…[/bold yellow]",
        "done": "[bold]DONE[/bold]",
        "starting": "[dim]STARTING…[/dim]",
    }.get(status, status)
    header = Panel(
        Text.from_markup(
            f"[bold]AT Live Translation[/bold]  ({state.target_language} target)     "
            f"{badge}     {time_field}     "
            f"captured {submitted} / processed {processed}"
        ),
        border_style="blue",
    )

    bar_width = 40
    filled = min(bar_width, round(bar_width * mic_level))
    meter_color = "green" if speech_active else "grey50"
    meter = Panel(
        Text.from_markup(
            f"mic  [{meter_color}]{'█' * filled}{' ' * (bar_width - filled)}[/{meter_color}]  "
            + ("[bold green]speech[/bold green]" if speech_active else "[dim]silence[/dim]")
        ),
        border_style="grey50",
    )

    if current is None:
        current_body = Text("Waiting for speech…", style="dim")
    else:
        detected = current.detected_language
        lines = [
            f"Segment {current_index}",
            f"  Detected:   {detected.language if detected else '?'}  "
            f"(confidence {detected.confidence:.2f})" if detected else "  Detected:   ?",
            f"  Status:     {_status_text(current)}",
            f"  Heard:      {_truncate(current.transcription.text if current.transcription else None)}",
            f"  English:    {_truncate(current.translation.text if current.translation else (current.transcription.text if current.transcription and current.ok else None))}",
            f"  Latency:    {sum(current.stage_latencies_ms.values()) / 1000:.1f}s"
            if current.stage_latencies_ms else "  Latency:    -",
        ]
        current_body = Text.from_markup("\n".join(lines))
    current_panel = Panel(current_body, title="Current segment", border_style="cyan")

    table = Table(title="History", expand=True)
    table.add_column("#", width=3, justify="right")
    table.add_column("Lang", width=6)
    table.add_column("Status", width=16)
    table.add_column("Heard")
    table.add_column("English")
    table.add_column("Latency", width=8, justify="right")
    for index, result in history:
        detected = result.detected_language
        latency = (
            f"{sum(result.stage_latencies_ms.values()) / 1000:.1f}s"
            if result.stage_latencies_ms else "-"
        )
        english = (
            result.translation.text if result.translation
            else (result.transcription.text if result.transcription and result.ok else "-")
        )
        table.add_row(
            str(index),
            detected.language if detected else "?",
            _status_text(result),
            _truncate(result.transcription.text if result.transcription else None, 30),
            _truncate(english, 30),
            latency,
        )

    return Group(header, meter, current_panel, table)


def run_tui_live_mode(args, pipeline: TranslationPipeline, console: Console) -> None:
    """Everything after the model is loaded: live mic -> VAD -> pipeline ->
    speaker, rendered as the live dashboard. Pulled out of main() so
    tools.at_main (the consolidated entry point) can drive this directly
    without re-parsing argv or duplicating this setup. `args` needs
    `.target`, `.duration` (float seconds, or None to run until Ctrl+C),
    `.device`, `.out_dir`, `.no_play` - the same shape tools.at_translate's
    run_live_mode expects, so a single argparse namespace serves both."""
    state = LiveState(target_language=args.target, duration_s=args.duration, status="listening")
    cfg = load_config()
    vad = WebRtcVAD(aggressiveness=cfg.vad.aggressiveness)
    segmenter = SpeechSegmenter(
        vad=vad, sample_rate_hz=cfg.audio.sample_rate_hz, frame_ms=cfg.vad.frame_ms,
        min_speech_ms=cfg.vad.min_speech_ms, hangover_ms=cfg.vad.hangover_ms,
        max_segment_ms=cfg.vad.max_segment_ms,
    )
    playback = None if args.no_play else AudioPlayback()
    leftover = bytearray()
    frame_samples = segmenter.frame_samples

    def on_result(result: PipelineResult) -> None:
        with state.lock:
            state.processed += 1
            state.current = result
            state.current_index = state.processed
            state.history.append((state.processed, result))
        if result.ok and playback is not None and result.synthesis is not None:
            playback.play(result.synthesis.audio, result.synthesis.sample_rate_hz, blocking=True)
        if result.ok and args.out_dir is not None and result.synthesis is not None:
            write_wav(
                args.out_dir / f"segment_{state.processed:03d}.wav",
                result.synthesis.audio, result.synthesis.sample_rate_hz,
            )

    session = StreamingSession(pipeline, cfg.audio.sample_rate_hz, on_result=on_result)

    def on_frames(pcm: np.ndarray) -> None:
        nonlocal leftover
        level = min(1.0, float(np.sqrt(np.mean(pcm.astype(np.float64) ** 2))) / MIC_LEVEL_REFERENCE)
        with state.lock:
            state.mic_level = level

        leftover.extend(pcm.tobytes())
        frame_bytes = frame_samples * 2
        while len(leftover) >= frame_bytes:
            chunk = leftover[:frame_bytes]
            del leftover[:frame_bytes]
            frame = np.frombuffer(bytes(chunk), dtype=np.int16)
            segment = segmenter.push(frame)
            with state.lock:
                state.speech_active = segmenter.in_segment
            if segment is not None:
                with state.lock:
                    state.submitted += 1
                session.submit(segment.audio)

    capture = MicrophoneCapture(
        sample_rate_hz=cfg.audio.sample_rate_hz, channels=cfg.audio.channels,
        blocksize_samples=cfg.audio.blocksize_samples, device=args.device,
        ring_buffer_seconds=cfg.audio.ring_buffer_seconds, on_frames=on_frames,
    )

    with Live(render(state), console=console, refresh_per_second=10, screen=True) as live:
        with capture:
            try:
                if args.duration is None:
                    while True:
                        live.update(render(state))
                        time.sleep(0.1)
                else:
                    deadline = time.perf_counter() + args.duration
                    while time.perf_counter() < deadline:
                        live.update(render(state))
                        time.sleep(0.1)
            except KeyboardInterrupt:
                pass

        final = segmenter.flush()
        if final is not None:
            with state.lock:
                state.submitted += 1
            session.submit(final.audio)

        with state.lock:
            state.status = "draining"
        drain_deadline = time.perf_counter() + 300.0
        while True:
            with state.lock:
                done = state.processed >= state.submitted
            if done or time.perf_counter() > drain_deadline:
                break
            live.update(render(state))
            time.sleep(0.1)

        session.stop()
        with state.lock:
            state.status = "done"
        live.update(render(state))
        time.sleep(1.5)  # let the final frame stay visible before the alt-screen exits

    console.print(
        f"\ndone: captured {state.submitted} segment(s), processed {state.processed}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default="en")
    parser.add_argument(
        "--duration", type=float, default=120.0,
        help="seconds to listen (for indefinite listening until Ctrl+C, use tools.at_main instead)",
    )
    parser.add_argument("--asr-model", default=None, help="e.g. tiny, base (default: config)")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--device", default=None, help="mic device")
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--no-play", action="store_true")
    args = parser.parse_args()

    configure_logging(level="WARNING")  # keep stray log lines out of the live display
    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)

    console = Console()
    console.print("[bold]Loading models…[/bold] (this can take a few seconds)")
    pipeline = build_pipeline(args.target, args.asr_model, args.threads)
    run_tui_live_mode(args, pipeline, console)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
