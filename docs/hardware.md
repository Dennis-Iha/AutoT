# AT (AutoT) Hardware Overview

**Zero physical hardware exists for this project.** No SoC has been
purchased, no board has been wired up, no enclosure has been machined or
printed, and no PCB has been fabricated. Every file under `hardware/` is a
design document — desk research, requirements derived from this project's
own measured software workload (Phases 0-11), and citations to real
third-party reference data (comparable shipped products, published
datasheets, safety standards). None of it is a claim that something has
been built. This document synthesizes those six documents into one picture;
it adds no new numbers and states nothing that isn't already backed by one
of them.

The six source documents, each already carrying its own "design document,
not built" status line:

- `hardware/hardware-selection.md` (Phase 12)
- `hardware/AT-H1-headphone-prototype.md` (Phase 13)
- `hardware/battery-thermal-engineering.md` (Phases 22-23)
- `hardware/pcb-and-miniaturization.md` (Phases 24-25)
- `hardware/charging-case.md` (Phase 26)
- `hardware/manufacturing-and-factory-test.md` (Phases 27-28)

Read those for the full reasoning and citations. This page is a map, not a
replacement.

## The hardware progression

`docs/architecture.md`'s "Hardware progression" section lays out the plan as
seven stages, software-first, moving to progressively smaller/more
constrained hardware only after the workload has been proven and benchmarked
at the previous stage:

1. Workstation
2. Portable embedded computer (dev board)
3. Standalone AT headphone prototype (AT-H1)
4. Custom headphone motherboard
5. Large standalone earbud prototype
6. Custom AT earbud PCB
7. Production miniaturization

Only stage 1 has actually happened. It isn't a "hardware" deliverable in the
sense the rest of this document uses the word — it's the ordinary dev
workstation this project's software (Phases 0-11, 16-17, 19-21, 29) has been
built and tested on. Everything from stage 2 onward is paper.

## Stage-by-stage status

| Stage | Status | Doc |
|---|---|---|
| 1. Workstation | Done — the software stack is real, tested, running today | `docs/architecture.md` (implementation status table) |
| 2. Portable embedded computer (dev board) | Desk research only; no board purchased or benchmarked. Phase 12 compared three candidate SoCs (Jetson Orin Nano Super, Qualcomm QCS6490, NXP i.MX 8M Plus) against this project's own measured ASR/translation/TTS latency, and recommends starting physical validation with the Jetson, but that validation hasn't happened | `hardware/hardware-selection.md` |
| 3. AT-H1 headphone prototype | Design document only; defines the target architecture (mic array -> dev-board SoC -> the same `core/` pipeline, ported not rewritten -> speaker) and sizes it against this project's own real model-storage/RAM figures. No unit built | `hardware/AT-H1-headphone-prototype.md` |
| 4. Custom headphone motherboard | Requirements only, no schematic. Explicitly blocked on stage 2's SoC selection being physically validated first | `hardware/pcb-and-miniaturization.md` (Phase 24) |
| 5. Large standalone earbud prototype | Not documented yet — no `hardware/*.md` file currently addresses this intermediate stage specifically; the closest existing coverage is Phase 25's miniaturization discussion, which jumps straight to the custom-PCB earbud case | none yet |
| 6. Custom AT earbud PCB | Requirements only, no schematic. Also blocked on stage 2, and additionally on the earbud-specific battery/thermal/PCB-density constraints below | `hardware/pcb-and-miniaturization.md` (Phase 25) |
| 7. Production miniaturization | Process defined (standard EVT/DVT/PVT stage-gate model, cited from industry sources), nothing executed — no prototype exists to run through it | `hardware/manufacturing-and-factory-test.md` (Phases 27-28) |

Two more documents don't map to a single stage — they're constraints that
apply across stages 3 through 7, sharpening as the form factor shrinks:

| Topic | Status | Doc |
|---|---|---|
| Battery and thermal engineering | Cites real reference data (Sony WH-1000XM5, AirPods Pro 2, and directly-relevant competitor Timekettle M3/W4 translator-earbud battery capacities; IEC 62368-1's 43-48°C touch-temperature limit). Defines the battery-life formula to apply once real target-silicon power exists. No AT-specific mAh or °C number exists | `hardware/battery-thermal-engineering.md` (Phases 22-23) |
| Charging case | Grounded in Timekettle's case-assisted-runtime model (25h with case vs. 7.5h earbud-only) as the design pattern to plan around. No case battery capacity or BOM decided | `hardware/charging-case.md` (Phase 26) |

## The one finding that recurs across all six documents

**No chip this project has evaluated sits in the power/compute band AT's
workload actually needs**, and this shows up independently in both the
compute-selection research and the battery-sizing research:

- Phase 12's comparison of Jetson Orin Nano Super, QCS6490, and i.MX 8M Plus
  found that AI-accelerator support for the specific workload (Whisper-class
  transformer-encoder inference) is not equivalent across the three, and
  isn't visible from TOPS numbers alone. Only the Jetson has a real (if
  community-verified, not vendor-certified) whisper.cpp acceleration path
  today; QCS6490's own vendor tooling doesn't yet cleanly support
  Whisper-class models, and no working path was found for the i.MX 8M Plus
  at all.
- Phase 22 sharpened this into a power-budget argument: at the low end of
  the Jetson's 7-25W range, a Sony WH-1000XM5-sized 4.56Wh battery would
  last under 40 minutes — nowhere near usable for a wearable. At the other
  end, MCU-class parts named in the project's original spec (e.g. Ambiq's
  Apollo4 Blue Plus, ~4µA/MHz active from MRAM per its datasheet) are
  genuinely wearable-power-friendly but have neither the RAM nor the
  floating-point/vector throughput to run whisper.cpp's encoder at any
  usable latency.

Nothing identified so far sits between those two bands. That gap is the
actual blocker behind every "requirements only, no schematic" and "not
built" status above — Phase 24's custom motherboard, Phase 25's earbud PCB,
and Phases 27-28's manufacturing process are all sequenced *after* a
production SoC is selected, and that selection can't happen honestly until
a chip exists in the needed band and gets physically benchmarked against
this project's own `tools/asr_benchmark.py` / `tools/quantization_benchmark.py`
— not before, per this project's Engineering Principles against committing
to hardware ahead of measurement.

## Manufacturing

Phases 27-28 (EVT/DVT/PVT stage-gating and the automated factory-test
station) get their own detailed treatment in `docs/manufacturing.md`; see
`hardware/manufacturing-and-factory-test.md` for the underlying source
document. In short: the process is standard consumer-electronics practice
with AT-specific per-stage acceptance criteria already mapped to this
project's real, tested tools (`core/common/offline_runtime.py`'s readiness
check, Phase 20's signature verification, `core/orchestration/pipeline.py`'s
end-to-end smoke test) — but none of it has been executed, because there is
no manufactured unit to run it against.

## Readiness, using this project's own framework

Per this project's readiness labels (prototype / engineering prototype /
production candidate / production ready), every hardware-facing item above
is **prototype (design document only)**, and Phase 12's SoC choice is more
precisely **not selected** — there is no candidate today that clears both
the whisper.cpp-inference requirement and a wearable power budget. This
matches `docs/commercial-product-architecture.md`'s readiness matrix, which
lists Phases 12-15, 18, and 22-28 the same way: real engineering work with
real citations, but no hardware to point to yet.
