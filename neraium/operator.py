"""
Operator-facing output layer.

Translates engine output into human-readable, decision-support language.
Makes no failure predictions or exact root-cause claims.
"""


PATTERN_SUMMARIES = {
    "RELATIONSHIP_DECAY": "Existing signal relationships are weakening.",
    "RELATIONSHIP_FORMATION": "Previously weak signal relationships are strengthening.",
    "LOAD_RESPONSE_MISMATCH": "Drift is rising without a matching covariance shift.",
    "UNCONTROLLED_DIVERGENCE": "Drift, relationship shift, and trajectory pressure are all elevated.",
    "RECOVERY_PATTERN": "Recent confirmed evidence is moving toward recovery.",
    "STRUCTURAL_CHANGE_UNCERTAIN": "Structural change is confirmed, but the pattern is uncertain.",
}

PATTERN_MEANINGS = {
    "RELATIONSHIP_FORMATION": "Signals are becoming more tightly coupled than normal",
    "RELATIONSHIP_DECAY": "Signals are losing their normal coordination",
    "LOAD_RESPONSE_MISMATCH": "System response is no longer aligning with operating conditions",
    "UNCONTROLLED_DIVERGENCE": "System behavior is rapidly moving away from baseline",
    "RECOVERY_PATTERN": "System behavior is moving back toward baseline",
    "STRUCTURAL_CHANGE_UNCERTAIN": "System structure is changing in a way not yet clearly characterized",
}

# States that indicate active structural change
_ACTIVE_STATES = {"ALERT", "ALERT_HELD"}
# State used for "watching but not yet confirmed"
_WATCH_STATE = "WATCH"


def build_operator_output(engine_output: dict, sensor_context: dict | None = None) -> dict:
    status = engine_output.get("status")

    if status == _WATCH_STATE:
        return {"status": _WATCH_STATE}

    if status not in _ACTIVE_STATES:
        return {"status": status}

    context = sensor_context or {}
    what_is_happening = engine_output.get("what_is_happening", {})
    pattern = what_is_happening.get("pattern", "STRUCTURAL_CHANGE_UNCERTAIN")

    contributors = engine_output.get("where", engine_output.get("contributors", {}))
    trajectory = engine_output.get("trajectory", {})

    top_signal_ids = _top_signal_ids(contributors)
    top_signals = [_signal_name(sid, context) for sid in top_signal_ids]
    relationship_pair_ids = _top_relationship_pair_ids(contributors)
    relationship_pair = (
        [_signal_name(sid, context) for sid in relationship_pair_ids]
        if relationship_pair_ids else None
    )
    where_to_look = _where_to_look(top_signal_ids, relationship_pair_ids, context)

    return {
        "status": status,
        "confidence_score": engine_output.get("confidence_score"),
        "what_is_happening": {
            "pattern": pattern,
            "summary": PATTERN_SUMMARIES.get(pattern, PATTERN_SUMMARIES["STRUCTURAL_CHANGE_UNCERTAIN"]),
        },
        "where": {
            "top_signals": top_signals,
            "top_relationship_pair": relationship_pair,
        },
        "where_to_look": where_to_look,
        "plain_english": _plain_english(relationship_pair, where_to_look),
        "trajectory": {
            "direction": trajectory.get("direction"),
            "urgency": _trajectory_urgency(trajectory),
        },
        "if_ignored": {
            "expected_behavior": _expected_behavior(trajectory.get("direction")),
            "basis": "current trajectory direction and persistence",
        },
        "why_it_matters": {
            "meaning": PATTERN_MEANINGS.get(pattern, PATTERN_MEANINGS["STRUCTURAL_CHANGE_UNCERTAIN"]),
            "implication": "current behavior may not remain consistent under the same conditions",
            "not_claiming": "does not assert specific failure mode or timing",
        },
        "recommended_next_step": _recommended_next_step(status),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _top_signal_ids(contributors):
    signals = contributors.get("top_signals", [])
    signal_ids = [s.get("signal") for s in signals]
    relationships = contributors.get("top_relationships", [])
    if relationships:
        pair = relationships[0].get("pair", [])
        prioritized = list(pair)
        for sid in signal_ids:
            if sid not in prioritized:
                prioritized.append(sid)
        return prioritized[:2]
    return signal_ids[:2]


def _top_relationship_pair_ids(contributors):
    relationships = contributors.get("top_relationships", [])
    if not relationships:
        return None
    return relationships[0].get("pair")


def _signal_name(signal_id, sensor_context):
    return sensor_context.get(signal_id, {}).get("name", signal_id)


def _where_to_look(top_signal_ids, relationship_pair_ids, sensor_context):
    ordered = []
    for sid in (relationship_pair_ids or []) + top_signal_ids:
        if sid not in ordered:
            ordered.append(sid)

    subsystems, components = [], []
    for sid in ordered:
        ctx = sensor_context.get(sid, {})
        sub = ctx.get("subsystem")
        comp = ctx.get("component")
        if sub and sub not in subsystems:
            subsystems.append(sub)
        if comp and comp not in components:
            components.append(comp)

    return {"subsystems": subsystems, "components": components}


def _plain_english(relationship_pair, where_to_look):
    if relationship_pair and len(relationship_pair) >= 2:
        what = (
            f"{relationship_pair[0]} and {relationship_pair[1]} are moving together more than normal."
        )
    else:
        what = "The top signals are no longer behaving like the learned baseline."

    subsystems = where_to_look.get("subsystems", [])
    if len(subsystems) >= 2:
        where = f"Start inspection around the {subsystems[0]} and {subsystems[1]}."
    elif len(subsystems) == 1:
        where = f"Start inspection around the {subsystems[0]}."
    else:
        where = "Start inspection around the top reported signals."

    return {
        "what_this_means": what,
        "where_to_start": where,
        "what_we_are_not_claiming": (
            "This does not identify an exact failed component without machine-specific "
            "topology and inspection context."
        ),
    }


def _recommended_next_step(status):
    if status == "ALERT_HELD":
        return "CONTINUE_MONITORING"
    if status == "ALERT":
        return "INSPECT_TOP_SIGNALS_AND_RELATIONSHIPS"
    return "CONTINUE_MONITORING"


def _trajectory_urgency(trajectory):
    slopes = trajectory.get("recent_slopes", [])
    current_slope = float(trajectory.get("drift_velocity", 0.0))
    if not slopes:
        if current_slope > 0.05:
            return "high"
        if current_slope > 0.01:
            return "medium"
        return "low"

    percentile_rank = sum(float(s) <= current_slope for s in slopes) / len(slopes)
    if percentile_rank >= 0.8:
        return "high"
    if percentile_rank >= 0.5:
        return "medium"
    return "low"


def _expected_behavior(direction):
    return {
        "diverging": "continued structural divergence",
        "stabilizing": "structural stabilization likely if current trend continues",
        "flat": "structural state likely to remain similar in near term",
        "ambiguous": "trajectory unclear; additional observation required",
    }.get(direction or "ambiguous", "trajectory unclear; additional observation required")
