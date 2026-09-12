# AT (AutoT) — Security: Package Integrity, Authenticity, and Auth

Phase 20 (model package signing) and Phase 29 (OTA update system), plus
Phase 19's backend authentication. This document is the security reference:
what cryptographic and authentication mechanisms actually exist in this
codebase, verified against the code, versus what is designed-only or not
built at all. It is distinct from `docs/privacy.md`, which covers what
happens to a user's *speech data* (network calls, disk writes, retention,
logging) — this document does not repeat that data-flow content; see
`docs/privacy.md` for it.

## 1. Model package integrity and authenticity

Two independent layers protect a model file before it is trusted, built in
two different phases for two different reasons.

### Phase 10: SHA256 checksums (integrity)

`core/common/model_manifest.py` computes and verifies SHA256 checksums,
streamed in 1MB chunks. Every entry in the three model registries
(`models/registry/asr_models.json`, `models/registry/translation_models.json`,
`models/registry/tts_voices.json`) carries a `sha256` field computed from
the real file on disk. This protects against *corruption* — Phase 7's real
incident (a parallel download silently produced a truncated 27MB file for
an expected 63MB TTS model) is exactly the failure class this catches: a
checksum mismatch is now a clear, immediate rejection instead of an opaque
downstream error from onnxruntime.

A checksum alone does not protect against *substitution*: a malicious actor
who can replace a model file can also recompute and republish a matching
checksum alongside it. That gap is what signing closes.

### Phase 20: Ed25519 signatures (authenticity)

`core/security/package_signing.py` adds Ed25519 signing/verification on top
of the checksums. Its module docstring states the distinction directly:
a signature proves a file was published by whoever holds AT's private
signing key, "as long as the verifying device's copy of the public key is
trustworthy" — signing does not eliminate the need for a trustworthy public
key distribution path, it shifts the trust problem there.

Key implementation details, read from the code:

- `sign_digest()` and `verify_digest()` operate on the SHA256 hex digest
  (`bytes.fromhex(sha256_hex)`) already computed by
  `core.common.model_manifest` — **not the raw file bytes**. The module
  docstring gives the reason: it avoids re-reading a potentially
  hundreds-of-MB model file a second time just to sign it. This means the
  signature's integrity guarantee is only as strong as the checksum's — a
  signature over a wrong or stale digest would be worse than no signature,
  which is why `tools/verify_model_manifests.py` always re-verifies both
  the checksum and the signature, never the signature alone.
- `PackageSignature` is a frozen dataclass: `signature_b64`, `key_id`,
  `algorithm` (default `"ed25519"`).
- `generate_signing_keypair()` returns a PEM-encoded Ed25519 keypair, and
  its docstring is explicit that this is **development/testing use only**.
  There is no production AT signing key in this repository, because there
  is no production AT deployment — the module comment states a real
  deployment's private key "must live in an HSM or equivalent, never in
  this repository or its tests."
- `sign_digest`/`verify_digest` both type-check the key with `isinstance`
  and raise `TypeError` (not a silent no-op or a generic exception) if
  handed a non-Ed25519 key, so passing e.g. an RSA key by mistake fails
  loudly.

`tests/security/test_package_signing.py` covers the roundtrip, tampered-
digest rejection, wrong-public-key rejection, corrupted-signature-byte
rejection, key-id rotation, and rejection of a non-Ed25519 (RSA) key.

### Signing and verifying the real registries end to end

`tools/sign_model_manifests.py` and `tools/verify_model_manifests.py` are
not synthetic demonstrations — they run the above logic against this
project's actual, already-checksummed model registry entries:

- `sign_model_manifests.py`'s `load_or_create_dev_keypair()` writes (or
  reuses, if already present) a development keypair at `.dev_signing_key/`
  — `private.pem` and `public.pem`. This directory is listed in
  `.gitignore` (confirmed: `.gitignore` contains `.dev_signing_key/`) so
  the dev private key is never committed. Re-running the script reuses the
  existing key rather than rotating it silently, so re-signing after a
  model changes doesn't invalidate previously-distributed signatures for
  no reason. `KEY_ID = "dev-key-1"` is hardcoded as the current dev key's
  identifier.
- It iterates all three manifests (`asr_models.json`, `translation_models.json`
  with list key `"models"`, and `tts_voices.json` with list key `"voices"`)
  and writes a `signature` object (the serialized `PackageSignature`) into
  every entry that has a `sha256`.
- `verify_model_manifests.py` loads the dev public key, then for every
  entry with a `signature` field, re-verifies both the checksum
  (implicitly, by verifying the signature against the same `sha256` field
  the checksum-verification path uses) and the Ed25519 signature, printing
  `[OK]`/`[FAIL]` per entry and `[NO SIGNATURE]` for any entry that has
  none.

