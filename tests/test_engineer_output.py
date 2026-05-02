from neraium.engineer import build_engineer_output


def make_engine_output():
    return {
        "status": "CONFIRMED_CHANGE",
        "drift_score": 12.5,
        "relational_stability": 1.4,
        "covariance_drift": 0.8,
        "trajectory": {
            "direction": "diverging",
            "drift_velocity": 0.2,
            "drift_acceleration": 0.05,
        },
        "supporting_families": {
            "sensor_deviation": True,
            "relationship_shift": True,
            "relational_stability_change": False,
            "trajectory_pressure": False,
        },
        "active_families": 2,
        "persistence_satisfied": True,
        "where": {
            "top_signals": [
                {"signal": "sensor_0", "contribution": 0.6},
            ],
            "top_relationships": [],
        },
        "what_is_happening": {
            "pattern": "RELATIONSHIP_FORMATION",
        },
        "rule_triggered": "high_rel_stability_with_cov_shift",
    }


def test_transient_returns_minimal_output():
    result = build_engineer_output(
        {
            "status": "TRANSIENT",
            "drift_score": 3.0,
        }
    )

    assert result == {"status": "TRANSIENT"}


def test_initializing_returns_minimal_output():
    result = build_engineer_output({"status": "INITIALIZING"})

    assert result == {"status": "INITIALIZING"}


def test_confirmed_returns_full_output():
    result = build_engineer_output(make_engine_output())

    assert result == {
        "status": "CONFIRMED_CHANGE",
        "structural_metrics": {
            "drift_score": 12.5,
            "relational_stability": 1.4,
            "covariance_shift": 0.8,
        },
        "trajectory_metrics": {
            "direction": "diverging",
            "drift_velocity": 0.2,
            "drift_acceleration": 0.05,
        },
        "evidence": {
            "supporting_families": {
                "sensor_deviation": True,
                "relationship_shift": True,
                "relational_stability_change": False,
                "trajectory_pressure": False,
            },
            "active_families": 2,
            "persistence_satisfied": True,
        },
        "contributors": {
            "top_signals": [
                {"signal": "sensor_0", "contribution": 0.6},
            ],
            "top_relationships": [],
        },
        "pattern": {
            "type": "RELATIONSHIP_FORMATION",
            "rule_triggered": "high_rel_stability_with_cov_shift",
        },
    }


def test_missing_fields_are_none_or_default_false():
    result = build_engineer_output(
        {
            "status": "CONFIRMED_CHANGE_HELD",
            "trajectory": {},
            "what_is_happening": {},
        }
    )

    assert result["structural_metrics"] == {
        "drift_score": None,
        "relational_stability": None,
        "covariance_shift": None,
    }
    assert result["trajectory_metrics"] == {
        "direction": None,
        "drift_velocity": None,
        "drift_acceleration": None,
    }
    assert result["evidence"] == {
        "supporting_families": None,
        "active_families": None,
        "persistence_satisfied": False,
    }
    assert result["contributors"] is None
    assert result["pattern"] == {
        "type": None,
        "rule_triggered": None,
    }
