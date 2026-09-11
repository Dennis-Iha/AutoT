"""Phase 20: signs every entry in the ASR/translation/TTS model manifests
with a development Ed25519 keypair, demonstrating core/security/
package_signing.py against this project's real, already-checksummed
models (Phase 10) rather than only synthetic test bytes.

The generated keypair is written under .dev_signing_key/ (gitignored) -
this is explicitly a DEVELOPMENT key, not a production AT signing key (no
production AT deployment exists). Re-running this script reuses the
existing dev key if present, so re-signing after a model changes doesn't
silently rotate keys.

Usage:
    python -m tools.sign_model_manifests
    python -m tools.verify_model_manifests   # separate script, see below
"""

from __future__ import annotations

import json
from dataclasses import asdict

from core.common.config import REPO_ROOT
from core.security.package_signing import generate_signing_keypair, sign_digest

KEY_DIR = REPO_ROOT / ".dev_signing_key"
KEY_ID = "dev-key-1"

MANIFESTS = [
    (REPO_ROOT / "models" / "registry" / "asr_models.json", "models"),
    (REPO_ROOT / "models" / "registry" / "translation_models.json", "models"),
    (REPO_ROOT / "models" / "registry" / "tts_voices.json", "voices"),
]


def load_or_create_dev_keypair() -> tuple[str, str]:
    KEY_DIR.mkdir(exist_ok=True)
    private_path = KEY_DIR / "private.pem"
    public_path = KEY_DIR / "public.pem"
    if private_path.exists() and public_path.exists():
        return private_path.read_text(), public_path.read_text()
    private_pem, public_pem = generate_signing_keypair()
    private_path.write_text(private_pem)
    public_path.write_text(public_pem)
    print(f"Generated new dev signing keypair at {KEY_DIR}")
    return private_pem, public_pem


def main() -> int:
    private_pem, _ = load_or_create_dev_keypair()

    for manifest_path, list_key in MANIFESTS:
        if not manifest_path.exists():
            print(f"skip (not found): {manifest_path}")
            continue
        data = json.loads(manifest_path.read_text())
        signed_count = 0
        for entry in data[list_key]:
            sha256 = entry.get("sha256")
            if not sha256:
                continue
            signature = sign_digest(sha256, private_pem, key_id=KEY_ID)
            entry["signature"] = asdict(signature)
            signed_count += 1
        manifest_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"signed {signed_count} entr(y/ies) in {manifest_path.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
