from neraium.engineer import build_engineer_output
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
            "recent_slopes": [0.0, 0.1, 0.2],
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


def test_initializing_input_returns_minimal_output():
    result = build_operator_output({"status": "INITIALIZING"})

    assert result == {"status": "INITIALIZING"}


def test_confirmed_change_returns_full_structured_output_without_raw_math():
    result = build_operator_output(make_confirmed_output())

    assert result == {
        "status": "CONFIRMED_CHANGE",
        "confidence_score": 0.75,
        "what_is_happening": {
            "summary": "Previously weak signal relationships are strengthening.",
        },
        "where": {
            "top_signals": ["Spindle Vibration", "Spindle Motor Current"],
            "top_relationship_pair": [
                "Spindle Vibration",
                "Spindle Motor Current",
            ],
        },
        "where_to_look": {
            "subsystems": ["Spindle assembly", "Spindle drive"],
            "components": ["spindle_assembly", "spindle_motor"],
        },
        "plain_english": {
            "what_this_means": (
                "Spindle Vibration and Spindle Motor Current are moving together more than normal."
            ),
            "where_to_start": (
                "Start inspection around the Spindle assembly and Spindle drive."
            ),
            "what_we_are_not_claiming": (
                "This does not identify an exact failed component without machine-specific topology and inspection context."
            ),
        },
        "trajectory": {
            "direction": "diverging",
            "urgency": "high",
        },
        "confidence_level": "medium",
        "decision_basis": [
            "confirmed structural change",
            "top relationship involves two tracked signals",
            "inspection area is mapped from contributing signals",
            "trajectory direction is diverging",
        ],
        "recommended_checks": [
            "Compare live traces for Spindle Vibration and Spindle Motor Current.",
            "Inspect around Spindle assembly and Spindle drive.",
            "Check recent operating conditions for a change that matches the signal movement.",
        ],
        "watch_next": {
            "signals": ["Spindle Vibration", "Spindle Motor Current"],
            "relationship": ["Spindle Vibration", "Spindle Motor Current"],
            "direction": "diverging",
        },
        "if_ignored": {
            "expected_behavior": "continued structural divergence",
            "basis": "current trajectory direction and persistence",
        },
        "why_it_matters": {
            "meaning": "Signals are becoming more tightly coupled than normal",
            "implication": "current behavior may not remain consistent under the same conditions",
            "not_claiming": "does not assert specific failure mode or timing",
        },
        "recommended_next_step": "INSPECT_TOP_SIGNALS_AND_RELATIONSHIPS",
    }
    assert "drift_score" not in result
    assert "pattern" not in result["what_is_happening"]


def test_held_state_with_diverging_trajectory_recommends_inspection():
    result = build_operator_output(make_confirmed_output("CONFIRMED_CHANGE_HELD"))

    assert result["status"] == "CONFIRMED_CHANGE_HELD"
    assert result["recommended_next_step"] == "INSPECT_TOP_SIGNALS_AND_RELATIONSHIPS"


def test_held_state_without_diverging_or_high_urgency_continues_monitoring():
    engine_output = make_confirmed_output("CONFIRMED_CHANGE_HELD")
    engine_output["trajectory"]["direction"] = "flat"

    result = build_operator_output(engine_output)

    assert result["recommended_next_step"] == "CONTINUE_MONITORING"


def test_operator_output_includes_actionable_checks_and_watch_items():
    result = build_operator_output(make_confirmed_output())

    assert result["decision_basis"][0] == "confirmed structural change"
    assert result["recommended_checks"] == [
        "Compare live traces for Spindle Vibration and Spindle Motor Current.",
        "Inspect around Spindle assembly and Spindle drive.",
        "Check recent operating conditions for a change that matches the signal movement.",
    ]
    assert result["watch_next"] == {
        "signals": ["Spindle Vibration", "Spindle Motor Current"],
        "relationship": ["Spindle Vibration", "Spindle Motor Current"],
        "direction": "diverging",
    }
    assert result["confidence_level"] == "medium"


def test_raw_sensor_ids_are_mapped_to_cnc_friendly_names():
    result = build_operator_output(make_confirmed_output())

    assert result["where"]["top_signals"] == [
        "Spindle Vibration",
        "Spindle Motor Current",
    ]
    assert result["where"]["top_relationship_pair"] == [
        "Spindle Vibration",
        "Spindle Motor Current",
    ]


def test_where_to_look_includes_spindle_context_for_sensor_0_and_sensor_1():
    result = build_operator_output(make_confirmed_output())

    assert result["where_to_look"] == {
        "subsystems": ["Spindle assembly", "Spindle drive"],
        "components": ["spindle_assembly", "spindle_motor"],
    }


def test_top_signals_prioritizes_relationship_pair_over_contributor_rank():
    engine_output = make_confirmed_output()
    # Put an unrelated sensor first in contributor rank
    engine_output["where"]["top_signals"] = [
        {"signal": "sensor_2", "contribution": 0.6},
        {"signal": "sensor_1", "contribution": 0.3},
        {"signal": "sensor_0", "contribution": 0.1},
    ]
    result = build_operator_output(engine_output)

    assert result["where"]["top_signals"] == [
        "Spindle Vibration",
        "Spindle Motor Current",
    ]


def test_top_signals_uses_contributor_rank_when_no_relationship_pair():
    engine_output = make_confirmed_output()
    engine_output["where"]["top_relationships"] = []
    result = build_operator_output(engine_output)

    assert result["where"]["top_signals"] == [
        "Spindle Vibration",
        "Spindle Motor Current",
    ]


def test_engineer_output_remains_raw_and_technical():
    result = build_engineer_output(
        {
            **make_confirmed_output(),
            "relational_stability": 1.4,
            "covariance_drift": 0.8,
            "supporting_families": {
                "sensor_deviation": True,
                "relationship_shift": True,
            },
            "active_families": 2,
            "persistence_satisfied": True,
            "rule_triggered": "high_rel_stability_with_cov_shift",
        }
    )

    assert result["contributors"]["top_signals"][0]["signal"] == "sensor_0"
    assert result["contributors"]["top_relationships"][0]["pair"] == [
        "sensor_0",
        "sensor_1",
    ]
