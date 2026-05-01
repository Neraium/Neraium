RELATIONSHIP_DECAY = "RELATIONSHIP_DECAY"
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

    if previous_scores is not None:
        previous_drift = _score(previous_scores, "drift_score")
        previous_rel_stability = _score(previous_scores, "rel_stability", 1.0)
        if (
            drift_score < previous_drift
            and rel_stability > previous_rel_stability
        ):
            return _result(
                RECOVERY_PATTERN,
                "drift_decreasing_and_rel_stability_improving",
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
