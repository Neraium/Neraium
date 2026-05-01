from neraium.operator import build_operator_output


def engine_output_with_slope(current_slope, recent_slopes):
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
            "direction": "diverging",
            "drift_velocity": current_slope,
            "recent_slopes": recent_slopes,
        },
    }


def test_high_slope_vs_history_maps_to_high_urgency():
    result = build_operator_output(
        engine_output_with_slope(0.5, [0.1, 0.2, 0.3, 0.4, 0.5])
    )

    assert result["trajectory"]["urgency"] == "high"


def test_medium_slope_vs_history_maps_to_medium_urgency():
    result = build_operator_output(
        engine_output_with_slope(0.3, [0.1, 0.2, 0.3, 0.4, 0.5])
    )

    assert result["trajectory"]["urgency"] == "medium"


def test_low_slope_vs_history_maps_to_low_urgency():
    result = build_operator_output(
        engine_output_with_slope(0.1, [0.1, 0.2, 0.3, 0.4, 0.5])
    )

    assert result["trajectory"]["urgency"] == "low"


def test_insufficient_slope_history_maps_to_low_urgency():
    result = build_operator_output(engine_output_with_slope(0.5, [0.5]))

    assert result["trajectory"]["urgency"] == "low"
