# AT Mobile App

**Status: design document only. No mobile app code exists, and none of it
has ever been built, run, or tested.** This page is a synthesis of
`apps/mobile-app-architecture.md` (Phase 18) — read that file for the full
screen-by-screen architecture and reasoning. This page adds one thing that
document doesn't focus on: a precise statement of what the app's backend
dependency actually is today, verified against the real code in `backend/`
rather than against the master spec's description of what it should be.

## Why there is no mobile app code in this repo

Confirmed directly in this environment: no `node`, `npm`, `npx`, `flutter`,
or `dart` executable is on `PATH`. There is also no phone or emulator to
run a mobile app on — this is a headless Linux workstation. `apps/android/`,
`apps/ios/`, and `apps/desktop/` exist only as empty directories (each
holding a single `.gitkeep`).

Installing a mobile SDK to generate UI code that has never executed, on a
device that doesn't exist, would produce exactly the kind of untested
"complete" work this project's Engineering Principles reject: a claim of
done-ness with nothing behind it. `apps/mobile-app-architecture.md` stops
at the design layer for that reason, the same way `firmware/architecture.md`
(Phases 14-15, see `docs/firmware.md`) and `hardware/hardware-selection.md`
(Phase 12, see `docs/hardware.md`) do for embedded firmware and physical
hardware.

## The property the design commits to

**The app is a companion, not a dependency.** Every screen in the design
manages device state — pairing, language packs, settings, diagnostics —
and none of them sit on the path between a spoken utterance and its
translation. That path already runs standalone today, on this workstation,
in `core/orchestration/pipeline.py` and `tools/at_translate.py`, with no
call out to a phone or network. The mobile app's job, per the design, is
configuration and updates only; it must not grow translation logic of its
own when it's eventually built.

## Screens (per the master spec, from the Phase 18 design)

```
Splash -> Login/Create account -> Add AT device (BT pairing) ->
Device detected -> Device setup -> Language Packs ->
Translation Mode (Listen Mode) -> Conversation Mode -> Device Settings
```

Two points worth pulling out from `apps/mobile-app-architecture.md`:

- **Language Packs** installs models via Phase 10's manifest/checksum
  format (`core/common/model_manifest.py`'s logic) — the design calls for
  porting that same verification logic to the device side, not inventing a
  second one.
- **Translation Mode** and **Conversation Mode** map directly onto
  functionality that already exists and is tested on the workstation:
  Phase 8's single-pipeline flow and Phase 17's two-directional
  `ConversationSession` (`core/orchestration/conversation.py`). The app
  doesn't reimplement either — it would just be a UI in front of a paired
  device eventually running that logic.

## The app's real backend dependency (Phase 19, not a design document)

This is the one part of the mobile picture that isn't purely aspirational:
`backend/` is a real, tested FastAPI + SQLAlchemy service, and it already
implements every endpoint the master spec names for the mobile app to call.
Verified by reading the route definitions directly (`backend/routes/`),
not by trusting the spec's description of itself:

| Endpoint | File | Purpose |
|---|---|---|
| `POST /auth/register` | `backend/routes/auth.py` | account creation |
| `POST /auth/login` | `backend/routes/auth.py` | login, returns a bearer token |
| `GET /devices`, `POST /devices` | `backend/routes/devices.py` | list / register the user's device(s) |
| `GET /devices/{device_id}` | `backend/routes/devices.py` | single device detail |
| `GET /models` | `backend/routes/models.py` | available language packs — reuses Phases 6/7/10's real ASR/translation/TTS registries directly, not a second catalog |
| `GET /models/{model_id}/download` | `backend/routes/models.py` | the actual byte transport for a model package (Phase 29); not in the master spec's endpoint list but needed to make the OTA flow real rather than metadata-only |
| `POST /devices/{device_id}/models` | `backend/routes/models.py` | records a request to push a language pack to a device |
| `GET /firmware` | `backend/routes/firmware.py` | firmware release list — honestly returns an empty list; no firmware has been built (Phase 15 is a design document) |
| `POST /devices/{device_id}/ota` | `backend/routes/firmware.py` | records a firmware OTA request |

Backend auth (`backend/auth.py`) is real bearer-token auth on top of
`bcrypt`-hashed passwords; every route that takes a `device_id` enforces
that the device belongs to the requesting user (`device.owner_id !=
current_user.id` checks in `backend/routes/devices.py`, `models.py`,
`firmware.py`) before returning or mutating anything. `GET /models`,
`GET /models/{model_id}/download`, and `GET /firmware` are deliberately
unauthenticated — per `models.py`'s own docstring, the real security
boundary for a model package is its Phase 20/29 checksum+signature,
verified client-side after download, not access control on the catalog
or download endpoints themselves. This was verified by running the
backend's test suite in this environment: `tests/backend/` — 30 tests,
all passing.

What this means concretely: **the mobile app has nothing left to build on
the backend side.** The moment a real mobile dev environment exists, the
app can start making real HTTP calls against a real, running backend — the
gap is entirely the client (Phase 18) and the physical device to pair with
over Bluetooth (Phase 13+), not the server. The backend does not, and
should not, do any translation itself — per Phase 19's own docstring
(`backend/main.py`), it deliberately never touches customer speech/
translation content, matching `docs/privacy.md`'s on-device promise.

One gap on the backend side worth naming honestly: it's real and tested
against local SQLite (`AT_DATABASE_URL`, see `backend/database.py`), and
has only ever been run locally in this repo's own Docker setup — not
deployed anywhere a real phone could reach it over the internet. "The
backend already has every endpoint" is not the same claim as "the backend
is deployed and reachable."

## Suggested stack (not installed, not validated)

Per `apps/mobile-app-architecture.md`: React Native (Expo) or Flutter —
either is reasonable per the master spec, and nothing in this project's own
work constrains the choice, since no mobile-specific code exists yet to
make one option fit better than the other. Left to whoever sets up the
first real mobile dev environment.

## Readiness

Per this project's readiness framework (prototype / engineering prototype /
production candidate / production ready — see
`docs/commercial-product-architecture.md`):

| Component | Readiness | Why |
|---|---|---|
| Mobile app (Phase 18) | prototype (design document only) | no code, no SDK, no device/emulator in this environment |
| Backend API surface the app depends on (Phase 19) | production candidate | real, tested FastAPI+SQLAlchemy service, every endpoint the spec names implemented and covered by `tests/backend/`; not yet deployed anywhere a phone could reach |

## What has to happen before any of this is a real app

In order, per `apps/mobile-app-architecture.md`:

1. A real mobile development environment (Node+Expo, or a Flutter SDK)
   installed somewhere that can actually build and run the app.
2. A physical phone or emulator to run it on.
3. Phase 19's backend deployed somewhere network-reachable, not just
   running locally against SQLite in this repo's Docker setup.
4. A physical Phase 13+ device to actually pair with over Bluetooth.

None of these four exist in this development environment today. The
backend piece (3) is the closest to real — the code and tests already
exist — but deploying it is still an unfinished, unverified step.
