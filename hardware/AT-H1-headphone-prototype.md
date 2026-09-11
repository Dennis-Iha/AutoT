# AT-H1: Standalone AI Translator Headphones — Prototype Architecture

**Status: design document, not built.** This defines what a first physical
AT-H1 prototype would need, derived from this project's own measured
software requirements (Phases 5-11) and Phase 12's hardware research. No
physical prototype has been built or tested in this environment — there is
no hardware here to build one on. Treat every number below as a design
target to validate once real hardware exists, not a spec that has been
confirmed to work.

## Why headphones before earbuds

Per the master architecture decision (`docs/architecture.md`): headphones
have far more physical room than earbuds for compute, battery, RAM, and
microphones, so they are the first real physical product target — prove
the workload standalone before attempting the earbud form factor's much
tighter constraints (Phase 24+).

## Target architecture

```
Microphone array (2-4 MEMS mics)
        |
Embedded AI compute module (Phase 12: Jetson Orin Nano Super class, pending
physical validation - see hardware/hardware-selection.md)
        |
   core/vad -> core/denoise -> core/language_id -> core/asr ->
   core/translation -> core/tts    (the SAME software stack proven on the
                                     dev workstation in Phases 2-11, ported
                                     as-is - not rewritten for this target)
        |
Speaker driver(s)
```

Phone connection (Bluetooth or USB) is setup/diagnostics/language-pack-
install/firmware-update ONLY, per the master spec's core requirement -
translation must work with the phone absent or off. This project's
`tools/at_translate.py` and `core/orchestration/pipeline.py` already
enforce this architecturally: nothing in the translation path depends on
a phone/network connection today, on the dev workstation. Porting to
AT-H1 hardware doesn't change that property, only where it runs.

## Hardware requirements, sized against this project's own measured needs

Storage: this project's actual installed models total ~1.4GB gitignored
under `models/` on the dev workstation (base ASR ~148MB or ~82MB at q8_0;
8 translation pairs at 79-315MB each, ~1GB total; one TTS voice ~63MB).
A production AT-H1 needs flash storage sized for this PLUS the OS and
firmware - **>= 8GB flash** is a reasonable starting target, not a
measured requirement (no embedded storage has been tested).

RAM: Phase 11's peak-RSS measurements for ASR alone ranged 185-288MB
depending on quantization; translation models add 80-300MB each while
loaded (Phase 6); TTS ~small. A single active language pipeline (one ASR
model + one translation pair + one TTS voice loaded) measured comfortably
under 1GB peak RSS on the dev workstation - **doesn't by itself demand
more than the Jetson Orin Nano Super's 8GB**, but this has never been
measured on constrained embedded RAM, only a workstation with 15GB
available.

Other requirements per the master spec, none built or sourced yet:
MEMS microphone array (2-4 mics, for Phase 3's beamforming/denoise work -
built and tested only against synthetic multi-channel signals so far, see
`docs/architecture.md`'s Phase 3 status row), speaker driver(s), battery +
PMIC + fuel gauge, Bluetooth (a companion chip on every Phase 12 candidate
- see hardware-selection.md), physical buttons, USB-C, temperature sensor
(relevant to Phase 23's thermal work).

## What's actually proven vs. what's designed on paper

| Claim | Status |
|---|---|
| The software stack (Phases 2-11) works correctly | Proven, on a workstation CPU |
| The software stack fits in a Jetson-class device's RAM/storage budget | Design estimate from workstation measurements, not measured on embedded hardware |
| Beamforming/denoise improve real multi-mic array audio | NOT proven - only synthetic 2-channel test signals (Phase 3) |
| Battery life on this workload | NOT measured - no battery-powered hardware exists to test (Phase 22) |
| Thermal behavior under sustained translation load | NOT measured on embedded hardware (Phase 23 partial workstation data may exist separately) |
| Bluetooth media playback alongside translation | NOT implemented or tested - the hardware target's dual-purpose requirement (see project memory) is a known gap |

## Next action

Acquire the Phase 12-recommended dev kit, port `tools/at_translate.py`'s
pipeline to run on it, and replace every "design estimate" row above with
a measured one - in that order. Do not proceed to Phase 14 (embedded audio
drivers) or beyond on paper alone; those need the physical board this
document assumes but does not have.
