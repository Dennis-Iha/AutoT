"""Phase 31: product metrics ingestion + aggregation - the real,
software-buildable half of "product metrics dashboards." No visual
dashboard is built here: this project has no frontend build tooling
anywhere (apps/ is architecture-only, same honest gap as Phase 18), so a
web UI would be exactly the kind of never-run code this project's
Engineering Principles refuse to fabricate. tools/metrics_report.py is the
actual "dashboard" - a real, tested CLI report over this real API.

Every event is aggregate and content-free by construction
(MetricEventCreate has no field for transcript/translation text or audio) -
Phase 21's privacy constraint on this exact phase, enforced at the schema
level.
"""

from __future__ import annotations

from statistics import mean, median

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import get_db
from backend.models import Device, MetricEvent, User
from backend.schemas import (
    LanguagePairCount,
    MetricEventCreate,
    MetricEventResponse,
    MetricsSummaryResponse,
)

router = APIRouter(tags=["metrics"])


def _get_owned_device(device_id: str, current_user: User, db: Session) -> Device:
    device = db.get(Device, device_id)
    if device is None or device.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="device not found")
    return device


@router.post(
    "/devices/{device_id}/metrics",
    response_model=MetricEventResponse,
    status_code=status.HTTP_201_CREATED,
)
def record_metric_event(
    device_id: str,
    body: MetricEventCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MetricEvent:
    _get_owned_device(device_id, current_user, db)
    event = MetricEvent(device_id=device_id, **body.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.get("/devices/{device_id}/metrics/summary", response_model=MetricsSummaryResponse)
def get_metrics_summary(
    device_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MetricsSummaryResponse:
    _get_owned_device(device_id, current_user, db)
    events = db.query(MetricEvent).filter(MetricEvent.device_id == device_id).all()

    status_counts: dict[str, int] = {}
    pair_counts: dict[tuple[str | None, str | None], int] = {}
    latencies: list[float] = []
    for event in events:
        status_counts[event.status] = status_counts.get(event.status, 0) + 1
        pair_key = (event.source_language, event.target_language)
        pair_counts[pair_key] = pair_counts.get(pair_key, 0) + 1
        if event.total_latency_ms is not None:
            latencies.append(event.total_latency_ms)

    latencies.sort()
    p95_index = int(len(latencies) * 0.95)

    return MetricsSummaryResponse(
        device_id=device_id,
        n_events=len(events),
        status_counts=status_counts,
        language_pair_counts=[
            LanguagePairCount(source_language=s, target_language=t, count=c)
            for (s, t), c in sorted(pair_counts.items(), key=lambda kv: -kv[1])
        ],
        avg_latency_ms=round(mean(latencies), 1) if latencies else None,
        p50_latency_ms=round(median(latencies), 1) if latencies else None,
        p95_latency_ms=round(latencies[min(p95_index, len(latencies) - 1)], 1) if latencies else None,
    )
