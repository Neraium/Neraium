from neraium.operator import build_operator_output


def engine_output_with_trajectory(
    direction,
    current_slope=0.0,
    recent_slopes=None,
    drift_score=12.0,
    persistence_satisfied=True,
):
    return {
        "status": "CONFIRMED_CHANGE",
        "confidence_score": 0.75,
        "drift_score": drift_score,
        "persistence_satisfied": persistence_satisfied,
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
            "drift_velocity": current_slope,
            "recent_slopes": recent_slopes or [],
        },
    }


def test_diverging_maps_to_high_urgency():
    result = build_operator_output(engine_output_with_trajectory("diverging"))

    assert result["trajectory"]["urgency"] == "high"


def test_persistent_low_magnitude_diverging_maps_to_medium_urgency():
    result = build_operator_output(
        engine_output_with_trajectory(
            "diverging",
            current_slope=0.2,
            drift_score=6.0,
            persistence_satisfied=True,
        )
    )

    assert result["trajectory"]["urgency"] == "medium"


def test_stabilizing_maps_to_low_urgency():
    result = build_operator_output(engine_output_with_trajectory("stabilizing"))

    assert result["trajectory"]["urgency"] == "low"


def test_flat_maps_to_low_urgency():
    result = build_operator_output(engine_output_with_trajectory("flat"))

    assert result["trajectory"]["urgency"] == "low"


def test_ambiguous_maps_to_low_urgency():
    result = build_operator_output(engine_output_with_trajectory("ambiguous"))

    assert result["trajectory"]["urgency"] == "low"
