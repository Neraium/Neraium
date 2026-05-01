from neraium.operator import build_operator_output


def make_confirmed_output(status="CONFIRMED_CHANGE"):
    return {
        "status": status,
        "confidence_score": 0.75,
        "what_is_happening": {
            "pattern": "RELATIONSHIP_FORMATION",
            "summary": "high_rel_stability_with_cov_shift",
        },
        "where": {
            "top_signals": [
                {"signal": "sensor_0", "contribution": 0.6},
                {"signal": "sensor_1", "contribution": 0.3},
                {"signal": "sensor_2", "contribution": 0.1},
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
            "drift_acceleration": 0.1,
            "relational_recovery": 0.0,
            "cycles_of_evidence": 5,
        },
        "drift_score": 12.0,
    }


def test_transient_input_returns_minimal_output():
    result = build_operator_output(
        {
            "status": "TRANSIENT",
            "drift_score": 4.0,
        }
    )

    assert result == {"status": "TRANSIENT"}


def test_confirmed_change_returns_full_structured_output_without_raw_math():
    result = build_operator_output(make_confirmed_output())

    assert result == {
        "status": "CONFIRMED_CHANGE",
        "confidence_score": 0.75,
        "what_is_happening": {
            "pattern": "RELATIONSHIP_FORMATION",
            "summary": "Previously weak signal relationships are strengthening.",
        },
        "where": {
            "top_signals": ["sensor_0", "sensor_1"],
            "top_relationship_pair": ["sensor_0", "sensor_1"],
        },
        "trajectory": {
            "direction": "diverging",
        },
        "recommended_next_step": "INSPECT_TOP_SIGNALS_AND_RELATIONSHIPS",
    }
    assert "drift_score" not in result


def test_held_state_outputs_held_status_and_continue_monitoring_action():
    result = build_operator_output(make_confirmed_output("CONFIRMED_CHANGE_HELD"))

    assert result["status"] == "CONFIRMED_CHANGE_HELD"
    assert result["recommended_next_step"] == "CONTINUE_MONITORING"
