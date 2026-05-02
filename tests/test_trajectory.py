from neraium.trajectory import compute_trajectory_direction


def test_increasing_drift_is_diverging():
    history = [
        {"drift_score": 1.0, "rel_stability": 0.8},
        {"drift_score": 2.0, "rel_stability": 0.8},
        {"drift_score": 3.0, "rel_stability": 0.78},
        {"drift_score": 4.0, "rel_stability": 0.76},
    ]
    current = {"drift_score": 5.0, "rel_stability": 0.75}

    result = compute_trajectory_direction(history, current)

    assert result["direction"] == "diverging"
    assert round(result["drift_velocity"], 6) == 1.0
    assert round(result["drift_acceleration"], 6) == 0.0
    assert result["cycles_of_evidence"] == 5


def test_increasing_faster_is_diverging_with_acceleration():
    history = [
        {"drift_score": 1.0, "rel_stability": 0.8},
        {"drift_score": 1.5, "rel_stability": 0.8},
        {"drift_score": 2.5, "rel_stability": 0.78},
        {"drift_score": 4.0, "rel_stability": 0.76},
    ]
    current = {"drift_score": 6.0, "rel_stability": 0.75}

    result = compute_trajectory_direction(history, current)

    assert result["direction"] == "diverging"
    assert result["drift_velocity"] > 0.01
    assert result["drift_acceleration"] > 0


def test_decreasing_drift_and_increasing_stability_is_stabilizing():
    history = [
        {"drift_score": 5.0, "rel_stability": 0.5},
        {"drift_score": 4.0, "rel_stability": 0.55},
        {"drift_score": 3.0, "rel_stability": 0.6},
        {"drift_score": 2.0, "rel_stability": 0.65},
    ]
    current = {"drift_score": 1.0, "rel_stability": 0.7}

    result = compute_trajectory_direction(history, current)

    assert result["direction"] == "stabilizing"
    assert round(result["drift_velocity"], 6) == -1.0
    assert round(result["relational_recovery"], 6) == 0.05


def test_no_meaningful_change_is_flat():
    history = [
        {"drift_score": 2.0, "rel_stability": 0.7},
        {"drift_score": 2.005, "rel_stability": 0.7},
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
        {"drift_score": 2.5, "rel_stability": 0.75},
        {"drift_score": 3.0, "rel_stability": 0.8},
    ]
    current = {"drift_score": 3.5, "rel_stability": 0.85}

    result = compute_trajectory_direction(history, current)

    assert result == {
        "direction": "ambiguous",
        "drift_velocity": 0.0,
        "drift_acceleration": 0.0,
        "relational_recovery": 0.0,
        "cycles_of_evidence": 4,
    }


def test_persistent_relationship_formation_with_cov_shift_biases_diverging():
    history = [
        {"drift_score": 8.0, "rel_stability": 1.3},
        {"drift_score": 7.0, "rel_stability": 1.35},
        {"drift_score": 7.5, "rel_stability": 1.4},
        {"drift_score": 7.0, "rel_stability": 1.45},
    ]
    current = {
        "drift_score": 7.2,
        "rel_stability": 1.5,
        "cov_shift": 0.3,
    }

    result = compute_trajectory_direction(
        history,
        current,
        pattern="RELATIONSHIP_FORMATION",
        persistence_satisfied=True,
        cov_shift_threshold=0.15,
    )

    assert result["direction"] == "diverging"


def test_persistent_relationship_formation_does_not_require_extra_stability_check():
    history = [
        {"drift_score": 8.0, "rel_stability": 1.0},
        {"drift_score": 7.5, "rel_stability": 1.0},
        {"drift_score": 7.0, "rel_stability": 1.0},
        {"drift_score": 6.8, "rel_stability": 1.0},
    ]
    current = {
        "drift_score": 6.9,
        "rel_stability": 1.0,
        "cov_shift": 0.3,
    }

    result = compute_trajectory_direction(
        history,
        current,
        pattern="RELATIONSHIP_FORMATION",
        persistence_satisfied=True,
        cov_shift_threshold=0.15,
    )

    assert result["direction"] == "diverging"


def test_confirmed_persistent_relationship_shift_with_cov_shift_is_diverging():
    history = [
        {"drift_score": 8.0, "rel_stability": 1.0},
        {"drift_score": 7.8, "rel_stability": 1.0},
        {"drift_score": 7.5, "rel_stability": 1.0},
        {"drift_score": 7.3, "rel_stability": 1.0},
    ]
    current = {
        "drift_score": 7.2,
        "rel_stability": 1.0,
        "cov_shift": 0.25,
    }

    result = compute_trajectory_direction(
        history,
        current,
        status="CONFIRMED_CHANGE",
        pattern="STRUCTURAL_CHANGE_UNCERTAIN",
        persistence_satisfied=True,
        relationship_shift=True,
        cov_shift_threshold=0.15,
    )

    assert result["direction"] == "diverging"
