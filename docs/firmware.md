# AT Firmware: Embedded Audio, Bootloader, Secure Boot, OTA

**Status: 100% design document. No physical firmware has been written,
flashed, or tested anywhere in this project.** Everything below either
describes an architecture that has not been built, or describes real,
tested *software* that runs on a development workstation today and would
need to be ported onto real embedded hardware before it is firmware in any
meaningful sense. This document does not blur that line.

This covers Phases 14-15 of the roadmap (`docs/roadmap.md`), whose primary
source is `firmware/architecture.md` — read that file for the full
design; this document adds the readiness framing and the connection to the
two software components (Phases 20 and 29) that firmware would eventually
need to host.

## Why there is no firmware code in this repo

This project's Engineering Principles forbid placeholder implementations of
core functionality presented as complete. Writing I2S/PDM driver code or
bootloader code with no physical board to load it onto, no oscilloscope or
logic analyzer to check its signal timing, and no way to run it past a
compiler would produce exactly that: code that has never executed, dressed
up as an embedded subsystem. `firmware/architecture.md` says this
explicitly and stops at the design layer instead. Phase 12
(`hardware/hardware-selection.md`) and Phase 13
(`hardware/AT-H1-headphone-prototype.md`) are also desk-research/design
documents for the same reason — there is no physical development board in
this environment, only a headless Linux workstation.

## Phase 14: embedded audio HAL (design)

The goal is to give `core/audio/capture.py`'s `MicrophoneCapture` and
`core/audio/playback.py`'s `AudioPlayback` — both real, tested against
this workstation's PortAudio/`sounddevice` backend since Phase 1 — a second
backend targeting embedded I2S/PDM hardware, without changing any
downstream code (`core/vad/`, `core/orchestration/`,
`tools/at_translate.py`). Those two classes were deliberately built as
small, swappable wrappers for exactly this reason.

```
MicrophoneCapture / AudioPlayback (core/audio/)
    |
    +-- PortAudio/sounddevice backend   IMPLEMENTED, tested (Phase 1)
    +-- Embedded I2S/PDM backend        NOT IMPLEMENTED — needs real hardware
            |
        vendor Linux audio driver stack exposing an ALSA PCM device
        (e.g. NVIDIA L4T's audio stack, per hardware-selection.md's
        Jetson recommendation — or the equivalent for whatever board
        Phase 12/13 actually acquires)
```

`firmware/architecture.md` lays out the concrete precondition chain: a
physical board with wired mics (Phase 13) must exist, its vendor's Linux
audio driver stack must actually load and expose an ALSA device, and only
then does writing `core/audio/embedded_capture.py` make sense — and per
that document, this may need little or no new code, since PortAudio
already supports arbitrary ALSA device names and `MicrophoneCapture`
already accepts a `device` parameter. That parameter is real and merged,
but it has never been pointed at an embedded ALSA device, because no such
device exists here to point it at.

**Readiness: prototype.** The PortAudio-backed interface it would extend
is production-candidate-grade software; the embedded backend itself is an
unimplemented design sketch.

## Phase 15: boot/firmware stack (design)

```
Bootloader        vendor-provided for whichever Phase 12 board is acquired
                   (e.g. Jetson's preinstalled bootloader / L4T flashing tools)
    -> Secure boot NOT designed — needs a real hardware root of trust
                   (see "Secure boot vs. package signing" below)
    -> OS          embedded Linux (Yocto, or the vendor BSP), per Phase 12's
                   OS-support findings for whichever board is acquired
    -> Drivers     audio (Phase 14 above), Bluetooth (per hardware-selection.md's
                   companion-chip findings), storage, power
    -> Device services   watchdog, thermal protection, battery management —
                   none implemented; expected to be systemd units or a small
                   supervisor process, since Phase 12's candidates are all
                   full Linux-capable SoCs, not bare-metal MCUs
    -> AI runtime  whisper.cpp + ctranslate2 + onnxruntime — ALREADY BUILT
                   and tested on this workstation (Phases 5-7); porting means
                   rebuilding for the target architecture/OS, not rewriting
    -> Translation service   core/orchestration/pipeline.py + core/streaming/ —
                   ALREADY BUILT and tested (Phases 8-9); pure Python/subprocess
                   glue with no hardware-specific code today, so this is the
                   layer most likely to port with the least change
```

The honest summary from `firmware/architecture.md`: because every Phase 12
candidate SoC is a full embedded-Linux-capable part rather than a
bare-metal MCU, most of what Phase 15 calls "firmware" is standard embedded
Linux systems engineering (BSP bring-up, systemd services, an OTA scheme)
rather than bespoke low-level firmware. That is good news for how much of
Phases 5-10's software should survive the port unchanged, but none of it —
not the driver stack, not the boot chain, not the OTA scheme running from
an actual bootloader — has been built or validated, because the Phase 12/13
hardware this would require does not exist in this environment.

**Readiness: prototype** (architecture description only; no boot code, no
driver code, no OS image).

## The software half that IS real: package signing and OTA updates

Two pieces of what firmware will eventually need to run are not
design sketches — they are real, tested Python modules running on this
workstation today, and they are the parts of Phases 20/29 that don't
require physical hardware to build or verify:

