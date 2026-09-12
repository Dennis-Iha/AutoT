# Model Registry

This document describes the three model registries AT uses at runtime -
ASR, translation, and TTS - the manifest schema they share, and where the
actual model files come from. It does not cover translation quality or
latency; see `docs/roadmap.md`'s Phase 6/17/30 sections and
`docs/commercial-product-architecture.md`'s readiness matrix for that.

## The pattern: three registries, one manifest primitive

AT has three independent model registries, one per pipeline stage:

- `core/asr/model_registry.py` - `ASRModelRegistry` / `ASRModelEntry`
- `core/translation/model_registry.py` - `TranslationModelRegistry` /
  `TranslationModelEntry`
- `core/tts/voice_registry.py` - `VoiceRegistry` / `VoiceEntry`

Each loads a JSON file under `models/registry/` (`asr_models.json`,
`translation_models.json`, `tts_voices.json` respectively) into a list of
frozen dataclass entries, indexed for lookup (`get()` by `model_id`/
`voice_id`, plus `get_by_size_class()` for ASR, `get()` by
`(source, target)` for translation, and `default_for_language()` for TTS).
This is Phase 10's design: before it, ASR models were just raw file paths
in `ASRConfig` (`core/common/config.py`) with no version or integrity
tracking at all, while translation and TTS already had this registry shape.
Phase 10 added the ASR registry and gave all three a shared checksum
primitive, `core/common/model_manifest.py`, so integrity checking isn't
three different ad-hoc implementations.

`core/common/model_manifest.py` is deliberately small: `compute_sha256()`
streams a file in 1MB chunks (model files run into the hundreds of MB, and
this runs at startup, not just once after download) and `verify_checksum()`
compares against an expected hex digest. Every registry's `is_valid()`
calls into this.

### `is_ready()` vs `is_valid()`

Every entry class exposes the same two methods, applied uniformly across
all three registries:

- **`is_ready()`** - a fast existence check (does the file exist on disk).
  Cheap enough for a hot path: `TranslationModelRegistry.supports_pair()`
  calls it per translation request.
- **`is_valid()`** - a full SHA256 checksum verification, which means
  reading the whole file. Meant for startup / offline-readiness checks,
  not per-request use.

This split exists because of a real incident, not a hypothetical one:
Phase 7 hit a silently truncated TTS model download (27MB received for a
63MB file) that onnxruntime reported as an opaque "Protobuf parsing
failed" instead of a clear "this file is wrong" error. A `Content-Length`
check at download time (`tools/setup_tts_models.sh`) catches that case
once, at download; the checksum is the general fix, since it also catches
later corruption - a disk error, an interrupted transfer, manual tampering
- that a download-time check can't see.

One asymmetry worth flagging rather than glossing over: `ASRModelEntry.sha256`
is a required field, so its `is_valid()` always does a full checksum read.
`TranslationModelEntry.sha256` and `VoiceEntry.sha256` are typed
`str | None`, and if `None`, `is_valid()` silently falls back to
`is_ready()`'s existence-only check. In practice every entry currently in
all three registry JSON files has a `sha256` populated, so this fallback
path isn't exercised today - but the schema does allow an unchecksummed
translation or TTS entry in a way the ASR schema doesn't.

## Manifest schema

Common fields across all three JSON files, read directly from
`models/registry/*.json`:

| Field | ASR | Translation | TTS |
|---|---|---|---|
| identifier | `model_id` | `model_id` | `voice_id` |
| `sha256` | required | optional (`str \| None`) | optional (`str \| None`) |
| `size_mb` | required | optional | optional |
| `signature` | present (`{signature_b64, key_id, algorithm}`) | present | present |
| on-disk location | `path` (single file) | `model_dir` + `tokenizer_model` | `model_dir` |

