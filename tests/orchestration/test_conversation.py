"""Deterministic tests of ConversationSession's direction-routing and
transcript-tracking logic using fakes (same pattern as
test_pipeline.py) - no real models. See test_conversation_live.py for the
real end-to-end version.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.orchestration.conversation import ConversationSession, ConversationSide
from tests.orchestration.test_pipeline import (
    FakeASR,
    FakeLanguageIdentifier,
    FakeTranslation,
    FakeTTS,
)

SR = 16000


def make_session(**overrides):
    defaults = {
        "language_identifier": FakeLanguageIdentifier(language="es"),
        "asr_engine": FakeASR(text="hola"),
        "translation_engine": FakeTranslation(
            supported_pairs=(("es", "en"), ("en", "es")), output_text="hello"
        ),
        "tts_engine": FakeTTS(),
        "side_a": ConversationSide(side_id="A", language="es"),
        "side_b": ConversationSide(side_id="B", language="en"),
    }
    defaults.update(overrides)
    return ConversationSession(**defaults)


def make_audio():
    return np.zeros(SR, dtype=np.int16)


def test_side_a_speaking_routes_to_side_b_language():
    session = make_session()
    result = session.process_utterance(make_audio(), SR, speaking_side_id="A")
    assert result.ok
    assert result.translation is not None
    assert result.translation.target_language == "en"


def test_side_b_speaking_routes_to_side_a_language():
    session = make_session(
        language_identifier=FakeLanguageIdentifier(language="en"),
        asr_engine=FakeASR(text="hello"),
    )
    result = session.process_utterance(make_audio(), SR, speaking_side_id="B")
    assert result.ok
    assert result.translation is not None
    assert result.translation.target_language == "es"


def test_unknown_side_id_raises():
    session = make_session()
    with pytest.raises(ValueError, match="unknown side_id"):
        session.process_utterance(make_audio(), SR, speaking_side_id="C")


def test_duplicate_side_ids_rejected_at_construction():
    with pytest.raises(ValueError, match="distinct side_id"):
        make_session(
            side_a=ConversationSide(side_id="A", language="es"),
            side_b=ConversationSide(side_id="A", language="en"),
        )


def test_other_side_lookup():
    session = make_session()
    assert session.other_side("A").side_id == "B"
    assert session.other_side("B").side_id == "A"


def test_other_side_unknown_raises():
    session = make_session()
    with pytest.raises(ValueError):
        session.other_side("C")


def test_transcript_records_turns_in_order():
    session = make_session()
    session.process_utterance(make_audio(), SR, speaking_side_id="A")
    session.process_utterance(make_audio(), SR, speaking_side_id="A")
    transcript = session.transcript()
    assert len(transcript) == 2
    assert transcript[0]["side_id"] == "A"
    assert transcript[0]["source_text"] == "hola"
    assert transcript[0]["translated_text"] == "hello"


def test_transcript_reflects_low_confidence_turns():
    session = make_session(language_identifier=FakeLanguageIdentifier(language="es", confidence=0.1))
    session.process_utterance(make_audio(), SR, speaking_side_id="A")
    transcript = session.transcript()
    assert transcript[0]["status"] == "low_confidence"
    assert transcript[0]["source_text"] is None


def test_pipelines_share_engines_not_duplicated():
    asr = FakeASR(text="hola")
    session = make_session(asr_engine=asr)
    # Both directions' pipelines should reference the exact same engine
    # instance, not a re-constructed/reloaded copy.
    assert session._pipelines["A"].asr_engine is asr
    assert session._pipelines["B"].asr_engine is asr
