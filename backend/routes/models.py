"""Phase 19's model-registry endpoint - deliberately reuses Phases 6/7/10's
real, checksum-verified registries rather than maintaining a second,
divergent list of what models "exist." If a model isn't installed on this
backend's own filesystem, it isn't listed - this endpoint reflects what
Phase 10's core.common.offline_runtime would actually find, not a static
catalog."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import get_db
from backend.models import Device, OTAJob, User
from backend.schemas import ModelPackageResponse, OTAJobResponse, OTARequest
from core.asr.model_registry import ASRModelRegistry
from core.ota.model_updater import resolve_update_targets
from core.translation.model_registry import TranslationModelRegistry
from core.tts.voice_registry import VoiceRegistry

router = APIRouter(tags=["models"])


@router.get("/models", response_model=list[ModelPackageResponse])
def list_models() -> list[ModelPackageResponse]:
    result: list[ModelPackageResponse] = []

    asr_registry = ASRModelRegistry.load()
    for model_id in asr_registry.model_ids():
        asr_entry = asr_registry.get(model_id)
        if asr_entry is not None and asr_entry.is_ready():
            result.append(ModelPackageResponse(
                model_id=asr_entry.model_id, kind="asr", size_mb=asr_entry.size_mb, sha256=asr_entry.sha256,
            ))

    translation_registry = TranslationModelRegistry.load()
    for source, target in translation_registry.pairs():
        translation_entry = translation_registry.get(source, target)
        if translation_entry is not None and translation_entry.is_ready():
            result.append(ModelPackageResponse(
                model_id=translation_entry.model_id, kind="translation", source=translation_entry.source,
                target=translation_entry.target, size_mb=translation_entry.size_mb,
                sha256=translation_entry.sha256,
            ))

    tts_registry = VoiceRegistry.load()
    for voice_id in tts_registry.voice_ids():
        voice_entry = tts_registry.get(voice_id)
        if voice_entry is not None and voice_entry.is_ready():
            result.append(ModelPackageResponse(
                model_id=voice_entry.voice_id, kind="tts", language=voice_entry.language,
                size_mb=voice_entry.size_mb, sha256=voice_entry.sha256,
            ))

    return result


@router.get("/models/{model_id}/download")
def download_model(model_id: str) -> FileResponse:
    """Phase 29: the actual byte transport half of OTA, closing the loop
    `GET /models` (metadata) leaves open. No auth check, deliberately
    consistent with `GET /models` above - the real security boundary for a
    model package is its checksum+signature (Phase 20/29's
    core.ota.model_updater), verified client-side after download, not
    access control on the download itself.

    Reuses core.ota.model_updater.resolve_update_targets() for the
    model_id -> real file path mapping instead of a second lookup table -
    the same registries Phase 10 already built, same as list_models()
    above."""
    targets = {t.id_: t for t in resolve_update_targets()}
    target = targets.get(model_id)
    if target is None or not target.install_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="model package not found")
    return FileResponse(target.install_path, media_type="application/octet-stream")


@router.post(
    "/devices/{device_id}/models", response_model=OTAJobResponse, status_code=status.HTTP_202_ACCEPTED
)
def request_model_install(
    device_id: str,
    body: OTARequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OTAJob:
    """Records a request to push a model package to a device. Cannot
    actually deliver it - no physical device exists in this environment
    (see hardware/hardware-selection.md); this records what a real
    deployment would queue for the device to pull on its next check-in."""
    device = db.get(Device, device_id)
    if device is None or device.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="device not found")
    job = OTAJob(device_id=device_id, job_type="model_package", package_id=body.package_id)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job
