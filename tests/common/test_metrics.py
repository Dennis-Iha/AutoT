import time

from core.common.metrics import Metrics


def test_counter_increments():
    m = Metrics(namespace="test")
    m.incr("events")
    m.incr("events", 4)
    assert m.snapshot()["counters"]["events"] == 5


def test_gauge_overwrites():
    m = Metrics()
    m.gauge("battery_pct", 91.0)
    m.gauge("battery_pct", 88.5)
    assert m.snapshot()["gauges"]["battery_pct"] == 88.5


def test_timer_context_manager_records_elapsed():
    m = Metrics()
    with m.timer("op"):
        time.sleep(0.01)
    stats = m.snapshot()["timers"]["op"]
    assert stats["count"] == 1
    assert stats["avg_ms"] >= 9.0  # allow scheduling slack below the 10ms sleep


def test_record_ms_directly():
    m = Metrics()
    m.record_ms("op", 5.0)
    m.record_ms("op", 15.0)
    stats = m.snapshot()["timers"]["op"]
    assert stats["count"] == 2
    assert stats["min_ms"] == 5.0
    assert stats["max_ms"] == 15.0
    assert stats["avg_ms"] == 10.0


def test_snapshot_namespace_included():
    m = Metrics(namespace="audio")
    assert m.snapshot()["namespace"] == "audio"