The registry-specific fields: ASR entries carry `size_class` (`tiny` /
`base` / `small`) and `multilingual`; translation entries carry `source`,
`target`, `version`, and a `ctranslate2_model_dir` property
(`model_dir / "model"`, since CTranslate2 wants that subdirectory
specifically, not its parent); TTS entries carry `language`, `quality`,
and `sample_rate_hz`, plus `onnx_path`/`config_path` properties derived
from `model_dir / f"{voice_id}.onnx"` and `.onnx.json`.

The `signature` object is written by `tools/sign_model_manifests.py` (see
below) and is present on every entry in all three files today. It's worth
being precise about what actually reads it: **none of the three registry
loader classes (`ASRModelEntry`, `TranslationModelEntry`, `VoiceEntry`)
parse or check the `signature` field at all** - their `__init__`/`load()`
code only reads `model_id`/`voice_id`, `sha256`, `size_mb`, and the
registry-specific fields shown above. Signature verification happens
exclusively through the standalone `tools/verify_model_manifests.py`
script, not through `is_ready()`, `is_valid()`, or
`core/common/offline_runtime.py`'s aggregate readiness check. That's a
real gap between "signed" and "verified at load time": a model whose
signature would fail verification could still load and pass `is_valid()`
today, because nothing in the load path checks the signature. Closing
that gap (wiring signature verification into `is_valid()` or the
offline-readiness check) is unbuilt.

## What's actually in each registry today

Counts and IDs below are read directly from the registry JSON files, not
estimated.

### ASR - `models/registry/asr_models.json`

Three entries, all `engine: "whisper_cpp"`, all `multilingual: true`:

| `model_id` | `size_class` | `size_mb` |
|---|---|---|
| `whisper-tiny` | tiny | 77.7 |
| `whisper-base` | base | 148.0 |
| `whisper-small` | small | 487.6 |

