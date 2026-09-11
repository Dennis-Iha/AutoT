"""Phase 29: the network half of OTA model updates - deliberately kept out
of core/ota/model_updater.py (which has zero network dependencies, matching
core/'s documented zero-network property - see docs/privacy.md) the same
way tools/setup_*.sh already keep real network downloads out of core/.

Talks to the AT backend's real GET /models and GET /models/{id}/download
endpoints (backend/routes/models.py, Phase 29), stages each download into
the target's own install directory (same filesystem as the final install
path - required for core.ota.model_updater.apply_update's atomic
os.replace), then verifies checksum + signature and installs.

Requires the `ota` optional dependency group (httpx) - deliberately NOT the
full `backend` group, since a device running this client tool has no need
for fastapi/uvicorn/sqlalchemy:
    pip install -e ".[ota]"

Usage:
    python -m tools.ota_download_and_apply --base-url http://127.0.0.1:8000
    python -m tools.ota_download_and_apply --model-id argos-es-en-1.9
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import httpx

from core.common.model_manifest import verify_checksum
from core.ota.model_updater import UpdateTarget, apply_update, resolve_update_targets
from tools.sign_model_manifests import KEY_DIR


def needs_update(target: UpdateTarget) -> bool:
    return not (target.install_path.exists() and verify_checksum(target.install_path, target.expected_sha256))


def download_one(client: httpx.Client, base_url: str, target: UpdateTarget) -> Path:
    target.install_path.parent.mkdir(parents=True, exist_ok=True)
    fd, staged_str = tempfile.mkstemp(dir=target.install_path.parent, suffix=".download")
    staged = Path(staged_str)
    with open(fd, "wb") as out, client.stream("GET", f"{base_url}/models/{target.id_}/download") as resp:
        resp.raise_for_status()
        out.writelines(resp.iter_bytes())
    return staged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--model-id", default=None, help="update only this model_id (default: all stale/missing)")
    parser.add_argument("--public-key", default=str(KEY_DIR / "public.pem"))
    args = parser.parse_args()

    public_key_path = Path(args.public_key)
    public_key_pem = public_key_path.read_text() if public_key_path.exists() else None
    if public_key_pem is None:
        print(f"warning: no public key at {public_key_path} - signed entries will fail closed", file=sys.stderr)

    targets = resolve_update_targets()
    if args.model_id:
        targets = [t for t in targets if t.id_ == args.model_id]
        if not targets:
            print(f"unknown model_id: {args.model_id}", file=sys.stderr)
            return 1
    else:
        targets = [t for t in targets if needs_update(t)]

    if not targets:
        print("nothing to update - all known models are already installed and verified")
        return 0

    exit_code = 0
    with httpx.Client() as client:
        for target in targets:
            print(f"[{target.kind}] {target.id_}: downloading from {args.base_url} ...")
            try:
                staged = download_one(client, args.base_url, target)
            except httpx.HTTPError as e:
                print(f"[{target.kind}] {target.id_}: download failed: {e}", file=sys.stderr)
                exit_code = 1
                continue

            result = apply_update(target, staged, public_key_pem)
            staged.unlink(missing_ok=True)  # apply_update already moved it on success; this is a no-op then
            if result.ok:
                print(f"[{target.kind}] {target.id_}: {result.status}")
            else:
                print(f"[{target.kind}] {target.id_}: FAILED - {result.error}", file=sys.stderr)
                exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
