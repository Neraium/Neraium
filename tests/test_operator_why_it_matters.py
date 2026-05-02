from neraium.operator import build_operator_output


EXPECTED_MEANINGS = {
    "RELATIONSHIP_FORMATION": "Signals are becoming more tightly coupled than normal",
    "RELATIONSHIP_DECAY": "Signals are losing their normal coordination",
    "LOAD_RESPONSE_MISMATCH": "System response is no longer aligning with operating conditions",
    "UNCONTROLLED_DIVERGENCE": "System behavior is rapidly moving away from baseline",
    "RECOVERY_PATTERN": "System behavior is moving back toward baseline",
    "STRUCTURAL_CHANGE_UNCERTAIN": "System structure is changing in a way not yet clearly characterized",
}


def engine_output_with_pattern(pattern):
    return {
        "status": "ALERT",
        "confidence_score": 0.75,
        "what_is_happening": {
            "pattern": pattern,
            "summary": "rule",
        },
        "where": {
            "top_signals": [],
            "top_relationships": [],
        },
        "trajectory": {
            "direction": "ambiguous",
            "drift_velocity": 0.0,
            "recent_slopes": [],
        },
    }


def test_each_pattern_returns_correct_meaning():
    for pattern, expected_meaning in EXPECTED_MEANINGS.items():
        result = build_operator_output(engine_output_with_pattern(pattern))
        assert result["why_it_matters"]["meaning"] == expected_meaning
        assert (
            result["why_it_matters"]["implication"]
            == "current behavior may not remain consistent under the same conditions"
        )
        assert (
            result["why_it_matters"]["not_claiming"]
            == "does not assert specific failure mode or timing"
        )


def test_why_it_matters_exists_in_alert_output():
    result = build_operator_output(engine_output_with_pattern("RELATIONSHIP_FORMATION"))
    assert "why_it_matters" in result


def test_why_it_matters_not_present_for_watch():
    result = build_operator_output({"status": "WATCH"})
    assert "why_it_matters" not in result
