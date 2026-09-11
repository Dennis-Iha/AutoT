"""Phase 20: cryptographic signing/verification for model packages.

Extends Phase 10's checksums (which prove a file wasn't corrupted/
truncated) with Ed25519 signatures (which prove a file was published by
someone holding AT's private signing key, not just that its bytes are
internally consistent) - the difference matters because a checksum alone
can't stop a malicious actor from distributing a DIFFERENT model with its
OWN correct checksum recorded alongside it; a signature can, as long as the
verifying device's copy of the public key is trustworthy.

Signs the SHA256 digest (already computed by core.common.model_manifest),
not the raw file bytes - avoids re-reading potentially-hundreds-of-MB model
files a second time just to sign them.

No production AT signing key exists (there is no production AT deployment)
- `generate_signing_keypair()` is for development/testing only. A real
deployment's private key must live in an HSM or equivalent, never in this
repository or its tests.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
    load_pem_public_key,
)


@dataclass(frozen=True)
class PackageSignature:
    signature_b64: str
    key_id: str
    algorithm: str = "ed25519"


def generate_signing_keypair() -> tuple[str, str]:
    """Returns (private_key_pem, public_key_pem). Dev/test use only - see
    module docstring."""
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
    ).decode("ascii")
    public_pem = private_key.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    ).decode("ascii")
    return private_pem, public_pem


def sign_digest(sha256_hex: str, private_key_pem: str, key_id: str) -> PackageSignature:
    private_key = load_pem_private_key(private_key_pem.encode("ascii"), password=None)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("private_key_pem must be an Ed25519 key")
    signature = private_key.sign(bytes.fromhex(sha256_hex))
    return PackageSignature(signature_b64=base64.b64encode(signature).decode("ascii"), key_id=key_id)


def verify_digest(sha256_hex: str, signature: PackageSignature, public_key_pem: str) -> bool:
    public_key = load_pem_public_key(public_key_pem.encode("ascii"))
    if not isinstance(public_key, Ed25519PublicKey):
        raise TypeError("public_key_pem must be an Ed25519 key")
    try:
        public_key.verify(base64.b64decode(signature.signature_b64), bytes.fromhex(sha256_hex))
        return True
    except InvalidSignature:
        return False
