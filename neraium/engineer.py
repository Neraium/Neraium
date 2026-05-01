def build_engineer_output(engine_output: dict) -> dict:
    status = engine_output.get("status")

    if status == "TRANSIENT":
        return {"status": "TRANSIENT"}

    trajectory = engine_output.get("trajectory", {})
    what_is_happening = engine_output.get("what_is_happening", {})

    return {
        "status": status,
        "structural_metrics": {
            "drift_score": engine_output.get("drift_score"),
            "relational_stability": engine_output.get("relational_stability"),
            "covariance_shift": engine_output.get("covariance_drift"),
        },
        "trajectory_metrics": {
            "direction": trajectory.get("direction"),
            "drift_velocity": trajectory.get("velocity"),
            "drift_acceleration": trajectory.get("acceleration"),
        },
        "evidence": {
            "active_families": engine_output.get("active_families"),
            "persistence_satisfied": engine_output.get(
                "persistence_satisfied",
                False,
            ),
        },
        "contributors": engine_output.get("where"),
        "pattern": {
            "type": what_is_happening.get("pattern"),
            "rule_triggered": engine_output.get("rule_triggered"),
        },
    }
