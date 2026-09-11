# AT Phases 27-28: Manufacturing (EVT/DVT/PVT) and Automated Factory Test

**Status: design document, not executed.** No physical prototype, contract
manufacturer relationship, or test fixture exists. Both phases are
downstream of Phase 24's custom PCB, which is itself blocked on Phase 12's
unresolved production SoC selection - nothing here can start for real
until a physical board exists to run through these stages. This document
defines the process AT should follow (standard consumer-electronics
practice, cited below, not invented) and what the factory test station
needs to check, derived from what this project has actually built and can
verify is worth testing.

## Phase 27: Manufacturing stage gates (EVT / DVT / PVT)

Standard three-stage hardware validation process before mass production
([OpenBOM overview](https://www.openbom.com/blog/evt-vs-dvt-vs-pvt-understanding-the-stages-of-product-development),
[Instrumental's stage-gate definitions](https://instrumental.com/build-better-handbook/evt-dvt-pvt)):

| Stage | Purpose | Typical unit count | Typical minimum duration |
|---|---|---|---|
| **EVT** (Engineering Validation Test) | Confirms the design works at a functional level - closest prototype to launch intent so far, narrows hardware faults | small batch | ~4-5 weeks |
| **DVT** (Design Validation Test) | Validates the complete design against product requirements under real-world conditions, using a production-representative process | 50-200 units | ~8 weeks |
| **PVT** (Production Validation Test) | Confirms the manufacturing process itself can build at scale with acceptable yield | 50-500 units | ~4 weeks |

AT's specific per-stage acceptance criteria, mapped to what this project
has actually already built and measured (not invented for this document):

- **EVT**: first physical AT-H1/earbud board boots, runs the exact same
  `core/` software stack proven on the dev workstation (Phases 2-11) without
  modification beyond the hardware abstraction layer, and reproduces
  Phase 9's latency benchmark methodology (`tools/latency_benchmark.py`) on
  real silicon for the first time. Also the first real chance to validate
  Phase 3's beamforming/denoise code against an actual multi-mic array
  (only synthetic signals tested so far) and Phase 22/23's battery/thermal
  design targets against real measured power draw.
- **DVT**: `tools/asr_benchmark.py`, `tools/translation_benchmark.py`,
  `tools/tts_benchmark.py`, and `tools/language_id_benchmark.py` re-run
  across a DVT-sized unit sample to confirm per-unit consistency, not just
  one prototype's numbers - catches component/manufacturing variance
  (e.g. mic sensitivity tolerance) a single EVT unit can't reveal. This is
  also the stage where Phase 30's full 9-language performance sweep should
  run for the first time on real target hardware, not workstation CPU.
  Real-world conversational use (not just synthesized fixtures) should
  start here too - Phase 8's LID accuracy gap (2-3/9 languages reliable on
  synthesized fixtures) is exactly the kind of finding that must be
  re-validated against real human speech before DVT can be considered
  passed, not assumed fixed by better hardware.
- **PVT**: yield analysis at production-representative scale using Phase
  28's automated factory test station (below) - the goal shifts from "does
  the design work" (EVT/DVT) to "can the line build it reliably," which
  needs the test station to exist first.

## Phase 28: Automated factory test station

A per-unit go/no-go test every manufactured AT unit runs before leaving the
line. Designed around what this project's own code already knows how to
verify, not a generic template:

- **Audio path**: play a known reference signal into the mic array, confirm
  capture (`core/audio/capture.py`'s existing real-hardware-tested path) and
  basic VAD triggering (`core/vad/`) - catches dead/miswired mics before a
  unit ships, which Phase 3's beamforming code would otherwise silently
  degrade around rather than fail loudly on.
- **Model/firmware integrity**: run `core/common/offline_runtime.py`'s
  `check_offline_readiness()` (already real, tested code from Phase 10) and
  `tools/verify_model_manifests.py` (Phase 20's real signature verification)
  against the unit's flashed storage - confirms every model file is present,
  checksummed, AND signed correctly before the unit is considered
  functional. This reuses two already-built, already-tested tools instead
  of inventing new factory-test-specific verification logic.
- **End-to-end smoke test**: one real utterance through the full pipeline
  (`core/orchestration/pipeline.py`, proven in Phase 8/17) on a
  known-reliable language (Phase 8 found es/en reliably detected on
  synthesized fixtures - a real human-speech reference set would be needed
  for factory use, not yet built) - confirms LID->ASR->translation->TTS
  produces output, not full accuracy validation (that's DVT/PVT's job, not
  a per-unit factory check).
- **Battery/charging**: confirms charge acceptance and reports state-of-
  charge via whatever fuel-gauge IC the eventual PMIC selection uses - not
  specified further here since no PMIC has been selected (blocked on the
  same Phase 12/22/24 chain as everything else in this document).
- **Bluetooth**: pairing + basic A2DP audio passthrough test - directly
  testing the dual-purpose (translation + media playback) hardware
  requirement this project has flagged as unimplemented since the earliest
  design docs, and specifically worth testing per-unit given it depends on
  a companion BT chip every Phase 12 candidate needs but none has on-die.

## What's actually proven vs. what's designed on paper

| Claim | Status |
|---|---|
| EVT/DVT/PVT process structure and typical durations | Standard industry practice, cited from multiple independent sources |
| AT-specific acceptance criteria per stage | Derived from this project's own real, tested tools (Phases 3, 8-11, 20) - not generic boilerplate |
| Factory test station design | Reuses real existing code (`offline_runtime.py`, `verify_model_manifests.py`, `pipeline.py`) rather than inventing new verification logic |
| Any of this has actually been executed | **No** - blocked on Phase 24's custom PCB, itself blocked on Phase 12/22's unresolved SoC selection |
