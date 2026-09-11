# AT (AutoT) Architecture

## Vision

AT Pods: standalone AI translation earbuds that hear speech, identify the
spoken language, translate it locally, and speak the English translation
into the user's ear — no phone, no Wi-Fi, no Bluetooth-to-phone connection,
no cloud required for translation.

**We do not start by designing earbud hardware.** We start by building
AT-CORE, a standalone real-time translation engine, and prove it on an
ordinary computer. Once the AI pipeline is proven and benchmarked, it is
ported to progressively smaller hardware. See "Hardware progression" below.

## Five layers

```
                  AT TRANSLATION ECOSYSTEM
                         |
        +----------------+----------------+
        |                                 |
   AT POD / EARPHONE                AT HEADPHONES
        |                                 |
        +----------------+----------------+
                         |
                 AT EDGE AI ENGINE
                         |
       +-----------------+-----------------+
       |                 |                 |
      ASR                MT                TTS
 Speech -> Text    Text -> English   English -> Speech
       |
       +---- Language ID / VAD / Noise Reduction
                         |
                   Audio playback
```

## Real-time pipeline

```
Microphone(s)
   |
Beamforming               <-- IMPLEMENTED (Phase 3): core/beamforming (synthetic-signal validated only, no real mic array yet)
   |
Noise suppression         <-- IMPLEMENTED (Phase 3): core/denoise (spectral subtraction + NLMS echo cancellation + spectral dereverb)
   |
Voice Activity Detection  <-- IMPLEMENTED (Phase 1/2): core/vad
   |
Language Identification   <-- IMPLEMENTED (Phase 4): core/language_id (whisper.cpp encoder)
   |
Speech Recognition        <-- IMPLEMENTED (Phase 5): core/asr (whisper.cpp)
   |
Translation                <-- IMPLEMENTED (Phase 6): core/translation (CTranslate2, 8 languages -> en)
   |
English Text
   |
Text-to-Speech              (Phase 7 - not yet implemented)
   |
Audio DAC / amplifier
   |
Speaker
```

