"""Tests tools/at_main.py's mode-dispatch logic - pure argument-parsing
decisions, testable without a real mic/models. The actual mode execution
(run_file_mode/run_live_mode/run_tui_live_mode) is tested where those
functions live (tools.at_translate, tools.at_translate_tui) and via real
manual smoke tests against the real mic - see docs/roadmap.md."""

from __future__ import annotations

from pathlib import Path

from tools.at_main import build_parser, choose_mode


def parse(*argv: str):
    return build_parser().parse_args(argv)


def test_default_mode_is_tui():
    assert choose_mode(parse()) == "tui"


def test_headless_flag_selects_headless_mode():
    assert choose_mode(parse("--headless")) == "headless"


def test_input_file_selects_file_mode():
    assert choose_mode(parse("--input-file", "speech.wav")) == "file"


def test_input_file_takes_priority_over_headless():
    assert choose_mode(parse("--input-file", "speech.wav", "--headless")) == "file"


def test_default_duration_is_none_meaning_indefinite():
    assert parse().duration is None


def test_explicit_duration_is_respected():
    assert parse("--duration", "45").duration == 45.0


def test_input_file_parses_to_path():
    args = parse("--input-file", "some/speech.wav")
    assert isinstance(args.input_file, Path)
    assert args.input_file == Path("some/speech.wav")
