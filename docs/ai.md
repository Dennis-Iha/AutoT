# AT-CORE AI/ML Pipeline

This is the architecture reference for AT-CORE's AI/ML stack: what engine
runs at each stage, what model it loads, and what has actually been
measured about it versus what still needs re-verifying on real hardware or
real speech. `docs/architecture.md` covers the whole product (five layers,
hardware progression); `docs/commercial-product-architecture.md` covers
shippability and the per-component readiness matrix. This document is
narrower: it is only the software pipeline inside `core/`, one level more
detailed than either of those.

Every number below comes from `docs/roadmap.md`'s Phase 3-11/17/30 results
sections and from reading the source directly, cited in backticks. Where a
number was only ever measured on synthetic signals, synthesized speech, or
this project's development workstation, that is stated explicitly rather
than implied to generalize.

## Pipeline (single utterance)

```
Speech segment (mono int16 PCM, 16kHz)
  produced by core/vad/segmenter.py's SpeechSegmenter
        |
        v
+----------------------------+
| Beamforming (Phase 3)      |  core/beamforming/delay_sum.py: DelaySumBeamformer
| multi-channel -> mono      |  NOT called by TranslationPipeline.process() today -
+----------------------------+  built and tested, but not wired into the live chain.
        |
        v
+----------------------------+
| Denoise (Phase 3)          |  core/denoise/{noise_suppression,echo_cancellation,
| noise / echo / reverb      |  dereverberation}.py - same status: tested in
+----------------------------+  isolation, not yet called from the pipeline.
        |
        v
+----------------------------+
| Language identification    |  core/language_id/whisper_lid.py ->
|                             |  WhisperCppRunner.detect_language() (`-dl`, encoder-only)
+----------------------------+
        | confidence >= 0.65 (LOW_CONFIDENCE_THRESHOLD, core/language_id/base.py)?
        |   no  -> PipelineStatus.LOW_CONFIDENCE, stop, nothing spoken
        v  yes
   source_language == target_language?
        | no  -> translation_engine.supports_pair(source, target)?
        |          no  -> PipelineStatus.UNSUPPORTED_LANGUAGE, stop (ASR never runs)
        v          yes, or source == target
+----------------------------+
| ASR, forced to detected    |  core/asr/whisper_cpp_asr.py ->
| language                   |  WhisperCppRunner.transcribe() (`-l <lang> -oj`)
+----------------------------+
        | transcription empty? -> yes -> PipelineStatus.EMPTY_TRANSCRIPTION, stop
        v no
   source_language == target_language?
        | yes -> skip translation, speak the transcription as-is
        v no
+----------------------------+
| Translation                |  core/translation/ctranslate2_translator.py ->
|                             |  CTranslate2TranslationEngine (CTranslate2 + tokenizer)
+----------------------------+
        v
+----------------------------+
| Text-to-speech             |  core/tts/piper_tts.py -> PiperTTSEngine (Piper/ONNX)
+----------------------------+
        v
   PipelineStatus.OK, PipelineResult{transcription, translation, synthesis,
   stage_latencies_ms}
```

This is `core/orchestration/pipeline.py`'s `TranslationPipeline.process()`
read literally: it takes one already-segmented utterance and returns a
`PipelineResult` whose `status` is always one of `PipelineStatus.OK`,
`LOW_CONFIDENCE`, `UNSUPPORTED_LANGUAGE`, `EMPTY_TRANSCRIPTION`, or `ERROR`
(the last catches an exception from any stage and is returned rather than
raised, with the partial result and `stage_latencies_ms` collected so far
attached). `TranslationPipeline` does no audio I/O itself - segmentation,
capture and playback are the caller's job (`tools/at_translate.py`), which
is why it can be tested with fakes and with real models independently of
any audio backend. `core/orchestration/conversation.py`'s
`ConversationSession` reuses this unchanged for two-directional
translation: it holds two `TranslationPipeline` instances that share the
same underlying LID/ASR/translation/TTS engine objects and differ only in
`target_language`, and it requires the caller to say which side is
speaking rather than guessing - automatic speaker diarization is out of
scope and explicitly documented as such in the module's own docstring.

## Stage 1: Voice activity detection & segmentation