Everything left of "IMPLEMENTED" above only claims to be an interface or a
plan, not working code. See `docs/roadmap.md` for what phase each stage
belongs to, and never report a stage as working without an automated test
proving it (Engineering Principle #1). Note these stages are not yet wired
together into one pipeline (that's Phase 8) - each is independently tested
today, e.g. via `tools/asr_benchmark.py` and `tools/translation_benchmark.py`.

## Current implementation status (as of Phase 0-3)

| Component | Status | Where |
|---|---|---|
| Config system | done | `core/common/config.py` |
| Logging system | done | `core/common/logging_setup.py` |
| Metrics system | done | `core/common/metrics.py` |
| Language registry | done | `core/common/languages.py`, `models/registry/languages.json` |
| Audio ring buffer | done, tested | `core/audio/ring_buffer.py` |
| Microphone capture | done, tested on real hardware | `core/audio/capture.py` |
| WAV I/O | done, tested | `core/audio/wav_io.py` |
| Audio diagnostics (latency/CPU/RSS) | done, tested | `core/audio/diagnostics.py` |
| VAD interface | done | `core/vad/base.py` |
| WebRTC VAD backend | done, tested (incl. documented false-positive-on-tone limitation) | `core/vad/webrtc_vad.py` |
| Speech segmenter (onset/offset/hangover state machine) | done, tested | `core/vad/segmenter.py` |
| mic -> VAD -> speech segment CLI demo | done, tested on real hardware | `tools/mic_vad_demo.py` |
| STFT/ISTFT utility | done, tested (round-trip error ~1e-15) | `core/denoise/stft.py` |
| Noise suppression (spectral subtraction) | done, tested; measured ~6dB noise reduction / ~72% speech retained; does NOT fix VAD's broadband-noise false-positive on its own (see `tools/audio_cleanup_benchmark.py` output) | `core/denoise/noise_suppression.py` |
| Echo cancellation (NLMS) | done, tested; measured ~29dB ERLE on a stationary synthetic echo path; no double-talk protection yet | `core/denoise/echo_cancellation.py` |
| Dereverberation (spectral tail subtraction) | done, tested; measured ~10dB reverberant-tail reduction; single-channel simplified technique, NOT full WPE | `core/denoise/dereverberation.py` |
| Beamforming (delay-and-sum + TDOA estimation) | done, tested; measured ~8.5dB SNR gain from correct alignment vs naive averaging; synthetic 2-channel signals only, no real mic array | `core/beamforming/delay_sum.py` |
| Language ID (whisper.cpp encoder, 9 languages) | done, tested on real (synthesized) speech per language; see `tools/language_id_benchmark.py` | `core/language_id/whisper_lid.py` |
| ASR (whisper.cpp, tiny/base multilingual) | done, tested on real speech, exact-match transcription on English fixture; base model far from real-time on this CPU (up to ~90s for a 2s clip) - see `tools/asr_benchmark.py` | `core/asr/whisper_cpp_asr.py` |
| Translation (CTranslate2, 8 source languages -> en) | done, tested; 270ms-1.2s warm latency, correct output for all 8; Spanish uniquely needs a BPE+Moses tokenizer (not SentencePiece) - see `tools/translation_benchmark.py` | `core/translation/ctranslate2_translator.py` |
| TTS | not started (Phase 7) | `core/tts/` (empty) |
| Streaming orchestration / full CLI pipeline | not started (Phase 8/9) | `core/streaming/`, `core/orchestration/` (empty) |
| Everything hardware/firmware/backend/mobile | not started (Phase 12+) | `firmware/`, `hardware/`, `backend/`, `apps/` (skeleton only) |

## Language coverage is a claim, not an assumption

Initial v1 language set: English, Mandarin Chinese, Hindi, Spanish, Arabic,
French, Bengali, Portuguese, Russian (`models/registry/languages.json`).
Translation logic is never hard-coded around these nine — everything routes
through a **language registry -> model registry -> language-pair registry**,
so adding language #10 is a data change, not a rewrite.

Every language entry has a `status` field (`initial` / `asr_ready` /
`translation_ready` / `tts_ready` / `production`) and must not be reported to
end users as supported until it reaches `production` — i.e. until its
ASR+translation+TTS models are actually registered and benchmarked. Coverage
and quality vary dramatically between languages; we do not promise "every
language in the world" until each one has actually been tested.

## Hardware progression

We are not designing an earbud PCB yet. The plan, in order:

1. **Workstation** (current phase) — Linux/macOS/Windows dev machine, proves
   the AI pipeline end to end.
2. **Portable embedded computer** — e.g. NVIDIA Jetson Orin Nano Super class
   hardware, to measure real inference latency/power/thermal before
   committing to any custom silicon.
3. **Standalone AT headphone prototype** — first real physical product;
   headphones have far more room than earbuds for battery, RAM, compute, and
   microphones.
4. **Custom headphone motherboard**
5. **Large standalone earbud prototype**
6. **Custom AT earbud PCB**
7. **Production miniaturization**

Chip selection happens after the AI workload is benchmarked on real
hardware, not before (Engineering Principle #17/#18). A high TOPS number
alone does not indicate suitability for real-time speech translation.

## Repository layout

```
apps/          desktop/android/ios companion apps (Phase 18)
core/          ASR/MT/TTS/audio pipeline library - the installable "autot" package
  audio/       microphone capture, ring buffer, WAV I/O, diagnostics
  vad/         voice activity detection interface + WebRTC backend + segmenter
  denoise/     noise suppression interface (Phase 3)
  beamforming/ beamforming interface (Phase 3)
  language_id/ language identification (Phase 4)
  asr/         speech recognition (Phase 5)
  translation/ text translation (Phase 6)
  tts/         text-to-speech (Phase 7)
  streaming/   real-time streaming orchestration (Phase 9)
  orchestration/ full pipeline wiring (Phase 8)
  common/      config, logging, metrics, language registry - shared by all of the above
models/        language/model/language-pair registries + local model storage (gitignored binaries)
firmware/      embedded firmware (Phase 15+)
hardware/      schematics/PCB/BOM/enclosure/manufacturing (Phase 24+)
backend/       cloud control-plane: accounts, device registry, OTA (Phase 19)
tests/         automated tests, mirrors core/ layout
tools/         CLI utilities (e.g. mic_vad_demo.py) and dev scripts
docs/          this file + phase-specific docs as they're written
docker/        containerized dev environment
config/        default.yaml + environment overrides
```

## Engineering principles this repo follows

See the master spec for the full list; the ones most load-bearing day to day:

1. Never claim something works until it is tested.
2. Never fabricate benchmark numbers or hardware capabilities.
3. Keep hardware abstraction separate from AI logic (every `core/*` module
   defines an ABC in `base.py` before any concrete backend is written).
4. Design for offline operation and privacy-first from the beginning.
5. Record measurable performance (every audio/VAD stage feeds
   `core/common/metrics.py`).
6. Identify whether a component is prototype / engineering prototype /
   production candidate / production ready — this doc's status table exists
   for exactly that.
