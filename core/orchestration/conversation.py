"""Phase 17: AT Conversation Mode - two-direction translation between two
people speaking different languages, reusing Phase 8's TranslationPipeline
for each direction rather than building new ASR/translation/TTS logic.

Honest scope limit, not silently assumed away: "speaker identification"
and "turn detection" from raw audio alone (automatically figuring out WHO
is talking without being told) is a real, unimplemented research problem
(speaker diarization) this project has no model or hardware for - Phase
3's beamforming is synthetic-signal-only (see docs/architecture.md), and
there's no real multi-mic array to localize speakers with (Phase 13+ is
unbuilt hardware). So ``ConversationSession.process_utterance`` requires
the caller to say which side is speaking (e.g. from a push-to-talk button,
a physically dedicated mic per person, or a future diarization model) -
it does not guess. Do not present this as automatic turn detection to
users until that gap is actually closed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from core.asr.base import ASREngine
from core.language_id.base import LanguageIdentifier
from core.orchestration.pipeline import PipelineResult, TranslationPipeline
from core.translation.base import TranslationEngine
from core.tts.base import TTSEngine


@dataclass(frozen=True)
class ConversationSide:
    side_id: str  # caller-defined, e.g. "A" / "B" or "guest" / "host"
    language: str


@dataclass
class Turn:
    side_id: str
    timestamp: float
    result: PipelineResult


class ConversationSession:
    def __init__(
        self,
        language_identifier: LanguageIdentifier,
        asr_engine: ASREngine,
        translation_engine: TranslationEngine,
        tts_engine: TTSEngine,
        side_a: ConversationSide,
        side_b: ConversationSide,
    ):
        if side_a.side_id == side_b.side_id:
            raise ValueError("side_a and side_b must have distinct side_id values")
        self.side_a = side_a
        self.side_b = side_b
        # Two lightweight pipeline wrappers sharing the same underlying
        # engines (ASR/LID/translation/TTS are not duplicated or reloaded -
        # only the target_language differs per direction).
        self._pipelines = {
            side_a.side_id: TranslationPipeline(
                language_identifier, asr_engine, translation_engine, tts_engine,
                target_language=side_b.language,
            ),
            side_b.side_id: TranslationPipeline(
                language_identifier, asr_engine, translation_engine, tts_engine,
                target_language=side_a.language,
            ),
        }
        self.turns: list[Turn] = []

    def other_side(self, side_id: str) -> ConversationSide:
        if side_id == self.side_a.side_id:
            return self.side_b
        if side_id == self.side_b.side_id:
            return self.side_a
        raise ValueError(f"unknown side_id: {side_id!r}")

    def process_utterance(
        self, audio: np.ndarray, sample_rate_hz: int, speaking_side_id: str
    ) -> PipelineResult:
        """Routes audio spoken by `speaking_side_id` to the other side's
        language. Raises ValueError for an unrecognized side_id rather than
        silently guessing which direction to translate."""
        if speaking_side_id not in self._pipelines:
            raise ValueError(
                f"unknown side_id {speaking_side_id!r}, expected one of "
                f"{[self.side_a.side_id, self.side_b.side_id]}"
            )
        pipeline = self._pipelines[speaking_side_id]
        result = pipeline.process(audio, sample_rate_hz)
        self.turns.append(Turn(side_id=speaking_side_id, timestamp=time.time(), result=result))
        return result

    def transcript(self) -> list[dict]:
        """Simultaneous conversation state as a simple turn-by-turn log -
        who spoke, what was said, what was translated, in order."""
        entries = []
        for turn in self.turns:
            r = turn.result
            entries.append({
                "side_id": turn.side_id,
                "timestamp": turn.timestamp,
                "status": r.status,
                "source_text": r.transcription.text if r.transcription else None,
                "translated_text": (
                    r.translation.text if r.translation
                    else (r.transcription.text if r.transcription else None)
                ),
            })
        return entries
