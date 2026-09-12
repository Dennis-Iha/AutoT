# AT (AutoT) Backend Architecture

Phase 19. This document describes the control-plane backend as it actually
exists in `backend/` — a real FastAPI service, verified by reading its
source, not a design sketch. It deliberately covers architecture and
structure; endpoint-by-endpoint request/response detail belongs in
`docs/api.md`, and the history of where (if anywhere) this backend has run
belongs in `docs/deployment.md` — this doc points at both rather than
duplicating them.

## What this backend is, and isn't

`backend/main.py`'s module docstring states the scope directly: this is
"AT control-plane backend (api.autot.ai in the master spec)." It manages
accounts, registered devices, and which models/firmware are available to
push. It deliberately does **not** process customer speech or translation —
that work (Phases 5-11's ASR/translation/TTS pipeline) runs standalone in
`core/`, today on the dev workstation and eventually on-device, with no
dependency on this backend at all. This split is the same privacy
constraint `docs/privacy.md` documents for Phase 21: the backend stores
accounts, devices, model-registry metadata, and OTA job records only —
`backend/models.py`'s `MetricEvent` has no column for transcript or audio
content (see below), and no route under `backend/routes/` accepts either.

## Stack

- **FastAPI** (`0.141.1` in this environment) for the HTTP layer and
  request/response validation.
- **SQLAlchemy 2.0** (`2.0.52`) as the ORM, using the modern
  `DeclarativeBase`/`Mapped`/`mapped_column` typed-mapping style (not the
  legacy `declarative_base()` function).
- **SQLite** as the default database, via `backend/database.py`:

  ```python
  DATABASE_URL = os.environ.get("AT_DATABASE_URL", "sqlite:///./at_backend.db")
  ```

  This is explicitly a Phase 0 "don't overengineer it yet" choice, not a
  production scaling decision — `database.py`'s own module docstring says
  so directly, tying it back to the master spec's own guidance ("For
  initial development, don't overengineer it... FastAPI, PostgreSQL, Redis,
  Docker and scale later"). The `AT_DATABASE_URL` env var is the swap
  point: point it at a PostgreSQL URL and the same models and routes work
  unchanged, since nothing in `backend/routes/` or `backend/models.py`
  depends on SQLite-specific behavior. The one SQLite-specific line in the
  codebase is `_connect_args = {"check_same_thread": False} if
  DATABASE_URL.startswith("sqlite") else {}` — SQLite's default
  same-thread restriction doesn't apply to other backends, so this is
  skipped for anything else.
- **bcrypt** directly for password hashing (not passlib — see below).
- **PyJWT** (`2.14.0`) for access-token issuance and verification.

## Startup: lifespan, not `on_event`

`backend/main.py` wires app startup through FastAPI's `asynccontextmanager`
lifespan pattern:

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield

app = FastAPI(
    title="AT Backend",
    description="AutoT control-plane API (accounts, devices, models, OTA)",
    lifespan=lifespan,
)
```

`init_db()` (`backend/database.py`) calls `Base.metadata.create_all(bind=engine)`
once at startup, creating any missing tables. This is FastAPI's current
recommended startup/shutdown mechanism; the older `@app.on_event("startup")`
decorator style is deprecated upstream. There is no `on_event` call
anywhere in this codebase — a repo-wide search turns up none — so the
service is on the current, non-deprecated pattern rather than carrying
technical debt forward. Because the lifespan function here only runs
`init_db()` and has no shutdown-side cleanup (no `yield` followed by
teardown code), it's a minimal but correct use of the pattern: it does
exactly what the old `@app.on_event("startup")` hook would have done,
without depending on an API FastAPI has moved away from.

Routers are registered directly on `app` after construction:

```python
app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(models.router)
app.include_router(firmware.router)
app.include_router(metrics.router)
```

plus one inline `GET /health` endpoint returning `{"status": "ok"}` for
liveness checks.

## ORM models (`backend/models.py`)

Four tables, all using string UUID primary keys (`_uuid()`, a thin wrapper
over `uuid.uuid4()`) and UTC-aware timestamps (`_now()`, over
`datetime.now(UTC)`):

- **`User`** (`users`): `id`, unique/indexed `email`, `hashed_password`,
  `created_at`. Has a one-to-many `devices` relationship with
  `cascade="all, delete-orphan"` — deleting a user deletes their devices.
- **`Device`** (`devices`): `id`, `owner_id` (FK to `users.id`), `name`,
  `device_type` (`"at_pods"` or `"at_headphones"`, matching the two SKUs
  `docs/commercial-product-architecture.md` describes), optional
  `firmware_version`, `registered_at`. Owns two cascading child
  relationships: `ota_jobs` and `metric_events`.
- **`MetricEvent`** (`metric_events`): `id`, `device_id` (FK), `event_type`,
  `status`, optional `source_language`/`target_language`,
  optional `total_latency_ms`, `recorded_at`. The class docstring is
  explicit about why: this is "one aggregate, content-free product-metrics
  event," carrying **no transcript/translation text and no audio column at
  all** — not a policy note someone could forget, but a fact enforced at
  the schema level, since there is no column to put that content in even
  if a caller wanted to. This is Phase 21's privacy-by-construction
  constraint applied to Phase 31's metrics work: `docs/privacy.md`
  requires that when a telemetry system gets built, transcript/translation
  text must not be included by default, and this model makes that the only
  option rather than a convention to remember. The docstring also notes
  `status` mirrors `core.orchestration.pipeline.PipelineStatus`'s values,
  so a real pipeline run's outcome maps onto one event with no translation
  step needed between the two.
- **`OTAJob`** (`ota_jobs`): `id`, `device_id` (FK), `job_type`
  (`"model_package"` or `"firmware"`), `package_id`, `status` (defaults to
  `"queued"`; `"delivered"`/`"failed"` are the other documented values),
  `requested_at`. Its docstring is upfront about scope: this backend
  "cannot actually deliver it to physical hardware (none exists in this
  environment) — it records the request, matching what a real deployment
  would queue for delivery next time the device checks in."

## Auth (`backend/auth.py`)

Password hashing calls the `bcrypt` package directly rather than going
through passlib's `CryptContext`. The module docstring explains the real
bug this project hit and the reasoning for the workaround:

> Uses the `bcrypt` package directly rather than passlib's CryptContext:
> passlib 1.7.4 (last released 2020, effectively unmaintained) probes
> `bcrypt.__about__.__version__` to detect the backend version, which
> recent bcrypt releases (this environment installed 5.0.0) no longer
> expose - a real, encountered failure, not hypothetical: it silently
> mis-detects the backend and then raises "password cannot be longer than
> 72 bytes" even for short passwords. Calling bcrypt directly sidesteps
> passlib's broken version-sniffing entirely.

This is a genuine compatibility break between an unmaintained wrapper
library (passlib) and a current major version of the library it wraps
(bcrypt `5.0.0`, confirmed installed in this environment), not a
hypothetical concern written defensively. `hash_password()` and
`verify_password()` call `bcrypt.hashpw`/`bcrypt.checkpw` directly, so the
fix is a dependency-avoidance choice, not a behavior change to how
passwords are actually hashed.

JWT handling is straightforward PyJWT: `create_access_token()` signs
`{"sub": subject, "exp": expire}` with `HS256`, expiring after
`ACCESS_TOKEN_EXPIRE_MINUTES` (`60 * 24`, i.e. 24 hours);
`decode_access_token()` verifies and returns the subject. The signing
secret comes from `AT_JWT_SECRET`, defaulting to a placeholder string the
module docstring calls out explicitly as dev-only and not safe for
production use. `get_current_user()` is the FastAPI dependency every
authenticated route uses: it decodes the bearer token via
`OAuth2PasswordBearer(tokenUrl="/auth/login")`, loads the `User` row by id,
and raises `401` if the token is invalid/expired or the user no longer
exists.

## Routes (`backend/routes/`)

Endpoint-by-endpoint request/response shapes are `docs/api.md`'s job; this
is the one-sentence-per-router summary:

- **`auth.py`** (`/auth`): registers a new account (`POST /auth/register`,
  rejecting a duplicate email with `409`) and logs in
  (`POST /auth/login`, issuing a JWT on valid credentials, `401`
  otherwise).
- **`devices.py`** (`/devices`): lists a user's own devices, registers a
  new one, and fetches one by id — every read/write is scoped to
  `current_user.id`, so one account can never see or touch another
  account's devices (`get_device()`'s `device.owner_id != current_user.id`
  check, mirrored in every other router that touches a device).
- **`models.py`** (no fixed prefix; contributes `/models` and
  `/devices/{device_id}/models`): lists installable model packages and
  serves model package downloads. Its own module docstring is explicit
  that this deliberately reuses Phases 6/7/10's real, checksum-verified
  registries (`core.asr.model_registry`, `core.translation.model_registry`,
  `core.tts.voice_registry`) rather than maintaining a second, divergent
  catalog — a model is listed only if it's actually installed and
  `is_ready()` on this backend's own filesystem. `GET /models/{model_id}/download`
  has no auth check by design: the docstring argues the real security
  boundary for a model package is checksum+signature verification
  (`core.ota.model_updater`, Phase 20/29), done client-side after download,
  not access control on the download endpoint itself.
  `POST /devices/{device_id}/models` records an OTA request as a queued
  `OTAJob` row; it cannot push anything to real hardware, since none
  exists in this environment.
- **`firmware.py`** (contributes `/firmware` and
  `/devices/{device_id}/ota`): `GET /firmware` returns a hardcoded empty
  list, because no firmware has actually been built — Phase 15 is
  architecture-only (`firmware/architecture.md`) — and the module docstring
  is explicit that this is "an empty, honestly-typed list rather than
  fabricated firmware releases." `POST /devices/{device_id}/ota` records a
  generic OTA job request (model package or firmware) the same way
  `models.py` does.
- **`metrics.py`** (contributes `/devices/{device_id}/metrics` and
  `/devices/{device_id}/metrics/summary`): ingests one `MetricEvent` per
  call and serves an aggregated summary (status counts, language-pair
  counts, and mean/median/p95 latency) over a device's recorded events.
  The module docstring frames this as the real, software-buildable half of
  "product metrics dashboards" — there is no visual dashboard, since this
  project has no frontend build tooling anywhere (`apps/` is
  architecture-only); `tools/metrics_report.py` is the actual CLI-based
  "dashboard" over this same API.

Every device-scoped route across `devices.py`, `models.py`, `firmware.py`,
and `metrics.py` repeats the same ownership check inline (or, in
`metrics.py`, factored into a shared `_get_owned_device()` helper) — a
device that doesn't exist or belongs to a different user returns `404`,
not `403`, so the endpoint doesn't reveal whether a given device id exists
under another account.

## Tests

`tests/backend/` currently has 4 test files —
`find /home/prt/Desktop/translate/tests/backend -name "test_*.py" | wc -l`
returns 4 (`test_auth.py`, `test_devices.py`,
`test_models_and_firmware.py`, `test_metrics.py`) — containing 30 `def
test_` functions between them (6 + 7 + 10 + 7). `docs/architecture.md`'s
status table cites "20 tests" for the backend; that figure is stale
relative to the current file contents and should be treated as an
approximate historical snapshot, not the current count — 30 is what's
actually in the tree as of this writing.

## Status and where this has actually run

Per `docs/commercial-product-architecture.md`'s readiness matrix, Phase
19's backend is rated **production candidate**: "real, tested
FastAPI+SQLAlchemy service; SQLite is a dev/test choice, not a scaling
decision." That matches what's verifiable here — the code, models, and
routes are real and exercised by a real test suite, not a stub — with the
caveat that "production candidate" is about code quality and test
coverage, not deployment history. This backend has never been deployed
anywhere outside this local dev environment; see `docs/deployment.md` for
the full account of that gap.
