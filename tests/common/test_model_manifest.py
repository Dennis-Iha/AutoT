import hashlib

import pytest

from core.common.model_manifest import compute_sha256, verify_checksum


def test_compute_sha256_matches_hashlib_directly(tmp_path):
    path = tmp_path / "model.bin"
    data = b"fake model weights " * 1000
    path.write_bytes(data)
    expected = hashlib.sha256(data).hexdigest()
    assert compute_sha256(path) == expected


def test_compute_sha256_handles_files_larger_than_chunk_size(tmp_path):
    path = tmp_path / "big.bin"
    data = bytes(range(256)) * 10000  # 2.56MB, several chunks at chunk_size=1MB
    path.write_bytes(data)
    expected = hashlib.sha256(data).hexdigest()
    assert compute_sha256(path, chunk_size=1024 * 1024) == expected


def test_compute_sha256_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        compute_sha256(tmp_path / "does_not_exist.bin")


def test_verify_checksum_true_for_matching_file(tmp_path):
    path = tmp_path / "model.bin"
    path.write_bytes(b"correct data")
    expected = hashlib.sha256(b"correct data").hexdigest()
    assert verify_checksum(path, expected) is True


def test_verify_checksum_false_for_corrupted_file(tmp_path):
    # Regression scenario for the real Phase 7 truncated-download bug: a
    # file that exists but doesn't match its recorded checksum.
    path = tmp_path / "model.bin"
    path.write_bytes(b"correct data")
    expected = hashlib.sha256(b"correct data").hexdigest()
    path.write_bytes(b"corrupted / truncated")
    assert verify_checksum(path, expected) is False


def test_verify_checksum_false_for_missing_file(tmp_path):
    assert verify_checksum(tmp_path / "missing.bin", "0" * 64) is False


def test_verify_checksum_is_case_insensitive(tmp_path):
    path = tmp_path / "model.bin"
    path.write_bytes(b"data")
    expected_upper = hashlib.sha256(b"data").hexdigest().upper()
    assert verify_checksum(path, expected_upper) is True
