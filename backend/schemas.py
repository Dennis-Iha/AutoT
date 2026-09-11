"""Phase 19: Pydantic request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    created_at: datetime


class DeviceCreateRequest(BaseModel):
    name: str
    device_type: str


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    device_type: str
    firmware_version: str | None
    registered_at: datetime


class ModelPackageResponse(BaseModel):
    """Mirrors core/*/model_registry.py's entries - the backend surfaces
    the SAME registries Phases 6/7/10 already built and tested, rather than
    maintaining a separate, divergent copy of what models exist."""
    model_id: str
    kind: str  # "asr" | "translation" | "tts"
    source: str | None = None
    target: str | None = None
    language: str | None = None
    size_mb: float | None = None
    sha256: str | None = None


class OTARequest(BaseModel):
    job_type: str  # "model_package" | "firmware"
    package_id: str


class OTAJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    device_id: str
    job_type: str
    package_id: str
    status: str
    requested_at: datetime


class FirmwareReleaseResponse(BaseModel):
    version: str
    device_type: str
    release_notes: str


class MetricEventCreate(BaseModel):
    """Phase 31: deliberately has no field for transcript/translation text
    or audio - Phase 21's privacy constraint enforced at the request-schema
    level, not just documented as policy."""
    event_type: str
    status: str
    source_language: str | None = None
    target_language: str | None = None
    total_latency_ms: float | None = None


class MetricEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    device_id: str
    event_type: str
    status: str
    source_language: str | None
    target_language: str | None
    total_latency_ms: float | None
    recorded_at: datetime


class LanguagePairCount(BaseModel):
    source_language: str | None
    target_language: str | None
    count: int


class MetricsSummaryResponse(BaseModel):
    device_id: str
    n_events: int
    status_counts: dict[str, int]
    language_pair_counts: list[LanguagePairCount]
    avg_latency_ms: float | None
    p50_latency_ms: float | None
    p95_latency_ms: float | None
