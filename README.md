# AT (AutoT) — Offline AI Speech Translation

AT Pods is the long-term goal: standalone AI translation earbuds that hear
speech, identify the spoken language, translate it locally, and speak the
English translation into the user's ear — no phone, no Wi-Fi, no cloud
required for translation.

This repository does **not** start with earbud hardware. It starts with
**AT-CORE**, a standalone, offline, real-time translation engine that runs on
an ordinary computer. Once the AI pipeline is proven and benchmarked, it gets
ported to progressively smaller hardware: embedded dev board → standalone
headphone prototype → custom motherboard → earbud prototype → custom earbud
PCB.

See `docs/architecture.md` for the full layered architecture and
`docs/roadmap.md` for the phase-by-phase development plan.

## Status

**Phases 0-11 done** (software, all tested on a Linux workstation): project
foundation, audio capture/playback, VAD, audio cleanup, language ID, ASR
(whisper.cpp), translation (CTranslate2), TTS (Piper), a complete wired
pipeline (`at-translate`), real-time streaming, offline-mode model
manifests with checksum verification, and ASR quantization benchmarking.
Phase 11 found something genuinely useful: the most aggressive quantization
was NOT the fastest one on this CPU — see `docs/roadmap.md`'s Phase 11
section before assuming "smaller = faster."

**Phase 12 (embedded hardware selection) is desk research only** — see
`hardware/hardware-selection.md`. This environment has no physical hardware
to validate against; from here on, phases that need physical devices, lab
equipment, or infrastructure this environment doesn't have are handled
honestly: real work where possible, clearly flagged as unvalidated where
not, never simulated as if tested. See `docs/architecture.md`'s status table for
exactly what's tested vs. still a stub, and `docs/roadmap.md`'s Phase 8/9
sections for two important corrections: language ID accuracy on this
project's synthesized test fixtures is honestly only 2-3/9 languages, not
all 9; and per-utterance latency (~40s on this CPU with the base model) is
dominated by ASR/LID compute, not fixable by streaming architecture alone -
read those before assuming either works end-to-end for every language or is
fast today.

## Initial language set

English, Mandarin Chinese, Hindi, Spanish, Arabic, French, Bengali,
Portuguese, Russian — see `models/registry/languages.json`. The system is
architected around a language registry / model registry / language-pair
registry so more languages can be added without redesigning the pipeline.

## Development setup

Requires Python >= 3.11, a C compiler + cmake (for native audio/VAD/ASR
extensions), and a working ALSA/PortAudio input device.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pytest   # ASR/LID/translation tests skip gracefully until the two setup scripts below are run
```

Run the microphone → VAD → speech-segment demo:

```bash
python -m tools.mic_vad_demo --duration 10 --out-dir /tmp/at_segments
```

ASR/language-ID, translation, and TTS need three one-time setup scripts
(build whisper.cpp from source, ~150MB of ggml models; download ~1GB of
CTranslate2 translation models; ~63MB Piper voice) before their tests run
for real instead of skipping:

```bash
tools/setup_whisper_cpp.sh          # -> third_party/whisper.cpp, models/asr/whisper/
tools/setup_translation_models.sh   # -> models/translation/argos/
tools/setup_tts_models.sh           # -> models/tts/piper/
python -m tools.asr_benchmark            # per-language WER/CER/latency
python -m tools.language_id_benchmark    # per-language LID accuracy (currently weak, see docs/roadmap.md)
python -m tools.translation_benchmark    # per-language-pair latency + output
python -m tools.tts_benchmark            # TTS latency + TTS->ASR round-trip WER
python -m tools.latency_benchmark        # full capture/VAD/LID/ASR/translation/TTS/playback breakdown
python -m tools.check_offline_readiness  # verify every model is present + checksum-valid
tools/quantize_asr_models.sh base q4_0 q5_0 q8_0  # produce quantized ASR model variants
python -m tools.quantization_benchmark   # size/RAM/latency/accuracy across quantization levels
```

Run the complete pipeline (mic → VAD → language ID → ASR → translation →
TTS → speaker):

```bash
at-translate --duration 30                              # live mic, speaks the English translation
at-translate --input-file some_speech.wav --no-play --out-dir /tmp/out  # batch/file mode
```

## Repository layout

```
core/          # ASR/MT/TTS/audio pipeline library (installable Python package)
models/        # language/model/language-pair registries + local model storage
firmware/      # embedded firmware (later phases)
hardware/      # schematics/PCB/BOM (later phases)
backend/       # cloud control-plane: accounts, device registry, OTA (later phases)
apps/          # desktop/mobile companion apps (later phases)
tests/         # automated tests, mirrors core/ layout
tools/         # CLI utilities and dev scripts
docs/          # architecture, hardware selection, and phase docs
docker/        # containerized dev environment
```
