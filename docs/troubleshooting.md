# AT (AutoT) — Troubleshooting Log

A record of real bugs this project hit during development, how each was
found, and how (or whether) it was fixed — Symptom / Cause / Fix / Where,
one entry per incident. This is pulled from `docs/roadmap.md`'s per-phase
notes and this repo's own commit history (`git log`), not reconstructed
from memory; every number and file path below was checked against the
current code before being written down. Where a fix has since been
superseded by a later, more general mechanism, that's noted rather than
left stale. Not every entry here ends in "fixed" — two are documented
because the finding itself (an architectural cost that isn't worth
chasing, or an open gap that isn't resolvable in this environment) is the
useful part, and this project's engineering principles treat an honestly
recorded non-fix as more valuable than a quietly dropped problem.

## 1. SentencePiece detokenization silently dropped word-boundary markers

**Symptom**: Translated output for some languages came back with missing
or misplaced spaces around certain words — word-boundary markers present
in the token stream weren't reliably turning into spaces in the decoded
string.

**Cause**: `sentencepiece` 0.2.2's `SentencePieceProcessor.decode()`, when
given a list of piece-strings (rather than ids), was observed during
development to inconsistently drop *some* of the `▁` (U+2581) word-boundary
markers depending on the exact token sequence — e.g. producing
`"Where is the▁railway▁station?"` instead of `"Where is the railway
station?"`. This wasn't a one-off fluke; it was reproducible for specific
token sequences and specific to decoding from piece-strings rather than ids.

**Fix**: Stopped relying on `decode()`'s type-dispatch behavior entirely.
`_SentencePieceTokenizer.decode()` in
`core/translation/ctranslate2_translator.py` does the standard manual
SentencePiece detokenization instead: concatenate all piece-strings, then
replace every `▁` with a space and strip. This was verified correct across
all 7 SentencePiece-based v1 languages (Spanish uses a different,
subword-nmt/BPE tokenizer and isn't affected).

**Where**: `core/translation/ctranslate2_translator.py`
(`_SentencePieceTokenizer.decode`, with the mechanism documented in the
method's own comment); regression-tested in
`tests/translation/test_ctranslate2_translator.py`. Phase 6.

## 2. Duplicate-nested-directory bug in translation model extraction

**Symptom**: Running `tools/setup_translation_models.sh` a second time for
a language pair that was already installed silently doubled that model's
on-disk size. It wasn't caught by output or an error — no script failed —
it surfaced because a readiness check that should have reported the model
ready started reporting it as *not* ready.

**Cause**: The Argos `.argosmodel` archive extracts into a package
directory whose name varies by version; the script located that directory
and copied its `model/` subdirectory into the destination. On a second run
against an already-extracted destination, the copy step nested the model
directory inside itself instead of being a no-op, leaving
`ctranslate2_model_dir` pointing at a directory that no longer contained
`model.bin` directly — which is exactly what
`TranslationModelEntry.is_ready()` checks for. The bug was caught by that
check returning `False` when manual inspection said the model should have
been present and correct.

**Fix**: `tools/setup_translation_models.sh` now checks for
`$dest_dir/model/model.bin` up front and skips (prints "Already present")
instead of re-extracting when a pair is already installed, so a repeated
run is a genuine no-op rather than a corrupting copy. Phase 10's
`core/common/model_manifest.py` checksum system (see incident 3) is the
general safeguard that would catch a recurrence of this class of problem
immediately via `is_valid()`, instead of requiring someone to notice
`is_ready()` disagreeing with what's on disk.

**Where**: `tools/setup_translation_models.sh`; the detection mechanism is
`TranslationModelEntry.is_ready()` in
`core/translation/model_registry.py`. Phase 6, generalized by Phase 10.

## 3. Silently truncated TTS model download

**Symptom**: A downloaded Piper voice model failed to load with
`onnxruntime` raising "Protobuf parsing failed" — an opaque error that gave
no indication the actual problem was an incomplete file, not a malformed
or incompatible one.

**Cause**: A parallel `curl` download was interrupted partway through and
silently wrote a 27MB file to disk for a voice model that should have been
63MB. Nothing checked the downloaded file's size against what the server
actually offered, so the truncated file was treated as a complete,
installed model until something tried to actually parse it.

**Fix**: First fixed locally: `tools/setup_tts_models.sh`'s
`download_verified()` reads the server's `Content-Length` header before
downloading and compares it against the actual downloaded file size
afterward, deleting the file and failing loudly if they don't match. This
was a point fix for one script — `docs/roadmap.md` notes at the time that
the earlier whisper.cpp and Argos Translate setup scripts "got lucky, not
verified-safe." Phase 10 generalized the real fix:
`core/common/model_manifest.py`'s `compute_sha256`/`verify_checksum`
(streamed in 1MB chunks) is now used uniformly by all three model
registries (ASR, translation, TTS), each carrying a real computed `sha256`
in its registry entry and an `is_valid()` method that verifies the whole
file — not just its size at download time, but at any later point
(startup, OTA install) that something needs to trust the file.

**Where**: `tools/setup_tts_models.sh` (`download_verified`);
`core/common/model_manifest.py`; per-registry `is_valid()` in
`core/asr/model_registry.py`, `core/translation/model_registry.py`,
`core/tts/voice_registry.py`. Phase 7, generalized by Phase 10.

## 4. Language-ID accuracy overclaim, caught by actually running the benchmark

**Symptom**: Earlier project documentation stated that all 9 v1 languages
had "valid LID/ASR output shape, tested end-to-end." That claim was true
about output *shape* (every language produced some non-empty result), but
it was read — and written — as if it meant the detected language was
usually *correct*, which had never actually been checked beyond English.

**Cause**: `tools/language_id_benchmark.py` had existed since Phase 4 but
had never actually been run and checked against all 9 languages; the
original claim was written from the pipeline not crashing, not from
comparing detected language against ground truth. Running it for real
during Phase 8 found only 2/9 (22%) correct language detection on the base
Whisper model against this project's espeak-ng-synthesized fixtures.
Investigated rather than dismissed as a fluke: looping each clip 4x didn't
help, and the larger "small" model (487MB) only reached 3/9 — and gave
confidently *wrong* answers (0.79–0.85 confidence) for zh/hi/bn, above the
pipeline's 0.5 fallback threshold, which is a more dangerous failure mode
than the base model's mostly-low-confidence wrong guesses.

**Fix**: Not a code fix — a documentation correction, made explicitly
rather than quietly: the "all 9 languages tested" framing was corrected in
`docs/roadmap.md` and `docs/architecture.md` to state the real number and
what it actually measures. The pipeline's existing `LOW_CONFIDENCE`
fallback (`core/orchestration/pipeline.py`) was reframed from "a spec
checkbox" to "the thing currently protecting the pipeline from
mistranslating on 6–7 of 9 languages" — it was already required by the
master spec, but this is what made clear *how load-bearing* it actually is.
`es`/`en` (plus `en`/`ru` on the small model) are the languages confirmed
reliably detected on these fixtures.

**Where**: `tools/language_id_benchmark.py`;
`core/orchestration/pipeline.py` (`PipelineStatus.LOW_CONFIDENCE`);
`tests/orchestration/test_pipeline_live.py` (exercises both the `es` happy
path and the `ar` fallback path with real models). Phase 4 claim, corrected
in Phase 8.

## 5. Audio capture blocked for 17–90+ seconds per segment (real-time thread)

**Symptom**: In live streaming mode, the microphone effectively stopped
listening while a previous utterance was still being translated and
spoken — directly contradicting the requirement that the program
continuously listen, translate, and speak. This wasn't caught by Phase 8's
own tests.

**Cause**: `tools/at_translate.py` called
`TranslationPipeline.process()` and blocking audio playback directly from
`MicrophoneCapture`'s `on_frames` callback — which runs on PortAudio's
real-time audio thread. Since a single segment could take 17–90+ seconds to
process (the encoder-pass cost measured in Phase 9's profiling, see
incident 6), this blocked audio capture for that entire duration. It was
never caught by Phase 8's tests because the only live-mode smoke test used
3 seconds of silence, so no segment ever actually reached the blocking code
path.

**Fix**: `core/streaming/session.py`'s `StreamingSession` decouples capture
from processing with a producer/consumer queue: `submit()` (called from
the audio callback) is an O(1) non-blocking queue push; a single background
worker thread drains the queue and runs the pipeline and playback. This was
verified with a `threading.Event`-gated fake pipeline (not sleep-based
timing, which would be a race) that `submit()` returns in under 100ms even
while the worker is mid-`process()`, and with a real live-mode run where
capture started and stopped exactly on a requested 3-second schedule while
a segment was still draining in the background afterward. This does *not*
reduce single-utterance latency — that's the encoder-pass cost, unaffected
by threading — it only stops speech from being lost while a previous
segment plays out, and exposes backlog via `pending_count`.

**Where**: `core/streaming/session.py` (`StreamingSession`; see the
module's own docstring for the full story);
`tests/streaming/test_session.py`. Phase 9.

## 6. `whisper.cpp`'s `-l auto` pays for two full encoder passes (not a bug — kept as-is)

**Symptom**: While profiling where Phase 8's per-segment latency actually
went, a single `whisper.cpp -l auto -oj` CLI call showed double the
expected encoder cost for its input length.

**Cause**: Measured directly (`encode time = 28681ms / 2 runs` for one
call): `whisper.cpp`'s own `-l auto` mode runs the encoder once inside
`whisper_lang_auto_detect_with_state()` for language detection, then a
*second*, separate encoder pass for the actual transcription decode — it
does not reuse the first pass's encoder output for the second. This is an
architectural property of whisper.cpp itself, not something caused by how
this project calls it.

**Fix**: None applied, deliberately. `core/asr/whisper_cpp_asr.py` already
uses a *forced* language (skipping the `-l auto` path entirely) after
`core/language_id/whisper_lid.py`'s dedicated `-dl` call — which means this
project's existing two-call architecture already pays close to the
practical minimum: exactly two encoder passes total (one for LID, one for
transcription), the same count `-l auto` pays internally in one call.
Merging the two calls into a single `-l auto` call would not reduce total
encoder cost, and would remove the ability to skip decode, translation, and
TTS entirely when LID confidence is too low to bother — a path exercised
often in practice given the LID accuracy gap (incidents 4 and 10). The
two-call architecture was kept as-is rather than "optimized" into something
strictly worse.

**Where**: `core/asr/whisper_cpp_asr.py`, `core/language_id/whisper_lid.py`;
measurement and reasoning recorded in `docs/roadmap.md`'s Phase 9 section
and `core/streaming/session.py`'s module docstring. Phase 9.

## 7. Conversation Mode's first live test assumed a translation direction that didn't exist

**Symptom**: The first live test of two-direction Conversation Mode
(English speaker ↔ Spanish speaker) failed immediately with
`unsupported_language` on the en→es direction.

**Cause**: Not a bug in `core/orchestration/conversation.py` — the
`ConversationSession` code was correct. Phase 6's translation work had only
ever built the X→English direction for all 8 non-English v1 languages;
nothing English-to-X had been downloaded or registered, so the failure was
exactly correct given what models actually existed on disk.

**Fix**: Rather than weaken the test to avoid the missing direction,
downloaded the missing en→X direction for all 8 v1 languages from the same
Argos Translate model source Phase 6 used (all 8 packages existed), and
extended `tools/setup_translation_models.sh` to support arbitrary pair
directions (previously X→en only). Translation is now genuinely
bidirectional for all 9 languages (16 model pairs total, registered in
`models/registry/translation_models.json`), verified with a real
Spanish↔English two-directional exchange test.

**Where**: `tools/setup_translation_models.sh`;
`models/registry/translation_models.json`;
`tests/orchestration/test_conversation_live.py`. Phase 17. Note this fixes
the *es↔en* direction specifically — per
`docs/commercial-product-architecture.md`'s readiness matrix, es↔en is
still the only language pair with verified-correct full-pipeline output
(see incident 10); the other 7 directions are installed and checksummed
but not yet verified correct end-to-end.

## 8. `passlib`/`bcrypt` 5.0.0 incompatibility broke password hashing

**Symptom**: `backend/auth.py`'s password hashing raised "password cannot
be longer than 72 bytes" even for short (8-character) passwords — a
confusing error unrelated to the actual password supplied.

**Cause**: `passlib` 1.7.4 (unmaintained since 2020) detects which bcrypt
backend is installed by probing `bcrypt.__about__.__version__`. The
installed `bcrypt` 5.0.0 no longer exposes that attribute, so passlib's
version-sniffing silently mis-detected the backend and then applied the
wrong length-handling logic, producing the 72-byte error as a side effect
rather than from any real input problem.

**Fix**: Stopped routing through passlib's `CryptContext` entirely.
`backend/auth.py`'s `hash_password`/`verify_password` call `bcrypt`
directly (`bcrypt.hashpw`/`bcrypt.checkpw`), sidestepping passlib's broken
version-sniffing shim. This is current, active code, not a historical
description — `backend/auth.py`'s own module docstring documents the exact
mechanism.

**Where**: `backend/auth.py`. Phase 19; also cited as the test suite's
first caught real bug in `docs/testing.md`'s readiness section.

## 9. Recurring mypy variable-shadowing from reused loop-variable names

**Symptom**: Across several phases that each needed to loop over more than
one of this project's three model registries (ASR, translation, TTS)
within the same function, naming the loop variable generically (e.g.
`entry`) for more than one registry type in the same scope fails mypy,
because the same name would get two different, incompatible inferred types
(`ASRModelEntry | None`, then reassigned as `TranslationModelEntry | None`,
etc.) in one scope.

**Cause**: Each of these registries' `.get()` returns a different
dataclass type (`ASRModelEntry`, `TranslationModelEntry`, `VoiceEntry`), and
several functions genuinely need to check all three kinds in sequence —
`check_offline_readiness()` checks the configured ASR model, every needed
translation pair, and the target-language TTS voice; `resolve_update_targets()`
builds update targets across all three; the `/models` listing endpoint
lists all three kinds. Reusing one variable name across these checks is the
natural first thing to write, and it's what mypy's scope-wide type
inference catches.

**Fix**: The consistent, recurring fix is distinct per-loop variable names
instead of a shared generic one — `asr_entry`, `translation_entry` (or a
bare `entry` scoped to a loop that only ever iterates one registry type),
and `voice_entry`, never reused across registry types in the same function.
This pattern is applied consistently in every current function that needs
it.

**Where**: `core/common/offline_runtime.py`'s `check_offline_readiness()`
(Phase 10); `backend/routes/models.py`'s `GET /models` handler (Phase 19);
`core/ota/model_updater.py`'s `resolve_update_targets()` (Phase 29);
`tools/performance_sweep.py`'s readiness checks (Phase 30, via
`translation_entry :=` / `voice_entry :=` walrus assignments). Recurred
across Phases 10, 19, 29, and 30.

## 10. LID can be confidently *wrong* in a way worse than a low-confidence failure

**Symptom**: `tools/performance_sweep.py`'s full-pipeline sweep across all 9
v1 languages initially looked like a 5/9 (56%) raw pass rate. Reading what
those "ok" rows actually contained showed 3 of them were fluent-sounding
but meaningless English sentences, not the source language's content in
any form.

**Cause**: For bn, hi, and zh, whisper.cpp's language detection misdetected
the (synthesized) non-English utterance *as English*, with confidence at or
above the pipeline's 0.5 fallback threshold (bn: 0.55, hi: 0.59, zh: 0.51).
Once `source_language == target_language`, translation is skipped entirely
by design — correct behavior for genuinely English input — and whatever
whisper.cpp's English-forced decode hallucinated from the foreign-language
audio got spoken back as if it were a legitimate response:
`"rail station, go tight."` (bn), `"Realme station, Kaha."` (hi),
`"Watcher, Chan, Cai, Ali."` (zh). This is worse than the `LOW_CONFIDENCE`
path that correctly caught ar/fr/pt/ru, because there's no visible failure
signal at all — the pipeline reports `status=ok`.

**Fix**: Not resolved — deliberately recorded as an open, actionable gap
rather than patched over. `tools/performance_sweep.py` now computes and
prints both the raw pass rate and a genuinely-correct rate (excluding rows
flagged `suspect_misdetected_as_target`), so this gap can't be missed by
trusting the raw "ok" count alone; the genuinely-correct rate is 2/9 (22%)
— en and es only, unchanged from incident 4's original finding, now proven
at the full-pipeline level with a concrete downstream cost attached. The
documented next step is to either raise the 0.5 threshold or add a
same-language sanity check specifically for the
detected-language-equals-target-language case, since that case currently
has no safety net at all once LID clears 0.5.

**Where**: `tools/performance_sweep.py` (module docstring and the
`suspect_misdetected_as_target` flag); full numbers in `docs/roadmap.md`'s
Phase 30 section. Phase 30. Per
`docs/commercial-product-architecture.md`'s readiness matrix, this keeps
language ID at *engineering prototype, with a known defect*.

## 11. CI had been failing to run on every push since at least Phase 12, unnoticed

**Symptom**: While auditing project state ahead of Phase 33's documentation
consolidation, checking GitHub Actions run history (`gh run list`) for the
first time found CI had reported `startup_failure` (0 jobs scheduled, 0s
duration) on every push for a long stretch of the project's history — a gap
that had gone unnoticed because all testing up to that point had been done
locally.

**Cause**: Two independent problems:

1. An account/repo-level block on GitHub's side (jobs: 0, "this run likely
   failed because of a workflow file issue" despite the YAML parsing
   validly) — not diagnosable further with this session's authorized
   OAuth scopes, and not something fixable from this environment; it needs
   the repository owner to check GitHub's own Settings → Billing/Actions
   for the account.
2. A real, independent bug in `.github/workflows/ci.yml` itself: the
   workflow only ever installed the `[dev]` extras group, never `[backend]`
   or `[ota]`. Even with problem 1 resolved, `tests/backend/` and
   `tests/tools/test_metrics_report.py` would fail to import at all
   (missing `fastapi`/`sqlalchemy`/`httpx`), and `ruff`/`mypy` had never
   actually checked `backend/` in CI despite `backend/` existing since
   Phase 19.

**Fix**: Problem 2 is fixed: the workflow now installs
`.[dev,backend,ota]`, lints and type-checks `backend/` too, and builds
whisper.cpp plus downloads the one language pair (es↔en) and TTS voice
this project's own testing has actually verified produce correct
end-to-end output, so CI exercises real live tests rather than only the
fake-backed ones. Problem 1 is **not fixed** — it's outside what this
environment/session can resolve and is recorded as an open item for the
repository owner.

**Where**: `.github/workflows/ci.yml`. Phase 32 (found while preparing
Phase 33).
