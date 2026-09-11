# AT Phase 12: Embedded Development Platform Selection

**Status: desk research, pending physical validation.** This document
compares three candidate embedded AI SoCs against AT's actual measured
software workload (Phases 5-11). It was compiled by researching each
vendor's *current, official* documentation (cited inline; claims that could
not be verified from a primary source are explicitly marked
**unverified**), not by benchmarking physical hardware — none is available
in this development environment. Per this project's own Engineering
Principles (#16-18): do not buy hardware in quantity or commit to a chip
before physically benchmarking the actual workload on it, and never assume
a high TOPS number implies good speech-translation performance. Treat every
number here as a starting point for physical evaluation, not a purchase
decision.

## Why these three

Named in AT's original master spec as reference/development platforms, and
representative of three different approaches: a GPU-based dev-kit-class SoM
(Jetson), a mobile-class SoC built for exactly this kind of embedded
audio/AI product (QCS6490), and a lower-power industrial NPU part (i.MX 8M
Plus). Two MCU-class parts named in the original spec (Nordic nRF54L15:
1.5MB NVM / 256KB RAM; Ambiq Apollo510) are not compared in the matrix below
— they're correctly ruled out already as too small for the full translation
stack, not candidates needing re-evaluation.

## Our actual workload, measured (not estimated)

From Phases 5-11's real benchmarks on this project's reference workstation
CPU (see `docs/roadmap.md` for full detail):

- **ASR (whisper.cpp, base model, forced language)**: encoder-pass-dominated,
  6.4s avg (q8_0 quantized) to 20.6s avg (unquantized f16) per ~2s utterance.
  Peak RSS 185-288MB depending on quantization.
- **Translation (CTranslate2)**: 270ms-1.2s warm latency per utterance,
  82-315MB per loaded language-pair model.
- **TTS (Piper)**: 0.4-1.4s warm latency, ~63MB model.
- **Full pipeline**: ~38-44s total per utterance end-to-end on this
  workstation CPU with unoptimized settings - dominated by the ASR/LID
  encoder passes specifically, not translation or TTS (Phase 9's finding).

This means the deciding factor for any embedded candidate is **real
transformer-encoder throughput for a ~74M-parameter (base) or larger Whisper
model**, not raw advertised TOPS - Phase 11 already found quantization level
and speed aren't simply related, so TOPS-per-dollar comparisons across these
three chips would be premature without physically running the same encoder
pass on each.

## Comparison matrix

| | Jetson Orin Nano Super (8GB devkit) | Qualcomm QCS6490 | NXP i.MX 8M Plus |
|---|---|---|---|
| AI compute | 67 INT8 TOPS sparse / 33 dense (8GB, Super mode) | ~12 TOPS (Hexagon; precision unstated) | 2.3 TOPS (NPU) |
| CPU | 6x Cortex-A78AE, up to 1.7GHz | 4x Cortex-A78 + 4x Cortex-A55 (Kryo 670), up to 2.7GHz | 4x Cortex-A53 up to 1.6-1.8GHz + Cortex-M7 800MHz + HiFi4 DSP |
| GPU | Ampere, 1024 CUDA + 32 Tensor cores | Adreno 643 | (none dedicated) |
| RAM | 8GB LPDDR5, 128-bit, 102GB/s (Super) | LPDDR5 3200MHz or LPDDR4X, "up to 16GB" | LPDDR4-4000, capacity not officially stated (EVK ships 6GB) |
| Storage | microSD (devkit default boot) + 2x M.2 NVMe (carrier board; SOM itself has none) | UFS 2.x/3.1, eMMC 5.1, SD 3.0, NVMe (2-lane PCIe) | eMMC 5.1, SD/SDIO 3.0 x3, raw NAND, SPI NOR, PCIe Gen3 x1 |
| Audio/mic | I2S/PCM + dedicated Audio Processing Engine w/ PDM in/out; exact channel count **unverified** | 5x MI2S + 1x 8-channel MI2S, 2x I2S, SoundWire, **3 dedicated DMIC ports** in a low-power island | **8-channel PDM mic input** (confirmed - corrects nothing, original spec claim verified accurate), 6x SAI, SPDIF |
| Bluetooth | Not on-die - M.2 Key-E slot, devkit ships with a Wi-Fi 5/BT 5.x card (community-identified, not a formal NVIDIA spec) | Not on-die - WCN6750/6856 companion, BT 5.2 | Not on-die - EVK pairs an AzureWave module (BT 5.1) |
| Power | 7-25W (Super mode profiles) | Only a partial figure published (6.9W CPU-only Dhrystone max); full SoC TDP **unverified**, not publicly accessible | No single TDP; per-rail app note only (e.g. ~1.06W idle-DDR); workload-dependent |
| OS | JetPack 6.2 = L4T 36.4.3, Ubuntu 22.04, kernel 5.15. **No Android support** (forum statement, not formal) | Linux (Yocto + Ubuntu 24.04 documented), Android, Windows 11 IoT Enterprise | Linux (Yocto/meta-imx), Android (GA through Android 14), Windows 10 IoT, FreeRTOS |
| whisper.cpp/GGML support | **Official CUDA backend exists in whisper.cpp itself**; Jetson/Orin use is community-verified via GitHub issues, not NVIDIA-certified | **Not production-ready**: community ggml-hexagon/ggml-qnn ports only; Qualcomm's own ai-hub-models repo (issue #281) reports Whisper models currently fail to export/quantize cleanly for this NPU | **No official support found**. eIQ's Whisper entries are explicitly scoped to the newer i.MX 95 "Neutron" NPU, not this chip's VeriSilicon NPU - an easy mistake to make from the docs alone |
| Lifecycle | Commercial modules through Jan 2032; **NVIDIA states no lifecycle commitment for the devkit itself** (prototyping only) | Product Longevity Program: launched Jul 2021, committed through **Jul 2036** (15yr), subject to annual MOQ terms | Formal Longevity Program exists (10-15yr baseline) but this specific part **did not appear in the visible program table** during this research - unverified for this SKU; third parties (Toradex, Variscite) informally cite 2033-2036 |
| Dev board price | ~$249 (Super devkit bundle); bare SOM ~$199-299 at 1k units (pre-Super pricing) | Dragonwing RB3 Gen 2 (Thundercomm): Core Kit $439, Vision Kit $639 | i.MX 8M Plus EVK: NXP publishes no price; ~$683-700 via DigiKey (not NXP-direct) |

## The one finding that should drive Phase 12's next step

**AI accelerator support for our specific workload (Whisper-family encoder
inference) is not equivalent across these three**, and this is not visible
from TOPS numbers alone - exactly the trap Engineering Principle #18 warns
against:

- **Jetson**: real path exists today (CUDA backend, community-run on Orin).
  Lowest integration risk for proving the workload fast.
- **QCS6490**: the vendor's own Hexagon NPU tooling does not yet cleanly
  support Whisper-class models (their own bug tracker says so) - CPU-only
  fallback would be the realistic near-term path, which changes the whole
  comparison (12 TOPS of NPU capability may be largely unusable for us
  right now).
- **i.MX 8M Plus**: no working path found at all for this specific chip;
  its own vendor's ML guide's Whisper support targets different, newer
  silicon. At 2.3 TOPS it was already the weakest compute candidate; this
  makes it the weakest software-readiness candidate too.

## Recommendation

Start Phase 12/13 physical validation with the **Jetson Orin Nano Super
devkit**: it has a real (if community-verified) whisper.cpp acceleration
path, boots from microSD by default (relevant to this project's actual
hardware target - see the project's hardware-target notes: a microSD-booted
system on the eventual headphone hardware), and its power range (7-25W) is
configurable for controlled benchmarking. Use it to get a first real
physical measurement of encoder latency with GPU acceleration, replacing
this document's estimates with actual numbers - then revisit whether
QCS6490 (once/if its NPU tooling matures for Whisper) or a different part
entirely is the better production fit, since none of these three is
remotely close to earbud form factor or power budget yet regardless (that's
Phases 24-25's job, far downstream).

**What this recommendation is not**: a purchase order, a claim that Jetson
GPU-class power draw (7-25W) is acceptable for a battery-powered headphone
(it clearly is not - that's exactly why Phase 12 is a *development*
platform, shrunk later), or a claim that whisper.cpp's CUDA backend has been
tested by this project - it hasn't, because there is no Jetson hardware in
this environment. The honest next action is acquiring one physical unit and
re-running `tools/asr_benchmark.py`/`tools/quantization_benchmark.py`
against it, not proceeding further on paper.

## Open items for physical validation (not resolved by desk research)

- Real encoder latency/RAM/power on each board, using this project's actual
  benchmark scripts (`tools/asr_benchmark.py`, `tools/quantization_benchmark.py`,
  `tools/latency_benchmark.py`) - not synthetic AI benchmarks.
- Real Bluetooth audio (A2DP sink) stack maturity on Linux for whichever
  companion BT chip ships with the board - all three candidates need a
  companion chip, none have it on-die, and this project's hardware target
  explicitly requires solid Bluetooth media playback alongside translation.
- Full-system power draw under our actual workload (none of the three
  vendors publish this cleanly; Phase 11 already found this project's own
  workstation can't measure real power either without root RAPL access -
  expect to need either vendor eval tools or an external power meter).
- Audio interface channel counts/PDM mic array wiring in practice, not just
  datasheet claims.
