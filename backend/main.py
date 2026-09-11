"""Phase 19: AT control-plane backend (api.autot.ai in the master spec).

Deliberately does NOT process customer speech/translation - that's the
whole point (Phase 21's privacy promise: "your conversation stays on your
device"). This backend only manages accounts, devices, and which models/
firmware are available to push - all of Phases 5-11's actual translation
work already runs standalone without this backend, on the dev workstation
today and eventually on-device.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.database import init_db
from backend.routes import auth, devices, firmware, metrics, models


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(
    title="AT Backend",
    description="AutoT control-plane API (accounts, devices, models, OTA)",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(models.router)
app.include_router(firmware.router)
app.include_router(metrics.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
