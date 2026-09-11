from __future__ import annotations

import hashlib
import shutil

import pytest

from core.ota.model_updater import UpdateTarget, apply_update, resolve_update_targets
from core.security.package_signing import generate_signing_keypair, sign_digest
from tools.sign_model_manifests import KEY_DIR


def make_target(tmp_path, content: bytes, signature=None, kind="asr", id_="test-model") -> UpdateTarget:
    install_path = tmp_path / "installed" / "model.bin"
    return UpdateTarget(
        kind=kind, id_=id_, install_path=install_path,
        expected_sha256=hashlib.sha256(content).hexdigest(), signature=signature,
    )


def test_apply_update_installs_when_checksum_matches_no_signature(tmp_path):
    content = b"a real model package"
    staged = tmp_path / "staged.bin"
    staged.write_bytes(content)
    target = make_target(tmp_path, content)

    result = apply_update(target, staged, public_key_pem=None)

    assert result.status == "installed"
    assert target.install_path.read_bytes() == content
    assert not staged.exists()  # os.replace moves it, doesn't copy


def test_apply_update_rejects_checksum_mismatch_leaves_existing_untouched(tmp_path):
    old_content = b"the currently-installed, working model"
    target = make_target(tmp_path, b"expected content that will NOT match")
    target.install_path.parent.mkdir(parents=True)
    target.install_path.write_bytes(old_content)

    staged = tmp_path / "staged.bin"
    staged.write_bytes(b"a truncated or corrupted download")

    result = apply_update(target, staged, public_key_pem=None)

    assert result.status == "failed"
    assert "checksum" in result.error
    assert target.install_path.read_bytes() == old_content, "existing working model must survive a rejected update"


def test_apply_update_rejects_missing_staged_file(tmp_path):
    target = make_target(tmp_path, b"content")
    result = apply_update(target, tmp_path / "does_not_exist.bin", public_key_pem=None)
    assert result.status == "failed"
    assert "not found" in result.error


def test_apply_update_returns_unchanged_when_install_path_already_matches(tmp_path):
    content = b"already installed, identical bytes"
    target = make_target(tmp_path, content)
    target.install_path.parent.mkdir(parents=True)
    target.install_path.write_bytes(content)
    staged = tmp_path / "staged.bin"
    staged.write_bytes(content)

    result = apply_update(target, staged, public_key_pem=None)

    assert result.status == "unchanged"


def test_apply_update_verifies_real_signature_and_installs(tmp_path):
    private_pem, public_pem = generate_signing_keypair()
    content = b"signed model package bytes"
    digest = hashlib.sha256(content).hexdigest()
    signature = sign_digest(digest, private_pem, key_id="test-key")
    target = make_target(tmp_path, content, signature=signature)
    staged = tmp_path / "staged.bin"
    staged.write_bytes(content)

    result = apply_update(target, staged, public_key_pem=public_pem)

    assert result.status == "installed"
    assert target.install_path.read_bytes() == content


def test_apply_update_rejects_wrong_public_key_leaves_existing_untouched(tmp_path):
    private_pem, _ = generate_signing_keypair()
    _, wrong_public_pem = generate_signing_keypair()
    old_content = b"currently installed"
    content = b"new package signed by the real key"
    digest = hashlib.sha256(content).hexdigest()
    signature = sign_digest(digest, private_pem, key_id="test-key")
    target = make_target(tmp_path, content, signature=signature)
    target.install_path.parent.mkdir(parents=True)
    target.install_path.write_bytes(old_content)
    staged = tmp_path / "staged.bin"
    staged.write_bytes(content)

    result = apply_update(target, staged, public_key_pem=wrong_public_pem)

    assert result.status == "failed"
    assert "signature" in result.error
    assert target.install_path.read_bytes() == old_content


def test_apply_update_fails_closed_when_signature_present_but_no_key_given(tmp_path):
    """A caller that forgets to pass a public key must NOT silently fall
    back to checksum-only verification for a manifest entry that IS signed -
    that would defeat the entire point of Phase 20's signing work."""
    private_pem, _ = generate_signing_keypair()
    content = b"signed package"
    digest = hashlib.sha256(content).hexdigest()
    signature = sign_digest(digest, private_pem, key_id="test-key")
    target = make_target(tmp_path, content, signature=signature)
    staged = tmp_path / "staged.bin"
    staged.write_bytes(content)

    result = apply_update(target, staged, public_key_pem=None)

    assert result.status == "failed"
    assert "public key" in result.error
    assert not target.install_path.exists()


def test_resolve_update_targets_covers_all_real_installed_entries(translation_registry, tts_registry, whisper_cpp_available):
    if translation_registry is None and tts_registry is None and whisper_cpp_available is None:
        pytest.skip("no real models installed - run the tools/setup_*.sh scripts first")

    targets = resolve_update_targets()
    assert len(targets) > 0
    by_id = {t.id_: t for t in targets}

    if whisper_cpp_available is not None:
        assert any(t.kind == "asr" for t in targets)
    if translation_registry is not None:
        installed_pairs = [p for p in translation_registry.pairs() if translation_registry.get(*p).is_ready()]
        for source, target_lang in installed_pairs:
            entry = translation_registry.get(source, target_lang)
            assert entry.model_id in by_id, f"{entry.model_id} missing from resolve_update_targets()"
            t = by_id[entry.model_id]
            assert t.install_path == entry.ctranslate2_model_dir / "model.bin"
            assert t.signature is not None, "committed manifests were signed in Phase 20 - every entry should carry one"


def test_full_update_flow_reinstalls_real_model_with_real_signature(tmp_path, translation_registry):
    """The strongest version of this test: takes one REAL, currently
    installed translation model's genuine checksum+signature from the
    committed manifest (Phase 20's real signing output, not test fixtures),
    stages a copy of its real bytes, and runs it through the actual
    verify-then-atomically-install pipeline - end to end, real crypto, real
    model bytes. Installs into a tmp_path copy of the target, never the
    developer's real models/ directory, so a failing assertion can't corrupt
    a real downloaded model."""
    if translation_registry is None:
        pytest.skip("no translation models installed - run tools/setup_translation_models.sh first")

    ready_pairs = [p for p in translation_registry.pairs() if translation_registry.get(*p).is_ready()]
    if not ready_pairs:
        pytest.skip("no ready translation models installed")

    public_key_path = KEY_DIR / "public.pem"
    if not public_key_path.exists():
        pytest.skip("no dev signing key - run tools/sign_model_manifests.py first")

    targets = resolve_update_targets()
    source, target_lang = ready_pairs[0]
    entry = translation_registry.get(source, target_lang)
    real_target = next(t for t in targets if t.id_ == entry.model_id)
    assert real_target.signature is not None

    staged = tmp_path / "staged_model.bin"
    shutil.copyfile(real_target.install_path, staged)
    fake_install_path = tmp_path / "reinstalled" / "model.bin"
    target_into_tmp = UpdateTarget(
        kind=real_target.kind, id_=real_target.id_, install_path=fake_install_path,
        expected_sha256=real_target.expected_sha256, signature=real_target.signature,
    )

    result = apply_update(target_into_tmp, staged, public_key_pem=public_key_path.read_text())

    assert result.status == "installed", result.error
    assert fake_install_path.read_bytes() == real_target.install_path.read_bytes()
