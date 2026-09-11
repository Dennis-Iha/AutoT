from core.audio.diagnostics import AudioDiagnostics


def test_frames_captured_accumulates():
    diag = AudioDiagnostics()
    diag.record_frames_captured(320)
    diag.record_frames_captured(320)
    assert diag.frames_captured == 640
    assert diag.metrics.snapshot()["counters"]["frames_captured"] == 640


def test_stream_status_events_recorded():
    diag = AudioDiagnostics()
    diag.record_stream_status("input_overflow")
    assert diag.stream_status_events == ["input_overflow"]
    assert diag.metrics.snapshot()["counters"]["stream_status.input_overflow"] == 1


def test_inter_callback_timing_recorded():
    diag = AudioDiagnostics()
    diag.record_inter_callback_ms(20.5)
    diag.record_inter_callback_ms(19.8)
    timers = diag.metrics.snapshot()["timers"]["inter_callback"]
    assert timers["count"] == 2
    assert 19.0 < timers["avg_ms"] < 21.0


def test_resource_usage_has_expected_keys():
    diag = AudioDiagnostics()
    usage = diag.resource_usage()
    assert set(usage.keys()) == {"cpu_percent", "rss_mb", "elapsed_s"}
    assert usage["rss_mb"] > 0


def test_snapshot_shape():
    diag = AudioDiagnostics()
    diag.record_frames_captured(160)
    snap = diag.snapshot()
    assert snap["frames_captured"] == 160
    assert "resource_usage" in snap
    assert "metrics" in snap
