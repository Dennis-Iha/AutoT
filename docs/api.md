# AT (AutoT) — Backend HTTP API Reference

Phase 19's control-plane backend (`backend/`, a FastAPI + SQLAlchemy service).
This document lists every real route as it exists in the code today, read
directly from `backend/main.py` and each file in `backend/routes/` — not from
a spec or an earlier description. It is not a schema reference: FastAPI
auto-generates interactive docs at `/docs` and a full machine-readable OpenAPI
schema at `/openapi.json` when the server is running, and those are the
authoritative source for exact request/response field types. Duplicating full
schemas here would just create a second copy that drifts from the code; this
doc's job is the route list, the auth boundary, and enough context per route
to know what it actually does.

Per `docs/commercial-product-architecture.md`'s readiness matrix: **Backend
(Phase 19) — production candidate** (real, tested FastAPI+SQLAlchemy service;
SQLite is a dev/test choice, not a scaling decision). **Product metrics
(Phase 31) — production candidate** (real backend aggregation; no fleet
exists yet to generate real-world volume).

## What this backend is and isn't

Per `backend/main.py`'s own module docstring: this backend manages accounts,
devices, and which models/firmware are available to push. It deliberately
does **not** process customer speech or translation — that work (Phases 5-11)
runs standalone, independent of this backend. `docs/privacy.md` confirms
there is no route anywhere in `backend/routes/` that accepts or stores audio
or recognized/translated text; `POST /devices/{device_id}/metrics` accepts
only aggregate, content-free fields (see `MetricEventCreate` in
`backend/schemas.py`) by construction, not just by convention.

## Auth mechanism

Auth is OAuth2 password-bearer + JWT, implemented in `backend/auth.py`:

- `POST /auth/login` issues a JWT (`create_access_token`, HS256, 24-hour
  expiry per `ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24`) whose subject is the
  user's id.
- Protected routes depend on `get_current_user` (`backend/auth.py`), which
  decodes the bearer token via `OAuth2PasswordBearer(tokenUrl="/auth/login")`
  and loads the corresponding `User` row, raising `401` if the token is
  missing, invalid, expired, or names a user that no longer exists.
- The signing secret comes from the `AT_JWT_SECRET` environment variable; the
  in-code default (`dev-only-insecure-secret-do-not-use-in-production`) is an
  explicit dev-only placeholder, not something meant to reach a real
  deployment.

"Auth?" below means the route has `current_user: User = Depends(get_current_user)`
in its signature — verified per-route by reading the decorator and function
signature in each file, not assumed from the route's path.

## Routes

### App-level (`backend/main.py`)

| Method | Path | Auth? | Purpose |
|---|---|---|---|
| GET | `/health` | No | Liveness check; returns `{"status": "ok"}`. |
| GET | `/docs` | No | FastAPI's auto-generated interactive API docs (Swagger UI). |
| GET | `/openapi.json` | No | FastAPI's auto-generated OpenAPI schema — the authoritative source for exact request/response types. |

### Auth (`backend/routes/auth.py`, prefix `/auth`)

| Method | Path | Auth? | Purpose |
|---|---|---|---|
| POST | `/auth/register` | No | Creates a new user account (email + bcrypt-hashed password); `409` if the email is already registered. |
| POST | `/auth/login` | No | Verifies email/password and returns a bearer JWT (`TokenResponse`); `401` on bad credentials. |

### Devices (`backend/routes/devices.py`, prefix `/devices`)

| Method | Path | Auth? | Purpose |
|---|---|---|---|
| GET | `/devices` | Yes | Lists devices owned by the current user. |
| POST | `/devices` | Yes | Registers a new device (name + device_type) under the current user. |
| GET | `/devices/{device_id}` | Yes | Fetches one device; `404` if it doesn't exist or isn't owned by the current user. |

### Models (`backend/routes/models.py`)

| Method | Path | Auth? | Purpose |
|---|---|---|---|
| GET | `/models` | No | Lists installed ASR/translation/TTS model packages, read live from Phases 6/7/10's real on-filesystem registries (`ASRModelRegistry`, `TranslationModelRegistry`, `VoiceRegistry`) — not a static catalog; only models actually present and `is_ready()` are listed. |
| GET | `/models/{model_id}/download` | No | Streams the model package file itself (`FileResponse`), resolved via `core.ota.model_updater.resolve_update_targets()`; `404` if the id is unknown or the file isn't on disk. |
| POST | `/devices/{device_id}/models` | Yes | Records a request to push a model package to a device (`OTAJob`, `job_type="model_package"`); `404` if the device isn't owned by the current user. |

Per the module docstring in `backend/routes/models.py`, `GET /models` and
`GET /models/{model_id}/download` deliberately have no auth check — the
comment states this is intentional, on the reasoning that the real security
boundary for a model package is its checksum+signature (verified client-side
after download, per Phase 20/29's `core.ota.model_updater`), not access
control on the download endpoint. `POST /devices/{device_id}/models` only
records that a push was requested; per its own docstring it cannot actually
deliver anything, since no physical device exists in this environment (see
`hardware/hardware-selection.md`).

### Firmware (`backend/routes/firmware.py`)

| Method | Path | Auth? | Purpose |
|---|---|---|---|
| GET | `/firmware` | No | Lists firmware releases. Currently always returns an empty list — `_FIRMWARE_RELEASES` is a hardcoded empty list in the code, because per the module docstring no real firmware exists yet (Phase 15 is architecture-only; see `docs/firmware.md`). |
| POST | `/devices/{device_id}/ota` | Yes | Records an OTA request against a device (`OTAJob`, arbitrary `job_type`/`package_id` from the request body); `404` if the device isn't owned by the current user. |

### Metrics (`backend/routes/metrics.py`)

| Method | Path | Auth? | Purpose |
|---|---|---|---|
| POST | `/devices/{device_id}/metrics` | Yes | Records one aggregate metric event for a device owned by the current user (`event_type`, `status`, optional `source_language`/`target_language`/`total_latency_ms` — no transcript, translation, or audio field exists on the schema). |
| GET | `/devices/{device_id}/metrics/summary` | Yes | Returns an aggregated summary for a device: event count, counts by status, counts by language pair, and avg/p50/p95 latency computed from the device's recorded events. |

Per the module docstring in `backend/routes/metrics.py`, this is the real,
software-buildable half of "product metrics dashboards" — there is no visual
dashboard here (this project has no frontend build tooling; `apps/` is
architecture-only). `tools/metrics_report.py` is the actual CLI-based report
consumer of this API.

## Notes on what's out of scope for this doc

- **Request/response field types and validation rules** — read the Pydantic
  models in `backend/schemas.py`, or query the running server's
  `/openapi.json`. This doc names the fields that matter for understanding
  what a route does (e.g. metrics having no text/audio field) but doesn't
  restate full schemas.
- **Database backing** — `backend/database.py` (SQLite for dev, configurable
  via `AT_DATABASE_URL`); not an HTTP-API concern.
- **Ordering of `app.include_router(...)` calls in `backend/main.py`** does
  not affect path resolution here since no two routers register overlapping
  paths; not documented further.
