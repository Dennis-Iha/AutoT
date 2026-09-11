# AT Development Roadmap

High-level phase order (see the master engineering spec for full detail on
each phase's deliverables). Each phase is only started once the previous one
is implemented, tested, and documented — not designed on paper and assumed
to work.

| # | Phase | Status |
|---|---|---|
| 0 | Project foundation (repo, config, logging, metrics, CI, test framework) | **done** |
| 1 | Audio engine (mic capture, ring buffer, WAV I/O, diagnostics) | **done** |
| 2 | Voice activity detection (streaming VAD, speech segmenter) | **done** |
| 3 | Audio cleanup (noise suppression, echo cancellation, dereverberation, beamforming) | not started |
| 4 | Language identification | not started |
| 5 | ASR (offline multilingual speech recognition) | not started |
| 6 | Translation engine | not started |
| 7 | Text-to-speech | not started |
| 8 | Complete software pipeline (`at-translate` CLI) | not started |
| 9 | Real-time streaming + latency benchmarking | not started |
| 10 | Offline mode / model manifest / checksum verification | not started |
| 11 | Model optimization (quantization/distillation/pruning benchmarks) | not started |
| 12 | Embedded development platform selection | not started |
| 13 | AT Headphones prototype (first standalone physical product) | not started |
| 14 | Embedded audio (I2S/PDM drivers, HAL) | not started |
| 15 | Firmware (bootloader, secure boot, OTA) | not started |
| 16 | Dual-earbud system (master election, promotion, sync) | not started |
| 17 | AT Conversation Mode (two-direction translation) | not started |
| 18 | Mobile companion app | not started |
| 19 | Backend (auth, device registry, model/firmware registry, OTA) | not started |
| 20 | Security (secure boot, signed firmware, encrypted comms) | not started |
| 21 | Privacy controls and documentation | not started |
| 22 | Battery engineering | not started |
| 23 | Thermal engineering | not started |
| 24 | Custom PCB | not started |
| 25 | Earbud miniaturization | not started |
| 26 | Charging case | not started |
| 27 | Manufacturing (EVT/DVT/PVT plans) | not started |
| 28 | Automated factory test station | not started |
| 29 | OTA model update system | not started |
| 30 | Performance testing across all 9 languages/environments | not started |
| 31 | Product metrics dashboards | not started |
| 32 | Commercial product architecture | not started |
| 33 | Full documentation set | in progress (this file + architecture.md) |

## Immediate next step (Phase 3)

Implement noise suppression / echo cancellation / beamforming interfaces
under `core/denoise/` and `core/beamforming/`, following the same pattern
used in Phase 2 (`base.py` ABC + concrete backend + tests using synthetic
signals with known SNR so accuracy claims are measurable, not assumed).
Benchmark the effect on VAD false-positive rate using the tonal/noise test
cases already identified in `tests/vad/test_webrtc_vad.py`.
