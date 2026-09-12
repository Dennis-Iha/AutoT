# AT (AutoT) — Manufacturing and Factory Test

Phases 27-28. This is a synthesis; the full design document with sourced
citations, per-stage rationale, and the complete factory-test checklist is
`hardware/manufacturing-and-factory-test.md`. Read that file for detail —
this page summarizes what it says and states the same bottom line up
front: **nothing described here has been executed.** No physical AT unit
exists, no contract manufacturer relationship exists, and no test fixture
exists. Both phases are blocked on Phase 24's custom PCB, which is itself
blocked on Phase 12's unresolved production SoC selection (see
`docs/roadmap.md`'s Phase 12 and 22-28 entries). Everything below is a plan
for what to do once a physical board exists, not a report of anything done.

## Why this exists now, before there's hardware to run it on

This project's software-first strategy means the manufacturing and
factory-test process was worth writing down honestly *before* physical
hardware arrives, for the same reason `hardware/hardware-selection.md` and
the other Phase 12-28 documents were: so the plan is grounded in this
project's own real, tested tools and real measured findings (Phases 3,
8-11, 20) rather than invented at the moment a board actually shows up
under time pressure.

## Phase 27: EVT / DVT / PVT stage gates

Standard three-stage hardware validation process used across consumer
electronics, not something specific to AT. `hardware/manufacturing-and-factory-test.md`
cites two independent industry sources for the stage definitions and
typical durations (OpenBOM's overview and Instrumental's stage-gate
handbook — see that file for the links).

| Stage | Purpose | Typical unit count | Typical minimum duration |
|---|---|---|---|
| **EVT** | Confirms the design works at a functional level; narrows hardware faults | small batch | ~4-5 weeks |
| **DVT** | Validates the complete design against product requirements under real-world conditions, on a production-representative process | 50-200 units | ~8 weeks |
| **PVT** | Confirms the manufacturing process itself can build at scale with acceptable yield | 50-500 units | ~4 weeks |

AT-specific acceptance criteria per stage, each tied to a real tool or
finding this project has already built and measured (not generic
boilerplate — full rationale in the source document):

- **EVT**: the first physical board boots the same `core/` software stack
  already proven on the dev workstation, with the hardware abstraction
  layer as the only allowed change. Phase 9's `tools/latency_benchmark.py`
  methodology re-runs on real silicon for the first time. This is also the
  first real chance to validate Phase 3's beamforming/denoise code against
  an actual multi-mic array (only synthetic signals tested so far) and
  Phase 22/23's battery/thermal targets against real measured power draw.
- **DVT**: `tools/asr_benchmark.py`, `tools/translation_benchmark.py`,
  `tools/tts_benchmark.py`, and `tools/language_id_benchmark.py` re-run
  across a DVT-sized unit sample, to catch per-unit/component variance a
  single EVT prototype can't reveal. Phase 30's full 9-language sweep
  should run here for the first time on real target hardware instead of
  workstation CPU, and — critically — Phase 30's real finding (genuinely-
  correct rate 2/9 on synthesized fixtures, plus a confident-misdetection
  failure mode worse than a low-confidence one) must be re-validated
  against real human speech before DVT can be considered passed, not
  assumed fixed by better hardware.
- **PVT**: yield analysis at production-representative scale using the
  Phase 28 factory test station below. The question shifts from "does the
  design work" to "can the line build it reliably" — which needs the test
  station to exist first.

## Phase 28: automated factory test station

A per-unit go/no-go test every manufactured unit would run before leaving
the line, designed to reuse this project's own already-built, already-
tested code rather than invent new factory-specific verification logic:

- **Audio path** — play a known reference signal into the mic array;
  confirm capture via `core/audio/capture.py`'s existing real-hardware-
  tested path, plus basic VAD triggering (`core/vad/`). Catches dead or
  miswired mics before a unit ships — a defect Phase 3's beamforming code
  would otherwise silently degrade around rather than fail loudly on.
- **Model/firmware integrity** — run `core/common/offline_runtime.py`'s
  `check_offline_readiness()` (real, tested since Phase 10) and
  `tools/verify_model_manifests.py` (Phase 20's real Ed25519 signature
  verification) against the unit's flashed storage. Confirms every model
  file is present, checksummed, *and* signed correctly before the unit is
  considered functional — reusing two tools already proven on this
  project's own model registries instead of writing new checks.
- **End-to-end smoke test** — one real utterance through the full
  pipeline (`core/orchestration/pipeline.py`'s `TranslationPipeline`,
  proven in Phase 8/17) on a known-reliable language. Phase 8/30 found
  es/en are the languages reliably detected on this project's synthesized
  test fixtures; a real human-speech reference set for factory use isn't
  built yet. This step confirms LID→ASR→translation→TTS produces output at
  all — it is not accuracy validation, which is DVT/PVT's job, not a
  per-unit factory check.
- **Battery/charging** — confirm charge acceptance and state-of-charge
  reporting via whatever fuel-gauge IC the eventual PMIC uses. Not
  specified further since no PMIC has been selected — blocked on the same
  Phase 12/22/24 chain as everything else here.
- **Bluetooth** — pairing plus basic A2DP audio passthrough. This
  directly tests the dual-purpose (translation + media playback) hardware
  requirement this project has flagged as unimplemented since its earliest
  design docs, and is worth testing per-unit because it depends on a
  companion BT chip every Phase 12 candidate needs but none has on-die.

## Status

Using this project's readiness framework: both phases are **prototype**
(design documents only). Nothing above has run against real hardware —
there is no physical unit, no test fixture, and no factory line. The
EVT/DVT/PVT process structure and durations are standard, cited industry
practice; the AT-specific acceptance criteria and the factory-test
checklist are derived from this project's own real, tested tools (Phases
3, 8-11, 20) rather than invented for this document — but "derived from
real tools" is not the same as "executed." See
`hardware/manufacturing-and-factory-test.md`'s closing table for the full
claim-by-claim breakdown, and `docs/roadmap.md`'s Phase 22-28 summary for
how this fits into the rest of the hardware-blocked work.
