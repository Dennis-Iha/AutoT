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
| 4 | Language identification | **done, but accuracy gap found - see Phase 8 notes** |
| 5 | ASR (offline multilingual speech recognition) | **done** |
| 6 | Translation engine | **done** |
| 7 | Text-to-speech | **done** |
| 8 | Complete software pipeline (`at-translate` CLI) | **done** |
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
- ASR **with forced language** (`transcribe(audio, language=lang)`,
  bypassing auto-detection): exact-match transcription for English; all 9
  languages produce valid, non-empty output.
- **Base model is far from real-time on this CPU**: up to ~90s to
  transcribe a ~2s clip for some languages with `-l auto`. This workstation
  proves correctness, not embedded feasibility - exactly why Phase 11
  (quantization) and Phase 12 (embedded/NPU hardware) exist.

**Correction made during Phase 8, not swept under the rug**: the original
version of this section claimed "all 9 languages: valid LID/ASR output
shape, tested end-to-end" - true about shape, but `tools/
language_id_benchmark.py` was never actually run and checked against all 9
languages at the time, only spot-checked for English. Running it for real
during Phase 8 found only **2/9 (22%) correct language detection** on the
base model. Investigated rather than assumed: looping the clip 4x to rule
out "too short" didn't help, and testing the larger "small" model (487MB)
only reached 3/9 - *and* produced confidently WRONG answers for zh/hi/bn
(0.79-0.85 confidence, above the 0.5 fallback threshold, so the pipeline's
safety net wouldn't have caught them). This points to the espeak-ng
SYNTHESIZED voices for several languages being a poor proxy for Whisper's
language classifier specifically (as opposed to ASR-with-forced-language or
TTS round-trip, both of which validate fine on synthesized audio) - not a
model-size problem fixable by Phase 11 quantization work. Real LID accuracy
validation needs natural human speech or a licensed multilingual speech
corpus, neither available in this environment; tracked as a real, open gap
for Phase 30, not claimed as solved. es/en (and en/ru on the small model)
are the languages currently confirmed reliably detected on these fixtures -
Phase 8's pipeline tests exercise those, plus the low-confidence-fallback
path using ar (which the pipeline correctly refuses to mistranslate).

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

## Phase 7 results summary: TTS (Piper)

Piper (`tools/setup_tts_models.sh` downloads ONNX voice models from
`rhasspy/piper-voices`) needs only `onnxruntime` - no PyTorch, consistent
with every other engine chosen so far. Piper bundles its own espeak-ng
phonemization data, so it doesn't depend on the espeak-ng binary built
earlier for test fixtures.

Caught a real bug during setup, not assumed away: a parallel download
silently produced a truncated 27MB file for a 63MB voice model:
onnxruntime failed with an opaque "Protobuf parsing failed" rather than a
clear incomplete-download error. `tools/setup_tts_models.sh` now verifies
downloaded size against the server's Content-Length before accepting a
file - a general lesson applied only to this script so far; the earlier
whisper.cpp/Argos setup scripts got lucky, not verified-safe, and should
get the same check if they're touched again.

Measured (`tools/tts_benchmark.py`): 0.38-0.53 real-time factor after
model load (i.e. synthesis is 2-3x FASTER than real-time on this CPU,
unlike whisper.cpp's ASR which is far slower than real-time - a useful
asymmetry for Phase 9's streaming latency budget). The strongest quality
signal isn't a synthetic metric: a full TTS->ASR round trip (synthesize
with Piper, transcribe back with whisper.cpp) gives an exact match
(WER=0.0) on all 3 test sentences, evidence the audio is genuinely
intelligible speech, not just non-silent output.

## Phase 8 results summary: complete pipeline (`at-translate`)

`core/orchestration/pipeline.py`'s `TranslationPipeline` wires language ID
-> ASR -> translation -> TTS behind one `process(audio, sample_rate_hz)`
call, with an explicit `PipelineStatus` for each way a segment can
legitimately not produce speech (`LOW_CONFIDENCE`, `UNSUPPORTED_LANGUAGE`,
`EMPTY_TRANSCRIPTION`, `ERROR`) rather than silently swallowing failures or
crashing. `core/audio/playback.py` (new - only capture existed before) plus
`tools/at_translate.py` wire it to a real microphone/speaker or a WAV
file (`--input-file`, useful for reproducible testing and batch use without
live hardware). Denoise (Phase 3) is NOT yet in this chain - deferred, see
below.

**The important finding from building this phase**: running
`tools/language_id_benchmark.py` for real during Phase 8 (it existed since
Phase 4 but had never actually been executed and checked against all 9
languages - a real verification gap, not hidden here) found only 2/9 (22%)
correct language detection on the base model against this project's
espeak-ng-synthesized fixtures. Investigated, not assumed: neither a 4x
longer clip nor the larger "small" model (487MB) fixed it - small reached
3/9 but gave confidently WRONG answers (0.79-0.85, above the 0.5 fallback
threshold) for 3 languages, which is a more dangerous failure mode than
base's mostly-low-confidence wrong guesses. This points to the synthesized
voices being a poor proxy for Whisper's language *classifier* specifically
(ASR-with-forced-language and TTS round-trip both validate fine on the same
audio), not a model-size problem. Real LID validation needs natural human
speech or a licensed corpus - neither available here - so this is tracked
as a genuine open gap for Phase 30, not solved.

Given that, `core/orchestration/pipeline.py`'s low-confidence fallback
(required by the master spec: "do not immediately translate if confidence
is too low") is not just a nice-to-have - it is the thing currently
protecting the pipeline from confidently mistranslating from a wrong
language guess on 6-7 of 9 languages. `tests/orchestration/test_pipeline_live.py`
tests both the happy path (es, reliably detected) and this fallback path
(ar, reliably NOT detected) with real models, rather than assuming uniform
9-language accuracy the way earlier Phase 4 documentation incorrectly did
(now corrected here and in docs/architecture.md).

Measured end-to-end (`tools/at_translate.py --input-file`, base ASR model):
a Spanish 2-second clip produced correct English speech output in ~41s
total (language_id=13s, asr=17s, translation=2.4s, tts=8.5s) - consistent
with Phase 5's finding that the base model is far from real-time on this
CPU; Phase 11 (quantization) and Phase 12 (embedded/NPU hardware) remain
the path to fixing that, not this phase.

## Immediate next step (Phase 9)

Real-time streaming: process audio in chunks as it arrives rather than
waiting for a complete VAD segment before starting ASR, and pipe partial
ASR hypotheses into incremental translation/TTS. Given Phase 8's measured
~41s total latency for one short utterance (dominated by ASR), prioritize
investigating why language_id + asr together cost ~30s before assuming
streaming alone fixes user-perceived latency - profile whether a smaller
model or reused warm state closes more of the gap than chunking does.
Also revisit whether Phase 3's denoise/beamforming should sit in this live
chain (currently bypassed) now that there's an end-to-end pipeline to
measure its real effect on, rather than only the synthetic benchmarks from
Phase 3.
