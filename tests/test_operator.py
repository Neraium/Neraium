"""
Tests for build_operator_output().

Operator output translates engine state into human-readable decision support.
No CNC-specific sensor context is assumed; generic sensor names are used.
Pass sensor_context to get human-friendly names.
"""

from neraium.engineer import build_engineer_output
from neraium.operator import build_operator_output


# ── Fixture helpers ───────────────────────────────────────────────────────────

SENSOR_CTX = {
    "sensor_0": {"name": "Signal A", "subsystem": "Subsystem X", "component": "comp_a"},
    "sensor_1": {"name": "Signal B", "subsystem": "Subsystem Y", "component": "comp_b"},
    "sensor_2": {"name": "Signal C", "subsystem": "Subsystem Z", "component": "comp_c"},
}


def make_alert_output(status="ALERT"):
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


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_watch_state_returns_minimal_output():
    result = build_operator_output({"status": "WATCH", "drift_score": 4.0})
    assert result == {"status": "WATCH"}


def test_stable_state_returns_stable_status():
    result = build_operator_output({"status": "STABLE"})
    assert result == {"status": "STABLE"}


def test_alert_returns_full_structured_output():
    result = build_operator_output(make_alert_output(), sensor_context=SENSOR_CTX)

    assert result["status"] == "ALERT"
    assert result["confidence_score"] == 0.75
    assert result["what_is_happening"]["pattern"] == "RELATIONSHIP_FORMATION"
    assert "where" in result
    assert "where_to_look" in result
    assert "plain_english" in result
    assert "trajectory" in result
    assert "if_ignored" in result
    assert "why_it_matters" in result
    assert "recommended_next_step" in result
    assert "drift_score" not in result


def test_alert_held_returns_continue_monitoring():
    result = build_operator_output(make_alert_output("ALERT_HELD"))
    assert result["status"] == "ALERT_HELD"
    assert result["recommended_next_step"] == "CONTINUE_MONITORING"


def test_alert_returns_inspect_action():
    result = build_operator_output(make_alert_output())
    assert result["recommended_next_step"] == "INSPECT_TOP_SIGNALS_AND_RELATIONSHIPS"


def test_signal_names_mapped_when_context_provided():
    result = build_operator_output(make_alert_output(), sensor_context=SENSOR_CTX)
    assert result["where"]["top_signals"] == ["Signal A", "Signal B"]
    assert result["where"]["top_relationship_pair"] == ["Signal A", "Signal B"]


def test_generic_sensor_ids_used_when_no_context():
    result = build_operator_output(make_alert_output())
    assert result["where"]["top_signals"] == ["sensor_0", "sensor_1"]


def test_where_to_look_uses_context_subsystems():
    result = build_operator_output(make_alert_output(), sensor_context=SENSOR_CTX)
    assert "Subsystem X" in result["where_to_look"]["subsystems"]
    assert "Subsystem Y" in result["where_to_look"]["subsystems"]


def test_top_signals_prioritizes_relationship_pair_over_contributor_rank():
    engine_output = make_alert_output()
    engine_output["where"]["top_signals"] = [
        {"signal": "sensor_2", "contribution": 0.6},
        {"signal": "sensor_1", "contribution": 0.3},
        {"signal": "sensor_0", "contribution": 0.1},
    ]
    result = build_operator_output(engine_output, sensor_context=SENSOR_CTX)
    # Relationship pair (sensor_0, sensor_1) should take priority
    assert result["where"]["top_signals"] == ["Signal A", "Signal B"]


def test_top_signals_uses_contributor_rank_when_no_relationship_pair():
    engine_output = make_alert_output()
    engine_output["where"]["top_relationships"] = []
    result = build_operator_output(engine_output, sensor_context=SENSOR_CTX)
    assert result["where"]["top_signals"] == ["Signal A", "Signal B"]


def test_engineer_output_exposes_raw_signal_ids():
    result = build_engineer_output(
        {
            **make_alert_output(),
            "relational_stability": 1.4,
            "covariance_shift": 0.8,
            "supporting_families": {"sensor_deviation": True, "relationship_shift": True},
            "active_families": 2,
            "persistence_satisfied": True,
            "rule_triggered": "high_rel_stability_with_cov_shift",
        }
    )
    assert result["contributors"]["top_signals"][0]["signal"] == "sensor_0"
    assert result["contributors"]["top_relationships"][0]["pair"] == ["sensor_0", "sensor_1"]
