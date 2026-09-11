"""Real end-to-end conversation mode test: actual whisper.cpp, CTranslate2,
Piper - a two-directional Spanish<->English exchange. Uses es/en, the
languages Phase 8 established are reliably detected by LID on this
project's synthesized fixtures (see docs/roadmap.md's Phase 8 section) -
this test is about conversation-mode ROUTING, not re-litigating the LID
accuracy question.
"""

from __future__ import annotations

import pytest

from core.asr.whisper_cpp_asr import WhisperCppASR
from core.audio.wav_io import read_wav
from core.language_id.whisper_lid import WhisperLanguageIdentifier
from core.orchestration.conversation import ConversationSession, ConversationSide
from core.translation.ctranslate2_translator import CTranslate2TranslationEngine
from core.tts.piper_tts import PiperTTSEngine


@pytest.fixture(scope="module")
def session(whisper_cpp_available, translation_registry, tts_registry):
    if whisper_cpp_available is None:
        pytest.skip("whisper.cpp not built - run tools/setup_whisper_cpp.sh first")
    if translation_registry is None:
        pytest.skip("no translation models installed - run tools/setup_translation_models.sh first")
    if tts_registry is None:
        pytest.skip("no TTS voices installed - run tools/setup_tts_models.sh first")
    if not translation_registry.supports_pair("es", "en"):
        pytest.skip("es->en translation model not installed")

    binary_path, model_path = whisper_cpp_available
    return ConversationSession(
        language_identifier=WhisperLanguageIdentifier(binary_path, model_path),
        asr_engine=WhisperCppASR(binary_path, model_path),
        translation_engine=CTranslate2TranslationEngine(translation_registry),
        tts_engine=PiperTTSEngine(tts_registry),
        side_a=ConversationSide(side_id="guest", language="es"),
        side_b=ConversationSide(side_id="host", language="en"),
    )


def test_guest_speaks_spanish_host_hears_english(session, speech_fixtures):
    audio, sr = read_wav(speech_fixtures["es"]["wav_path"])
    result = session.process_utterance(audio, sr, speaking_side_id="guest")

    assert result.ok, f"pipeline failed: status={result.status} error={result.error}"
    assert result.detected_language is not None
    assert result.detected_language.language == "es"
    assert result.translation is not None
    assert result.translation.target_language == "en"
    lowered = result.translation.text.lower()
    assert "where" in lowered or "station" in lowered


def test_host_speaks_english_guest_hears_spanish(session, speech_fixtures):
    audio, sr = read_wav(speech_fixtures["en"]["wav_path"])
    result = session.process_utterance(audio, sr, speaking_side_id="host")

    assert result.ok, f"pipeline failed: status={result.status} error={result.error}"
    assert result.detected_language is not None
    assert result.detected_language.language == "en"
    assert result.translation is not None
    assert result.translation.target_language == "es"


def test_transcript_captures_both_directions_of_a_real_exchange(session, speech_fixtures):
    es_audio, es_sr = read_wav(speech_fixtures["es"]["wav_path"])
    en_audio, en_sr = read_wav(speech_fixtures["en"]["wav_path"])

    session.process_utterance(es_audio, es_sr, speaking_side_id="guest")
    session.process_utterance(en_audio, en_sr, speaking_side_id="host")

    transcript = session.transcript()
    assert len(transcript) >= 2
    sides_spoken = {t["side_id"] for t in transcript[-2:]}
    assert sides_spoken == {"guest", "host"}
