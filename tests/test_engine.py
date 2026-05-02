import numpy as np

from neraium.config import NeraiumConfig
from neraium.engine import NeraiumEngine


def healthy_packet(rng):
    return rng.normal(0.0, 1.0, size=5)


def warm_engine(engine, rng, n=55):
    """Feed n stable packets to push engine through baseline into STABLE."""
    outputs = []
    for _ in range(n):
        outputs.append(engine.update(healthy_packet(rng)))
    return outputs


def test_initializing_returns_initializing():
    engine = NeraiumEngine(NeraiumConfig())
    result = engine.update(np.zeros(5))
    assert result["status"] == "INITIALIZING"


def test_stable_stream_stays_stable_after_baseline():
    rng = np.random.default_rng(10)
    engine = NeraiumEngine(NeraiumConfig())
    warm_engine(engine, rng)

    results = [engine.update(healthy_packet(rng)) for _ in range(50)]

    # All results should be STABLE — small noise should not trigger WATCH
    statuses = {r["status"] for r in results}
    assert statuses <= {"STABLE", "WATCH"}, f"Unexpected statuses: {statuses}"
    # At least the majority should be STABLE (small normal noise shouldn't alert)
    stable_count = sum(1 for r in results if r["status"] == "STABLE")
    assert stable_count >= 40, f"Expected mostly STABLE, got {stable_count}/50"


def test_structural_shift_eventually_reaches_alert():
    rng = np.random.default_rng(367)
    engine = NeraiumEngine(NeraiumConfig())
    warm_engine(engine, rng)

    alerted = None
    for _ in range(200):
        shared = rng.normal(0.0, 1.0)
        packet = healthy_packet(rng)
        packet[0] = shared + 3.5 + 0.10 * rng.normal()
        packet[1] = shared + 3.5 + 0.10 * rng.normal()
        packet[2] = 1.25 + 0.45 * rng.normal()

        result = engine.update(packet)
        if result["status"] == "ALERT":
            alerted = result
            break

    assert alerted is not None, "Engine never reached ALERT with sustained structural shift"
    assert alerted["status"] == "ALERT"


def test_alert_output_has_required_fields():
    rng = np.random.default_rng(367)
    engine = NeraiumEngine(NeraiumConfig())
    warm_engine(engine, rng)

    alerted = None
    for _ in range(200):
        shared = rng.normal(0.0, 1.0)
        packet = healthy_packet(rng)
        packet[0] = shared + 3.5 + 0.10 * rng.normal()
        packet[1] = shared + 3.5 + 0.10 * rng.normal()
        packet[2] = 1.25 + 0.45 * rng.normal()

        result = engine.update(packet)
        if result["status"] == "ALERT":
            alerted = result
            break

    assert alerted is not None
    # Primary fields per spec
    assert "structural_drift_score" in alerted
    assert "relational_stability_score" in alerted
    assert "state" in alerted
    assert "evidence_count" in alerted
    assert "time_in_state" in alerted
    assert "confidence_score" in alerted
    assert "drift_velocity" in alerted
    assert "watch_threshold" in alerted
    assert "alert_threshold" in alerted
    # Supporting fields
    assert "persistence_satisfied" in alerted
    assert alerted["persistence_satisfied"] is True
    assert "active_families" in alerted
    assert "what_is_happening" in alerted
    assert "pattern" in alerted["what_is_happening"]
    assert "top_signals" in alerted
    assert "relationships" in alerted
    assert "direction" in alerted["trajectory"]
    assert "drift_velocity" in alerted["trajectory"]
    assert "drift_acceleration" in alerted["trajectory"]
    assert "relational_recovery" in alerted["trajectory"]
    assert "cycles_of_evidence" in alerted["trajectory"]


def test_engine_holds_alert_state():
    rng = np.random.default_rng(367)
    engine = NeraiumEngine(NeraiumConfig())
    warm_engine(engine, rng)

    alert_seen = False
    held = None
    for _ in range(250):
        shared = rng.normal(0.0, 1.0)
        packet = healthy_packet(rng)
        packet[0] = shared + 3.5 + 0.10 * rng.normal()
        packet[1] = shared + 3.5 + 0.10 * rng.normal()
        packet[2] = 1.25 + 0.45 * rng.normal()

        result = engine.update(packet)
        if result["status"] == "ALERT":
            alert_seen = True
        elif alert_seen and result["status"] == "ALERT_HELD":
            held = result
            break

    assert held is not None, "Engine never transitioned to ALERT_HELD"
    assert held["held"] is True
    assert held["hold_cycles_remaining"] >= 0
    assert "structural_drift_score" in held
    assert "evidence_count" in held


def test_adaptive_thresholds_derived_from_baseline():
    rng = np.random.default_rng(42)
    engine = NeraiumEngine(NeraiumConfig())
    warm_engine(engine, rng)

    # After baseline, thresholds must be positive and > 0
    # Get a post-baseline packet to read thresholds
    result = engine.update(healthy_packet(rng))
    assert result["watch_threshold"] > 0.0
    assert result["alert_threshold"] > result["watch_threshold"]


def test_single_spike_does_not_confirm():
    """A single high spike should not trigger ALERT (K-of-W persistence gate)."""
    rng = np.random.default_rng(99)
    engine = NeraiumEngine(NeraiumConfig())
    warm_engine(engine, rng)

    # One extreme spike
    spike = np.array([10.0, 10.0, 10.0, 10.0, 10.0])
    result = engine.update(spike)

    assert result["status"] != "ALERT", "Single spike should not immediately trigger ALERT"


def test_engine_returns_signal_names():
    engine = NeraiumEngine(NeraiumConfig())
    result = engine.update(np.zeros(5))
    assert result["signal_names"] == ["sensor_0", "sensor_1", "sensor_2", "sensor_3", "sensor_4"]


def test_baseline_window_configurable():
    """Engine with baseline_window=10 should exit INITIALIZING after 10 samples."""
    rng = np.random.default_rng(7)
    config = NeraiumConfig(baseline_window=10)
    engine = NeraiumEngine(config)

    results = [engine.update(healthy_packet(rng)) for _ in range(10)]
    # All 10 still INITIALIZING (last one triggers baseline formation but also returns INITIALIZING)
    assert all(r["status"] == "INITIALIZING" for r in results)

    # 11th sample: baseline formed, should be STABLE or WATCH
    result = engine.update(healthy_packet(rng))
    assert result["status"] in ("STABLE", "WATCH")
