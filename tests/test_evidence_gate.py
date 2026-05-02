"""
Tests for compute_evidence_families().

Evidence families determine *why* a structural change was detected, not *if*.
All thresholds are derived from the baseline (injected, not hardcoded).
"""

import numpy as np

from neraium.config import NeraiumConfig
from neraium.evidence import compute_evidence_families


def _make_baseline_corr(n=5, seed=7):
    rng = np.random.default_rng(seed)
    data = rng.normal(0, 1, size=(200, n))
    return np.corrcoef(data.T)


def _call_families(
    z_scores,
    window_rows=30,
    seed=11,
    baseline_median=None,
    baseline_mad=None,
    baseline_corr=None,
    drift_score=3.0,
    watch_threshold=1.0,
    alert_threshold=2.0,
    config=None,
):
    rng = np.random.default_rng(seed)
    n = len(z_scores)
    window = [rng.normal(0, 1, size=n) for _ in range(window_rows)]
    if baseline_median is None:
        baseline_median = np.zeros(n)
    if baseline_mad is None:
        baseline_mad = np.ones(n)
    if baseline_corr is None:
        baseline_corr = np.eye(n)
    if config is None:
        config = NeraiumConfig()

    return compute_evidence_families(
        z_scores=np.array(z_scores, dtype=float),
        window=window,
        baseline_median=baseline_median,
        baseline_mad=baseline_mad,
        baseline_corr=baseline_corr,
        drift_score=drift_score,
        watch_threshold=watch_threshold,
        alert_threshold=alert_threshold,
        config=config,
    )


def test_returns_required_keys():
    result = _call_families([0.0, 0.0, 0.0, 0.0, 0.0])
    assert "families" in result
    assert "active_families" in result
    assert "trajectory_pressure" in result


def test_families_dict_has_four_families():
    result = _call_families([0.0] * 5)
    assert set(result["families"]) == {
        "sensor_deviation",
        "relationship_shift",
        "relational_stability_change",
        "trajectory_pressure",
    }


def test_no_deviation_gives_no_sensor_family():
    # z-scores well within watch band (3 sigma)
    result = _call_families([0.5, -0.5, 0.1, -0.1, 0.0])
    assert result["families"]["sensor_deviation"] is False


def test_large_z_score_triggers_sensor_deviation():
    # z-score of 5 exceeds the default watch_mad_multiplier=3 band
    result = _call_families([5.0, 0.0, 0.0, 0.0, 0.0])
    assert result["families"]["sensor_deviation"] is True
    assert "sensor_deviation" in result["active_families"]


def test_trajectory_pressure_is_always_false():
    # DMD not yet implemented
    result = _call_families([10.0, 10.0, 10.0, 10.0, 10.0])
    assert result["families"]["trajectory_pressure"] is False
    assert result["trajectory_pressure"] == 0.0


def test_active_families_list_matches_true_values():
    result = _call_families([5.0, 0.0, 0.0, 0.0, 0.0])
    for family in result["active_families"]:
        assert result["families"][family] is True


def test_relationship_shift_with_coupled_window():
    """Strongly correlated window should trigger relationship shift family."""
    rng = np.random.default_rng(42)
    n = 5
    shared = rng.normal(0, 1, size=30)
    window = [
        np.array([
            shared[i],
            shared[i] + rng.normal(0, 0.02),
            rng.normal(0, 1),
            rng.normal(0, 1),
            rng.normal(0, 1),
        ])
        for i in range(30)
    ]
    config = NeraiumConfig()
    result = compute_evidence_families(
        z_scores=np.ones(n) * 2.0,
        window=window,
        baseline_median=np.zeros(n),
        baseline_mad=np.ones(n),
        baseline_corr=np.eye(n),
        drift_score=3.0,
        watch_threshold=1.0,
        alert_threshold=2.0,
        config=config,
    )
    # Strongly coupled signals deviate from identity baseline → relationship shift active
    assert result["families"]["relationship_shift"] is True


def test_config_has_required_adaptive_fields():
    config = NeraiumConfig()
    assert hasattr(config, "watch_mad_multiplier")
    assert hasattr(config, "alert_mad_multiplier")
    assert hasattr(config, "persistence_window")
    assert hasattr(config, "persistence_min_hits")
    assert hasattr(config, "alert_hold_cycles")
    assert hasattr(config, "baseline_window")
    # Default values
    assert config.watch_mad_multiplier == 3.0
    assert config.alert_mad_multiplier == 5.0
    assert config.baseline_window == 50
    assert config.mad_scale == 1.4826
    assert config.cov_epsilon == 1e-6
