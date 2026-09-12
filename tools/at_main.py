"""AT (AutoT) - the main entry point: one command to launch the system.

Defaults to the live terminal UI (tools.at_translate_tui): microphone ->
VAD -> language ID -> ASR -> translation -> TTS -> speaker, shown live, and
runs until interrupted (Ctrl+C) rather than a fixed test duration - because
"turn it on and it just works" is the actual product experience this
project is building toward (the master spec's "must continuously listen,
translate and speak" requirement, core/streaming/session.py's docstring),
not a timed demo.

This is a thin dispatcher, not new pipeline logic: every mode below reuses
tools.at_translate's build_pipeline/run_live_mode/run_file_mode and
tools.at_translate_tui's run_tui_live_mode unchanged.

Modes:
    autot                          default: live terminal UI, runs until Ctrl+C
    autot --duration 60            live terminal UI for a fixed window
    autot --headless               live mode with no UI (plain log lines) -
                                    the shape a future embedded/headless target
                                    would use, since it has no terminal to
                                    render a UI into
    autot --input-file speech.wav  process one WAV file, no mic, no UI

Usage:
    python -m tools.at_main
    python -m tools.at_main --headless --duration 30
    python -m tools.at_main --input-file some_speech.wav
"""

from __future__ import annotations

import argparse
from pathlib import Path

from core.common.logging_setup import configure_logging
from tools.at_translate import build_pipeline, run_file_mode, run_live_mode


def choose_mode(args: argparse.Namespace) -> str:
    """Pulled out as its own function so the dispatch decision is testable
    without needing a real mic/models - mode selection is pure logic,
    mode execution below is not."""
    if args.input_file is not None:
        return "file"
    if args.headless:
        return "headless"
    return "tui"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", default="en")
    parser.add_argument(
        "--duration", type=float, default=None,
        help="seconds to listen (default: run until Ctrl+C)",
    )
    parser.add_argument("--headless", action="store_true", help="live mode without the terminal UI")
    parser.add_argument("--input-file", type=Path, default=None, help="process a WAV file instead of the mic")
    parser.add_argument("--asr-model", default=None, help="e.g. tiny, base (default: config)")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--device", default=None, help="mic device (live modes only)")
    parser.add_argument("--out-dir", type=Path, default=None, help="save each segment's synthesized WAV")
    parser.add_argument("--no-play", action="store_true", help="don't play audio out loud")
    parser.add_argument("--json-logs", action="store_true", help="--headless/--input-file only")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)

    mode = choose_mode(args)

    if mode == "tui":
        try:
            from rich.console import Console

            from tools.at_translate_tui import run_tui_live_mode
        except ImportError as e:
            raise SystemExit(
                'The live terminal UI needs the "tui" extra: pip install -e ".[tui]"\n'
                "(or pass --headless to run without a UI)"
            ) from e
        configure_logging(level="WARNING")  # keep stray log lines out of the live display
        console = Console()
        console.print("[bold]Loading models…[/bold] (this can take a few seconds)")
        pipeline = build_pipeline(args.target, args.asr_model, args.threads)
        run_tui_live_mode(args, pipeline, console)
        return 0

    configure_logging(level="INFO", json_output=args.json_logs)
    pipeline = build_pipeline(args.target, args.asr_model, args.threads)
    if mode == "file":
        run_file_mode(args, pipeline)
    else:
        run_live_mode(args, pipeline)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
