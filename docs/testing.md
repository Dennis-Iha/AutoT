# AT (AutoT) — Testing Conventions

This describes how this specific codebase tests itself, not general testing
advice. As of this writing there are 41 test files under `tests/`
(`find tests -name "test_*.py" | wc -l`) collecting 294 tests
(`.venv/bin/python -m pytest --collect-only -q`). Re-run both commands
yourself before quoting either number in anything else — they will drift as
the project grows, and this project's Engineering Principles forbid citing a
stale number as current.

## The graceful-skip convention (`tests/conftest.py`)

Four session-scoped fixtures in `tests/conftest.py` are the backbone of
every test that needs a real model instead of a fake:

- `speech_fixtures` — loads `tests/fixtures/speech/manifest.json` and
  attaches each language's WAV path.
- `whisper_cpp_available` — returns `(binary_path, model_path)` if
  `tools/setup_whisper_cpp.sh` has been run and the configured whisper.cpp
  binary and model both exist on disk, else `None`.
- `translation_registry` — returns a loaded `TranslationModelRegistry` if
  `tools/setup_translation_models.sh` has installed at least one ready
  language pair, else `None`.
- `tts_registry` — returns a loaded `VoiceRegistry` if
  `tools/setup_tts_models.sh` has installed at least one ready voice, else
  `None`.

Tests that need real models take the relevant fixture and call
`pytest.skip(...)` with a message naming the setup script, when the fixture
comes back `None`. This is a deliberate choice, not a shortcut: a developer
who hasn't run the (multi-hundred-MB) setup scripts gets `SKIPPED`, never a
fabricated `PASSED` and never a hard `FAILED` that has nothing to do with
their change. The same fixtures are what let `pytest` run identically on a
bare checkout and in CI — see "CI" below for how CI avoids skipping almost
everything by actually installing a minimal real model set first.

## Fakes for logic, real models for behavior

Where both exist, this project deliberately splits orchestration tests into
two files with two different jobs:

- **`tests/orchestration/test_pipeline.py`** — fake `ASREngine` /
  `LanguageIdentifier` / `TranslationEngine` / `TTSEngine` implementations,
  no real model loaded, no `skip` possible. These test
  `TranslationPipeline`'s state machine itself: low-confidence fallback,
  unsupported-language-pair short-circuit, empty-transcription handling,
  source-equals-target skip, and exception propagation per stage. Fast and
  deterministic by construction — a regression here is a real logic bug,
  never a flaky model.
- **`tests/orchestration/test_pipeline_live.py`** — the same pipeline
  wired to the real `WhisperCppASR`, `WhisperLanguageIdentifier`,
  `CTranslate2TranslationEngine`, and `PiperTTSEngine`, run against the
  espeak-ng fixtures in `tests/fixtures/speech/`. Skips via the
  `whisper_cpp_available` / `translation_registry` / `tts_registry`
  fixtures if the setup scripts haven't been run. Its docstring is worth
  reading directly: it records that a real run of
  `tools/language_id_benchmark.py` found only 2/9 languages reliably
  detected, and the file deliberately does not assert 9-language accuracy —
  it tests the two things that actually matter for the pipeline's wiring
  (a reliably-detected language produces correct end-to-end output; an
  unreliably-detected one trips the low-confidence safeguard instead of
  mistranslating).

`tests/orchestration/test_conversation.py` /
`test_conversation_live.py` follow the identical split for
`ConversationSession`'s direction-routing logic.

Two other areas use the same fakes-plus-real idea but inside one file
rather than two, because most of their value comes from the real-model
path and only a couple of cases need a fake:

- **`tests/ota/test_model_updater.py`** — most tests use a `tmp_path` and
  synthetic content/signatures (checksum mismatch, missing staged file,
  wrong public key, signed-but-no-key-given fail-closed behavior — none of
  that needs a real model). `test_resolve_update_targets_covers_all_real_installed_entries`
  and `test_full_update_flow_reinstalls_real_model_with_real_signature` at
  the bottom of the same file take the `translation_registry` /
  `tts_registry` / `whisper_cpp_available` fixtures and run the real
  verify-then-atomically-install pipeline against a real, currently
  installed model's genuine checksum and signature (copied into `tmp_path`,
  never touching the developer's real `models/` directory) — skipping if
  none are installed.
- **`tests/privacy/test_no_audio_persistence.py`** — proves Phase 21's
  no-audio-persistence claim rather than merely asserting it.
  `test_runner_cleans_up_temp_wav_even_when_subprocess_call_raises` is
  fake-based (no whisper.cpp binary required) and forces the whisper.cpp
  subprocess call to raise, confirming the `finally`-block cleanup in
  `core/asr/whisper_cpp_runner.py` holds on the failure path — arguably the
  single most important test in this file, since a crash is exactly when
  persisted audio would be most likely to be forgotten about.
  `test_runner_cleans_up_temp_files_after_real_detect_language`,
  `..._after_real_transcribe`, and
  `test_full_pipeline_leaves_no_new_temp_files` are real, via
  `whisper_cpp_available` / `translation_registry` / `tts_registry`, and
  snapshot the system temp directory's filenames before and after to prove
  nothing new was left behind.

