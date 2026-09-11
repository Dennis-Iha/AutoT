"""Phase 10: shared model manifest primitives - checksum computation and
verification used by every model registry (ASR, translation, TTS).

Exists because of a real, already-encountered failure class: Phase 7 hit a
silently truncated model download (27MB of an expected 63MB file) that
onnxruntime reported as an opaque "Protobuf parsing failed" rather than a
clear "this file is wrong" error. That was patched locally in
tools/setup_tts_models.sh with a Content-Length size check at download
time. Checksums are the general, permanent fix: verifiable at ANY time
(not just immediately after download - a disk error, an interrupted git-lfs
pull, or manual tampering could corrupt a file long after it was
successfully downloaded), and uniform across all three model registries
instead of three different ad-hoc checks.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def compute_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Streams the file in chunks rather than reading it whole - model
    files run into the hundreds of MB (see docs/roadmap.md's Phase 6/7
    notes), and this is called at startup, not just once after download."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def verify_checksum(path: Path, expected_sha256: str) -> bool:
    if not path.exists():
        return False
    return compute_sha256(path) == expected_sha256.lower()
