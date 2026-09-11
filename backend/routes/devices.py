from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import get_db
from backend.models import Device, User
from backend.schemas import DeviceCreateRequest, DeviceResponse

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[DeviceResponse])
def list_devices(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[Device]:
    return db.query(Device).filter(Device.owner_id == current_user.id).all()


@router.post("", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
def register_device(
    body: DeviceCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Device:
    device = Device(owner_id=current_user.id, name=body.name, device_type=body.device_type)
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


@router.get("/{device_id}", response_model=DeviceResponse)
def get_device(
    device_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Device:
    device = db.get(Device, device_id)
    if device is None or device.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="device not found")
    return device
