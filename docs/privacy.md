# AT (AutoT) — Privacy: Data Flow, Retention, Telemetry

Phase 21. This document describes what actually happens to a user's speech
in this codebase today, verified against the code and tests listed below —
not a policy aspiration written ahead of the implementation. Where a claim
is backed by an automated test, the test is named so it can be re-run to
re-verify the claim after any future change.

## Data flow (per utterance)

```
Microphone (int16 PCM, 16kHz)
   |  in-memory numpy array
VAD / speech segmentation        core/vad/
   |  in-memory numpy array
Language ID (whisper.cpp)        core/language_id/whisper_lid.py
   |  briefly written to a temp WAV file (see "Temp files" below),
   |  deleted before this stage returns
ASR / transcription (whisper.cpp) core/asr/whisper_cpp_asr.py
   |  same temp-file pattern as language ID
   |  produces: recognized TEXT (in-memory)
Translation (CTranslate2)         core/translation/
   |  in-memory TEXT -> TEXT, no network call, no model API
Text-to-speech (Piper)            core/tts/
   |  produces: synthesized English audio (in-memory numpy array)
Playback (speaker)                core/audio/playback.py
```

**No network call happens anywhere in this flow.** `core/` has zero
imports of `requests`, `httpx`, `urllib`, or raw sockets (verified by
`grep -rl` across `core/` — see the repo at commit time of this doc). ASR,
translation, and TTS are all local model inference (whisper.cpp,
CTranslate2, Piper); none of them talk to a remote API. This is the
architectural consequence of Engineering Principle "design for
offline/privacy-first from the start," not a claim added after the fact —
Phases 5-7 built these as local-inference engines specifically to avoid a
cloud dependency.

## Raw audio is never written to disk by default — proven, not assumed

`core/orchestration/pipeline.py`'s `TranslationPipeline.process()` operates
only on in-memory numpy arrays; it never opens a file. That much is true by
inspection.

The more subtle, more important fact: `core/asr/whisper_cpp_runner.py`
shells out to the whisper.cpp CLI, which requires a real file path (there is
no stdin/in-memory API in the mode this project uses) — so raw audio *does*
briefly touch disk, twice per utterance (once for language ID, once for
transcription — the two-encoder-pass architecture documented in Phase 9's
roadmap section). Both writes go to a `tempfile.mkstemp()` path (mode 0600,
readable only by the owning user) and are deleted in a `finally` block
immediately after each whisper.cpp call returns — including on the failure
path, not only on success.

This is proven, not merely asserted, by `tests/privacy/test_no_audio_persistence.py`:

- `test_runner_cleans_up_temp_wav_even_when_subprocess_call_raises` — forces
  the whisper.cpp subprocess call to raise and confirms the temp WAV is
  still deleted. This is the guarantee that matters most, since a crash is
  exactly when persisted audio would be most likely to be forgotten about.
- `test_runner_cleans_up_temp_files_after_real_detect_language` /
  `..._after_real_transcribe` — run the real whisper.cpp binary and diff the
  system temp directory's contents before/after each call.
- `test_full_pipeline_leaves_no_new_temp_files` — runs the complete
  LID→ASR→translation→TTS pipeline on real recorded speech and confirms the
  system temp directory is byte-for-byte identical (same filenames) before
  and after. This is the strongest version of the claim: the same code path
  a live device would use per utterance, with a real assertion, not a
  reasoning-based claim.

All four pass as of this writing (`pytest tests/privacy -v`).

## Known gap: not crash/power-loss safe, and unlink is not secure erase

Two honest limitations, not swept under the rug:

