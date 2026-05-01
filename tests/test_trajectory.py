from neraium.trajectory import compute_trajectory_direction


def test_increasing_drift_is_diverging():
    history = [
        {"drift_score": 1.0, "rel_stability": 0.8},
        {"drift_score": 2.0, "rel_stability": 0.8},
    ]
    current = {"drift_score": 2.5, "rel_stability": 0.75}

    result = compute_trajectory_direction(history, current)

    assert result["direction"] == "diverging"
    assert result["drift_velocity"] == 0.5
    assert result["drift_acceleration"] == -0.5
    assert result["cycles_of_evidence"] == 3


def test_increasing_faster_is_diverging_with_acceleration():
    history = [
        {"drift_score": 1.0, "rel_stability": 0.8},
        {"drift_score": 1.5, "rel_stability": 0.8},
    ]
    current = {"drift_score": 2.5, "rel_stability": 0.75}

    result = compute_trajectory_direction(history, current)

    assert result["direction"] == "diverging"
    assert result["drift_velocity"] == 1.0
    assert result["drift_acceleration"] == 0.5


def test_decreasing_drift_and_increasing_stability_is_stabilizing():
    history = [
        {"drift_score": 4.0, "rel_stability": 0.5},
        {"drift_score": 3.0, "rel_stability": 0.55},
    ]
    current = {"drift_score": 2.0, "rel_stability": 0.7}

    result = compute_trajectory_direction(history, current)

    assert result["direction"] == "stabilizing"
    assert result["drift_velocity"] == -1.0
    assert result["relational_recovery"] == 0.1499999999999999


def test_no_meaningful_change_is_flat():
    history = [
        {"drift_score": 2.0, "rel_stability": 0.7},
        {"drift_score": 2.005, "rel_stability": 0.7},
    ]
    current = {"drift_score": 2.01, "rel_stability": 0.7}

    result = compute_trajectory_direction(history, current)

    assert result["direction"] == "flat"
    assert abs(result["drift_velocity"]) <= 0.01


def test_not_enough_history_is_ambiguous():
    history = [
        {"drift_score": 2.0, "rel_stability": 0.7},
    ]
    current = {"drift_score": 2.5, "rel_stability": 0.75}

    result = compute_trajectory_direction(history, current)

    assert result == {
        "direction": "ambiguous",
        "drift_velocity": 0.0,
        "drift_acceleration": 0.0,
        "relational_recovery": 0.0,
        "cycles_of_evidence": 2,
    }
