import numpy as np

from neraium.config import NeraiumConfig
from neraium.contributors import decompose_contributors


def make_baseline(n_sensors=5):
    return {
        "mean": np.zeros(n_sensors),
        "mad": np.ones(n_sensors),
        "cov": np.eye(n_sensors),
        "correlation": np.eye(n_sensors),
    }


def test_single_sensor_drift_is_top_contributor():
    config = NeraiumConfig(top_n=3)
    baseline = make_baseline()
    packet = np.array([0.0, 0.0, 8.0, 0.0, 0.0])
    window = np.tile(packet, (30, 1))

    result = decompose_contributors(packet, window, baseline, config)

    assert result["top_signals"][0]["signal"] == "sensor_2"
    assert result["top_signals"][0]["contribution"] > 0.99


def test_correlated_pair_appears_in_top_relationships():
    config = NeraiumConfig(top_n=3, top_n_relationships=5)
    baseline = make_baseline()

    rng = np.random.default_rng(42)
    shared = np.linspace(-2.0, 2.0, 40)
    window = np.column_stack(
        [
            shared,
            shared + 0.02 * rng.normal(size=40),
            rng.normal(0.0, 1.0, size=40),
            rng.normal(0.0, 1.0, size=40),
            rng.normal(0.0, 1.0, size=40),
        ]
    )
    packet = np.array([4.0, 4.0, 0.25, 0.0, 0.0])

    result = decompose_contributors(packet, window, baseline, config)
    pairs = [item["pair"] for item in result["top_relationships"]]
    relationship = next(
        item for item in result["top_relationships"]
        if item["pair"] == ["sensor_0", "sensor_1"]
    )

    assert ["sensor_0", "sensor_1"] in pairs
    assert "covariance_shift_abs" in relationship
    assert "covariance_shift_norm" in relationship
    assert "covariance_shift" not in relationship
    assert relationship["covariance_shift_norm"] < 10.0


def test_noise_input_has_diffuse_contributions():
    config = NeraiumConfig(top_n=5)
    baseline = make_baseline()
    packet = np.array([0.2, -0.2, 0.2, -0.2, 0.2])
    window = np.tile(packet, (30, 1))

    result = decompose_contributors(packet, window, baseline, config)
    contributions = [item["contribution"] for item in result["top_signals"]]

    assert max(contributions) < 0.25
    assert min(contributions) > 0.15


def test_near_zero_pairwise_baseline_covariance_does_not_explode_shift():
    config = NeraiumConfig(top_n=2, top_n_relationships=1)
    baseline = make_baseline()

    shared = np.linspace(-1.0, 1.0, 30)
    window = np.column_stack(
        [
            shared,
            shared,
            np.zeros(30),
            np.zeros(30),
            np.zeros(30),
        ]
    )
    packet = np.array([3.0, 3.0, 0.0, 0.0, 0.0])

    result = decompose_contributors(packet, window, baseline, config)
    relationship = result["top_relationships"][0]

    assert relationship["pair"] == ["sensor_0", "sensor_1"]
    assert relationship["covariance_shift_abs"] < 1.0
    assert relationship["covariance_shift_norm"] < 10.0
