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

**Phase 0/1 in progress**: project foundation, audio capture, and voice
activity detection (VAD) — running on a Linux workstation, no ASR/MT/TTS yet.

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
pytest
```

Run the microphone → VAD → speech-segment demo:

```bash
python -m tools.mic_vad_demo --duration 10 --out-dir /tmp/at_segments
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
