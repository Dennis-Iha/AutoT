"""Phase 29: verified, atomic on-device model package installation.

Directly generalizes two things already proven separately: Phase 10's
model manifest/checksum verification pattern, and Phase 20's Ed25519
signature verification (`core/security/package_signing.py`). Neither, on
its own, protects against the exact failure this module exists to prevent:
Phase 7's real incident was a *silently truncated* download (27MB of an
expected 63MB TTS model) that got treated as a complete, ready model
because nothing checked before use - not because no checksum existed
anywhere.

The rule this module enforces: a downloaded/staged package is checksum-
verified, then signature-verified (when the manifest carries one), and
ONLY THEN atomically swapped into the live install path via `os.replace`.
The live model is never touched, and no partial/corrupt/unsigned file is
ever left in its place, until every check has passed. If any check fails,
the existing installed model (if any) is left exactly as it was - a failed
update must never leave a device with no working model, or a wrong one
silently swapped in.

`os.replace` is atomic only within a single filesystem/mount - callers must
stage downloaded files on the same filesystem as the install path (the
project's `tools/ota_download_and_apply.py` does this by staging into the
install path's own parent directory), a real constraint documented here
rather than glossed over.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from core.asr.model_registry import ASRModelRegistry
from core.common.model_manifest import verify_checksum
from core.security.package_signing import PackageSignature, verify_digest
from core.translation.model_registry import TranslationModelRegistry
from core.tts.voice_registry import VoiceRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]

_MANIFESTS: list[tuple[Path, str, str]] = [
    # (manifest path, list key, id field name in each row)
    (REPO_ROOT / "models" / "registry" / "asr_models.json", "models", "model_id"),
    (REPO_ROOT / "models" / "registry" / "translation_models.json", "models", "model_id"),
    (REPO_ROOT / "models" / "registry" / "tts_voices.json", "voices", "voice_id"),
]


@dataclass(frozen=True)
class UpdateTarget:
    """One installable unit: a single on-disk file this project's model
    registries (Phase 10) resolve to, plus the checksum/signature it must
    satisfy before being installed. `kind`/`id_` identify it the same way
    Phase 19's backend already does (`ModelPackageResponse.model_id`), so a
    remote catalog entry maps to exactly one UpdateTarget."""

    kind: str  # "asr" | "translation" | "tts"
    id_: str
    install_path: Path
    expected_sha256: str
    signature: PackageSignature | None


@dataclass(frozen=True)
class UpdateResult:
    target: UpdateTarget
    status: str  # "installed" | "unchanged" | "failed"
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in ("installed", "unchanged")


def _load_signatures(manifest_path: Path, list_key: str, id_field: str) -> dict[str, PackageSignature | None]:
    if not manifest_path.exists():
        return {}
    data = json.loads(manifest_path.read_text())
    result: dict[str, PackageSignature | None] = {}
    for row in data[list_key]:
        sig_data = row.get("signature")
        result[row[id_field]] = PackageSignature(**sig_data) if sig_data else None
    return result


def resolve_update_targets() -> list[UpdateTarget]:
    """Builds one UpdateTarget per registry entry across all three real
    model registries (ASR/translation/TTS), regardless of whether it's
    currently installed - a target that isn't installed yet (is_ready() is
    False) is exactly what a fresh-install OTA job would need to fetch."""
    targets: list[UpdateTarget] = []

    asr_sigs = _load_signatures(*_MANIFESTS[0])
    asr_registry = ASRModelRegistry.load()
    for model_id in asr_registry.model_ids():
        asr_entry = asr_registry.get(model_id)
        assert asr_entry is not None
        targets.append(UpdateTarget(
            kind="asr", id_=asr_entry.model_id, install_path=asr_entry.path,
            expected_sha256=asr_entry.sha256, signature=asr_sigs.get(asr_entry.model_id),
        ))

    translation_sigs = _load_signatures(*_MANIFESTS[1])
    translation_registry = TranslationModelRegistry.load()
    for source, target_lang in translation_registry.pairs():
        translation_entry = translation_registry.get(source, target_lang)
        assert translation_entry is not None
        if translation_entry.sha256 is None:
            continue
        targets.append(UpdateTarget(
            kind="translation", id_=translation_entry.model_id,
            install_path=translation_entry.ctranslate2_model_dir / "model.bin",
            expected_sha256=translation_entry.sha256,
            signature=translation_sigs.get(translation_entry.model_id),
        ))

    tts_sigs = _load_signatures(*_MANIFESTS[2])
    tts_registry = VoiceRegistry.load()
    for voice_id in tts_registry.voice_ids():
        voice_entry = tts_registry.get(voice_id)
        assert voice_entry is not None
        if voice_entry.sha256 is None:
            continue
        targets.append(UpdateTarget(
            kind="tts", id_=voice_entry.voice_id, install_path=voice_entry.onnx_path,
            expected_sha256=voice_entry.sha256, signature=tts_sigs.get(voice_entry.voice_id),
        ))

    return targets


def apply_update(
    target: UpdateTarget, staged_path: Path, public_key_pem: str | None
) -> UpdateResult:
    """Verifies `staged_path` against `target`, then atomically installs it.

    Fails closed, not open: if `target.signature` is set but no
    `public_key_pem` is given, this FAILS rather than silently falling back
    to checksum-only - a caller must not be able to accidentally skip
    signature verification just by forgetting to pass a key.
    """
    if not staged_path.exists():
        return UpdateResult(target, "failed", error=f"staged file not found: {staged_path}")

    if not verify_checksum(staged_path, target.expected_sha256):
        return UpdateResult(target, "failed", error="checksum mismatch - staged file rejected")

    if target.signature is not None:
        if public_key_pem is None:
            return UpdateResult(
                target, "failed",
                error="manifest entry is signed but no public key was provided to verify against",
            )
        if not verify_digest(target.expected_sha256, target.signature, public_key_pem):
            return UpdateResult(target, "failed", error="signature verification failed - staged file rejected")

    if target.install_path.exists() and verify_checksum(target.install_path, target.expected_sha256):
        return UpdateResult(target, "unchanged")

    target.install_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staged_path, target.install_path)
    return UpdateResult(target, "installed")