Counting the real registries as they exist in this repo today: the ASR
registry (`models/registry/asr_models.json`) has 3 entries, the translation
registry (`models/registry/translation_models.json`) has 16 entries (8
language pairs × 2 directions, per Phase 17's bidirectional extension), and
the TTS voice registry (`models/registry/tts_voices.json`) has 1 entry — 20
entries total, matching `docs/roadmap.md`'s Phase 20 section ("signs every
one of the 20 real entries ... all 20 pass"). This was re-confirmed for
this document by reading the registry files directly, not by trusting the
roadmap's prior count.

**Status**: model package integrity (Phase 10 checksums) and authenticity
(Phase 20 signatures) are **production candidate** — real, tested logic,
applied uniformly to every real installed model entry, but never yet
exercised as part of a real production release process (there is no
production signing key, and no shipped device to receive a signed
package). This matches `docs/commercial-product-architecture.md`'s
readiness table, which labels "Offline mode / checksums / signing (Phase
10, 20)" **production ready** at the logic level while separately marking
secure boot **not started** (see §3 below) — the two are graded
independently because they are different problems.

## 2. OTA updates reuse this, and fail closed

`core/ota/model_updater.py` (Phase 29) is the client-side installer that
sits on top of both of the above. Its module docstring names the exact
failure it exists to prevent: Phase 7's real incident again, generalized —
"a downloaded/staged package is checksum-verified, then signature-verified
(when the manifest carries one), and ONLY THEN atomically swapped into the
live install path via `os.replace`."

Reading `apply_update()` directly, the check order is:

1. `staged_path.exists()` — reject if the staged file is simply missing.
2. `verify_checksum(staged_path, target.expected_sha256)` — reject on
   mismatch (`"checksum mismatch - staged file rejected"`).
3. **Only if `target.signature is not None`** (i.e. the manifest entry for
   this model was signed): if `public_key_pem` is `None`, `apply_update`
   returns a `"failed"` result with error `"manifest entry is signed but no
   public key was provided to verify against"` — it does **not** fall back
   to checksum-only and proceed. If a public key *is* provided, it calls
   `verify_digest()` and rejects on signature failure
   (`"signature verification failed - staged file rejected"`).
4. Only after every check above passes does it call `os.replace(staged_path,
   target.install_path)` — an atomic swap (atomic only within a single
   filesystem/mount, which is why callers must stage on the same
   filesystem as the install path).

This is the fail-closed property the task of writing this document was
specifically asked to confirm by reading the code rather than assuming it:
a signed manifest entry with no supplied public key is a **hard failure**,
not a silent degrade to checksum-only trust. The function's own docstring
states this as a design rule: "a caller must not be able to accidentally
skip signature verification just by forgetting to pass a key." If any
check fails, `target.install_path` is left completely untouched — the
existing installed model, if any, keeps working.

`tests/ota/test_model_updater.py` (9 tests) exercises this, including one
test that runs the real verify-then-install pipeline against a genuinely
currently-installed translation model's real checksum and real Phase 20
signature — not synthetic test data. `backend/routes/models.py`'s
`GET /models/{model_id}/download` plus `tools/ota_download_and_apply.py`
close the loop with an actual network transport, smoke-tested against a
live `uvicorn` instance of the backend on the development workstation (see
`docs/roadmap.md`'s Phase 29 section for the exact smoke-test result,
including an honestly-recorded environment limitation from the backend and
device sharing one filesystem in this single-machine dev setup).

**Status**: **production candidate** — real, tested checksum+signature+
atomic-swap logic with a working network transport, but (like §1) never
run on real device hardware, only on this workstation and a local backend.

## 3. Backend authentication

`backend/auth.py` (Phase 19) implements password hashing and JWT issuance
for the FastAPI backend's `/auth/register` and `/auth/login` endpoints
(`backend/routes/auth.py`).

- **Password hashing**: `bcrypt.hashpw()` / `bcrypt.checkpw()`, called
  directly — not through passlib's `CryptContext`. The module's docstring
  documents exactly why, and it's a real bug this project hit, not a
  hypothetical: passlib 1.7.4 (last released 2020, effectively
  unmaintained) probes `bcrypt.__about__.__version__` to detect which
  bcrypt backend is installed; the `bcrypt` version this environment has
  installed (5.0.0) no longer exposes that attribute, so passlib's
  version-sniffing silently mis-detects the backend and then raises
  `"password cannot be longer than 72 bytes"` — even for an 8-character
  password. `docs/roadmap.md`'s Phase 19 section confirms this was an
  actually-encountered failure during development, fixed by dropping
  passlib and calling `bcrypt` directly, which sidesteps the broken
  detection entirely.
- **Tokens**: PyJWT (`jwt.encode`/`jwt.decode`), HS256, with a 24-hour
  expiry (`ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24`). `create_access_token()`
  embeds the user id as `sub` and an expiry as `exp`; `decode_access_token()`
  and `get_current_user()` (a FastAPI dependency) validate and raise a 401
  on any `jwt.PyJWTError` (expired, tampered, or malformed token) or an
  unknown user id.
