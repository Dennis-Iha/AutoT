"""These hit the REAL model registries (core/asr, core/translation,
core/tts) - the backend reuses them rather than a separate mock list, so
what's asserted here depends on what's actually installed via the
tools/setup_*.sh scripts, same as every other "if entry.is_ready()"-guarded
test in this project."""


def test_list_models_does_not_require_auth(client):
    resp = client.get("/models")
    assert resp.status_code == 200


def test_list_models_reflects_real_registries(client):
    from core.translation.model_registry import TranslationModelRegistry

    resp = client.get("/models")
    body = resp.json()
    assert isinstance(body, list)

    registry = TranslationModelRegistry.load()
    installed_pairs = [(s, t) for s, t in registry.pairs() if registry.get(s, t).is_ready()]
    if installed_pairs:
        translation_entries = [m for m in body if m["kind"] == "translation"]
        assert len(translation_entries) == len(installed_pairs)
        for entry in translation_entries:
            assert entry["sha256"] is not None
            assert len(entry["sha256"]) == 64


def test_download_nonexistent_model_404s(client):
    resp = client.get("/models/does-not-exist/download")
    assert resp.status_code == 404


def test_download_real_installed_model_matches_registry_checksum(client):
    """Phase 29: proves the download endpoint actually streams the correct
    bytes, not just that it returns 200 - hashes the downloaded response
    body and compares against the SAME registry checksum list_models()
    already surfaces, catching a route that serves the wrong file just as
    reliably as one that serves nothing."""
    import hashlib

    from core.ota.model_updater import resolve_update_targets

    targets = [t for t in resolve_update_targets() if t.install_path.exists()]
    if not targets:
        import pytest
        pytest.skip("no real models installed - run the tools/setup_*.sh scripts first")

    target = targets[0]
    resp = client.get(f"/models/{target.id_}/download")
    assert resp.status_code == 200
    assert hashlib.sha256(resp.content).hexdigest() == target.expected_sha256


def test_full_ota_loop_download_verify_atomic_install(client, tmp_path):
    """The strongest version of this: download a real model's bytes through
    the real FastAPI backend (no mocked HTTP - TestClient exercises the
    real route/response path), then run the real Phase 29 install pipeline
    against the downloaded bytes, using the same dev keypair Phase 20 used
    to sign the committed manifests. Proves backend -> client -> verify ->
    atomic install works end to end, not just each half in isolation."""
    import pytest

    from core.ota.model_updater import UpdateTarget, apply_update, resolve_update_targets
    from tools.sign_model_manifests import KEY_DIR

    public_key_path = KEY_DIR / "public.pem"
    if not public_key_path.exists():
        pytest.skip("no dev signing key - run tools/sign_model_manifests.py first")

    targets = [t for t in resolve_update_targets() if t.install_path.exists() and t.signature is not None]
    if not targets:
        pytest.skip("no signed, installed models - run tools/setup_*.sh then tools/sign_model_manifests.py")

    real_target = targets[0]
    resp = client.get(f"/models/{real_target.id_}/download")
    assert resp.status_code == 200

    staged = tmp_path / "downloaded.bin"
    staged.write_bytes(resp.content)
    reinstalled_path = tmp_path / "reinstalled" / "model.bin"
    target_into_tmp = UpdateTarget(
        kind=real_target.kind, id_=real_target.id_, install_path=reinstalled_path,
        expected_sha256=real_target.expected_sha256, signature=real_target.signature,
    )

    result = apply_update(target_into_tmp, staged, public_key_pem=public_key_path.read_text())

    assert result.status == "installed", result.error
    assert reinstalled_path.read_bytes() == real_target.install_path.read_bytes()


def test_list_firmware_is_empty_no_firmware_built_yet(client):
    resp = client.get("/firmware")
    assert resp.status_code == 200
    assert resp.json() == []  # Phase 15 is a design doc only, see firmware/architecture.md


def test_request_model_install_creates_ota_job(client, auth_headers):
    device = client.post(
        "/devices", json={"name": "Pods", "device_type": "at_pods"}, headers=auth_headers
    ).json()
    resp = client.post(
        f"/devices/{device['id']}/models",
        json={"job_type": "model_package", "package_id": "argos-es-en-1.9"},
        headers=auth_headers,
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["device_id"] == device["id"]
    assert body["status"] == "queued"


def test_request_model_install_for_nonexistent_device_404s(client, auth_headers):
    resp = client.post(
        "/devices/nonexistent/models",
        json={"job_type": "model_package", "package_id": "argos-es-en-1.9"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_request_ota_creates_job(client, auth_headers):
    device = client.post(
        "/devices", json={"name": "Pods", "device_type": "at_pods"}, headers=auth_headers
    ).json()
    resp = client.post(
        f"/devices/{device['id']}/ota",
        json={"job_type": "firmware", "package_id": "at-h1-1.0.0"},
        headers=auth_headers,
    )
    assert resp.status_code == 202
    assert resp.json()["job_type"] == "firmware"


def test_ota_requests_require_auth(client):
    resp = client.post(
        "/devices/some-id/ota", json={"job_type": "firmware", "package_id": "x"}
    )
    assert resp.status_code == 401
