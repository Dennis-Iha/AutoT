# AT Phases 22-23: Battery and Thermal Engineering

**Status: design document, not measured.** No production AI SoC has been
selected for AT (Phase 12's Jetson Orin Nano Super recommendation is
explicitly a *development* platform - see `hardware/hardware-selection.md`'s
own caveat that its 7-25W power range "clearly is not" acceptable for a
battery-powered headphone), and no physical battery, enclosure, or thermal
hardware exists in this environment. Real power draw for AT's actual
workload has never been measured (Phase 11 already documented this: this
workstation has no root RAPL/`perf` access, so `power_watts` is `null` in
every quantization benchmark rather than guessed). This document does three
honest things instead of fabricating numbers: (1) cites real, sourced
reference data points for comparable products and safety standards, (2)
defines the methodology/formula AT's own battery-life and thermal budget
must be computed with once real hardware exists, and (3) states the one
finding this research already surfaces clearly - **no candidate chip
currently known to this project sits in the power/compute band AT actually
needs.**

## Battery, Phase 22

### Reference data points (real, cited - not this project's own measurements)

| Product class | Capacity | Rated runtime | Source |
|---|---|---|---|
| Premium ANC over-ear headphone (Sony WH-1000XM5) | 3.8V, 1200mAh (4.56Wh) | 30h with ANC on | [Sony ME spec sheet](https://www.sony-mea.com/en/electronics/headband-headphones/wh-1000xm5/specifications) |
| Premium TWS earbud (AirPods Pro 2, per-bud) | 49.7mAh | ~6h per Apple's published rating | [TechInsights teardown](https://www.techinsights.com/blog/apple-a2731-lithium-ion-battery-apple-airpods-pro-2nd-generation-battery-essentials) |
| Premium TWS charging case (AirPods Pro 2) | 523mAh | — | same teardown |
| Existing offline translator earbuds (Timekettle M3, per-bud / case) | 50mAh / 400mAh | 7.5h earbud-only, 25h with case recharge cycles | [Timekettle M3 product page](https://www.timekettle.co/products/m3-travel-translator-earbuds) |
| Existing offline translator earbuds (Timekettle W4, per-bud / case) | 60mAh / 500mAh | not separately confirmed here | [Timekettle W4 product page](https://www.timekettle.co/products/w4-ai-interpreter-earbuds) |

Timekettle's products are the most directly relevant reference of all: they
are a shipping product in AT's own category (translator earbuds), and their
per-bud capacity (50-60mAh) lands in the same range as AirPods Pro 2's
49.7mAh above - independent confirmation this is roughly the achievable
battery volume in a real earbud shell today, not a coincidence of one
product line. Also directly relevant and worth stating honestly: Timekettle
markets only **13 offline language pairs** on the M3 - AT's v1 target of 9
languages with full bidirectional translation (16 pairs, Phase 17) is a
larger claim than an existing shipped competitor's offline mode, which is
exactly why Phase 6/17's real, tested translation models matter and why
this project should not overclaim readiness beyond what Phases 6/17 actually
verified per language (`docs/architecture.md`'s "Language coverage is a
claim, not an assumption" section already enforces this).

These bound AT's two physical form factors from the master spec's hardware
progression: **AT-H1 headphones** (Phase 13, first physical prototype) have
roughly the WH-1000XM5's battery volume budget available; the eventual
**AT earbud** (Phase 25) has roughly AirPods Pro 2's ~50mAh-per-bud budget -
an order of magnitude less energy, for a workload (local Whisper-class ASR +
CTranslate2 + Piper TTS) that is far more compute-intensive per second of
audio than AirPods' on-device processing (noise cancellation DSP, not a
~74M-parameter transformer encoder).

### The gap this surfaces

Phase 12 already found no production-ready chip provides both a working
Whisper-class inference path AND a wearable-appropriate power envelope.
Two more data points sharpen that gap rather than close it:

- **Low end (MCU-class, confirmed too small for our workload)**: Ambiq's
  Apollo4 Blue Plus - a chip class the master spec itself named as a
  reference part (alongside the also-named Nordic nRF54L15, both already
  ruled out in Phase 12 for insufficient RAM/flash) - runs its Cortex-M4 at
  4µA/MHz active from MRAM ([Ambiq datasheet](https://ambiq.com/wp-content/uploads/2022/05/Apollo4-Blue-Plus-SoC-Datasheet.pdf)).
  That is genuinely wearable-battery-friendly, but this class of chip cannot
  run whisper.cpp's encoder at any usable latency - it has neither the RAM
  nor the floating-point/vector throughput Phase 5-11 measured we need.
- **High end (compute-class, confirmed capable but power-unsuitable)**:
  Jetson Orin Nano Super, 7-25W (`hardware/hardware-selection.md`). At even
  the low end of that range, a WH-1000XM5-sized 4.56Wh battery would last
  **under 40 minutes** - nowhere close to a usable wearable product.

**No chip this project has evaluated sits between those two bands** for a
Whisper-class encoder workload. This is Phase 22's real deliverable: not a
battery capacity number, but a clearly-stated, sourced constraint that must
drive Phase 24's production SoC search - the part needs on the order of
QCS6490-class (Phase 12's middle candidate, ~12 TOPS Hexagon NPU, full SoC
power **unverified** - see hardware-selection.md) compute at something
closer to the Apollo4's power class, and no such part has been identified
yet. Buying hardware or committing to a battery capacity before that part
exists and its workload power is physically measured would violate
Engineering Principles #16-18.

### Battery-life estimation methodology (to be filled in with real numbers)

Once a candidate production SoC exists and Phase 12's benchmark scripts
(`tools/asr_benchmark.py`, `tools/quantization_benchmark.py`) are re-run on
it with real power instrumentation (vendor eval board power rails, or an
external inline power meter - this workstation cannot self-measure, per
Phase 11), compute:

```
duty_cycle = active_processing_seconds / total_session_seconds
avg_power_w = idle_power_w * (1 - duty_cycle) + active_power_w * duty_cycle
runtime_hours = (battery_mAh / 1000 * battery_voltage_v) / avg_power_w
```

`active_processing_seconds` is NOT the length of the user's speech - it is
the pipeline's actual compute time per utterance, which Phase 9 measured at
~38-44s end-to-end on this workstation's CPU for a ~2s utterance (dominated
by the LID+ASR encoder passes, run twice per utterance - Phase 9's
documented two-pass architecture). This ratio must be re-measured on
whatever production SoC is eventually chosen; workstation-CPU timing is not
a valid proxy for embedded-NPU timing (Phase 11's own quantization finding -
speed does not scale predictably even between quantization *levels* on the
*same* CPU - is a direct warning against assuming it transfers across
architectures).

`idle_power_w` also has no measurement yet - it depends on whether the
production design keeps the AI accelerator fully powered down between VAD
triggers (an actual design requirement, not yet implemented anywhere in
this codebase: `core/vad/segmenter.py` currently only segments audio, it
does not gate hardware power state).

## Thermal, Phase 23

### The one real, sourced constraint: skin/touch temperature limits

IEC 62368-1 (the safety standard superseding IEC 60950-1/60065 for audio/
video/ICT equipment, cited from multiple engineering references including
[Regulatory Decoded's summary](https://regulatorydecoded.com/temperature-limits-in-product-design/)
and [Electronics Cooling's wearable-specific writeup](https://www.electronics-cooling.com/2025/07/thermal-design-for-externally-worn-wearable-electronics/))
sets touch-temperature limits between **43-48°C** depending on the contacted
material's thermal effusivity and expected contact duration - sustained
contact (>1 minute, which describes headphone/earbud wear directly) against
plastic/rubber (TS1 classification) is commonly cited at a 48°C ceiling;
metal surfaces are held to a lower limit at the same contact duration
because metal's higher thermal effusivity transfers heat into skin faster
at the same surface temperature. This is the hard external-surface design
target for both AT-H1 and the eventual earbud enclosure - not a number this
project invented, and not one it has independently verified against the
full standard text (worth confirming against a licensed copy of IEC
62368-1:2020 itself before any enclosure is finalized, since this document
relied on secondary engineering-press summaries, not the primary standard).

### What is NOT known and cannot be estimated honestly yet

- **Where heat is generated**: no production SoC is selected, so there is
  no die/package thermal resistance (θJA/θJC) data to work from.
- **Enclosure thermal path**: no CAD/enclosure design exists (Phase 24-25
  are also not started) to model conduction from the SoC package to the
  external plastic/silicone surface IEC 62368-1's limit applies to.
  Over-ear headphones (AT-H1) have far more surface area and airflow to
  dissipate heat into than an in-ear earbud sealed against skin - the
  earbud form factor (Phase 25) is the harder thermal problem by a wide
  margin, compounding the same form-factor squeeze already identified for
  battery capacity above.
- **Sustained vs. burst duty cycle**: whether the accelerator can be
  power-gated between utterances (relevant to both peak junction
  temperature and average skin temperature) depends on a production chip's
  actual power-state support, which doesn't exist yet to characterize.

### Next action

Identical prerequisite to Phase 22's: a real production-candidate SoC with
a working Whisper-class inference path and a published (or measured)
power/thermal profile. Until one exists, any specific junction temperature,
heatsink, or duty-cycle-throttling design would be invented, not
engineered - Phases 22 and 23 stay in the "requirements and constraints
defined, physical validation pending" state alongside Phase 12, not a
"done" state.

## What's actually proven vs. what's designed on paper

| Claim | Status |
|---|---|
| AT's own compute workload latency (drives duty cycle) | Measured, on a workstation CPU (Phase 9/11) - NOT on any embedded or production-candidate SoC |
| Comparable product battery capacities cited above | Real, sourced from vendor specs/teardowns - not this project's own measurement |
| IEC 62368-1 touch-temperature limit (43-48°C) | Sourced from secondary engineering references, not independently verified against the primary standard text |
| Any AT-specific battery-life or thermal number (mAh needed, °C reached) | **Not established** - no production SoC, enclosure, or physical hardware exists to measure or even credibly estimate from |
| A chip exists today in the power/compute band AT needs | **No** - this is this document's central, real finding, not a placeholder |
