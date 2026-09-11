"""Phase 31: product metrics ingestion + aggregation. Every event recorded
here is synthetic test data describing a hypothetical pipeline outcome
(status/language pair/latency) - deliberately never transcript/translation
text, matching MetricEventCreate's schema (no such field exists)."""

from __future__ import annotations


def _register_device(client, auth_headers):
    return client.post(
        "/devices", json={"name": "Pods", "device_type": "at_pods"}, headers=auth_headers
    ).json()


def test_record_metric_event_requires_auth(client):
    resp = client.post("/devices/some-id/metrics", json={"event_type": "translation_attempt", "status": "ok"})
    assert resp.status_code == 401


def test_record_metric_event_for_nonexistent_device_404s(client, auth_headers):
    resp = client.post(
        "/devices/nonexistent/metrics",
        json={"event_type": "translation_attempt", "status": "ok"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_record_metric_event_never_accepts_transcript_text(client, auth_headers):
    """Even if a client tried to smuggle transcript content in, the
    response schema (and the underlying ORM model) has no field to carry
    it - this is Phase 21's privacy constraint enforced structurally."""
    device = _register_device(client, auth_headers)
    resp = client.post(
        f"/devices/{device['id']}/metrics",
        json={
            "event_type": "translation_attempt", "status": "ok",
            "source_language": "es", "target_language": "en", "total_latency_ms": 1234.5,
            "transcription_text": "this field does not exist on the schema",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "transcription_text" not in body
    assert "transcript" not in body
    assert set(body.keys()) == {
        "id", "device_id", "event_type", "status", "source_language",
        "target_language", "total_latency_ms", "recorded_at",
    }


def test_metrics_summary_for_device_with_no_events(client, auth_headers):
    device = _register_device(client, auth_headers)
    resp = client.get(f"/devices/{device['id']}/metrics/summary", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["n_events"] == 0
    assert body["status_counts"] == {}
    assert body["language_pair_counts"] == []
    assert body["avg_latency_ms"] is None


def test_metrics_summary_aggregates_status_counts_and_latency(client, auth_headers):
    device = _register_device(client, auth_headers)
    events = [
        {"event_type": "translation_attempt", "status": "ok", "source_language": "es",
         "target_language": "en", "total_latency_ms": 100.0},
        {"event_type": "translation_attempt", "status": "ok", "source_language": "es",
         "target_language": "en", "total_latency_ms": 200.0},
        {"event_type": "translation_attempt", "status": "low_confidence", "source_language": "ar",
         "target_language": "en", "total_latency_ms": None},
    ]
    for e in events:
        resp = client.post(f"/devices/{device['id']}/metrics", json=e, headers=auth_headers)
        assert resp.status_code == 201

    resp = client.get(f"/devices/{device['id']}/metrics/summary", headers=auth_headers)
    body = resp.json()
    assert body["n_events"] == 3
    assert body["status_counts"] == {"ok": 2, "low_confidence": 1}
    assert body["avg_latency_ms"] == 150.0
    pairs = {(p["source_language"], p["target_language"]): p["count"] for p in body["language_pair_counts"]}
    assert pairs == {("es", "en"): 2, ("ar", "en"): 1}


def test_metrics_summary_requires_auth(client):
    resp = client.get("/devices/some-id/metrics/summary")
    assert resp.status_code == 401


def test_cannot_see_another_users_device_metrics(client, auth_headers):
    device = _register_device(client, auth_headers)
    client.post("/auth/register", json={"email": "other@example.com", "password": "hunter22"})
    other_login = client.post("/auth/login", json={"email": "other@example.com", "password": "hunter22"})
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

    resp = client.get(f"/devices/{device['id']}/metrics/summary", headers=other_headers)
    assert resp.status_code == 404
