RELATIONSHIP_DECAY = "RELATIONSHIP_DECAY"
RELATIONSHIP_FORMATION = "RELATIONSHIP_FORMATION"
LOAD_RESPONSE_MISMATCH = "LOAD_RESPONSE_MISMATCH"
UNCONTROLLED_DIVERGENCE = "UNCONTROLLED_DIVERGENCE"
RECOVERY_PATTERN = "RECOVERY_PATTERN"
STRUCTURAL_CHANGE_UNCERTAIN = "STRUCTURAL_CHANGE_UNCERTAIN"


def _score(scores, key, default=0.0):
    return float(scores.get(key, default))


def _result(pattern, rule_triggered, scores, confidence_score):
    return {
        "pattern": pattern,
        "rule_triggered": rule_triggered,
        "scores_at_classification": scores,
        "confidence_score": float(confidence_score),
    }


def classify_pattern(scores, previous_scores=None, config=None):
    drift_score = _score(scores, "drift_score")
    rel_stability = _score(scores, "rel_stability", 1.0)
    cov_shift = _score(scores, "cov_shift")
    trajectory_pressure = _score(scores, "trajectory_pressure")

    recent_history = []
    if previous_scores is not None:
        recent_history = previous_scores.get("recent_history", [])
        recent_scores = (recent_history + [scores])[-5:]
        if len(recent_scores) >= 5 and _has_sustained_recovery(recent_scores):
            return _result(
                RECOVERY_PATTERN,
                "sustained_drift_decline_and_rel_stability_improvement",
                scores,
                0.65,
            )

    if (
        drift_score >= 8.0
        and rel_stability <= 0.5
        and cov_shift >= 0.4
        and trajectory_pressure >= 0.7
    ):
        return _result(
            UNCONTROLLED_DIVERGENCE,
            "high_drift_low_stability_high_cov_shift_high_trajectory_pressure",
            scores,
            0.85,
        )

    if rel_stability <= 0.75 and cov_shift >= 0.15:
        return _result(
            RELATIONSHIP_DECAY,
            "low_rel_stability_with_cov_shift",
            scores,
            0.75,
        )

    if rel_stability >= 1.25 and cov_shift >= 0.15:
        return _result(
            RELATIONSHIP_FORMATION,
            "high_rel_stability_with_cov_shift",
            scores,
            0.75,
        )

    if (
        drift_score >= 5.0
        and trajectory_pressure >= 0.5
        and cov_shift < 0.15
    ):
        return _result(
            LOAD_RESPONSE_MISMATCH,
            "high_drift_high_trajectory_pressure_without_cov_shift",
            scores,
            0.70,
        )

    return _result(
        STRUCTURAL_CHANGE_UNCERTAIN,
        "no_structural_pattern_rule_matched",
        scores,
        0.40,
    )


def _has_sustained_recovery(recent_scores):
    drift_values = [_score(score, "drift_score") for score in recent_scores]
    rel_values = [_score(score, "rel_stability", 1.0) for score in recent_scores]

    drift_declines = sum(
        current < previous
        for previous, current in zip(drift_values, drift_values[1:])
    )
    rel_improvements = sum(
        current > previous
        for previous, current in zip(rel_values, rel_values[1:])
    )
    recent_peak = max(drift_values)

    return (
        drift_declines >= 3
        and rel_improvements >= 3
        and drift_values[-1] <= recent_peak * 0.8
    )
