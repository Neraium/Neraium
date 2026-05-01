from neraium.system_output import build_system_output


def make_engine_output(status="CONFIRMED_CHANGE"):
    return {
        "status": status,
        "confidence_score": 0.75,
        "drift_score": 12.5,
        "relational_stability": 1.4,
        "covariance_drift": 0.8,
        "supporting_families": {
            "sensor_deviation": True,
            "relationship_shift": True,
            "relational_stability_change": False,
            "trajectory_pressure": False,
        },
        "active_families": 2,
        "persistence_satisfied": True,
        "what_is_happening": {
            "pattern": "RELATIONSHIP_FORMATION",
            "summary": "high_rel_stability_with_cov_shift",
        },
        "where": {
            "top_signals": [
                {"signal": "sensor_0", "contribution": 0.6},
                {"signal": "sensor_1", "contribution": 0.3},
            ],
            "top_relationships": [
                {
                    "pair": ["sensor_0", "sensor_1"],
                    "covariance_shift_abs": 1.0,
                    "covariance_shift_norm": 1.0,
                    "correlation_shift": 0.9,
                    "current_correlation": 0.9,
                    "baseline_correlation": 0.0,
                }
            ],
        },
        "trajectory": {
            "direction": "diverging",
            "drift_velocity": 0.2,
            "drift_acceleration": 0.05,
            "relational_recovery": 0.0,
            "cycles_of_evidence": 5,
            "recent_slopes": [0.0, 0.1, 0.2],
        },
        "rule_triggered": "high_rel_stability_with_cov_shift",
    }


def test_transient_input_returns_all_views_as_transient():
    engine_output = {"status": "TRANSIENT", "drift_score": 3.0}

    result = build_system_output(engine_output)

    assert result["operator"]["status"] == "TRANSIENT"
    assert result["engineer"]["status"] == "TRANSIENT"
    assert result["raw_engine"]["status"] == "TRANSIENT"


def test_confirmed_change_returns_all_views_and_raw_engine_identity():
    engine_output = make_engine_output()

    result = build_system_output(engine_output)

    assert "what_is_happening" in result["operator"]
    assert "structural_metrics" in result["engineer"]
    assert result["raw_engine"] is engine_output


def test_confirmed_change_held_returns_held_status_in_all_views():
    engine_output = make_engine_output("CONFIRMED_CHANGE_HELD")

    result = build_system_output(engine_output)

    assert result["operator"]["status"] == "CONFIRMED_CHANGE_HELD"
    assert result["engineer"]["status"] == "CONFIRMED_CHANGE_HELD"
    assert result["raw_engine"]["status"] == "CONFIRMED_CHANGE_HELD"
