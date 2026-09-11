"""Phase 19: SQLAlchemy ORM models for the AT control-plane backend.

Deliberately does NOT model customer conversation/speech data - the master
spec's core privacy promise ("your conversation stays on your device," see
Phase 21) means the backend never sees translated audio or text, only
account/device/model-registry metadata.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    devices: Mapped[list[Device]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String)
    device_type: Mapped[str] = mapped_column(String)  # "at_pods" | "at_headphones"
    firmware_version: Mapped[str | None] = mapped_column(String, nullable=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    owner: Mapped[User] = relationship(back_populates="devices")
    ota_jobs: Mapped[list[OTAJob]] = relationship(back_populates="device", cascade="all, delete-orphan")
    metric_events: Mapped[list[MetricEvent]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )


class MetricEvent(Base):
    """Phase 31: one aggregate, content-free product-metrics event.

    Deliberately carries NO transcript/translation text and no audio -
    Phase 21's privacy doc's explicit constraint on Phase 31, enforced here
    at the schema level (there is no column to put that content in), not
    just as a policy note someone could forget. `status` mirrors
    core.orchestration.pipeline.PipelineStatus's values so a real pipeline
    run's outcome maps directly onto one event with no translation
    required.
    """

    __tablename__ = "metric_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"))
    event_type: Mapped[str] = mapped_column(String)  # "translation_attempt"
    status: Mapped[str] = mapped_column(String)  # a core.orchestration.pipeline.PipelineStatus value
    source_language: Mapped[str | None] = mapped_column(String, nullable=True)
    target_language: Mapped[str | None] = mapped_column(String, nullable=True)
    total_latency_ms: Mapped[float | None] = mapped_column(nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    device: Mapped[Device] = relationship(back_populates="metric_events")


class OTAJob(Base):
    """Records a requested model/firmware push to a device. This backend
    cannot actually deliver it to physical hardware (none exists in this
    environment) - it records the request, matching what a real deployment
    would queue for delivery next time the device checks in."""

    __tablename__ = "ota_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"))
    job_type: Mapped[str] = mapped_column(String)  # "model_package" | "firmware"
    package_id: Mapped[str] = mapped_column(String)  # e.g. "argos-es-en-1.9" or a firmware version
    status: Mapped[str] = mapped_column(String, default="queued")  # queued|delivered|failed
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    device: Mapped[Device] = relationship(back_populates="ota_jobs")
