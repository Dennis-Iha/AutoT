# AT Phase 26: Charging Case

**Status: design document, not built.** No physical case, PCB, or battery
exists. This document states the case's real requirements and the design
options it should be evaluated against, grounded in real reference products
already cited in `hardware/battery-thermal-engineering.md`.

## Why the case matters more than "just a box with a battery"

Given Phase 25's finding that earbud-shell battery capacity is capped
around 50-60mAh (AirPods Pro 2, Timekettle M3/W4 - real shipped products,
see the battery/thermal doc), and Phase 22's still-unresolved compute-power
gap (no known chip sits in the power/compute band AT's Whisper-class
workload needs), the case is not a secondary accessory - for a workload
this compute-heavy, it may need to be load-bearing for the product's
usability, not just recharging convenience between uses.

## Direct reference: Timekettle's case-assisted runtime model

Timekettle's M3 (same category product, offline translation earbuds) rates
7.5h of earbud-only use but 25h "with the case" - i.e., the case is
expected to recharge the earbuds multiple times over a single day's use,
not simply top them up overnight
([Timekettle M3 spec](https://www.timekettle.co/products/m3-travel-translator-earbuds)).
Its case capacity (400mAh) is 8x a single earbud's 50mAh. AT should plan
around this same case-assisted-runtime model rather than assuming
earbud-only battery life needs to cover a full day unaided - especially
relevant given AT's per-utterance compute cost (measured 38-44s on a
workstation CPU per Phase 9, not yet measured on any embedded target) is
almost certainly higher energy-per-utterance than Timekettle's workload,
making frequent case recharging even more likely to be load-bearing for AT
than for a lighter-weight competitor product.

## Requirements

- **Battery capacity**: sized to recharge both earbuds multiple times per
  day, following the Timekettle case-to-earbud capacity ratio (~8x) as a
  starting point, not a final number - AirPods Pro 2's 523mAh case is a
  second, consistent reference point in a similar range. A real number
  requires Phase 22's still-missing measured per-utterance energy cost on
  actual target silicon; sizing the case before that exists would be
  guessing, same objection as sizing the earbud battery.
- **USB-C charging** for the case itself - matches Timekettle (1.5-2h
  empty-to-full) and is the near-universal standard for this product class;
  no reason to deviate.
- **Pairing/setup role**: the master spec's mobile app (Phase 18, currently
  `apps/mobile-app-architecture.md` design doc only) needs an initial
  pairing flow. Whether that flow goes earbud-direct or case-mediated is an
  open design choice, not decided here - case-mediated pairing (case has
  its own BT radio, brokers first-time setup) is common in this product
  category but adds a case-side BT chip and firmware surface this project
  has not designed. Recorded here as an open decision, not a default.
- **OTA/firmware staging**: if the case has its own compute/storage, it
  could stage firmware or model downloads (Phase 29) while earbuds are
  docked, transferring only the final verified package to the earbud over
  a short-range link rather than requiring the earbud radio to sustain a
  slow phone-tethered download itself. This is a plausible architecture,
  not a committed one - it depends entirely on whether the case ends up
  with its own SoC (see below), which is undecided.
- **Physical**: must accommodate whatever earbud shell Phase 25 eventually
  designs - genuinely blocked on Phase 25, which is itself blocked on
  Phase 12/22's unresolved SoC selection.

## Open design question this document does not resolve

Should the case carry its own compute (a small MCU/BT SoC purely for
charging management + pairing brokering, vs. a more capable chip that
offloads part of the translation workload from the earbud into the case
while docked/nearby)? The former is safe, well-precedented (every
reference product above does at least this much). The latter is more
speculative, would meaningfully change Phase 24's architecture (the
case would become a second compute node, not just a battery), and is not
assumed or designed here - flagged as a question for after Phase 22's SoC
gap is resolved, since it only matters once real compute/power numbers for
the earbud-alone case are known and shown to fall short.

## What's actually proven vs. what's designed on paper

| Claim | Status |
|---|---|
| Case-assisted runtime is the right model to design around (not earbud-only battery life) | Reasoned from real, cited competitor data (Timekettle) - a real product-category precedent, not invented |
| A specific case battery capacity (mAh) for AT | **Not established** - depends on Phase 22's still-missing per-utterance energy measurement on real target silicon |
| Case-mediated pairing / OTA staging architecture | Named as an open option with real precedent in the category, not designed or committed |
| Whether the case needs its own compute beyond charging/BT management | **Undecided** - explicitly flagged as blocked on Phase 22's SoC gap, not resolved here |
