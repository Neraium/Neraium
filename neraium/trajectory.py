"""
Trajectory direction computation.

Computes drift velocity and acceleration over recent history to characterize
whether the structural state is diverging, stabilizing, or flat.
"""

import numpy as np


def compute_trajectory_direction(
    history,
    current,
    *,
    pattern: str = None,
    status: str = None,
    persistence_satisfied: bool = False,
    relationship_shift: bool = False,
    cov_shift_threshold: float = 0.15,
):
    """
    Compute trajectory direction from a list of score dicts.

    history: list of dicts, each with at least 'drift_score' and
             'relational_stability' keys (most-recent last).
    current: dict for the current timestep.

    Returns a dict with direction, drift_velocity, drift_acceleration,
    relational_recovery, cycles_of_evidence.
    """
    all_points = list(history) + [current]
    cycles_of_evidence = len(all_points)

    if cycles_of_evidence < 5:
        return {
            "direction": "ambiguous",
            "drift_velocity": 0.0,
            "drift_acceleration": 0.0,
            "relational_recovery": 0.0,
            "cycles_of_evidence": cycles_of_evidence,
        }

    points = all_points[-5:]
    drift_values = np.array(
        [float(p.get("drift_score", 0.0)) for p in points], dtype=float
    )
    rel_values = np.array(
        # Accept both new and old key names
        [float(p.get("relational_stability", p.get("rel_stability", 1.0))) for p in points],
        dtype=float,
    )
    x = np.arange(len(points), dtype=float)

    drift_velocity = float(np.polyfit(x, drift_values, 1)[0])
    relational_recovery = float(np.polyfit(x, rel_values, 1)[0])

    # Acceleration: change in slope from first half to second half
    first_slope = float(np.polyfit(np.arange(3, dtype=float), drift_values[:3], 1)[0])
    second_slope = float(np.polyfit(np.arange(3, dtype=float), drift_values[2:], 1)[0])
    drift_acceleration = second_slope - first_slope

    if drift_velocity > 0.01:
        direction = "diverging"
    elif drift_velocity < -0.01 and relational_recovery > 0:
        direction = "stabilizing"
    elif abs(drift_velocity) <= 0.01:
        direction = "flat"
    else:
        direction = "ambiguous"

    # Structural context override: confirmed structural change with cov shift
    # forces "diverging" regardless of drift velocity trend.
    cov_shift = float(current.get("cov_shift", current.get("covariance_shift", 0.0)))
    if persistence_satisfied and cov_shift > cov_shift_threshold:
        if pattern == "RELATIONSHIP_FORMATION":
            direction = "diverging"
        elif relationship_shift or status in ("CONFIRMED_CHANGE", "ALERT", "ALERT_HELD"):
            direction = "diverging"

    return {
        "direction": direction,
        "drift_velocity": drift_velocity,
        "drift_acceleration": drift_acceleration,
        "relational_recovery": relational_recovery,
        "cycles_of_evidence": cycles_of_evidence,
    }
