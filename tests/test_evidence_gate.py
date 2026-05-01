import numpy as np

from neraium.config import NeraiumConfig
from neraium.evidence import compute_structural_evidence


def make_baseline(n_sensors=5, n_samples=500, seed=7):
    rng = np.random.default_rng(seed)
    data = rng.normal(0, 1, size=(n_samples, n_sensors))

    return {
        "mean": np.mean(data, axis=0),
        "mad": np.median(np.abs(data - np.median(data, axis=0)), axis=0) + 1e-6,
        "cov": np.cov(data.T),
        "correlation": np.corrcoef(data.T),
    }


def test_single_sensor_spike_is_transient():
    config = NeraiumConfig()
    baseline = make_baseline()

    packet = np.array([6.0, 0.0, 0.0, 0.0, 0.0])
    window = np.random.normal(0, 1, size=(30, 5))
    history = [10.0, 10.0]

    result = compute_structural_evidence(packet, window, baseline, history, config)

    assert result["status"] == "TRANSIENT"
    assert result["active_families"] < 2


def test_phase1_config_defaults_and_return_shape():
    config = NeraiumConfig()
    baseline = make_baseline()
    packet = np.zeros(5)
    window = np.random.normal(0, 1, size=(30, 5))

    result = compute_structural_evidence(packet, window, baseline, [], config)

    assert config.drift_threshold == 5.0
    assert config.cov_shift_threshold == 0.15
    assert config.rel_stability_threshold == 0.75
    assert config.persistence_cycles == 5
    assert config.sensor_threshold == 2.0
    assert config.cov_epsilon == 1e-6
    assert config.mad_scale == 1.4826

    assert set(result) == {
        "status",
        "drift_score",
        "supporting_families",
        "active_families",
        "has_relationship_evidence",
        "non_sensor_families",
        "persistence_satisfied",
        "diagnostics",
    }
    assert set(result["supporting_families"]) == {
        "sensor_deviation",
        "relationship_shift",
        "relational_stability_change",
        "trajectory_pressure",
    }
    assert set(result["diagnostics"]) == {"cov_shift", "rel_stability"}


def test_two_sensor_spike_without_relationship_shift_is_transient():
    config = NeraiumConfig()
    baseline = make_baseline()

    packet = np.array([6.0, 6.0, 0.0, 0.0, 0.0])
    window = np.random.normal(0, 1, size=(30, 5))
    history = [10.0, 10.0]

    result = compute_structural_evidence(packet, window, baseline, history, config)

    assert result["status"] == "TRANSIENT"


def test_covariance_shift_without_large_sensor_spike_can_confirm_change():
    config = NeraiumConfig(
        drift_threshold=0.1,
        cov_shift_threshold=0.15,
        rel_stability_threshold=1.5,
        persistence_cycles=3,
    )
    baseline = make_baseline()

    rng = np.random.default_rng(42)

    shared = rng.normal(0, 1, size=30)
    window = np.column_stack([
        shared,
        shared + rng.normal(0, 0.05, size=30),
        rng.normal(0, 1, size=30),
        rng.normal(0, 1, size=30),
        rng.normal(0, 1, size=30),
    ])

    packet = np.mean(window[-5:], axis=0)
    history = [1.0, 1.0]

    result = compute_structural_evidence(packet, window, baseline, history, config)

    assert result["status"] == "CONFIRMED_CHANGE"
    assert result["supporting_families"]["relationship_shift"] is True
    assert result["active_families"] >= 2


def test_persistence_gate_blocks_first_detection():
    config = NeraiumConfig(
        drift_threshold=3.0,
        persistence_cycles=3,
        sensor_threshold=2.0,
        cov_shift_threshold=0.15,
        rel_stability_threshold=1.5,
    )
    baseline = make_baseline()

    rng = np.random.default_rng(99)
    shared = rng.normal(0, 1, size=30)
    window = np.column_stack([
        shared + 4.0,
        shared + 4.0 + rng.normal(0, 0.05, size=30),
        rng.normal(0, 1, size=30),
        rng.normal(0, 1, size=30),
        rng.normal(0, 1, size=30),
    ])

    packet = window[-1]
    history = []

    result = compute_structural_evidence(packet, window, baseline, history, config)

    assert result["status"] == "TRANSIENT"
    assert result["persistence_satisfied"] is False


def test_persistent_multi_family_shift_confirms_change():
    config = NeraiumConfig(
        drift_threshold=3.0,
        persistence_cycles=3,
        sensor_threshold=2.0,
        cov_shift_threshold=0.15,
        rel_stability_threshold=1.5,
    )
    baseline = make_baseline()

    rng = np.random.default_rng(100)
    shared = rng.normal(0, 1, size=30)
    window = np.column_stack([
        shared + 4.0,
        shared + 4.0 + rng.normal(0, 0.05, size=30),
        rng.normal(0, 1, size=30),
        rng.normal(0, 1, size=30),
        rng.normal(0, 1, size=30),
    ])

    packet = window[-1]
    history = [10.0, 10.0]

    result = compute_structural_evidence(packet, window, baseline, history, config)

    assert result["status"] == "CONFIRMED_CHANGE"
    assert result["persistence_satisfied"] is True
    assert result["active_families"] >= 2