- **Engine**: `webrtcvad` (Google's WebRTC VAD, a small C extension) via
  `core/vad/webrtc_vad.py`'s `WebRtcVAD`. Frame-level only: classifies one
  fixed-size PCM frame (10/20/30ms at 8/16/32/48kHz) as speech or not, with
  an aggressiveness setting 0-3. No model file, sub-millisecond per frame.
- **Segmentation**: `core/vad/segmenter.py`'s `SpeechSegmenter` turns that
  frame stream into `SpeechSegment`s using onset/offset hysteresis (a
  sliding-window "ratio of voiced frames" collector, the same pattern the
  reference webrtcvad examples use): a segment starts once >90% of the last
  `min_speech_ms` (default 200ms) of frames are voiced, and ends once >90%
  of the last `hangover_ms` (default 300ms) are silent, or the segment hits
  `max_segment_ms` (default 20000ms) and is force-closed so a streaming
  pipeline never buffers unbounded audio waiting for silence.
- **Known limitation, tracked not hidden**: WebRTC VAD's accuracy on
  music/broadband non-speech noise is limited, and Phase 3's noise
  suppression does not fix this on its own - pushing the suppressor's
  over-subtraction higher to defeat that case trades away real speech
  retention (see Stage 2).
- **Status**: real, tested code, including the documented false-positive
  limitation; verified on real hardware for capture (`tools/mic_vad_demo.py`).

## Stage 2: Audio cleanup - denoise & beamforming (Phase 3)

Four independent, swappable components, each with a `Passthrough*` identity
baseline and a real algorithm behind a common ABC (`core/denoise/*.py`,
`core/beamforming/base.py`). **None of these are called from
`TranslationPipeline.process()` today** - they are built and benchmarked in
isolation (`tools/audio_cleanup_benchmark.py`) but not yet part of the live
`at-translate` chain.

| Component | Algorithm | Measured result | File |
|---|---|---|---|
| Noise suppression | Spectral subtraction (Boll 1979) with a causal running-minimum noise floor per frequency bin (simplified Martin 2001 minimum-statistics), over-subtraction factor 4.0 | ~6dB noise-floor reduction, ~72% in-band speech energy retained | `core/denoise/noise_suppression.py` |
| Echo cancellation | NLMS adaptive FIR filter (same family as WebRTC's AEC3), no double-talk protection | ~29dB ERLE on a stationary echo path | `core/denoise/echo_cancellation.py` |
| Dereverberation | Single-channel exponential-decay spectral-tail subtraction (Lebart/Habets-style), explicitly NOT full WPE - WPE needs multiple synchronized mics this project doesn't have | ~10dB reverberant-tail-energy reduction | `core/denoise/dereverberation.py` |
| Beamforming | Delay-and-sum: cross-correlation peak search for per-channel delay, then coherent averaging | ~8.5dB SNR gain vs. naive unaligned averaging | `core/beamforming/delay_sum.py` |

**All four numbers above are synthetic-signal measurements only** - known
ground-truth noise/echo/reverb/multi-channel signals constructed for the
benchmark, not real recordings. Beamforming in particular has never seen a
real microphone array (Phase 13+ hardware doesn't exist yet); the
cross-correlation delay estimator (`estimate_delay_samples`) is a plain
building block, not full GCC-PHAT. `core/denoise/stft.py` provides the
shared STFT/ISTFT (centered, weighted-overlap-add, periodic Hann window)
used by both spectral-domain components; it is a block/offline transform
(whole-buffer in, same-length buffer out), not yet the causal streaming
variant real-time use would eventually need.

- **Status**: engineering prototype (per `docs/commercial-product-architecture.md`'s
  readiness matrix) - real, tested code and real synthetic measurements,
  but neither validated against real acoustic conditions nor wired into
  the pipeline that actually runs today.

## Stage 3: Language identification

- **Engine**: `core/language_id/whisper_lid.py`'s `WhisperLanguageIdentifier`,
  a thin wrapper around `core/asr/whisper_cpp_runner.py`'s
  `WhisperCppRunner.detect_language()`, which shells out to whisper.cpp's
  CLI with `-dl` (encoder + language-detection head only, returns before
  any decoding). LID is not a separate model: a Whisper-family model
  produces both LID and transcription from the same encoder forward pass,
  so `core/asr/base.py` exposes `detect_language` on the ASR interface too
  and both modules share one runner rather than loading two models.
- **Confidence gate**: `core/language_id/base.py`'s
  `LOW_CONFIDENCE_THRESHOLD = 0.65` (raised from 0.5 - see below);
  `is_confident()` is what `TranslationPipeline` checks before doing
  anything else with a segment.
- **Measured accuracy, on this project's own espeak-ng-synthesized fixtures
  (`tests/fixtures/speech/`, one sentence per language, NOT natural
  speech)**: base multilingual model, **2/9 languages correctly
  detected**; the larger "small" model (487MB), **3/9** - a bigger model
  did not fix this, which points at the synthesized voices being a poor
  match for Whisper's language classifier specifically, not a model-size
  problem (ASR-with-forced-language and TTS round-trip both validate fine
  on the same audio).
- **Worse finding (Phase 30), found and then fixed, not just a
  restatement of the accuracy gap**: this is a separate, later run from the
  small-model finding above, on the **base** model (`ggml-base.bin`) via
  the full-pipeline sweep (`tools/performance_sweep.py`). At the original
  0.5 threshold, 3 of the sweep's 5 nominally "ok" rows were *confidently*
  wrong - Bengali, Hindi, and Mandarin fixtures were misdetected as English
  at 0.51-0.59 confidence (a different, lower confidence range than the
  small model's own confident-wrong-answer finding above at 0.79-0.85 for
  the same three languages - different model, different confidence
  numbers, same failure shape). Because that cleared the old confidence
  gate, `source_language == target_language` became true, translation was
  skipped by design (correct behavior for real English input), and
  whatever whisper.cpp's English-forced decode hallucinated from the
  foreign-language audio got spoken back as a fluent-sounding but
  meaningless English sentence - with no `LOW_CONFIDENCE` fallback, since
  that path only triggers when the detected language differs from the
  target. **Fix**: raised `LOW_CONFIDENCE_THRESHOLD` to 0.65, which cleanly
  separates those three (<=0.59) from es/en (>=0.91) on this fixture set;
  re-running the real sweep confirmed all three now correctly report
  `LOW_CONFIDENCE` instead of garbage, with es/en unaffected. Honest
  limitation: 0.65 is a targeted fix for this n=9 sample, not a
  precision/recall-calibrated threshold - see `docs/roadmap.md`'s Phase 30
  follow-up and `docs/troubleshooting.md`'s incident 10.
- **Status**: engineering prototype - the silent-garbage defect above is
  fixed and re-verified; overall LID accuracy on this fixture set (2/9
  languages reliably detected) is unchanged.

## Stage 4: Automatic speech recognition

- **Engine**: `core/asr/whisper_cpp_asr.py`'s `WhisperCppASR`, shelling out
  to the vendored `third_party/whisper.cpp` CLI binary
  (`tools/setup_whisper_cpp.sh`) via `WhisperCppRunner`, rather than Python
  bindings - chosen because whisper.cpp's CLI is well-tested and actively
  maintained, and shelling out avoids fragile C++ binding compilation.
  Requires 16kHz mono input (`WHISPER_SAMPLE_RATE` in
  `core/asr/whisper_cpp_runner.py`); the pipeline always calls
  `transcribe(audio, sample_rate_hz, language=<LID result>)`, i.e. forced
  language, never `-l auto` for the actual decode - see the latency finding
  below for why.
- **Models**: tiny/base/small multilingual GGML checkpoints; base is what
  the live pipeline and Phase 30's sweep use.
- **Correctness, forced language, on the same synthesized fixtures**: valid,
  non-empty output for all 9 languages; exact-match transcription for
  English specifically.
- **Latency, unquantized (f16) base model, this dev workstation CPU,
  `-l auto`**: up to ~90s to transcribe a ~2s clip for some languages -
  far from real-time. Profiling (Phase 9) found the encoder forward pass
  is the dominant cost (~4.5-6.5s tiny / ~13.8-14s base per full-buffer
  pass for a 2.3s clip), not model load (260-450ms, negligible) - so
  keeping a warm/resident model instead of a fresh CLI subprocess per call
  would not meaningfully help. A separate real inefficiency found in the
  same pass: whisper.cpp's own `-l auto` mode runs the encoder **twice**
  internally (once for language detection, once for the decode) in a
  single CLI invocation; because LID already runs its own encoder pass via
  `-dl`, forcing the language for the ASR call keeps total encoder cost at
  the same two passes it would be anyway, while allowing the pipeline to
  skip decode+translate+TTS entirely when LID confidence is too low.
- **Quantization (Phase 11, `tools/quantize_asr_models.sh` /
  `tools/quantization_benchmark.py`, en/es/ar fixtures, forced language,
  this workstation CPU)**:

  | Model | Size | Peak RSS | Avg latency | Avg WER | Avg CER |
  |---|---|---|---|---|---|
  | base (f16, unquantized) | 148.0 MB | 288 MB | 20597 ms | 0.56 | 0.26 |
  | q4_0 | 46.5 MB | 185 MB | 13363 ms | 0.44 | 0.26 |
  | q5_0 | 55.3 MB | 197 MB | 8498 ms | 0.44 | 0.23 |
  | q8_0 | 81.8 MB | 219 MB | 6432 ms | 0.44 | 0.28 |

  The counter-intuitive, measured result: q8_0 (least aggressive
  quantization tested) is the *fastest* - 3.2x faster than unquantized and
  faster than the smaller q4_0/q5_0 files, almost certainly because ggml's
  q8_0 kernels are better-vectorized for this x86 CPU's AVX2 than q4_0's
  bit-packing scheme - a CPU-specific effect, not a rule to assume holds on
  a different chip. WER/CER is essentially unaffected by quantization
  level. Arabic's WER stays high (~1.0-1.33) at every quantization level
  including unquantized, most likely the same synthesized-voice/training-
  distribution mismatch as the LID finding above, not something
  quantization introduced.
- **Status**: engineering prototype - real and tested with forced
  language; not real-time on this CPU, and the quantization numbers above
  are workstation-only and need re-measuring on any real embedded target
  (Phase 12).

## Stage 5: Machine translation

- **Engine**: `core/translation/ctranslate2_translator.py`'s
  `CTranslate2TranslationEngine`, using CTranslate2 directly (not the
  `argostranslate` Python package, which transitively pulls in PyTorch via
  `stanza` for sentence splitting AT doesn't need - VAD already segments
  utterances). Model files come from Argos Translate's `.argosmodel`
  packages (`tools/setup_translation_models.sh`), with the `stanza` model
  discarded.
- **Tokenizers are not uniform across languages** (verified by inspection,
  not assumed): most packages ship SentencePiece
  (`_SentencePieceTokenizer`); Spanish's package ships the older
  subword-nmt BPE format with Moses pre/post-tokenization
  (`_BPETokenizer`, needing `subword_nmt` + `sacremoses`). A real bug was
  found and fixed here: `sentencepiece` 0.2.2's `decode()` on a list of
  piece-strings inconsistently dropped some word-boundary markers, so
  `_SentencePieceTokenizer.decode()` does the concatenate-then-replace
  detokenization manually instead of trusting `decode()`.
- **Registry**: `core/translation/model_registry.py`'s
  `TranslationModelRegistry` maps `(source, target)` to an on-disk
  CTranslate2 model directory + tokenizer file, with a fast `is_ready()`
  existence check for the hot path (`supports_pair()`, called per request)
  and a full-checksum `is_valid()` for startup checks. `models/registry/translation_models.json`
  currently holds **16 pairs**: all 8 non-English v1 languages to English
  (Phase 6) plus English to all 8 (Phase 17, added for Conversation Mode -
  Phase 6 originally only built X-to-English).
- **Measured latency**: 270ms-1.2s warm (model already loaded), 82-315MB
  per loaded model, all 8 original X-to-English pairs translating
  correctly (`tools/translation_benchmark.py`).
- **Correctness caveat, important and specific**: per Phase 30's full-
  pipeline sweep, **es<->en is the only pair with verified-correct
  end-to-end output** through the real pipeline, despite 16 pairs being
  installed, checksummed, and (Phase 20) signed. The other pairs have
  never failed a translation-only benchmark, but they also haven't cleared
  a full-pipeline correctness check the way es/en has - they inherit
  Stage 3's LID accuracy gap upstream of ever reaching this stage on real
  (or even synthesized) audio.
- **Status**: production candidate for es<->en specifically; engineering
  prototype for the other 7 languages (matches
  `docs/commercial-product-architecture.md`'s readiness matrix exactly).

## Stage 6: Text-to-speech

- **Engine**: `core/tts/piper_tts.py`'s `PiperTTSEngine`, wrapping Piper
  (ONNX voice models via `onnxruntime`, no PyTorch). Piper bundles its own
  espeak-ng phonemization data, so it needs no espeak-ng install at
  runtime (espeak-ng was only used, separately, to synthesize the ASR/LID
  test fixtures). Voices are downloaded via `tools/setup_tts_models.sh`
  from `rhasspy/piper-voices` and tracked by `core/tts/voice_registry.py`.
  Loaded voices are cached per voice ID in `_loaded`, so repeated calls
  after the first don't pay model-load cost again.
- **A real bug caught during setup**: a parallel download once silently
  produced a truncated 27MB file for a 63MB voice model, and onnxruntime's
  failure was an opaque "Protobuf parsing failed" rather than a clear
  incomplete-download error; the setup script now checks downloaded size
  against the server's `Content-Length` before accepting a file.
- **Measured (`tools/tts_benchmark.py`)**: 0.38-0.53 real-time factor after
  model load (i.e. synthesis runs 2-3x faster than real-time on this CPU -
  the opposite asymmetry from ASR, useful for the streaming latency
  budget). The strongest quality signal is not a synthetic metric: a full
  TTS-to-ASR round trip (synthesize with Piper, transcribe back with an
  independent system, whisper.cpp) gives an exact match, **WER=0.0**, on
  all 3 test sentences - evidence of genuinely intelligible speech, not
  just non-silent output.
- **Status**: production candidate - real, tested, English-only voice
  coverage so far.

## What's measured on synthetic/workstation basis vs. what needs real-world re-verification

This project's engineering principles forbid fabricated benchmark numbers,
so every number above is real - but "real" does not mean "representative
of the eventual product." Reading the numbers honestly means keeping three
separate axes of "not yet real-world" straight, because they fail
independently:

1. **Synthetic signals, not recorded acoustic conditions** (Stage 2 only):
   the 6dB/29dB/10dB/8.5dB denoise and beamforming numbers come from
   signals with known, constructed ground truth - not a real noisy room, a
   real echo path, or a real microphone array. Beamforming in particular
   has never processed audio from more than a simulated 2-channel signal.
2. **Synthesized speech, not natural human speech** (Stages 3, 4, 6): every
   non-English test fixture is espeak-ng-synthesized, one sentence per
   language. This is a real, honestly-documented limitation of the
   evaluation, not of the engines - and it cuts in different directions
   per stage: TTS-to-ASR round-trip and forced-language ASR both validate
   fine on synthesized audio, while LID specifically does not, which is
   itself evidence the LID gap is about the classifier task, not about
   synthesized audio being unintelligible in general. Real accuracy
   numbers for LID and per-language ASR need natural speech or a licensed
   multilingual corpus, neither available in this development environment.
3. **This development workstation's CPU, not an embedded target** (Stages
   4, 5, and the quantization table): every latency and RSS number is
   workstation-only. Phase 11's own finding - that quantization level and
   speed are not monotonically related, and that the effect looks CPU-
   kernel-specific (AVX2) rather than universal - is itself the argument
   for re-measuring rather than assuming any of these latency numbers
   transfer to Phase 12's eventual chip choice.

Layered on top of all three: **only es<->en has been verified correct
through the complete, real, wired pipeline** (Phase 30). Every other
language has passed isolated per-stage benchmarks (ASR-forced-language,
translation-only, TTS-only) but not the full LID-must-also-be-right
end-to-end check - and Stage 3's confident-misdetection finding is a
concrete, demonstrated reason those two things are not the same claim.

## Readiness summary

Reusing this project's own readiness framework (prototype / engineering
prototype / production candidate / production ready) - see
`docs/commercial-product-architecture.md`'s readiness matrix for the full
product-wide table, of which the AI/ML rows are reproduced here:

| Stage | Readiness | Why |
|---|---|---|
| VAD & segmentation | engineering prototype | real, tested; VAD's broadband-noise false-positive limitation is documented, not fixed |
| Denoise & beamforming | engineering prototype | real, tested against synthetic signals only; not wired into the live pipeline yet |
| Language identification | engineering prototype, with a known defect | works, but 2-3/9 accuracy on synthesized fixtures, and 3 of those languages are confidently misdetected as the target language with no safety net |
| ASR | engineering prototype | real, tested with forced language; not real-time on this CPU |
| Translation | production candidate for es<->en; engineering prototype for the other 7 pairs | es<->en is the only pair verified correct end-to-end; the rest are installed/signed but not full-pipeline-verified |
| TTS | production candidate | real, tested, WER=0.0 round-trip; English voices only |
| Full pipeline orchestration | engineering prototype | correct status handling for every failure mode, but end-to-end latency (~14-32s/utterance) and Stage 3's defect both block a commercial claim beyond es<->en |