- **`core/security/package_signing.py`** (Phase 20): Ed25519 signing and
  verification of a model package's SHA256 digest. Its own module
  docstring explains the exact gap a checksum alone leaves open — nothing
  stops an attacker from distributing a *different* file with its own
  correct checksum recorded next to it, unless that checksum is itself
  signed by a key the verifying side trusts. `generate_signing_keypair()`
  is explicitly dev/test-only per that docstring; a real deployment's
  private key must live in an HSM or equivalent, never in this repository.
  Per `docs/roadmap.md`'s Phase 20 section, 7 unit tests
  (`tests/security/test_package_signing.py`) cover the roundtrip, tampered-
  digest rejection, wrong-key rejection, corrupted-signature rejection,
  key-id rotation, and rejection of a non-Ed25519 key — and
  `tools/sign_model_manifests.py` / `tools/verify_model_manifests.py` have
  actually signed and re-verified all real model-registry entries with a
  development keypair.
- **`core/ota/model_updater.py`** (Phase 29): checksum-then-signature-then-
  atomic-`os.replace` installation, built to prevent the exact failure this
  project hit for real in Phase 7 — a silently truncated download treated
  as a complete, usable model. Its `apply_update()` fails **closed**: if a
  manifest entry carries a signature but the caller doesn't supply a public
  key, the update is rejected rather than silently falling back to
  checksum-only verification. Per `docs/roadmap.md`'s Phase 29 section, 9
  tests (`tests/ota/test_model_updater.py`) exercise this, including one
  that runs the real pipeline against a genuine installed model's real
  checksum and signature — and `backend/routes/models.py`'s
  `GET /models/{model_id}/download` plus `tools/ota_download_and_apply.py`
  close the loop with a real network transport, smoke-tested against a
  live backend on this workstation.

**What this proves, and what it doesn't.** These two modules prove the
cryptographic and update *logic* is correct: signature verification
rejects tampering, and a failed or partial update cannot leave a device
worse off than before the update started. What they do not prove, and
cannot prove without physical hardware, is that this logic can actually
run as firmware — invoked from a boot ROM or a hardware secure element,
before an OS has booted, as the root of trust for everything that loads
after it. That is a different execution environment with different
constraints (no Python interpreter, no filesystem in the OS sense, often
no dynamic memory allocation, a completely different toolchain), and
porting proven logic into it is real, unstarted engineering work, not a
formality.

### Secure boot vs. package signing — not the same thing

It is worth being precise about what "signing" currently covers, because
Phase 20's real progress on model-package signing is easy to mistake for
progress on secure boot, and they are different problems:

- **Package signing (done, in software)**: proves a *model file* was
  published by whoever holds AT's signing key, verified by application code
  running under an already-trusted OS.
- **Secure boot (not designed, needs hardware)**: proves the *bootloader,
  OS image, and drivers themselves* haven't been tampered with, verified by
  a hardware root of trust (a boot ROM or secure element with its own
  immutable key storage) *before* any of that code — including the Python
  interpreter that would run `package_signing.py` — is trusted to run at
  all. `firmware/architecture.md` marks this explicitly "NOT designed."

Phase 20's signing logic is a necessary building block for a future secure
OTA story, but it is not itself secure boot, and nothing in this repository
implements the latter.

## Readiness summary

Per this project's readiness framework (prototype / engineering prototype /
production candidate / production ready — see
`docs/commercial-product-architecture.md`):

| Component | Readiness | Why |
|---|---|---|
| Embedded audio HAL (Phase 14) | prototype | design only; no embedded backend code, no board to test against |
| Bootloader / OS / driver stack (Phase 15) | prototype | architecture description only; vendor-provided pieces not yet selected or integrated |
| Secure boot | not started | needs a hardware root of trust this project doesn't have; explicitly out of scope for a software-only environment |
| Model package signing (Phase 20 logic) | production candidate | real, tested Ed25519 sign/verify, applied to all real model-registry entries; never run from a boot ROM or secure element |
| OTA verify + atomic install (Phase 29 logic) | production candidate | real, tested checksum+signature+atomic-swap pipeline with a working network transport; never run on-device, only on this workstation and a local backend |

"Production candidate" here describes the *logic*, proven on a development
workstation — not a claim that either module has been deployed to, or
tested on, any device.

## What has to happen before any of this is real firmware

In order, per `firmware/architecture.md` and `docs/roadmap.md`'s Phase 12
recommendation:

1. Acquire physical Phase 12/13 hardware (the roadmap's current
   recommendation is a Jetson Orin Nano Super devkit, chosen for its
   verified whisper.cpp support and microSD-boot-by-default match to this
   project's hardware target — not yet purchased or validated as of this
   writing).
2. Bring up the vendor's Linux driver stack on it and confirm audio capture
   actually works over I2S/PDM (Phase 14), which is ordinary embedded Linux
   bring-up, not novel firmware development, given the SoC candidates are
   all full Linux-capable parts.
3. Design and implement secure boot against that specific board's actual
   root-of-trust hardware — this is genuinely new work with no software
   equivalent already built, since nothing in Phases 1-31 touches a boot
   ROM or secure element.
4. Port `core/security/package_signing.py` and `core/ota/model_updater.py`
   onto that OS image and prove — with a real device, not this workstation
   — that verification and atomic install behave the same way under
   on-device constraints (a smaller filesystem, no root RAPL-style
   development conveniences, real power-loss scenarios per the open item
   already flagged in `docs/privacy.md`).

None of these four steps has been started. This document, and
`firmware/architecture.md` before it, exist to record the design honestly
while that hardware is unavailable — not to claim any part of the boot or
driver chain has been tried.
