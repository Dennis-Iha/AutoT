def test_list_devices_requires_auth(client):
    resp = client.get("/devices")
    assert resp.status_code == 401


def test_list_devices_empty_initially(client, auth_headers):
    resp = client.get("/devices", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_register_device(client, auth_headers):
    resp = client.post(
        "/devices", json={"name": "My AT Pods", "device_type": "at_pods"}, headers=auth_headers
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "My AT Pods"
    assert body["device_type"] == "at_pods"
    assert body["firmware_version"] is None


def test_registered_device_appears_in_list(client, auth_headers):
    client.post("/devices", json={"name": "Pods", "device_type": "at_pods"}, headers=auth_headers)
    resp = client.get("/devices", headers=auth_headers)
    assert len(resp.json()) == 1


def test_get_device_by_id(client, auth_headers):
    create = client.post(
        "/devices", json={"name": "Pods", "device_type": "at_pods"}, headers=auth_headers
    )
    device_id = create.json()["id"]
    resp = client.get(f"/devices/{device_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == device_id


def test_get_nonexistent_device_404s(client, auth_headers):
    resp = client.get("/devices/nonexistent-id", headers=auth_headers)
    assert resp.status_code == 404


def test_cannot_see_another_users_device(client, auth_headers):
    create = client.post(
        "/devices", json={"name": "Pods", "device_type": "at_pods"}, headers=auth_headers
    )
    device_id = create.json()["id"]

    client.post("/auth/register", json={"email": "other@example.com", "password": "hunter22"})
    login = client.post("/auth/login", json={"email": "other@example.com", "password": "hunter22"})
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = client.get(f"/devices/{device_id}", headers=other_headers)
    assert resp.status_code == 404  # not 403 - don't leak that it exists
