"""
Structural pattern classification.

All thresholds are expressed as relative quantities:
  - drift thresholds are normalized by alert_threshold (1.0 = at alert level)
  - relational_stability is a ratio vs baseline (1.0 = unchanged)
  - covariance_shift is a fraction of baseline covariance scale

No dataset-specific absolute values.
"""

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


def classify_pattern(scores, previous_scores=None, config=None, alert_threshold: float = 1.0):
    """
    Classify the structural pattern.

    alert_threshold: the engine's adaptive alert threshold; used to normalize
    the raw drift score so pattern rules are dataset-agnostic.
    """
    raw_drift = _score(scores, "drift_score")
    # Normalize drift by alert threshold so 1.0 = exactly at alert level.
    norm_drift = raw_drift / max(float(alert_threshold), 1e-6)

    # Accept both old (rel_stability/cov_shift) and new key names for compatibility
    rel_stability = _score(scores, "relational_stability", _score(scores, "rel_stability", 1.0))
    cov_shift = _score(scores, "covariance_shift", _score(scores, "cov_shift", 0.0))
    trajectory_pressure = _score(scores, "trajectory_pressure")

    # ── Recovery: sustained decline in drift + improving stability ─────────────
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

    # ── Uncontrolled divergence: very high normalized drift + all indicators ──
    # norm_drift >= 1.6 → 60 % above alert threshold
    if (
        norm_drift >= 1.6
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

    # ── Relationship decay: correlation structure weaker than baseline ─────────
    # rel_stability < 0.75 → strength dropped to 75 % of baseline
    # cov_shift > 0.15 → 15 % relative covariance change (already relative)
    if rel_stability <= 0.75 and cov_shift >= 0.15:
        return _result(
            RELATIONSHIP_DECAY,
            "low_rel_stability_with_cov_shift",
            scores,
            0.75,
        )

    # ── Relationship formation: correlation structure stronger than baseline ───
    if rel_stability >= 1.25 and cov_shift >= 0.15:
        return _result(
            RELATIONSHIP_FORMATION,
            "high_rel_stability_with_cov_shift",
            scores,
            0.75,
        )

    # ── Load-response mismatch: drift elevated but no covariance change ────────
    # norm_drift >= 1.0 → at or above alert threshold
    if norm_drift >= 1.0 and trajectory_pressure >= 0.5 and cov_shift < 0.15:
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
    drift_values = [_score(s, "drift_score") for s in recent_scores]
    # Accept both new and old key names
    rel_values = [
        _score(s, "relational_stability", _score(s, "rel_stability", 1.0))
        for s in recent_scores
    ]

    drift_declines = sum(
        cur < prev for prev, cur in zip(drift_values, drift_values[1:])
    )
    rel_improvements = sum(
        cur > prev for prev, cur in zip(rel_values, rel_values[1:])
    )
    recent_peak = max(drift_values)

    return (
        drift_declines >= 3
        and rel_improvements >= 3
        and drift_values[-1] <= recent_peak * 0.8
    )
