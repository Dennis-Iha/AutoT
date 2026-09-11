"""TTSEngine backed by Piper (ONNX, no PyTorch - onnxruntime only). Piper
bundles its own espeak-ng phonemization data, so no separate espeak-ng
install is needed at runtime (it was only used, separately, to synthesize
the ASR/LID/translation test fixtures in tests/fixtures/speech/)."""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np
from piper import PiperVoice
from piper.config import SynthesisConfig

from core.tts.base import SynthesisResult, TTSEngine
from core.tts.voice_registry import VoiceRegistry


class PiperTTSEngine(TTSEngine):
    def __init__(self, registry: VoiceRegistry):
        self._registry = registry
        self._loaded: dict[str, PiperVoice] = {}

    def available_voices(self) -> list[str]:
        return [
            v for v in self._registry.voice_ids()
            if (entry := self._registry.get(v)) is not None and entry.is_ready()
        ]

    def _get_voice(self, voice_id: str) -> PiperVoice:
        if voice_id not in self._loaded:
            entry = self._registry.get(voice_id)
            if entry is None or not entry.is_ready():
                raise ValueError(f"voice not ready: {voice_id}")
            self._loaded[voice_id] = PiperVoice.load(
                str(entry.onnx_path), config_path=str(entry.config_path)
            )
        return self._loaded[voice_id]

    def synthesize(self, text: str, voice: str | None = None, speed: float = 1.0) -> SynthesisResult:
        voice_id = voice or self._registry.voice_ids()[0]
        piper_voice = self._get_voice(voice_id)

        # Piper's length_scale is inversely related to speed: smaller =
        # faster speech. speed=2.0 (twice as fast) -> length_scale=0.5.
        syn_config = SynthesisConfig(length_scale=1.0 / speed) if speed != 1.0 else None
        chunks = list(piper_voice.synthesize(text, syn_config=syn_config))
        if not chunks:
            raise RuntimeError(f"Piper produced no audio for voice {voice_id!r}")

        audio_bytes = b"".join(chunk.audio_int16_bytes for chunk in chunks)
        audio = np.frombuffer(audio_bytes, dtype=np.int16)
        sample_rate_hz = chunks[0].sample_rate

        return SynthesisResult(audio=audio, sample_rate_hz=sample_rate_hz, text=text, voice=voice_id)

    def synthesize_stream(
        self, texts: Iterator[str], voice: str | None = None, speed: float = 1.0
    ) -> Iterator[SynthesisResult]:
        for text in texts:
            yield self.synthesize(text, voice=voice, speed=speed)

    def unload(self, voice_id: str) -> None:
        self._loaded.pop(voice_id, None)
