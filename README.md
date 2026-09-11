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

**Phases 0-6 done**: project foundation, audio capture, VAD, audio cleanup
(denoise/echo-cancel/dereverb/beamforming), language ID, ASR (whisper.cpp),
and translation (CTranslate2) — all running and tested on a Linux
workstation. TTS (Phase 7) and wiring these into one live pipeline (Phase 8)
are next. See `docs/architecture.md`'s status table for exactly what's
tested vs. still a stub.

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

ASR/language-ID and translation need two one-time setup scripts (build
whisper.cpp from source, ~150MB of ggml models; download ~1GB of CTranslate2
translation models) before their tests run for real instead of skipping:

```bash
tools/setup_whisper_cpp.sh          # -> third_party/whisper.cpp, models/asr/whisper/
tools/setup_translation_models.sh   # -> models/translation/argos/
python -m tools.asr_benchmark            # per-language WER/CER/latency
python -m tools.language_id_benchmark    # per-language LID accuracy
python -m tools.translation_benchmark    # per-language-pair latency + output
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
