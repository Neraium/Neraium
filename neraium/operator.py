PATTERN_SUMMARIES = {
    "RELATIONSHIP_DECAY": "Existing signal relationships are weakening.",
    "RELATIONSHIP_FORMATION": "Previously weak signal relationships are strengthening.",
    "LOAD_RESPONSE_MISMATCH": "Drift is rising without a matching covariance shift.",
    "UNCONTROLLED_DIVERGENCE": "Drift, relationship shift, and trajectory pressure are all elevated.",
    "RECOVERY_PATTERN": "Recent confirmed evidence is moving toward recovery.",
    "STRUCTURAL_CHANGE_UNCERTAIN": "Structural change is confirmed, but the pattern is uncertain.",
}


def build_operator_output(engine_output: dict) -> dict:
    status = engine_output.get("status")

    if status == "TRANSIENT":
        return {"status": "TRANSIENT"}

    what_is_happening = engine_output.get("what_is_happening", {})
    pattern = what_is_happening.get("pattern", "STRUCTURAL_CHANGE_UNCERTAIN")
    contributors = engine_output.get("where", {})
    trajectory = engine_output.get("trajectory", {})

    return {
        "status": status,
        "confidence_score": engine_output.get("confidence_score"),
        "what_is_happening": {
            "pattern": pattern,
            "summary": PATTERN_SUMMARIES.get(
                pattern,
                PATTERN_SUMMARIES["STRUCTURAL_CHANGE_UNCERTAIN"],
            ),
        },
        "where": {
            "top_signals": _top_signal_names(contributors),
            "top_relationship_pair": _top_relationship_pair(contributors),
        },
        "trajectory": {
            "direction": trajectory.get("direction"),
            "urgency": _trajectory_urgency(trajectory),
        },
        "if_ignored": {
            "expected_behavior": _expected_behavior(trajectory.get("direction")),
            "basis": "current trajectory direction and persistence",
        },
        "recommended_next_step": _recommended_next_step(status),
    }


def _top_signal_names(contributors):
    signals = contributors.get("top_signals", [])
    return [signal.get("signal") for signal in signals[:2]]


def _top_relationship_pair(contributors):
    relationships = contributors.get("top_relationships", [])
    if not relationships:
        return None
    return relationships[0].get("pair")


def _recommended_next_step(status):
    if status == "CONFIRMED_CHANGE_HELD":
        return "CONTINUE_MONITORING"
    if status == "CONFIRMED_CHANGE":
        return "INSPECT_TOP_SIGNALS_AND_RELATIONSHIPS"
    return "CONTINUE_MONITORING"


def _trajectory_urgency(trajectory):
    slopes = trajectory.get("recent_slopes", [])
    if len(slopes) < 2:
        return "low"

    current_slope = float(trajectory.get("drift_velocity", 0.0))
    percentile_rank = sum(float(slope) <= current_slope for slope in slopes) / len(slopes)

    if percentile_rank >= 0.8:
        return "high"
    if percentile_rank >= 0.5:
        return "medium"
    return "low"


def _expected_behavior(direction):
    behavior = {
        "diverging": "continued structural divergence",
        "stabilizing": "structural stabilization likely if current trend continues",
        "flat": "structural state likely to remain similar in near term",
        "ambiguous": "trajectory unclear; additional observation required",
    }
    return behavior.get(direction, behavior["ambiguous"])