1. **Process kill / power loss.** The `finally`-block cleanup above only
   runs if the Python process is still alive to run it. A `SIGKILL`, kernel
   panic, or — on the eventual headphone hardware — an abrupt battery
   disconnect mid-transcription would leave a temp WAV file on disk until
   the filesystem is next cleaned. On a Linux workstation `/tmp` is
   frequently `tmpfs` (RAM-backed, cleared on power-off) but this is a
   distribution/mount configuration, not something this code controls or
   has verified for the eventual embedded target. This is a real,
   open item for the embedded OS work (Phase 13+): the temp directory used
   for whisper.cpp's file-based CLI interface should be mounted `tmpfs` on
   the shipping device, so an abrupt power loss can't leave recoverable
   speech audio on non-volatile storage.
2. **`unlink()` is not a secure erase.** Deleting a file removes its
   directory entry; it does not overwrite the underlying storage blocks.
   On flash storage (the eventual microSD/eMMC target), deleted audio bytes
   may remain physically recoverable until the block is reused. This is a
   general property of most filesystems and flash storage, not unique to
   this code, but it means "temp file was deleted" is a weaker guarantee
   than "the bytes are gone" — worth knowing before calling this
   "forensically clean."

## What IS logged, and why that matters

`core/common/logging_setup.py` configures structured (optionally JSON)
logging to stderr. Critically, `tools/at_translate.py`'s per-segment log
line includes the **recognized and translated text**, not just metadata:

```python
logger.info(
    "segment %d [%s, conf=%.2f]: %r -> %r (total=%.0fms: %s)",
    segment_index, result.detected_language.language, result.detected_language.confidence,
    result.transcription.text, ...
)
```

Today this only goes to the local stderr stream of whatever process is
running — nothing ships it anywhere (no telemetry system exists yet; that's
Phase 31, not started). But this is the actual content of what the user
said and its translation, and it is worth flagging now, before a log
-shipping pipeline exists, rather than after: **when Phase 31's telemetry
system is built, transcript/translation text must not be included in
whatever gets shipped off-device by default.** Aggregate, content-free
metrics (latency, error rates, language-pair usage counts) are fine by
default; verbatim text is not, unless a user has explicitly opted in
(e.g. an explicit "send a diagnostic report" action), per the master
spec's privacy-first principle.

## Opt-in disk writes (diagnostic/demo tooling only)

Two CLI tools accept an explicit `--out-dir`/similar flag that writes audio
to disk — both are opt-in and neither persists the user's raw voice:

- `tools/at_translate.py --out-dir` writes `result.synthesis.audio` — the
  **synthesized English TTS output**, not the user's original speech — one
  file per translated segment. A user who never passes this flag gets no
  files written.
- `tools/mic_vad_demo.py --out-dir` is a VAD-segmentation debug tool; it
  writes the **raw captured segment** to disk when explicitly asked, for
  the specific purpose of inspecting VAD segmentation boundaries during
  development. This is a developer diagnostic tool, not part of the
  on-device translation runtime (`at-translate` / the eventual firmware),
  and is not expected to run on a shipping device.

## Backend (Phase 19)

`backend/` stores accounts, registered devices, model registry metadata, and
OTA job records in its database (SQLite for dev, `AT_DATABASE_URL`configurable) —
never audio or transcript/translation content. There is no endpoint in
`backend/routes/` that accepts or stores audio or recognized text.

## Summary

| Claim | Status |
|---|---|
| Core pipeline makes no network calls | verified by inspection (no network imports in `core/`) |
| Raw audio never persists after a normal call | tested (`tests/privacy/test_no_audio_persistence.py`, 4 tests) |
| Raw audio never persists after a failed/crashed call (process still alive) | tested |
| Raw audio survives an OS-level kill/power-loss | **not guaranteed** — open item, tracked above, for embedded `tmpfs` config |
| Deleted temp files are forensically unrecoverable | **not guaranteed** — `unlink()` only, general flash/filesystem limitation |
| Recognized/translated text is logged locally | true — `tools/at_translate.py` INFO logs, stderr only, not shipped anywhere today |
| Any telemetry/analytics system exists today | **no** — Phase 31, not started; this doc sets the constraint for when it is |
| Backend stores audio or transcript content | **no** — accounts/devices/model metadata/OTA jobs only |
