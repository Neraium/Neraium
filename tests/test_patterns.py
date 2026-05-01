from neraium.patterns import (
    LOAD_RESPONSE_MISMATCH,
    RECOVERY_PATTERN,
    RELATIONSHIP_DECAY,
    STRUCTURAL_CHANGE_UNCERTAIN,
    UNCONTROLLED_DIVERGENCE,
    classify_pattern,
)


def test_relationship_decay_scores_classify_as_relationship_decay():
    scores = {
        "drift_score": 4.0,
        "rel_stability": 0.6,
        "cov_shift": 0.2,
        "trajectory_pressure": 0.1,
    }

    result = classify_pattern(scores)

    assert result["pattern"] == RELATIONSHIP_DECAY
    assert result["confidence_score"] == 0.75
    assert result["scores_at_classification"] is scores


def test_high_drift_high_pressure_classifies_as_uncontrolled_divergence():
    scores = {
        "drift_score": 8.5,
        "rel_stability": 0.4,
        "cov_shift": 0.45,
        "trajectory_pressure": 0.75,
    }

    result = classify_pattern(scores)

    assert result["pattern"] == UNCONTROLLED_DIVERGENCE
    assert result["confidence_score"] == 0.85


def test_high_drift_pressure_without_covariance_shift_is_load_response_mismatch():
    scores = {
        "drift_score": 5.5,
        "rel_stability": 0.9,
        "cov_shift": 0.05,
        "trajectory_pressure": 0.6,
    }

    result = classify_pattern(scores)

    assert result["pattern"] == LOAD_RESPONSE_MISMATCH
    assert result["confidence_score"] == 0.70


def test_improving_drift_and_stability_classifies_as_recovery_pattern():
    previous_scores = {
        "drift_score": 8.0,
        "rel_stability": 0.55,
        "cov_shift": 0.4,
        "recent_history": [
            {"drift_score": 10.0, "rel_stability": 0.4, "cov_shift": 0.4},
            {"drift_score": 9.0, "rel_stability": 0.45, "cov_shift": 0.35},
            {"drift_score": 8.5, "rel_stability": 0.5, "cov_shift": 0.3},
            {"drift_score": 8.0, "rel_stability": 0.55, "cov_shift": 0.25},
        ],
    }
    scores = {
        "drift_score": 7.5,
        "rel_stability": 0.6,
        "cov_shift": 0.2,
        "trajectory_pressure": 0.8,
    }

    result = classify_pattern(scores, previous_scores=previous_scores)

    assert result["pattern"] == RECOVERY_PATTERN
    assert result["confidence_score"] == 0.65


def test_small_one_cycle_dip_does_not_classify_as_recovery_pattern():
    previous_scores = {
        "drift_score": 10.0,
        "rel_stability": 0.4,
        "cov_shift": 0.1,
    }
    scores = {
        "drift_score": 9.0,
        "rel_stability": 0.45,
        "cov_shift": 0.1,
        "trajectory_pressure": 0.0,
    }

    result = classify_pattern(scores, previous_scores=previous_scores)

    assert result["pattern"] == STRUCTURAL_CHANGE_UNCERTAIN
    assert result["confidence_score"] == 0.40


def test_large_one_cycle_drop_without_history_does_not_classify_as_recovery():
    previous_scores = {
        "drift_score": 10.0,
        "rel_stability": 0.4,
        "cov_shift": 0.1,
    }
    scores = {
        "drift_score": 7.0,
        "rel_stability": 0.5,
        "cov_shift": 0.1,
        "trajectory_pressure": 0.0,
    }

    result = classify_pattern(scores, previous_scores=previous_scores)

    assert result["pattern"] == STRUCTURAL_CHANGE_UNCERTAIN
    assert result["confidence_score"] == 0.40


def test_ambiguous_scores_classify_as_uncertain():
    scores = {
        "drift_score": 3.0,
        "rel_stability": 0.9,
        "cov_shift": 0.1,
        "trajectory_pressure": 0.2,
    }

    result = classify_pattern(scores)

    assert result["pattern"] == STRUCTURAL_CHANGE_UNCERTAIN
    assert result["confidence_score"] == 0.40
