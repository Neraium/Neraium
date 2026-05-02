"""
Tests for build_engineer_output().

Engineer output is the technical audit trail: raw metrics, evidence families,
contributors, and pattern classification.
"""

from neraium.engineer import build_engineer_output


def make_engine_output(status="ALERT"):
    return {
        "status": status,
        "drift_score": 12.5,
        "structural_drift_score": 12.5,
        "relational_stability": 1.4,
        "relational_stability_score": 0.6,
        "covariance_shift": 0.8,
        "covariance_drift": 0.8,
        "watch_threshold": 2.0,
        "alert_threshold": 4.0,
        "trajectory": {
            "direction": "diverging",
            "drift_velocity": 0.2,
            "drift_acceleration": 0.05,
        },
        "drift_velocity": 0.2,
        "supporting_families": {
            "sensor_deviation": True,
            "relationship_shift": True,
            "relational_stability_change": False,
            "trajectory_pressure": False,
        },
        "active_families": ["sensor_deviation", "relationship_shift"],
        "evidence_count": 3,
        "persistence_satisfied": True,
        "time_in_state": 2,
        "confidence_score": 0.75,
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


def test_watch_state_returns_minimal_output():
    result = build_engineer_output({"status": "WATCH", "drift_score": 3.0})
    assert result == {"status": "WATCH"}


def test_alert_returns_full_output():
    result = build_engineer_output(make_engine_output())

    assert result["status"] == "ALERT"
    assert result["structural_metrics"]["drift_score"] == 12.5
    assert result["structural_metrics"]["structural_drift_score"] == 12.5
    assert result["structural_metrics"]["relational_stability"] == 1.4
    assert result["structural_metrics"]["covariance_shift"] == 0.8
    assert result["structural_metrics"]["watch_threshold"] == 2.0
    assert result["structural_metrics"]["alert_threshold"] == 4.0
    assert result["trajectory_metrics"]["direction"] == "diverging"
    assert result["trajectory_metrics"]["drift_velocity"] == 0.2
    assert result["trajectory_metrics"]["drift_acceleration"] == 0.05
    assert result["evidence"]["persistence_satisfied"] is True
    assert result["evidence"]["evidence_count"] == 3
    assert result["evidence"]["confidence_score"] == 0.75
    assert result["pattern"]["type"] == "RELATIONSHIP_FORMATION"
    assert result["pattern"]["rule_triggered"] == "high_rel_stability_with_cov_shift"
    assert result["contributors"]["top_signals"][0]["signal"] == "sensor_0"


def test_alert_held_returns_full_output():
    result = build_engineer_output(make_engine_output("ALERT_HELD"))
    assert result["status"] == "ALERT_HELD"
    assert "structural_metrics" in result


def test_missing_fields_are_none_or_default():
    result = build_engineer_output(
        {
            "status": "ALERT",
            "trajectory": {},
            "what_is_happening": {},
        }
    )
    assert result["structural_metrics"]["drift_score"] is None
    assert result["structural_metrics"]["covariance_shift"] is None
    assert result["trajectory_metrics"]["direction"] is None
    assert result["evidence"]["persistence_satisfied"] is False
    assert result["contributors"] is None
    assert result["pattern"]["type"] is None
    assert result["pattern"]["rule_triggered"] is None
