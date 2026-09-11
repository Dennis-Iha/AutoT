def test_register_returns_user(client):
    resp = client.post("/auth/register", json={"email": "a@example.com", "password": "hunter22"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "a@example.com"
    assert "id" in body
    assert "hashed_password" not in body  # never leak the hash


def test_register_duplicate_email_rejected(client):
    client.post("/auth/register", json={"email": "a@example.com", "password": "hunter22"})
    resp = client.post("/auth/register", json={"email": "a@example.com", "password": "different"})
    assert resp.status_code == 409


def test_login_returns_access_token(client):
    client.post("/auth/register", json={"email": "a@example.com", "password": "hunter22"})
    resp = client.post("/auth/login", json={"email": "a@example.com", "password": "hunter22"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 20


def test_login_wrong_password_rejected(client):
    client.post("/auth/register", json={"email": "a@example.com", "password": "hunter22"})
    resp = client.post("/auth/login", json={"email": "a@example.com", "password": "wrong"})
    assert resp.status_code == 401


def test_login_unknown_email_rejected(client):
    resp = client.post("/auth/login", json={"email": "nobody@example.com", "password": "x"})
    assert resp.status_code == 401


def test_password_hashing_roundtrip():
    from backend.auth import hash_password, verify_password

    hashed = hash_password("hunter22")
    assert hashed != "hunter22"
    assert verify_password("hunter22", hashed)
    assert not verify_password("wrong", hashed)
