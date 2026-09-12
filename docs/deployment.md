# AT (AutoT) — Deployment

Phase 33. `docs/backend.md` already points here for "the history of where
(if anywhere) this backend has run" — this is that document. It
deliberately keeps **current reality** (verified today, in this
environment) and **target** (the master spec's eventual deployment model,
not built) in separate sections rather than blending them, because nothing
below the "Current" heading has actually shipped anywhere.

## Current: where this actually runs today

Nothing in this codebase is deployed anywhere except this local dev
workstation. There is no server, cloud VM, or container running AT
software outside this environment. Verified by searching the repository
tree: no `docker-compose.yml`, no Kubernetes manifests, no Terraform or
other cloud-IaC files, and no Fly.io/Heroku/Vercel/AWS/GCP/Azure
configuration of any kind exist anywhere in this repo.

### Backend process

The only documented way to run the backend (`README.md`) is:

```bash
pip install -e ".[backend]"
uvicorn backend.main:app --reload
```

a single local process on `127.0.0.1:8000`. It reads/writes a SQLite file
database — `backend/database.py`'s `DATABASE_URL` defaults to
`sqlite:///./at_backend.db` — and the repo root currently has two such
files sitting next to the code (`at_backend.db`, `at_backend_ota_demo.db`),
which is itself evidence of local-only runs rather than a hosted instance:
a real deployment wouldn't leave its database file checked into a
developer's working tree. `database.py`'s own docstring frames SQLite as
explicitly a "start simple" choice with an `AT_DATABASE_URL` env-var swap
point to PostgreSQL later — but nothing in this environment has ever set
that variable to anything but the SQLite default; the swap point exists in
code, unused in practice.

### Containerization

`docker/Dockerfile.dev` exists, but its own header comment is explicit
about what it is: "This is a dev environment image, not a
production/embedded image." It builds a CPU-only `debian:trixie-slim`
image, installs the `[dev]` extras, and its `CMD` runs `pytest -v` — a
test-runner container for reproducing the dev toolchain, not a deployable
service image. There is no Dockerfile for the backend itself, no
`docker-compose.yml`, and no evidence anywhere in the repo of an image ever
having been built for deployment or pushed to a registry.

### TLS / HTTPS

None configured, verified independently for this document by grepping
`backend/` for `tls`, `ssl`, `https`, and `cert` (case-insensitive): the
only hits are in `backend/auth.py`'s docstring, and they're about the
unrelated passlib/bcrypt version-sniffing bug, not transport security —
there is no TLS code anywhere in `backend/`. This matches
`docs/security.md`'s own dedicated section on the subject ("TLS /
encrypted transport for the backend — genuinely absent, confirmed by
grep"), which additionally checked `docker/Dockerfile.dev` and
`pyproject.toml` and found nothing there either. The dev server above
serves plain HTTP only. `docs/security.md` rates this **not started** and
calls it a hard requirement before any deployment beyond a local
workstation, since JWT tokens and login credentials would cross the
network in plaintext otherwise — that assessment holds; this document
adds no new information on it, just confirms it from the deployment angle.

## CI: what `.github/workflows/ci.yml` does today

Read directly from the file as it exists right now (rewritten in this same
Phase 33 audit). One job, `test`, on `ubuntu-latest`, triggered on push or
PR to `main`:

1. Checks out the repo, sets up Python 3.13.
2. Caches `third_party/whisper.cpp`, `models/asr/whisper`,
   `models/translation/argos`, and `models/tts/piper`, keyed on the setup
   scripts' contents.
3. Installs system packages needed for audio/native builds (`build-essential
   cmake pkg-config portaudio19-dev libsndfile1-dev`) via `apt-get`.
4. Installs Python dependencies with
   `python -m pip install -e ".[dev,backend,ota]"` — all three extras, not
   just `[dev]`.
