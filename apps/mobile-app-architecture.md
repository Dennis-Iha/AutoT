# Phase 18: Mobile Companion App — Architecture (design document, not built)

**Status: not implemented.** No Node.js/npm/Flutter/Dart toolchain exists
in this environment, and there is no phone or emulator to run/test a
mobile app on regardless (this environment is a headless Linux
workstation). Installing a mobile SDK to produce UI code that has never
run would be exactly the kind of untested "complete" work this project's
Engineering Principles reject. What follows is the app's intended
architecture and screen flow, to build against once a real mobile dev
environment and device/emulator are available.

## The one property that must not be compromised

**The app is a companion, not a dependency.** Every screen below manages
device state (pairing, language packs, settings, diagnostics) - none of
them are on the path between a spoken utterance and its translation.
`core/orchestration/pipeline.py` and `tools/at_translate.py` already
enforce this on the workstation: nothing in the translation path calls out
to a phone or network. Porting to real hardware (Phase 13+) must preserve
that property; the mobile app's job is configuration and updates, not
runtime translation.

## Screens (per the master spec)

```
Splash
  |
Login / Create account
  |
Add AT device (Bluetooth pairing)
  |
AT Pods/Headphones detected
  |
Device setup
  |
Language Packs           <- installs models via Phase 10's manifest format
  |                          (checksum-verified before the device accepts
  |                          a package - same core/common/model_manifest.py
  |                          logic, ported to whatever the device-side
  |                          runtime ends up being)
  |
Translation Mode (Listen Mode: Phase 8's single-pipeline flow)
  |
Conversation Mode (Phase 17's ConversationSession flow, two-directional)
  |
Device Settings (battery, volume, diagnostics per Phase 22/23's future
                  hardware measurements)
```

## API surface the app needs from the backend (Phase 19)

The app is a thin client over the backend's device/model/firmware
registries (see `backend/` and Phase 19's implementation) plus a local
Bluetooth connection to the paired device for pairing/settings/language-
pack transfer - it does not need its own translation logic, and should not
grow any (that would violate the "companion, not dependency" property
above). Relevant endpoints, once Phase 19 exists:

- `POST /auth/register`, `POST /auth/login` - account creation/login
- `GET /devices`, `POST /devices` - list/register the user's device(s)
- `GET /models` - available language packs (mirrors
  `models/registry/*.json`'s schema - source/target, version, sha256,
  size_mb, already implemented server-side in Phase 10's registries)
- `POST /devices/{id}/models` - request a language pack be pushed to a
  device
- `GET /firmware`, `POST /devices/{id}/ota` - firmware update flow

## Suggested stack (not installed, not validated)

React Native (Expo, for faster iteration without a full native toolchain)
or Flutter - either is a reasonable choice per the master spec; no
technical reason found in this project's own work to prefer one over the
other, since nothing mobile-specific exists yet to constrain the choice.
Defer the actual choice to whoever sets up the first real mobile dev
environment for this project, informed by team familiarity more than
anything decided here.

## What would need to happen before any of this is "done," not designed

1. A real mobile development environment (Node+Expo or Flutter SDK)
   installed somewhere that can actually run and test the app.
2. A physical or emulated device to run it on.
3. Phase 19's backend actually deployed somewhere reachable, not just
   running locally in this repo's Docker setup.
4. Phase 13+'s physical device to actually pair with over Bluetooth.

None of these four exist in this development environment today.
