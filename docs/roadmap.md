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
| 3 | Audio cleanup (noise suppression, echo cancellation, dereverberation, beamforming) | **done** |
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

## Phase 3 results summary

Implemented `core/denoise/{stft,noise_suppression,echo_cancellation,
dereverberation}.py` and `core/beamforming/{base,delay_sum}.py`, each with a
`base.py`-style ABC, a `Passthrough*` identity baseline, and a real
algorithm, all measured against synthetic signals with known ground truth
(not just "doesn't crash" tests) - see `tools/audio_cleanup_benchmark.py`
for the full numbers. Headline measurements:

- Noise suppression: ~6dB noise-floor reduction, ~72% speech energy retained
  (spectral subtraction, over-subtraction=4.0 to compensate the systematic
  underestimation bias of minimum-statistics noise tracking).
- Echo cancellation: ~29dB ERLE on a stationary synthetic echo path (NLMS,
  no double-talk protection).
- Dereverberation: ~10dB reverberant-tail-energy reduction (single-channel
  spectral technique, not full WPE - that needs real multi-mic hardware).
- Beamforming: ~8.5dB SNR improvement from correct delay-and-sum alignment
  vs. naive unaligned averaging (synthetic 2-channel only, no real array).

**Important negative result, not swept under the rug**: noise suppression
as currently tuned does NOT fix WebRtcVAD's false-positive-on-broadband-
noise behavior (`tools/audio_cleanup_benchmark.py`'s `vad_impact` section) -
pushing over-subtraction higher to try to defeat that synthetic case would
trade away real speech retention, which is the wrong tradeoff. Revisit VAD
noise-robustness with either a better VAD (e.g. a neural VAD) or the
segmenter's existing onset-ratio hysteresis, not by over-suppressing.

## Immediate next step (Phase 4)

Implement automatic language identification for the initial nine languages
(en/zh/hi/es/ar/fr/bn/pt/ru), returning `{language, confidence, timestamp}`
and an explicit low-confidence fallback path (per the master spec: "Do not
immediately translate if confidence is too low"). Follow the same pattern:
`base.py` ABC first, then a concrete backend, benchmarked per-language
rather than assumed to work uniformly.