- **Signing secret**: `SECRET_KEY = os.environ.get("AT_JWT_SECRET",
  "dev-only-insecure-secret-do-not-use-in-production")` — read directly
  from the source. The module docstring states this default is
  "explicitly a dev-only placeholder," and that the real secret "MUST come
  from the environment in any real deployment." Running the backend today
  without setting `AT_JWT_SECRET` uses that hardcoded placeholder string as
  the actual HS256 signing key.

`tests/backend/test_auth.py` covers registration, duplicate-email
rejection, login issuing a token, and wrong-password rejection; the
hashed password is confirmed never present in the register response body.

**Status**: **production candidate** — real, tested, standard primitives
(bcrypt, PyJWT), but running with a hardcoded dev secret by default and no
secret-rotation or revocation mechanism; a real deployment must supply
`AT_JWT_SECRET` itself.

## 4. What is NOT built

Named explicitly and honestly, mapped to the master spec's Phase 20 name,
**"secure boot, signed firmware, encrypted comms"** — of that three-part
name, only the model-signing piece above is done; the other two are not:

### Secure boot / signed firmware boot verification — design doc only

Proving that the bootloader, OS image, and drivers themselves haven't been
tampered with, verified by a hardware root of trust (a boot ROM or secure
element with its own immutable key storage) *before* any of that code —
including the Python interpreter that runs `core/security/package_signing.py`
— is trusted to run at all. This needs physical hardware this project does
not have (no committed SoC — Phase 12 is still pending physical
validation). `firmware/architecture.md` covers this as a design document
only, and `docs/firmware.md` states the distinction between this and
package signing directly: "Secure boot (not designed, needs hardware)"
versus "Package signing (done, in software)," and marks secure boot's
readiness as **not started** in its own readiness table. This document
defers to `docs/firmware.md` for the full explanation of that distinction
rather than repeating it — the short version is that Phase 20's signing
logic is a necessary building block for a future secure-boot/secure-OTA
story, but is not itself secure boot, and nothing in this repository
implements the latter.

### TLS / encrypted transport for the backend — genuinely absent, confirmed by grep

The backend (`backend/main.py`) is a FastAPI app with no TLS configuration
anywhere in this codebase. This was confirmed, not assumed: grepping
`backend/` for `ssl`, `tls`, `https`, and `cert` (case-insensitive) across
every Python file turns up nothing real — the only hits are incidental
substring matches of "passlib" (which literally contains "ssl") in
`backend/auth.py`'s docstring about the bcrypt/passlib incident; there is
no `ssl_certfile`/`ssl_keyfile` argument, no HTTPS redirect middleware,
nothing. The only documented way to
run it (`README.md`) is:

```bash
uvicorn backend.main:app --reload
```

which serves plain HTTP on `127.0.0.1:8000`. `docker/Dockerfile.dev` and
`pyproject.toml` were also checked for any TLS/SSL/certificate setup
(reverse proxy config, cert dependencies) — none exists there either. Every
smoke test this project has run against a live backend throughout this
build — Phase 29's OTA download/apply smoke test, Phase 31's metrics
report smoke test — has talked to that same plain-HTTP dev server. There
is no reverse proxy, no TLS-terminating load balancer, and no encrypted
device-to-backend or device-to-device (Phase 16 coordination channel)
transport of any kind in this repository today. JWT tokens and login
credentials, as currently implemented, would cross the network in
plaintext if this backend were reachable over anything but `localhost`.

**Status**: **not started**. This is a hard requirement before any real
deployment beyond a local development workstation — running the current
`backend/` as-is on a public network would expose credentials and tokens
in transit.

## Summary

| Claim | Status | Basis |
|---|---|---|
| Model checksums (Phase 10) | production candidate | `core/common/model_manifest.py`, applied to all real registry entries |
| Model signatures (Phase 20) | production candidate | `core/security/package_signing.py`, signs the digest not raw bytes, dev-only key at `.dev_signing_key/` (gitignored), 7 unit tests + real end-to-end verification of all 20 real entries |
| OTA update fails closed on missing key | verified by reading `apply_update()` | signed-but-no-key is a hard rejection, never a silent checksum-only fallback |
| OTA atomic install (Phase 29) | production candidate | `core/ota/model_updater.py`, 9 tests, real backend download loop |
| Backend password hashing | production candidate | `bcrypt` direct (passlib bypassed after a real 5.0.0 incompatibility bug) |
| Backend JWT auth | production candidate | PyJWT, HS256, but dev-placeholder secret by default |
| Secure boot / signed firmware | **not built** | needs physical boot ROM/secure element; `firmware/architecture.md` design doc only |
| TLS/encrypted backend transport | **not built** | confirmed by grep — no TLS/SSL/HTTPS setup anywhere in `backend/`, `docker/`, or `pyproject.toml`; dev server runs plain HTTP |

See `docs/privacy.md` for what happens to speech data (network calls, disk
writes, logging, retention) and `docs/commercial-product-architecture.md`
for how these readiness labels roll up into the overall product readiness
matrix.