5. Builds whisper.cpp and downloads a deliberately minimal real model set —
   whisper `tiny`/`base`, the `es-en`/`en-es` translation pair, and the
   `en_US-amy-medium` TTS voice — via `tools/setup_whisper_cpp.sh`,
   `tools/setup_translation_models.sh`, `tools/setup_tts_models.sh`. The
   workflow's own comment explains the scope choice: this is the one
   language pair and voice this project's Phase 8/30 testing has actually
   verified produce correct end-to-end output, not all 9 languages, which
   would make CI "prohibitively slow/network-heavy." Every real/live test
   gracefully skips if these assets aren't present, so this step failing
   degrades coverage rather than hard-failing the run.
6. Lints with `python -m ruff check core tools tests backend`.
7. Type-checks with `python -m mypy core tools backend`.
8. Tests with `python -m pytest -v`.

### The bug this audit found and fixed in that same file

Before this audit, step 4 ran `python -m pip install -e ".[dev]"` only,
step 6 ran `ruff check core tools tests` (no `backend`), and step 7 ran
`mypy core tools` (no `backend`) — confirmed by diffing the file's git
history, not just reading the current version's comment. `backend`'s real,
required dependencies (`fastapi`, `sqlalchemy`, `bcrypt`, `pyjwt`, `httpx`,
`python-multipart`, `email-validator` — see the `[project.optional-dependencies]`
table in `pyproject.toml`) were therefore never installed in CI, which
means `tests/backend/` and `tests/tools/test_metrics_report.py` would have
failed to even *import*, let alone pass, and `backend/` was never linted or
type-checked at all. The fix — installing `[dev,backend,ota]` and adding
`backend` to both the ruff and mypy invocations — is real and present in
the current file (commit `b63c30a`). It has not yet been confirmed to pass
on GitHub's own infrastructure, for the separate reason below.

## Two separate problems — do not conflate them

### Problem 1: GitHub Actions will not run for this repo at all (unresolved)

