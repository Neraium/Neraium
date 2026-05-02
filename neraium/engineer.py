"""
Engineer-facing technical output layer.

Returns the full audit trail of structural metrics, evidence families,
contributors, and pattern classification for technical review.
"""

_ACTIVE_STATES = {"ALERT", "ALERT_HELD"}
_WATCH_STATE = "WATCH"


def build_engineer_output(engine_output: dict) -> dict:
    status = engine_output.get("status")

    if status == _WATCH_STATE:
        return {"status": _WATCH_STATE}

    if status not in _ACTIVE_STATES:
        return {"status": status}

    trajectory = engine_output.get("trajectory", {})
    what_is_happening = engine_output.get("what_is_happening", {})

    return {
        "status": status,
        "structural_metrics": {
            "drift_score": engine_output.get("drift_score"),
            "structural_drift_score": engine_output.get("structural_drift_score"),
            "relational_stability": engine_output.get("relational_stability"),
            "relational_stability_score": engine_output.get("relational_stability_score"),
            "covariance_shift": engine_output.get("covariance_shift"),
            "watch_threshold": engine_output.get("watch_threshold"),
            "alert_threshold": engine_output.get("alert_threshold"),
        },
        "trajectory_metrics": {
            "direction": trajectory.get("direction"),
            "drift_velocity": trajectory.get("drift_velocity"),
            "drift_acceleration": trajectory.get("drift_acceleration"),
            "drift_velocity_per_spec": engine_output.get("drift_velocity"),
        },
        "evidence": {
            "supporting_families": engine_output.get("supporting_families"),
            "active_families": engine_output.get("active_families"),
            "evidence_count": engine_output.get("evidence_count"),
            "persistence_satisfied": engine_output.get("persistence_satisfied", False),
            "time_in_state": engine_output.get("time_in_state"),
            "confidence_score": engine_output.get("confidence_score"),
        },
        "contributors": engine_output.get("where"),
        "pattern": {
            "type": what_is_happening.get("pattern"),
            "rule_triggered": engine_output.get("rule_triggered"),
        },
    }