The file's own `_provenance` field states these are "ggml multilingual
Whisper models from ggerganov/whisper.cpp on HuggingFace (converted from
OpenAI's Whisper). Not trained or fine-tuned by AT." They're fetched by
`tools/setup_whisper_cpp.sh`, whose header notes it downloads the
multilingual ggml conversions specifically (not the `.en`-suffixed
English-only ones), since AT's language set requires multilingual models.

### Translation - `models/registry/translation_models.json`

Sixteen entries, all `engine: "ctranslate2"`: bilingual model pairs
covering both directions between English and 8 other languages (Arabic,
Bengali, Chinese, French, Hindi, Portuguese, Russian, Spanish) - `ar<->en`,
`bn<->en`, `zh<->en`, `fr<->en`, `hi<->en`, `pt<->en`, `ru<->en`, `es<->en`.
Each direction is its own entry (e.g. `argos-es-en-1.0` and
`argos-en-es-1.0` are separate rows, separate model files), because each
is a distinct bilingual CTranslate2 model - there is no single shared
multilingual translation model in this registry today. The registry's own
module docstring (`core/translation/model_registry.py`) notes that a future
multilingual model (e.g. an NLLB-200 CTranslate2 conversion serving many
pairs at once) would replace many of these rows with a wildcard-style
entry - a registry data change, not a change to any code that calls the
registry.

The file's `_provenance` field: "CTranslate2 models sourced from the
Argos Translate open model index
(https://github.com/argosopentech/argospm-index), fetched via
`tools/setup_translation_models.sh`. Not trained or fine-tuned by AT."
Important distinction, documented in `core/translation/ctranslate2_translator.py`'s
module docstring: AT does **not** depend on the `argostranslate` Python
package. That package pulls in `stanza` for paragraph-to-sentence
splitting, which transitively requires PyTorch - a multi-hundred-MB
dependency AT doesn't need, since utterance segmentation already happens
upstream in `core/vad/segmenter.py` (Phase 2). Instead,
`tools/setup_translation_models.sh` downloads Argos Translate's published
`.argosmodel` packages directly, extracts the CTranslate2 model + tokenizer
files, and discards the bundled `stanza` sentence-splitter model - then AT
loads the CTranslate2 files with the lightweight `ctranslate2` package
(no torch) plus `sentencepiece`/`subword_nmt`/`sacremoses` for
tokenization.

One non-uniformity documented in the same docstring, verified by inspection
during development rather than assumed: 15 of the 16 entries ship a
`sentencepiece.model` tokenizer, but one direction - `es->en`
(`argos-es-en-1.9`) - ships the older subword-nmt BPE format
(`bpe.model`) with Moses-style pre-tokenization instead; the other
direction of the same language pair, `en->es` (`argos-en-es-1.0`), uses
SentencePiece like every other entry (confirmed by reading
`models/registry/translation_models.json` directly - this is not
symmetric across the pair). Scheme selection isn't driven by the
registry's `tokenizer_model` field despite that field's name:
`ctranslate2_translator.py`'s `_load_tokenizer()` instead checks directly
for a `sentencepiece.model` or `bpe.model` file inside `entry.model_dir`
and picks the matching tokenizer class; `tokenizer_model` itself is only
read elsewhere, by `TranslationModelEntry.is_ready()`'s existence check.

### TTS - `models/registry/tts_voices.json`

One entry: `en_US-amy-medium` (`engine: "piper"`, `quality: "medium"`,
22050 Hz, 63.2 MB). The file's `_provenance` field: "Voice models from the
Piper project (rhasspy/piper-voices on HuggingFace), MIT-licensed. Not
trained by AT." See the Licensing section below for why the "MIT-licensed"
half of that sentence needs to be treated as unverified, not confirmed,
despite appearing in the repo's own comments.

## Signing (Phase 20)

`core/security/package_signing.py` adds Ed25519 signatures on top of Phase
10's checksums. Its own module docstring states the reason precisely: a
checksum alone proves a file wasn't corrupted or truncated, but does
nothing to stop someone from distributing a *different* model with its own
correct checksum recorded alongside it - a signature, verified against a
trusted public key, is what proves the file was actually published by
whoever holds AT's private signing key. It signs the SHA256 digest that
`core/common/model_manifest.py` already computes, not the raw file bytes,
so re-signing after a manifest update doesn't mean re-reading
hundred-plus-MB model files.

`generate_signing_keypair()` exists for development/testing only - the
module docstring is explicit that **no production AT signing key exists**,
because there is no production AT deployment. `tools/sign_model_manifests.py`
generates (or reuses, if already present) a development-only Ed25519
keypair under `.dev_signing_key/` (gitignored), then signs every entry
that has a `sha256` across all three manifest files, writing the resulting
`{signature_b64, key_id, algorithm}` object back into each entry as
`"signature"`. Today that's 3 ASR + 16 translation + 1 TTS = 20 entries,
all signed with `key_id: "dev-key-1"`. `tools/verify_model_manifests.py`
re-verifies every signature against the dev public key and the `sha256`
value recorded in the manifest. Worth being precise about what that
does and doesn't prove: it confirms the recorded digest is the one that
was actually signed (so a signature over a stale or wrong digest is
caught), but it does not itself re-read the model file and recompute a
fresh checksum from disk - that's `is_valid()`/`verify_checksum()`'s job
(Phase 10), run separately. The two together close the full gap:
`is_valid()` catches a file that no longer matches its recorded digest,
and `verify_model_manifests.py` catches a digest that was never validly
signed in the first place.

As noted above under "Manifest schema", this signing/verification path is
currently a standalone offline step (`python -m tools.sign_model_manifests`,
`python -m tools.verify_model_manifests`) - it is not wired into
`is_ready()`, `is_valid()`, or any code that runs when the pipeline
actually loads a model.

A real production deployment's private key would need to live in an HSM
or equivalent, never in this repository or its tests - that's stated
in the `package_signing.py` docstring as a requirement for a future state
that doesn't exist yet, not as something already built.

## Where the files actually live

The registry JSON files themselves (`models/registry/*.json`) are checked
into git - they're small metadata, not model weights. The model weight/
voice files they describe are not: `.gitignore` excludes them explicitly,
by extension (`models/**/*.bin`, `*.onnx`, `*.gguf`, `*.pt`, `*.model`) and
by directory (`models/asr/whisper/`, `models/translation/argos/`,
`models/tts/piper/`) - they're too large for git. They're fetched on
demand by three setup scripts:

- `tools/setup_whisper_cpp.sh` - clones and builds `third_party/whisper.cpp`,
  then downloads the ggml multilingual models into `models/asr/whisper/`.
- `tools/setup_translation_models.sh` - downloads and extracts Argos
  Translate `.argosmodel` packages into `models/translation/argos/`.
- `tools/setup_tts_models.sh` - downloads Piper ONNX voices into
  `models/tts/piper/`, verifying each download's size against the
  server's `Content-Length` before accepting it (the Phase 7 truncated-
  download fix mentioned above).

None of these are run automatically by anything in `core/` - a developer
or a build step runs them explicitly to populate `models/` before the
pipeline can load anything.

## Licensing: not verified, and that's an open item

This project has **not verified the redistribution license terms for any
of the three model sources** - Whisper ggml weights, Argos Translate
models, or Piper voices. This needs to be resolved before any commercial
distribution, and per this project's engineering principles it should not
be guessed at or asserted without reading the actual upstream LICENSE
file.

That gap is concrete, not theoretical: `tools/setup_tts_models.sh`'s own
header comment and `tts_voices.json`'s `_provenance` field both state the
Piper voices are "MIT-licensed," but that claim was written into this
repo's comments and JSON without this project confirming it against
Piper's/`rhasspy/piper-voices`'s actual upstream LICENSE file. It may well
be correct - but as written, it's an unverified assertion sitting in
source comments, which is exactly the kind of claim this project's
engineering principles say not to carry forward as fact. The ASR
(`asr_models.json`) and translation (`translation_models.json`) manifests
don't even carry a license claim in their `_provenance` fields - Whisper's
weights and Argos Translate's `.argosmodel` packages each come with their
own upstream license terms that haven't been looked at here at all.

Before any commercial distribution of AT, someone needs to actually read:
OpenAI Whisper's model license terms (and separately, ggerganov/whisper.cpp's
license for the ggml conversion itself, which may differ from the original
Whisper weights' terms), the Argos Translate / OPUS-MT model index's
license terms for the specific packages this project uses, and Piper's/
`rhasspy/piper-voices`'s actual LICENSE file - not the comment that
currently asserts one - and record what was actually found, not what was
assumed.

## Readiness

Per this project's readiness framework (prototype / engineering prototype
/ production candidate / production ready), `docs/commercial-product-architecture.md`'s
readiness table has two rows touching what's described here, at different
granularity. The combined row "Offline mode / checksums / signing (Phase
10, 20)" is labeled **production ready**: "real, tested, applied
uniformly, real end-to-end signature verification against all installed
models." A separate row, "Security / signing (Phase 20)," is labeled
**production candidate for model signing; not started for secure boot**:
the signing itself is real and tested, but secure boot (verifying a
signature against a boot ROM or secure element before running untrusted
code) needs physical hardware this environment doesn't have, consistent
with `docs/firmware.md`'s **production candidate** label for the same
Phase 20 signing logic. Model *content* quality (translation accuracy per
language pair, ASR accuracy, TTS quality) is a separate axis covered by
`docs/commercial-product-architecture.md`'s pipeline-stage rows, not by
this document.

The licensing gap described above is not reflected in that readiness
framework - it's a legal/compliance open item layered on top of code that
is otherwise production-ready or production-candidate, and should be
tracked and closed independently of the engineering readiness label.
