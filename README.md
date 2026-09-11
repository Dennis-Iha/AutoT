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

**Phases 12-19: hardware-blocked phases handled honestly, software-only
phases built for real.** No physical hardware, mobile SDK, or device exists
in this environment. Phases 12-15 and 18 (hardware selection, headphone
prototype, embedded audio, firmware, mobile app) are desk-research/design
documents only — see `hardware/hardware-selection.md`,
`hardware/AT-H1-headphone-prototype.md`, `firmware/architecture.md`,
`apps/mobile-app-architecture.md`. Phases 16, 17, and 19 (dual-earbud
coordination, Conversation Mode, backend) are genuinely software-testable
without physical hardware and are real, tested code — including extending
translation to full bidirectional support (16 language pairs) once
Conversation Mode needed it. See `docs/roadmap.md` for the full
phase-by-phase detail, including two real bugs found and fixed along the
way (a mobile-blocking audio-thread bug in Phase 9, a passlib/bcrypt
compatibility bug in Phase 19). See `docs/architecture.md`'s status table for
exactly what's tested vs. still a stub, and `docs/roadmap.md`'s Phase 8/9
sections for two important corrections: language ID accuracy on this
project's synthesized test fixtures is honestly only 2-3/9 languages, not
all 9; and per-utterance latency (~40s on this CPU with the base model) is
dominated by ASR/LID compute, not fixable by streaming architecture alone -
read those before assuming either works end-to-end for every language or is
fast today.

**Phase 20: model package signing, real and tested.** `core/security/`
extends Phase 10's checksums with Ed25519 signatures
(`core/security/package_signing.py`), so a model's integrity *and*
authenticity can both be verified before it's loaded, not just its
integrity. `tools/sign_model_manifests.py` /
`tools/verify_model_manifests.py` run this for real against all 20 entries
across the ASR/translation/TTS manifests (dev keypair only — no production
AT signing key exists). Secure boot / signed firmware verification is still
a design document (`firmware/architecture.md`) — it needs physical hardware
this environment doesn't have.

**Phase 21: privacy, real and tested.** `tests/privacy/test_no_audio_persistence.py`
(4 tests) proves the no-audio-persistence claim rather than just asserting
it — and testing it surfaced a real nuance: the pipeline itself never
touches a file, but its whisper.cpp-backed ASR/LID stage briefly writes raw
audio to a temp file (whisper.cpp's CLI needs a real file path) before
deleting it, including on a simulated crash path. `docs/privacy.md`
documents the full data flow and two honestly-stated residual gaps
(temp-file cleanup isn't power-loss-safe; `unlink()` isn't secure erase) —
corrections to an earlier, slightly-too-strong claim, not a new problem.

**Phases 22-28: hardware-blocked, honestly researched with real citations.**
Battery/thermal (`hardware/battery-thermal-engineering.md`), PCB/
miniaturization (`hardware/pcb-and-miniaturization.md`), charging case
(`hardware/charging-case.md`), and manufacturing/factory-test
(`hardware/manufacturing-and-factory-test.md`) are all desk-research design
documents grounded in real cited data (Timekettle/AirPods Pro 2/Sony
WH-1000XM5 battery specs, IEC 62368-1 thermal limits, standard EVT/DVT/PVT
process) rather than fabricated numbers — no production SoC, PCB, or
physical unit exists yet. The central finding worth knowing: no chip this
project has evaluated sits in the power/compute band AT's Whisper-class
workload actually needs.

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

Run the backend (auth/devices/models/firmware - never processes speech):

```bash
pip install -e ".[backend]"
uvicorn backend.main:app --reload   # http://127.0.0.1:8000/docs for the interactive API docs
pytest tests/backend                # 20 tests, SQLite in-memory, no external services needed
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
