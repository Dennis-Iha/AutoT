from __future__ import annotations

from tools.metrics_report import render_report


def test_render_report_empty_device_says_so_honestly():
    report = render_report({"device_id": "d1", "n_events": 0})
    assert "0 recorded event" in report
    assert "no real device fleet exists" in report


def test_render_report_includes_status_and_language_pairs():
    summary = {
        "device_id": "d1",
        "n_events": 3,
        "status_counts": {"ok": 2, "low_confidence": 1},
        "language_pair_counts": [
            {"source_language": "es", "target_language": "en", "count": 2},
            {"source_language": "ar", "target_language": "en", "count": 1},
        ],
        "avg_latency_ms": 150.0,
        "p50_latency_ms": 150.0,
        "p95_latency_ms": 200.0,
    }
    report = render_report(summary)
    assert "ok" in report
    assert "low_confidence" in report
    assert "es -> en" in report
    assert "ar -> en" in report
    assert "avg=150.0ms" in report