The naming pattern (`_live` suffix when there's a sibling fake-only file;
no suffix, with fake and real cases interleaved, when there isn't) is
consistent across the places it's used — check the module docstring of any
test file under `tests/` before assuming which kind it is; several name the
specific setup script to run if you hit a skip.

## Benchmark/sweep tools are not wrapped in pytest — mostly

`tools/asr_benchmark.py`, `tools/translation_benchmark.py`,
`tools/tts_benchmark.py`, `tools/language_id_benchmark.py`, and
`tools/performance_sweep.py` have no corresponding `tests/` file at all —
confirmed by searching `tests/` for each name. These are measure-and-report
tools, not pass/fail gates: they print or write a results JSON with real
numbers (latency, WER/CER, per-language accuracy) for a human to read, and
those numbers get written into `docs/roadmap.md`'s per-phase sections (for
example, the Phase 30 language-ID table, or Phase 11's quantization
results) rather than asserted against a threshold in CI. The reasoning is
in their own docstrings: `tools/translation_benchmark.py` explicitly
declines to compute a BLEU/chrF score because a proper reference corpus needs
multiple valid reference translations per sentence, which a single
hand-picked sentence per language "cannot provide honestly," and
`tools/quantization_benchmark.py`
explicitly declines to estimate power consumption because this workstation
has no accessible power measurement and "reporting a guessed number would
violate this project's own 'never fabricate benchmark numbers' principle."

This is not quite universal, though: `tools/quantization_benchmark.py` and
`tools/latency_benchmark.py` (the latter outside the six named above) each
have a thin `tests/tools/` file — `test_quantization_benchmark.py` and
`test_latency_benchmark.py` — but neither tests the benchmark's actual
measurement. Both test a small, deterministic helper the module exposes
(`discover_models()`'s return shape, `measure_vad_segmentation_latency()`'s
sign and rough scaling with input length) — the kind of thing that can have
a real right answer independent of hardware or installed models. The
benchmark's real output (timed RAM/latency/accuracy numbers, an actual
mic-to-speaker latency breakdown) is still unguarded by pytest and still
goes into `docs/roadmap.md`, not a test assertion.

## Static analysis gate

`.github/workflows/ci.yml` runs, in order, on every push and PR to `main`:

```
python -m ruff check core tools tests backend
python -m mypy core tools backend
python -m pytest -v
```

Treat both lint commands as required clean before committing, the same way
CI treats them — `docs/roadmap.md`'s phase-completion notes repeatedly cite
"ruff and mypy clean" as part of what "done" means for a phase (e.g. the
Phase 19 backend note: "20 backend tests, all passing, ruff and mypy clean
(backend/ added to the mypy gate)"). There is no enforced git pre-commit
hook in this repo (`.git/hooks/pre-commit` is still the stock
`.sample` file) — this is a workflow discipline enforced by CI and
self-discipline before pushing, not a client-side hook.

Note that `tests` appears in the ruff invocation but not the mypy one:
mypy type-checks `core`, `tools`, and `backend` (application code), while
ruff additionally lints the test suite itself for style/correctness issues
(unused imports, etc.) without requiring it to fully type-check.

## CI doesn't just skip everything

CI installs a real, minimal model set before running tests — whisper.cpp
`tiny`+`base`, the `es-en`/`en-es` translation pair, and one Piper voice
(`en_US-amy-medium`) — specifically so that the `_live` tests and the
fakes-plus-real files above exercise real models in CI rather than
skipping almost everything. The comment in `.github/workflows/ci.yml`
is explicit that this is deliberately not all 9 languages ("that would make
CI prohibitively slow/network-heavy") and is limited to the one language
pair and voice this project's own Phase 8/30 testing has actually verified
produce correct end-to-end output. If that model-install step fails or is
skipped, CI degrades to fake-only coverage rather than hard-failing, but
running it for real is what the project's Engineering Principles ask for
wherever the environment allows it.

## The speech fixtures are synthesized, not recorded — and this matters everywhere

`tests/fixtures/speech/manifest.json` carries a `_provenance` field stating
the fixtures were "Synthesized locally with espeak-ng 1.53.0 (built from
source, MPL-licensed), NOT natural human speech," generated so language-ID/
ASR/MT/TTS integration and gross regressions can be caught offline and
reproducibly, explicitly "not a substitute for human-speech accuracy
validation, which is a documented gap deferred to Phase 30 ... until real
recordings or a licensed speech corpus are available." All 9 clips are the
same sentence ("Where is the train station?") in 9 languages, specifically
so cross-language LID/translation consistency can be checked against one
controlled utterance rather than nine different ones.

This is a real, load-bearing limitation on every accuracy number anywhere
in this project, not a footnote: `tests/orchestration/test_pipeline_live.py`
documents that `tools/language_id_benchmark.py`'s real 2/9 language-ID
accuracy figure was measured against these synthesized clips, and is
explicit that synthesized speech "turns out to be a poor proxy for
whisper.cpp's language *detection* specifically" even though the same
fixtures work fine for forced-language ASR and TTS round-trip testing. Any
WER/CER, LID-confidence, or pipeline-success number produced by this test
suite or by the benchmark tools inherits this caveat — it is a statement
about behavior on synthetic, single-sentence, single-speaker-per-language
audio, not a production accuracy claim.

## Readiness

Per this project's readiness framework (prototype / engineering prototype /
production candidate / production ready — see
`docs/commercial-product-architecture.md`), the test infrastructure
described here (fixtures, fakes, live-skip convention, CI lint+test gate)
is itself **production candidate**: real, exercised on every CI run, and
it has already caught a real bug (the `passlib`/`bcrypt` version-sniffing
failure noted in `docs/roadmap.md`'s Phase 19 section). It falls short of
**production ready** only because of the gap this document spends most of
its length on: the fixtures it runs against are synthesized, not natural,
speech, so no number this suite produces is yet validated against how a
real user actually sounds.
