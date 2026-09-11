"""Phase 20: verifies every signed entry in the model manifests against the
dev public key, and re-verifies the underlying SHA256 checksum too (a
signature over a stale/wrong digest would be worse than no signature at
all - both must check out).

Usage: python -m tools.verify_model_manifests
"""

from __future__ import annotations

import json

from core.security.package_signing import PackageSignature, verify_digest
from tools.sign_model_manifests import KEY_DIR, MANIFESTS


def main() -> int:
    public_path = KEY_DIR / "public.pem"
    if not public_path.exists():
        print(f"no dev public key at {public_path} - run tools/sign_model_manifests.py first")
        return 1
    public_pem = public_path.read_text()

    all_ok = True
    for manifest_path, list_key in MANIFESTS:
        if not manifest_path.exists():
            continue
        data = json.loads(manifest_path.read_text())
        for entry in data[list_key]:
            model_id = entry.get("model_id") or entry.get("voice_id")
            sig_data = entry.get("signature")
            if sig_data is None:
                print(f"  [NO SIGNATURE] {model_id}")
                continue
            signature = PackageSignature(**sig_data)
            ok = verify_digest(entry["sha256"], signature, public_pem)
            print(f"  [{'OK' if ok else 'FAIL'}] {model_id} (key={signature.key_id})")
            all_ok = all_ok and ok

    print("\nAll signatures valid." if all_ok else "\nSome signatures FAILED verification.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
