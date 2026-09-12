# AT (AutoT) Commercial Product Architecture

Phase 32. This document synthesizes Phases 0-31 into one view of what a
shippable AT product actually is, what's blocking it from being sellable,
and how the pieces this project has built map onto real SKUs - a
product-architecture synthesis, not a business plan. Pricing, market
sizing, go-to-market, and unit economics are explicitly OUT of scope: this
codebase has no data to inform them, and inventing numbers for them would
violate the same "never fabricate" principle that governs every benchmark
and hardware claim in this project. What follows is engineering-honest
product architecture only.

## Two SKUs, one shared engine

Per `docs/architecture.md`'s "Hardware progression," AT is not one product
but two, sharing one software core:

- **AT Headphones (AT-H1)**: the first physical product target
  (`hardware/AT-H1-headphone-prototype.md`). Over-ear form factor, far more
  room for battery/compute/mics than an earbud - the easier of the two
  commercially, though still blocked (see below).
- **AT Pods (earbuds)**: the master spec's ultimate vision. Everything
  Phase 22-26 found (`hardware/battery-thermal-engineering.md`,
  `hardware/pcb-and-miniaturization.md`, `hardware/charging-case.md`)
  confirms this is a strictly harder version of the same unresolved
  constraints - not a separate problem, a compounded one.

Both SKUs run the identical AT-CORE software stack (Phases 2-11, 16-17,
20-21, 29): VAD, denoise, language ID, ASR, translation, TTS, dual-earbud
coordination, security, privacy, OTA. This is the actual commercial asset
this project has produced so far - a working, tested, offline speech
translation ENGINE, decoupled from either physical product.

## Readiness matrix

Per this project's own engineering principle: every component must be
labeled **prototype / engineering prototype / production candidate /
production ready** - not just "done."

| Component | Readiness | Why |
|---|---|---|
| VAD, audio cleanup, beamforming (Phase 1-3) | engineering prototype | real, tested code; beamforming only validated against synthetic signals, never a real mic array |
| Language ID (Phase 4) | engineering prototype | works; measured accuracy is 2-3/9 languages reliable on synthesized speech; Phase 30 found a worse failure mode (confident misdetection into the target language, bypassing the safety fallback) and it was fixed by raising the confidence threshold (0.5->0.65), re-verified against the real sweep |
| ASR (Phase 5) | engineering prototype | real, tested with forced language; not real-time on this CPU (up to 90s/utterance) |
| Translation (Phase 6, extended Phase 17) | production candidate for es<->en specifically; engineering prototype for the other 7 languages | es<->en is the only pair with end-to-end verified correct output (Phase 30); the rest have installed, checksummed, signed models but no verified correct full-pipeline output yet |
| TTS (Phase 7) | production candidate | real, tested, WER=0.0 round-trip on tested sentences |
| Full pipeline / streaming (Phase 8-9) | engineering prototype | real bug already found and fixed (audio-thread blocking); ~14-32s per-utterance latency is not commercially viable |
| Offline mode / checksums / signing (Phase 10, 20) | production ready | real, tested, applied uniformly, real end-to-end signature verification against all installed models |
| Model optimization (Phase 11) | engineering prototype | real quantization data exists for THIS workstation CPU only; must be re-measured on any real target chip, not assumed to transfer |
| Embedded hardware (Phase 12) | **not selected** | central open blocker - no chip found with both a working Whisper-class inference path and a wearable power budget |
| AT-H1 prototype design (Phase 13) | prototype (design doc only) | no physical unit exists |
| Embedded audio / firmware (Phase 14-15) | prototype (design doc only) | no physical unit exists |
| Dual-earbud coordination (Phase 16) | production candidate | real, tested distributed-systems logic; never run over real BLE |
| Conversation Mode (Phase 17) | engineering prototype | real, tested; inherits the same LID accuracy gap as the base pipeline |
| Mobile app (Phase 18) | prototype (design doc only) | no mobile SDK/device/emulator in this environment |
| Backend (Phase 19) | production candidate | real, tested FastAPI+SQLAlchemy service; SQLite is a dev/test choice, not a scaling decision |
| Security / signing (Phase 20) | production candidate for model signing; **not started** for secure boot | signing is real and tested; secure boot needs a boot ROM/secure element on real hardware |
| Privacy (Phase 21) | production ready | real, tested no-audio-persistence guarantee with two honestly-documented residual gaps (power-loss timing, unlink-not-secure-erase) |
| Battery/thermal/PCB/case/manufacturing (Phase 22-28) | prototype (design docs only) | all genuinely blocked on Phase 12's chip selection |
| OTA model updates (Phase 29) | production candidate | real, tested verify-then-atomic-install pipeline; network transport proven against a live server, not yet against real device hardware |
| Product metrics (Phase 31) | production candidate | real backend aggregation; no fleet exists to generate real-world volume |

## The critical path to a commercial launch

Not every gap above blocks launch equally. In dependency order:

1. **Chip selection (Phase 12/22)** - blocks everything physical
   (Phase 13-15, 24-28). This is the single highest-leverage open item:
   no other hardware work can start for real until it resolves.
2. **Language accuracy (Phase 8/30)** - blocks any commercial language
   claim beyond es<->en. Shipping a "9-language translator" today would be
   selling something this project's own tests show mostly doesn't work
   (`docs/roadmap.md`'s Phase 30 section: genuinely-correct rate 2/9 -
   originally masked by a raw pass rate of 5/9 until the underlying
   confidence-threshold defect was found and fixed, after which the raw
   rate also reads 2/9, matching reality). This must be fixed - actual LID
   accuracy on the other 7 languages, not just the safety-net bug around
   it - or the initial commercial claim must be narrowed to the languages
   actually verified - the latter is always available today, unlike the
   former.
3. **Real-time latency (Phase 9/11)** - a 14-32s round trip per utterance
   is not a commercially usable "conversation" product regardless of
   language accuracy; needs either the eventual production chip's NPU
   acceleration (unverified - Phase 12) or a smaller/faster model swap,
   itself needing re-benchmarking per Phase 11's own finding that
   optimization results don't transfer across hardware.
4. **Secure boot (Phase 20)** - not commercially blocking for a v1
   launch by itself, but should land before or alongside the first
   manufactured unit, not after.

Items NOT on the critical path, already at production-candidate or better:
model integrity/signing, privacy guarantees, backend, OTA update mechanics,
dual-earbud coordination logic, metrics infrastructure. This project's
software-first strategy (proving AT-CORE before any hardware commitment)
has done what it was meant to do: the parts that don't need physical
hardware are largely ready, and the remaining blockers are honestly
concentrated in the parts that do.

## What a defensible v1 commercial claim looks like today

Not "AT translates 9 languages" - Phase 30's own data contradicts that.
A defensible v1 claim, grounded only in what this project has actually
verified: **offline Spanish<->English speech translation**, with the other
7 languages explicitly marked (per `docs/architecture.md`'s own language
coverage policy) as in development, not shipped. Expanding the claim
language-by-language as each one clears the same bar es/en already did
(Phase 30's full-pipeline verification, not just isolated per-stage
benchmarks) is the only honest path to "9 languages" as a commercial
claim - not a target date, a verification gate.

## What this document deliberately does not contain

Pricing, bill-of-materials cost, target market segments, competitive
pricing analysis, unit economics, or a go-to-market plan. None of these
can be honestly derived from a codebase - they require market research,
supplier quotes, and business decisions outside this project's engineering
scope. Producing numbers for them here would be fabrication, the same
category of error this project's Engineering Principles already forbid for
benchmarks and hardware specs.
