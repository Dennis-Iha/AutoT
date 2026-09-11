"""Phase 19's firmware-registry endpoint. No real firmware exists yet
(Phase 15 is a design document only, see firmware/architecture.md) - this
returns an empty, honestly-typed list rather than fabricated firmware
releases, and exists so the API shape (and OTA request-recording, which
IS real) is in place for when real firmware ships."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import get_db
from backend.models import Device, OTAJob, User
from backend.schemas import FirmwareReleaseResponse, OTAJobResponse, OTARequest

router = APIRouter(tags=["firmware"])

# No firmware has been built (Phase 15 is architecture-only, see
# firmware/architecture.md) - deliberately empty, not fabricated entries.
_FIRMWARE_RELEASES: list[FirmwareReleaseResponse] = []


@router.get("/firmware", response_model=list[FirmwareReleaseResponse])
def list_firmware() -> list[FirmwareReleaseResponse]:
    return _FIRMWARE_RELEASES


@router.post(
    "/devices/{device_id}/ota", response_model=OTAJobResponse, status_code=status.HTTP_202_ACCEPTED
)
def request_ota(
    device_id: str,
    body: OTARequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OTAJob:
    device = db.get(Device, device_id)
    if device is None or device.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="device not found")
    job = OTAJob(device_id=device_id, job_type=body.job_type, package_id=body.package_id)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job
