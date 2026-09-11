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