Verified this session with `gh run list --limit 30`: it returns exactly 15
runs total — the complete recorded Actions history for this repo, from the
oldest (`Phase 4/5/6: language ID, ASR, and translation...`,
2026-09-11T17:46:02Z) to the newest (`Phase 32 + CI fix: ...`,
2026-09-12T00:45:42Z, triggered by this same audit's own commit). Every
single one shows `completed` / `startup_failure` / a duration of `0s`.
Spot-checking the most recent run with
`gh api repos/Dennis-Iha/AutoT/actions/runs/34662698904/jobs` returns
`{"total_count":0,"jobs":[]}` — zero jobs were ever scheduled for it. That
is the actual signature of the problem: not a workflow that parsed and
then failed a step, but Actions apparently refusing to schedule any job at
all, for every run this repo has ever had. `gh run view` prints a generic
"This run likely failed because of a workflow file issue" message, but
that's a canned heuristic string and doesn't match a 0-jobs-scheduled
result — a real YAML/workflow syntax error normally still produces one
failed job pointing at the bad line, which none of these 15 runs has.

This could not be diagnosed further with this session's current
credentials: `gh auth status` shows the authenticated token's scopes as
`gist, read:org, repo, workflow` — enough to list runs and read workflow
files (which is how the above was confirmed), not enough to view the
account's billing or Actions-permissions settings, which live behind
GitHub's web Settings UI rather than behind any scope these API tokens
expose. **This needs the repository owner to check GitHub's own Settings →
Billing and Settings → Actions pages for the account this repo lives
under.** Prior audits of this repo had already flagged the block as
present since at least Phase 12; this session's check goes further and
shows it's present across the repo's *entire* recorded Actions history —
there is no run on record, at any phase, that ever scheduled a job.

This is an account/platform-level block, not anything wrong with AT's own
code, tests, or (as of this audit) the workflow file's content.

### Problem 2: the workflow file had its own independent bug (fixed, unverified in CI)

Separately from Problem 1, the "CI section" above describes a real bug
that existed in `.github/workflows/ci.yml` regardless of whether Actions
ever ran it: only `[dev]` extras were installed, so `backend/` was
invisible to lint, type-check, and even test collection. That bug is fixed
in the file as it exists now. Because of Problem 1, the fix has not yet
been confirmed by an actual green (or red) run on GitHub's infrastructure —
it is correct by reading, not yet correct by observed CI execution. These
are two distinct failures with two distinct remedies: Problem 1 needs a
GitHub account/billing-settings fix only the repo owner can make; Problem 2
was a code/config bug in this repo, already fixed, and will only be
*provably* fixed once Problem 1 is resolved and a run actually executes
jobs.

## Target (per the master spec) — not built

Two separate deployment targets exist in the master spec. Neither is built;
this section is a statement of intent, not progress.

### Backend: a real cloud control-plane

`backend/main.py`'s own module docstring names the target directly:

> Phase 19: AT control-plane backend (api.autot.ai in the master spec).

Nothing about reaching `api.autot.ai` — DNS, hosting, a real PostgreSQL
instance, a reverse proxy terminating TLS, secrets management for
`AT_JWT_SECRET` (currently a dev-placeholder default per `backend/auth.py`,
per `docs/security.md`) — exists yet. The code's own readiness, per
`docs/commercial-product-architecture.md`'s matrix, is **production
candidate** ("real, tested FastAPI+SQLAlchemy service; SQLite is a dev/test
choice, not a scaling decision") — but that rating is about code quality
and test coverage, explicitly not about deployment, which this document
treats as a separate, currently-unstarted axis: hosting, TLS, a production
database, and secret management are all **not started**.

### Device: a microSD-booted OS image on the headphone/earbud hardware — not Docker, not a server

The device-side deployment target is not a server deployment at all: it's
an OS image booted from microSD, running directly on the physical
headphone/earbud hardware. This is stated explicitly in this project's own
hardware documents, not inferred: `hardware/pcb-and-miniaturization.md`
names "microSD boot support, matching this project's actual deployment
target (an OS image booted from microSD on the headphone hardware itself,
per the project's hardware-target notes)" as a real PCB requirement, and
`hardware/hardware-selection.md` gives the same reasoning for recommending
a devkit that "boots from microSD by default... a microSD-booted system on
the eventual headphone hardware." `docs/roadmap.md` and `docs/firmware.md`
both cite the same microSD-boot-by-default property as a reason the
Jetson Orin Nano Super devkit is the right *development* platform to start
physical validation with. None of this has happened yet — no physical
board has been acquired or booted in this environment (`hardware/hardware-selection.md`
is desk research, "pending physical validation").

This target is explicitly **dual-purpose**: the hardware must run
Bluetooth media playback (A2DP sink) alongside translation, not
translation alone. This is a real, separately tracked gap, not an
oversight — `hardware/AT-H1-headphone-prototype.md`'s own "what's actually
proven vs. what's designed on paper" table lists "Bluetooth media playback
alongside translation" as "NOT implemented or tested - the hardware
target's dual-purpose requirement... is a known gap," and
`hardware/pcb-and-miniaturization.md` repeats the same point: a Bluetooth
companion chip supporting A2DP sink is a real PCB requirement precisely
*because* "this project's hardware target explicitly requires solid
dual-purpose (translation + Bluetooth media) operation, which nothing in
this codebase has implemented or tested yet." Nothing in `core/` today
touches Bluetooth or media playback at all — the dual-purpose requirement
exists only as a documented hardware constraint, with zero corresponding
software.

Per this project's own readiness framework, device deployment itself is
**not started**: no physical hardware exists to boot anything on
(`docs/hardware.md`'s own build-stage table shows every physical hardware
stage from the AT-H1 prototype onward as undone), so the question of
whether an AT microSD image even boots, let alone runs the `core/`
pipeline and Bluetooth media concurrently, has not been reached. The
software that image would eventually run — VAD, ASR, translation, TTS,
dual-earbud coordination — is already real and tested on a workstation CPU
(engineering prototype to production candidate, component by component,
per `docs/commercial-product-architecture.md`'s matrix); porting it onto
booted, microSD-based device hardware is the unstarted step this section
describes.
