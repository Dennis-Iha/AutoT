"""Tests the parts of tools/at_translate_tui.py that don't need real
hardware (mic/speaker) or downloaded models - the full live-mic path was
smoke-tested manually (real mic, real pipeline, a real pty) rather than in
pytest, since it needs an actual microphone and is inherently interactive;
see docs/roadmap.md for that result."""

from __future__ import annotations

from core.asr.base import LanguageDetectionResult, TranscriptionResult
from core.orchestration.pipeline import PipelineResult, PipelineStatus
from core.translation.base import TranslationResult
from tools.at_translate_tui import LiveState, _status_text, _truncate, render


def make_ok_result() -> PipelineResult:
    return PipelineResult(
        status=PipelineStatus.OK,
        detected_language=LanguageDetectionResult(language="es", confidence=0.94),
        transcription=TranscriptionResult(text="¿Dónde está la estación?", language="es", segments=[]),
        translation=TranslationResult(text="Where is the station?", source_language="es", target_language="en"),
        stage_latencies_ms={"language_id": 6000.0, "asr": 7000.0, "translation": 1000.0, "tts": 400.0},
    )


def make_low_confidence_result() -> PipelineResult:
    return PipelineResult(
        status=PipelineStatus.LOW_CONFIDENCE,
        detected_language=LanguageDetectionResult(language="en", confidence=0.55),
        stage_latencies_ms={"language_id": 6000.0},
    )


def test_truncate_leaves_short_text_alone():
    assert _truncate("hello") == "hello"


def test_truncate_shortens_long_text_with_ellipsis():
    text = "x" * 50
    result = _truncate(text, width=10)
    assert len(result) == 10
    assert result.endswith("…")


def test_truncate_handles_none_and_empty():
    assert _truncate(None) == "-"
    assert _truncate("") == "-"


def test_status_text_covers_every_pipeline_status():
    for status in (
        PipelineStatus.OK, PipelineStatus.LOW_CONFIDENCE, PipelineStatus.UNSUPPORTED_LANGUAGE,
        PipelineStatus.EMPTY_TRANSCRIPTION, PipelineStatus.ERROR,
    ):
        result = PipelineResult(status=status)
        text = _status_text(result)
        assert isinstance(text, str) and len(text) > 0


def test_render_with_no_segments_yet_does_not_crash():
    state = LiveState(target_language="en", duration_s=120.0, status="listening")
    group = render(state)
    assert group is not None


def test_render_with_indefinite_duration_shows_elapsed_not_remaining():
    """duration_s=None means "run until Ctrl+C" (tools.at_main's default) -
    there's no countdown to show, so the header must show elapsed time
    instead, not crash on `None - elapsed`."""
    from rich.console import Console

    state = LiveState(target_language="en", duration_s=None, status="listening")
    console = Console(record=True, width=100)
    console.print(render(state))
    text = console.export_text()
    assert "elapsed" in text
    assert "Ctrl+C" in text


def test_render_with_ok_result_and_history_does_not_crash():
    state = LiveState(target_language="en", duration_s=120.0, status="listening")
    result = make_ok_result()
    state.current = result
    state.current_index = 1
    state.processed = 1
    state.submitted = 1
    state.history.append((1, result))
    group = render(state)
    assert group is not None


def test_render_with_low_confidence_result_does_not_crash():
    state = LiveState(target_language="en", duration_s=120.0, status="listening")
    result = make_low_confidence_result()
    state.current = result
    state.current_index = 1
    state.processed = 1
    state.submitted = 1
    state.history.append((1, result))
    group = render(state)
    assert group is not None


def test_render_actually_produces_readable_text():
    """Renders to a real Console buffer (not just "doesn't crash") and
    confirms the real content - detected language, transcription,
    translation - actually appears in the output."""
    from rich.console import Console

    state = LiveState(target_language="en", duration_s=120.0, status="listening")
    result = make_ok_result()
    state.current = result
    state.current_index = 1
    state.processed = 1
    state.submitted = 1
    state.history.append((1, result))

    console = Console(record=True, width=100)
    console.print(render(state))
    text = console.export_text()

    assert "es" in text
    assert "0.94" in text
    assert "Where is the station?" in text
