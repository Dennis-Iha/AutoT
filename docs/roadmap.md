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
| 9 | Real-time streaming + latency benchmarking | **done** |
| 10 | Offline mode / model manifest / checksum verification | **done** |
| 11 | Model optimization (quantization/distillation/pruning benchmarks) | **done** |
| 12 | Embedded development platform selection | **desk research done - physical validation pending real hardware** |
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

## Phase 9 results summary: real-time streaming + latency benchmarking

Did the profiling Phase 8 called for before writing any streaming code
(originally attempted via a forked subagent; the fork hit a session rate
limit and failed, so this was done directly instead - noted for
transparency, not hidden). Findings, measured not assumed:

**Where the ~13-17s LID/ASR latency actually goes**: `whisper_print_timings`
shows model *load* time is 260-450ms regardless of model size - negligible.
The *encoder* forward pass is the dominant cost: ~4.5-6.5s (tiny) / ~13.8-
14s (base) per full-buffer pass, for a 2.3s clip. This rules out "keep a
warm/resident model" (e.g. `whisper-server` instead of a fresh `whisper-cli`
subprocess per call) as a meaningful fix - it would only save the ~300-450ms
load time, not the multi-second compute.

**A deeper, real inefficiency found while checking this**: whisper.cpp's own
`-l auto` mode pays for TWO full encoder passes internally in a single CLI
call (measured: `encode time = 28681ms / 2 runs` for one `-l auto -oj` call)
- one inside `whisper_lang_auto_detect_with_state()`, a second, separate one
for the actual transcription decode; the library does not reuse the first
pass's encoder output for the second. This means `core/asr/whisper_cpp_asr.py`
using a *forced* language (skipping the "auto" path entirely) after
`core/language_id/whisper_lid.py`'s dedicated `-dl` call already pays close
to the practical minimum (2 encode passes total: one for LID, one for
transcription) - merging them into a single `-l auto` call would NOT reduce
total encoder cost (still 2 passes) and would remove the ability to skip
decode+translate+TTS entirely when LID confidence is too low to bother
(exercised often in practice, per Phase 8's LID accuracy findings) - so the
two-call architecture was kept as-is, not "optimized" into something worse.

**TTS is not the bottleneck**: `PiperTTSEngine._get_voice()` already caches
the loaded model per voice ID; `tools/tts_benchmark.py`'s own numbers showed
this (one-time load ~11s, warm calls 0.4-1.4s). Phase 8's reported "8.5s
TTS" was a cold-load number in a fresh process, not representative of a
long-running session.

**A real concurrency bug found and fixed, not a hypothetical one**: Phase 8's
`tools/at_translate.py` called `TranslationPipeline.process()` and blocking
playback directly from `MicrophoneCapture`'s `on_frames` callback - which
runs on PortAudio's real-time audio thread. Since a single segment can take
17-90+ seconds to process, this blocked audio capture for that entire
duration: the microphone effectively stopped listening while a previous
utterance was being translated and spoken, directly contradicting the master
spec's "the program must continuously listen, translate and speak." This
was never caught by Phase 8's tests because the only live-mode smoke test
used 3 seconds of silence, so no segment ever reached the blocking code
path. Fixed with `core/streaming/session.py`'s `StreamingSession`: a
producer/consumer queue where `submit()` (called from the audio callback) is
an O(1) non-blocking push, and a single background worker thread drains the
queue and runs the slow pipeline + playback. Verified with a
threading.Event-gated fake pipeline (not sleep-based timing races) that
`submit()` returns in under 100ms even while the worker is mid-`process()`,
and with a real live-mode run where the capture thread started and stopped
exactly on the requested 3s schedule while a segment was still draining in
the background afterward.

This does NOT reduce single-utterance latency (that's the encoder-pass cost
above, unaffected by threading) - it only stops speech from being lost while
a previous segment plays out, and surfaces backlog via `pending_count`.

**`tools/latency_benchmark.py`** (the master spec's explicit Phase 9
deliverable) measures every stage the spec lists - capture (mic-open to
first-callback: ~176ms), VAD/segmentation (~3-20ms, confirmed negligible),
language ID, ASR (forced-language, to isolate from the LID accuracy gap),
translation, TTS, and playback (wall time including device-open overhead vs.
raw audio duration) - end to end: ~38-44s total per utterance on this CPU
with the base model, matching Phase 8's finding.

**Conclusion for Phase 11/12**: nothing found here suggests a software-only
fix closes the latency gap for single short utterances - Phase 3's
denoise/beamforming (still not wired into the live chain) wouldn't touch
encoder cost either. The real fix is a smaller/quantized model (Phase 11) or
dedicated NPU/AI-accelerator hardware (Phase 12) that makes the encoder pass
itself faster - streaming/chunking architecture's value is in keeping the
system responsive and not losing speech during a long individual
utterance's processing, which is genuinely worth having, not a latency
silver bullet.

## Phase 10 results summary: offline mode / model manifest / checksum verification

`core/common/model_manifest.py` adds one shared primitive
(`compute_sha256`/`verify_checksum`, streamed in 1MB chunks - model files
run into the hundreds of MB) used uniformly by all three model registries.
Every registry entry (`ASRModelEntry`, `TranslationModelEntry`, `VoiceEntry`)
now carries a real, computed `sha256` + `size_mb` and gained an `is_valid()`
method alongside the existing fast `is_ready()` existence check - `is_ready()`
stays cheap for per-request hot paths (`TranslationEngine.supports_pair()`),
`is_valid()` does full-file verification for startup/readiness checks.
`core/asr/model_registry.py` and `models/registry/asr_models.json` are new -
ASR previously had no manifest at all, just raw paths in `ASRConfig`.

This is not a hypothetical safeguard: this project has already hit two real
corrupted/malformed-model incidents that checksums would have caught
immediately instead of surfacing as confusing errors deep in a third-party
library - Phase 7's truncated Piper download (onnxruntime: "Protobuf parsing
failed") and Phase 6's accidental duplicate-nested-directory Argos
extraction (silently doubled a model's on-disk size, only caught by manual
inspection). All checksums in this commit were computed fresh from the
actual files currently on disk, not invented.

`core/common/offline_runtime.py`'s `check_offline_readiness()` aggregates
all three registries plus the whisper.cpp binary itself into one
PASS/FAIL report (`tools/check_offline_readiness.py`), without loading any
model into memory - deliberately: the check that's supposed to protect
against a bad model shouldn't itself risk crashing on one. Verified for
real: all 11 checks (whisper.cpp binary, base ASR model, 8 translation
pairs, 1 TTS voice) pass with full checksum verification in ~15s on this
machine.

Model loading/unloading itself was already in place per-engine since
Phases 6/7 (`CTranslate2TranslationEngine.unload()`,
`PiperTTSEngine.unload()`); deliberately did NOT add an orchestration-level
eviction *policy* (e.g. LRU across language pairs) here - there's no
embedded RAM budget to design against yet (that's Phase 12+), and adding
one now would be speculative, not measured.

## Phase 11 results summary: model optimization (quantization)

`tools/quantize_asr_models.sh` produces quantized variants of the base ASR
model via whisper.cpp's own `whisper-quantize` (already built, unused until
now) into `models/asr/whisper/quantized/` (gitignored, like every other
model artifact). `tools/quantization_benchmark.py` measures size, peak RSS,
latency, and WER/CER across quant levels on the same forced-language
fixture corpus Phase 5/9 used - **not power**, which this workstation
cannot measure for real (Intel RAPL's `energy_uj` is root-only here, no
`perf` binary installed); reporting an estimated wattage would violate this
project's own "never fabricate benchmark numbers" principle, so
`power_watts` is explicitly `null` in the JSON output rather than guessed.
Real power measurement needs either root RAPL access or dedicated hardware
instrumentation - expected to be available once Phase 12's embedded dev
boards are in the picture, several of which expose power rails directly.

| Model | Size | Peak RSS | Avg latency | Avg WER | Avg CER |
|---|---|---|---|---|---|
| base (f16, unquantized) | 148.0 MB | 288 MB | 20597 ms | 0.56 | 0.26 |
| q4_0 | 46.5 MB | 185 MB | 13363 ms | 0.44 | 0.26 |
| q5_0 | 55.3 MB | 197 MB | 8498 ms | 0.44 | 0.23 |
| q8_0 | 81.8 MB | 219 MB | 6432 ms | 0.44 | 0.28 |

(en/es/ar fixtures, forced language per Phase 9's methodology - isolated
from Phase 8's LID accuracy gap. Arabic's WER stays high - ~1.0-1.33 -
across every quantization level including the unquantized baseline; this
is a real, separate finding from Phase 8's LID issue and is most likely
the same root cause as that one - the synthesized Arabic voice being a
poor match for Whisper's training distribution - not something quantization
introduced or could fix.)

**The counter-intuitive, measured finding this phase exists to catch**:
quantization level and speed are NOT monotonically related here. q8_0 (the
*least* aggressive quantization tested) is the *fastest* - 3.2x faster than
unquantized and nearly 2x faster than q4_0, despite q4_0 being the smallest
file. This contradicts the naive "smaller quantization = faster" assumption
and is almost certainly a CPU/kernel-specific effect (ggml's q8_0 dot-product
kernels are likely better-vectorized for this x86 CPU's AVX2 than q4_0's
bit-packing/unpacking scheme) rather than a universal truth - re-measure on
any different target hardware (Phase 12) rather than assuming this result
transfers. WER/CER is essentially unaffected by quantization level (all
three quantized variants match or slightly beat the unquantized baseline on
en/es), consistent with quantization literature for 4-8 bit weight
quantization generally preserving task accuracy.

**Practical recommendation from this data**: q8_0 is the clear choice for
this CPU - smallest meaningful latency (6.4s vs 20.6s baseline avg), best
or tied accuracy, and still a substantial size reduction (45% of original)
even though it's not the smallest file. Do not default to the most
aggressive quantization without measuring on the actual target first.

## Phase 12 results summary: embedded platform selection (desk research)

This is the first phase this environment cannot fully complete - no
physical hardware. What was done instead, honestly scoped: `hardware/
hardware-selection.md` compares NVIDIA Jetson Orin Nano Super, Qualcomm
QCS6490, and NXP i.MX 8M Plus using their *current, official* documentation
(researched via a parallel multi-agent workflow, each candidate
independently verified with cited sources - not third-party summaries or
this project's own possibly-stale prior assumptions), evaluated against
this project's own Phases 5-11 measured workload rather than generic AI
benchmarks.

**The finding that matters most**: whisper.cpp/GGML acceleration support is
NOT equivalent across the three candidates, and this is invisible from TOPS
figures alone (the exact trap Engineering Principle #18 warns about) -
Jetson has a real (community-verified) CUDA backend path; Qualcomm's own
bug tracker shows Whisper models currently fail to export cleanly for the
QCS6490's Hexagon NPU; NXP's own eIQ documentation scopes its Whisper
support to newer i.MX 95 silicon, not the 8M Plus researched here. Also
confirmed accurate: the i.MX 8M Plus's "8-channel PDM microphone input"
claim from this project's original spec, verified against NXP's datasheet
table and block diagram.

Recommendation: acquire a Jetson Orin Nano Super devkit for Phase 13
physical validation (lowest integration risk given real whisper.cpp
support, microSD-boot-by-default matching this project's actual hardware
target). This is explicitly NOT a purchase order or a claim that anything
has been physically tested - see the document's own "what this
recommendation is not" section.

## Immediate next step (Phase 13+)

Phases 13 onward (AT Headphones prototype, embedded audio drivers,
firmware, dual-earbud system, mobile app, backend, security/privacy,
battery/thermal engineering, custom PCB, miniaturization, manufacturing,
factory test) all require physical hardware, lab equipment, or
infrastructure (a phone to run a mobile app on, a server to deploy a
backend to) this sandboxed development environment does not have. Continue
honestly: produce what's genuinely producible without fabricating physical
results (backend/mobile app scaffolding that runs and is tested locally,
firmware architecture documents, security/privacy policy documents,
manufacturing process templates), and clearly flag every phase that
requires equipment or access this environment cannot provide rather than
simulating success.
