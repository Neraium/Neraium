from neraium.operator import build_operator_output


def engine_output_with_direction(direction):
    return {
        "status": "CONFIRMED_CHANGE",
        "confidence_score": 0.75,
        "what_is_happening": {
            "pattern": "RELATIONSHIP_FORMATION",
            "summary": "high_rel_stability_with_cov_shift",
        },
        "where": {
            "top_signals": [],
            "top_relationships": [],
        },
        "trajectory": {
            "direction": direction,
            "drift_velocity": 0.0,
            "recent_slopes": [],
        },
    }


def test_diverging_maps_to_divergence_message():
    result = build_operator_output(engine_output_with_direction("diverging"))

    assert result["if_ignored"] == {
        "expected_behavior": "continued structural divergence",
        "basis": "current trajectory direction and persistence",
    }


def test_stabilizing_maps_to_stabilization_message():
    result = build_operator_output(engine_output_with_direction("stabilizing"))

    assert result["if_ignored"] == {
        "expected_behavior": "structural stabilization likely if current trend continues",
        "basis": "current trajectory direction and persistence",
    }


def test_flat_maps_to_stable_message():
    result = build_operator_output(engine_output_with_direction("flat"))

    assert result["if_ignored"] == {
        "expected_behavior": "structural state likely to remain similar in near term",
        "basis": "current trajectory direction and persistence",
    }


def test_ambiguous_maps_to_unclear_message():
    result = build_operator_output(engine_output_with_direction("ambiguous"))

    assert result["if_ignored"] == {
        "expected_behavior": "trajectory unclear; additional observation required",
        "basis": "current trajectory direction and persistence",
    }
