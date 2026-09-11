import hashlib

import pytest

from core.security.package_signing import (
    PackageSignature,
    generate_signing_keypair,
    sign_digest,
    verify_digest,
)


def make_digest(data: bytes = b"fake model bytes") -> str:
    return hashlib.sha256(data).hexdigest()


def test_generate_signing_keypair_returns_pem_strings():
    private_pem, public_pem = generate_signing_keypair()
    assert "BEGIN PRIVATE KEY" in private_pem
    assert "BEGIN PUBLIC KEY" in public_pem


def test_sign_and_verify_roundtrip():
    private_pem, public_pem = generate_signing_keypair()
    digest = make_digest()
    signature = sign_digest(digest, private_pem, key_id="dev-key-1")
    assert verify_digest(digest, signature, public_pem) is True


def test_verify_fails_for_tampered_digest():
    private_pem, public_pem = generate_signing_keypair()
    signature = sign_digest(make_digest(b"original"), private_pem, key_id="dev-key-1")
    tampered_digest = make_digest(b"tampered")
    assert verify_digest(tampered_digest, signature, public_pem) is False


def test_verify_fails_for_wrong_public_key():
    private_pem, _ = generate_signing_keypair()
    _, other_public_pem = generate_signing_keypair()
    digest = make_digest()
    signature = sign_digest(digest, private_pem, key_id="dev-key-1")
    assert verify_digest(digest, signature, other_public_pem) is False


def test_verify_fails_for_corrupted_signature_bytes():
    private_pem, public_pem = generate_signing_keypair()
    digest = make_digest()
    signature = sign_digest(digest, private_pem, key_id="dev-key-1")
    corrupted = PackageSignature(signature_b64="AAAA" + signature.signature_b64[4:], key_id="dev-key-1")
    assert verify_digest(digest, corrupted, public_pem) is False


def test_signature_carries_key_id_for_rotation():
    private_pem, _ = generate_signing_keypair()
    signature = sign_digest(make_digest(), private_pem, key_id="at-signing-key-2026-09")
    assert signature.key_id == "at-signing-key-2026-09"
    assert signature.algorithm == "ed25519"


def test_reject_non_ed25519_private_key_pem():
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rsa_pem = rsa_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode("ascii")
    with pytest.raises(TypeError, match="Ed25519"):
        sign_digest(make_digest(), rsa_pem, key_id="wrong-type")
