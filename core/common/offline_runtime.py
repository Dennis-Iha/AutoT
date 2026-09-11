"""Phase 10: AT Offline Runtime - verifies every model a requested set of
languages needs is present AND not corrupted, before the pipeline tries to
use it.

Exists to fix a real failure-mode class, not a hypothetical one: this
project has already hit a truncated TTS model download (Phase 7) and an
accidental duplicated-nested-directory translation model (Phase 6) - both
would previously have surfaced as a confusing exception deep inside
onnxruntime or ctranslate2 the first time a user actually tried to use that
language, rather than a clear "language X isn't installed correctly, run
setup script Y" message before anything starts.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from core.asr.model_registry import ASRModelRegistry
from core.common.config import REPO_ROOT, load_config
from core.translation.model_registry import TranslationModelRegistry
from core.tts.voice_registry import VoiceRegistry


def _resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else REPO_ROOT / path


@dataclass
class ReadinessCheck:
    component: str
    ok: bool
    detail: str


@dataclass
class OfflineReadinessReport:
    checks: list[ReadinessCheck] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return all(c.ok for c in self.checks)

    def issues(self) -> list[ReadinessCheck]:
        return [c for c in self.checks if not c.ok]


def check_offline_readiness(
    languages: Iterable[str],
    target_language: str = "en",
    asr_model_id: str | None = None,
    tts_voice_id: str | None = None,
    verify_checksums: bool = True,
) -> OfflineReadinessReport:
    """Checks everything needed to run the pipeline fully offline for the
    given source languages -> target_language, WITHOUT loading any model
    into memory (registry/filesystem/checksum checks only - cheap enough to
    run at every startup, unlike actually loading whisper.cpp/ctranslate2/
    onnxruntime, which this deliberately avoids so a bad model doesn't crash
    the process it's meant to protect).

    verify_checksums=True reads every model file fully (see
    core/common/model_manifest.py) - do this at startup, not per-request.
    """
    checks: list[ReadinessCheck] = []
    cfg = load_config()

    binary_path = _resolve(cfg.asr.binary_path)
    checks.append(
        ReadinessCheck(
            component="whisper.cpp binary",
            ok=binary_path.exists(),
            detail=str(binary_path) if binary_path.exists() else f"missing: {binary_path} (run tools/setup_whisper_cpp.sh)",
        )
    )

    asr_registry = ASRModelRegistry.load()
    resolved_asr_id = asr_model_id
    if resolved_asr_id is None:
        # No explicit model requested - match whatever config.asr.model_path
        # points at, by filename, so this check reflects what the pipeline
        # actually uses by default.
        configured_path = _resolve(cfg.asr.model_path)
        for model_id in asr_registry.model_ids():
            candidate = asr_registry.get(model_id)
            if candidate is not None and candidate.path == configured_path:
                resolved_asr_id = model_id
                break
    asr_entry = asr_registry.get(resolved_asr_id) if resolved_asr_id else None
    if asr_entry is None:
        checks.append(
            ReadinessCheck(
                component=f"ASR model ({resolved_asr_id or cfg.asr.model_path})",
                ok=False,
                detail="not found in models/registry/asr_models.json",
            )
        )
    else:
        ok = asr_entry.is_valid() if verify_checksums else asr_entry.is_ready()
        checks.append(
            ReadinessCheck(
                component=f"ASR model ({asr_entry.model_id})",
                ok=ok,
                detail=str(asr_entry.path) if ok else f"missing or checksum mismatch: {asr_entry.path}",
            )
        )

    translation_registry = TranslationModelRegistry.load()
    for lang in languages:
        if lang == target_language:
            continue  # no translation needed when source already matches target
        entry = translation_registry.get(lang, target_language)
        if entry is None:
            checks.append(
                ReadinessCheck(
                    component=f"translation {lang}->{target_language}",
                    ok=False,
                    detail="not found in models/registry/translation_models.json",
                )
            )
        else:
            ok = entry.is_valid() if verify_checksums else entry.is_ready()
            checks.append(
                ReadinessCheck(
                    component=f"translation {lang}->{target_language}",
                    ok=ok,
                    detail=str(entry.model_dir) if ok else f"missing or checksum mismatch: {entry.model_dir}",
                )
            )

    tts_registry = VoiceRegistry.load()
    voice_entry = (
        tts_registry.get(tts_voice_id) if tts_voice_id else tts_registry.default_for_language(target_language)
    )
    if voice_entry is None:
        checks.append(
            ReadinessCheck(
                component=f"TTS voice for {target_language}",
                ok=False,
                detail="no voice registered in models/registry/tts_voices.json",
            )
        )
    else:
        ok = voice_entry.is_valid() if verify_checksums else voice_entry.is_ready()
        checks.append(
            ReadinessCheck(
                component=f"TTS voice ({voice_entry.voice_id})",
                ok=ok,
                detail=str(voice_entry.onnx_path) if ok else f"missing or checksum mismatch: {voice_entry.onnx_path}",
            )
        )

    return OfflineReadinessReport(checks=checks)
