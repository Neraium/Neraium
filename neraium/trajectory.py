import numpy as np


def compute_trajectory_direction(
    history,
    current,
    status=None,
    pattern=None,
    persistence_satisfied=False,
    relationship_shift=False,
    cov_shift_threshold=0.15,
):
    cycles_of_evidence = len(history) + 1

    if cycles_of_evidence < 5:
        direction = "ambiguous"
        if _relationship_shift_bias_applies(
            current=current,
            status=status,
            pattern=pattern,
            persistence_satisfied=persistence_satisfied,
            relationship_shift=relationship_shift,
            cov_shift_threshold=cov_shift_threshold,
            drift_velocity=0.0,
        ):
            direction = "diverging"
        return {
            "direction": direction,
            "drift_velocity": 0.0,
            "drift_acceleration": 0.0,
            "relational_recovery": 0.0,
            "cycles_of_evidence": cycles_of_evidence,
        }

    points = (history + [current])[-10:]
    drift_values = np.array([point["drift_score"] for point in points], dtype=float)
    rel_values = np.array([point["rel_stability"] for point in points], dtype=float)
    x = np.arange(len(points), dtype=float)

    drift_velocity = float(np.polyfit(x, drift_values, 1)[0])
    relational_recovery = float(np.polyfit(x, rel_values, 1)[0])

    drift_acceleration = 0.0
    if len(points) >= 5:
        midpoint = len(points) // 2
        first_half = drift_values[:midpoint]
        second_half = drift_values[midpoint:]
        first_half_x = np.arange(len(first_half), dtype=float)
        second_half_x = np.arange(len(second_half), dtype=float)
        first_half_slope = np.polyfit(first_half_x, first_half, 1)[0]
        second_half_slope = np.polyfit(second_half_x, second_half, 1)[0]
        drift_acceleration = float(second_half_slope - first_half_slope)

    positive_threshold = 0.01

    if drift_velocity > positive_threshold:
        direction = "diverging"
    elif drift_velocity < -positive_threshold:
        direction = "stabilizing"
    else:
        direction = "flat"

    if _relationship_shift_bias_applies(
        current=current,
        status=status,
        pattern=pattern,
        persistence_satisfied=persistence_satisfied,
        relationship_shift=relationship_shift,
        cov_shift_threshold=cov_shift_threshold,
        drift_velocity=drift_velocity,
    ):
        direction = "diverging"

    return {
        "direction": direction,
        "drift_velocity": drift_velocity,
        "drift_acceleration": drift_acceleration,
        "relational_recovery": relational_recovery,
        "cycles_of_evidence": cycles_of_evidence,
    }


def _relationship_shift_bias_applies(
    current,
    status,
    pattern,
    persistence_satisfied,
    relationship_shift,
    cov_shift_threshold,
    drift_velocity,
):
    relationship_formation_confirmed = (
        pattern == "RELATIONSHIP_FORMATION"
        and persistence_satisfied is True
    )
    relationship_shift_confirmed = (
        status == "CONFIRMED_CHANGE"
        and persistence_satisfied is True
        and relationship_shift is True
    )

    return (
        (relationship_formation_confirmed or relationship_shift_confirmed)
        and (
            drift_velocity > 0.0
            or current.get("cov_shift", 0.0) >= cov_shift_threshold
        )
    )
