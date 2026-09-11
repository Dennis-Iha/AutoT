# AT Phases 24-25: Custom PCB and Earbud Miniaturization

**Status: design document, not built.** No schematic, layout, or PCB
fabrication exists in this environment - there is no EDA tooling, no
component library, and no physical board to design against. This document
states the real prerequisites and constraints these two phases depend on
(most of which earlier phases already established) and is explicit about
what remains genuinely unresolved. Per Engineering Principles #16-18: do
not design a PCB before the workload is benchmarked on real target
silicon - Phase 12's own hardware selection is still "pending physical
validation," so a schematic today would be designed against a
never-confirmed SoC, not a validated one.

## Why PCB design cannot start yet

`hardware/hardware-selection.md`'s Phase 12 recommendation (Jetson Orin
Nano Super) is explicitly a *development* platform, not a production part -
its own document says none of the three evaluated candidates is "remotely
close to earbud form factor or power budget," and `hardware/battery-thermal-engineering.md`
sharpens that into a specific, sourced gap: no chip this project has
evaluated sits in the power/compute band AT's workload actually needs. A
custom PCB schematic requires a committed BOM (SoC, PMIC, memory, mic
array, BT front-end) - designing one now would mean inventing a part
selection this project has explicitly refused to fabricate (Engineering
Principle: never claim something works, or is chosen, without verifying
it against reality first).

## Phase 24: AT-H1 headphone custom motherboard - requirements, not schematic

The master spec's progression (`docs/architecture.md`'s "Hardware
progression") puts the custom headphone motherboard after the AT-H1
prototype (Phase 13, currently a dev-board-based design per
`hardware/AT-H1-headphone-prototype.md`) proves the software stack on
real hardware. Requirements a real schematic will need to satisfy, all
already established by earlier phases rather than invented here:

- Whatever SoC Phase 12's physical validation eventually selects, with
  a confirmed whisper.cpp-class inference path (Phase 12's central
  finding: this is NOT guaranteed by TOPS alone - QCS6490 and i.MX 8M
  Plus both currently lack a working path, only Jetson-class parts have
  one today, and Jetson-class parts fail Phase 22's power budget).
- >=8GB flash, sized against this project's own real installed model
  footprint (~1.4GB across ASR+translation+TTS, `hardware/AT-H1-headphone-prototype.md`).
- 2-4 MEMS microphone inputs (Phase 3's beamforming/denoise code is written
  and tested against synthetic 2-channel signals, but has never run against
  a real mic array - this remains true until Phase 24 hardware exists).
- A Bluetooth companion chip supporting A2DP sink (media playback) - every
  Phase 12 candidate needs one, none has it on-die, and this project's
  hardware target explicitly requires solid dual-purpose (translation +
  Bluetooth media) operation, which nothing in this codebase has
  implemented or tested yet (a known, tracked gap, not an oversight).
- microSD boot support, matching this project's actual deployment target
  (an OS image booted from microSD on the headphone hardware itself, per
  the project's hardware-target notes) - relevant when selecting a SoC,
  since not every Phase 12 candidate defaults to microSD boot the same way
  Jetson's devkit does.

## Phase 25: earbud miniaturization - the harder, still-unsolved squeeze

Earbud miniaturization is not "the same board, smaller" - it compounds
every constraint Phase 22-24 already found difficult:

- **Battery**: from ~1200mAh (headphone-class, Sony WH-1000XM5 reference)
  to ~50mAh per earbud (AirPods Pro 2 reference) - roughly a 24x reduction
  in energy budget for a workload that is far more compute-intensive per
  second than what a TWS earbud's DSP normally runs
  (`hardware/battery-thermal-engineering.md`).
- **Thermal**: an earbud is sealed against skin with far less surface area
  and no airflow, against the over-ear form factor's much larger radiating
  surface - the harder side of the same IEC 62368-1 touch-temperature
  constraint (43-48°C) that Phase 23 already flags as unresolved even for
  the easier headphone case.
- **PCB density**: general industry practice for TWS earbuds (not this
  project's own verified spec - these are secondary industry-blog sources,
  not primary vendor documentation, cited with that caveat, the same
  honesty bar Phase 12 applied to unverified claims) commonly uses 4-6
  layer, sometimes HDI, PCBs, often rigid-flex construction so a flex
  section can route into the earbud stem/antenna while rigid sections carry
  the SoC/PMIC/mic components ([HilPCB overview](https://hilpcb.com/en/blog/earbuds-pcb/),
  [Kingford rigid-flex earphone PCBs](https://www.kingfordpcb.com/rigid-flex-pcbs/4.html)).
  Whether AT's eventual production SoC package even fits this class of
  board is unknown - it depends on a chip that hasn't been selected yet.
- **Mic array within an earbud shell**: MEMS microphone packages are
  small, reflow-solderable surface-mount parts and are the standard choice
  in existing earbuds ([general MEMS mic overview](https://hilelectronic.com/microphone-pcb/)),
  which is reassuring for component availability, but Phase 3's
  beamforming code still has never been validated against ANY real mic
  array, let alone one squeezed into an earbud shell's much shorter
  baseline distance between microphones (shorter baseline = harder
  time-difference-of-arrival estimation - a real signal-processing
  consequence of miniaturization, not just a packaging problem).

## What's actually proven vs. what's designed on paper

| Claim | Status |
|---|---|
| Component-level requirements (flash size, mic count, BT need, microSD boot) | Derived from this project's own earlier measured/tested phases - real, not invented |
| A production SoC exists that meets Phase 24's compute+power requirements | **No** - this remains Phase 12/22's open, unresolved finding |
| Any schematic, layout, or BOM | **Does not exist** |
| Earbud-shell mic array baseline is short enough to hurt beamforming accuracy | Plausible signal-processing consequence, NOT measured (Phase 3 only tested synthetic 2-channel signals with an assumed baseline) |
| Rigid-flex PCB construction is standard for this form factor | Cited from secondary industry sources, not verified against a primary vendor spec |

## Next action

Unblocks only after Phase 12's physical validation identifies a real
candidate SoC with a working, measured inference path AND a power profile
that clears Phase 22's budget - at that point, and not before, a real
schematic can be drafted against a committed BOM instead of a hypothetical
one.
