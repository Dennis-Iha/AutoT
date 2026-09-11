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
| 4 | Language identification | **done** |
| 5 | ASR (offline multilingual speech recognition) | **done** |
| 6 | Translation engine | **done** |
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

## Phase 4/5 results summary: language ID + ASR (whisper.cpp)

Built `third_party/whisper.cpp` from source (`tools/setup_whisper_cpp.sh`,
gitignored - vendored, not repo source) and wrapped its CLI via subprocess
in `core/asr/whisper_cpp_runner.py`, verified against whisper.cpp's own
source (not guessed): `-dl` runs the encoder-only language-detection path
and exits before decoding; `-oj -l auto` gives full transcription + detected
language as JSON. `core/language_id/whisper_lid.py` and
`core/asr/whisper_cpp_asr.py` both wrap this one runner, since a Whisper
model computes LID and ASR from the same encoder pass - not two models.

To get real per-language test audio without a natural-speech corpus,
`tests/fixtures/speech/` was generated with espeak-ng (built from source, no
sudo needed - CMake-based build) for all 9 v1 languages, one controlled
sentence ("Where is the train station?") per language - documented as
synthesized, not natural, speech in the fixture manifest.

Measured (tiny/base multilingual models, `tools/asr_benchmark.py` /
`tools/language_id_benchmark.py`):
- English fixture: exact-match transcription, LID confidence ~0.93.
- All 9 languages: valid LID/ASR output shape, tested end-to-end.
- **Base model is far from real-time on this CPU**: up to ~90s to
  transcribe a ~2s clip for some languages with `-l auto`. This workstation
  proves correctness, not embedded feasibility - exactly why Phase 11
  (quantization) and Phase 12 (embedded/NPU hardware) exist.

## Phase 6 results summary: translation (CTranslate2)

Used `.argosmodel` packages from the Argos Translate open model index
directly via lightweight `ctranslate2` + tokenizer libraries
(`tools/setup_translation_models.sh`), NOT the `argostranslate` Python
package itself - it transitively requires PyTorch (via `stanza`, used only
for paragraph->sentence splitting, which AT doesn't need since VAD already
segments utterances). Verified two different tokenizer schemes are in use
across package versions (not assumed uniform): most languages ship
SentencePiece; Spanish's package uses the older subword-nmt BPE format with
Moses tokenization - `core/translation/ctranslate2_translator.py` auto-
detects and handles both.

All 8 non-English v1 languages translate correctly to English (`tools/
translation_benchmark.py`): 270ms-1.2s warm latency, 82-315MB per model.
Caught and fixed a real bug during development: `sentencepiece`
0.2.2's `decode()` on a list of piece-strings inconsistently dropped only
*some* word-boundary markers; switched to the standard manual
concatenate-then-replace-marker detokenization, verified correct across all
7 SentencePiece-based languages (regression-tested in
`tests/translation/test_ctranslate2_translator.py`).

## Immediate next step (Phase 7)

Implement offline English text-to-speech. Same pattern: `base.py` ABC
(`synthesize()`, `synthesize_stream()`) first, then a concrete backend.
Candidate: Piper (ONNX-based, no PyTorch, small per-voice models) - verify
this before committing, per Engineering Principle #1.
