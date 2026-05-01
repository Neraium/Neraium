import numpy as np


def compute_trajectory_direction(history, current):
    cycles_of_evidence = len(history) + 1

    if cycles_of_evidence < 5:
        return {
            "direction": "ambiguous",
            "drift_velocity": 0.0,
            "drift_acceleration": 0.0,
            "relational_recovery": 0.0,
            "cycles_of_evidence": cycles_of_evidence,
        }

    points = (history + [current])[-5:]
    drift_values = np.array([point["drift_score"] for point in points], dtype=float)
    rel_values = np.array([point["rel_stability"] for point in points], dtype=float)
    x = np.arange(len(points), dtype=float)

    drift_velocity = float(np.polyfit(x, drift_values, 1)[0])
    relational_recovery = float(np.polyfit(x, rel_values, 1)[0])

    drift_acceleration = 0.0
    if len(points) >= 5:
        first_half_x = np.arange(3, dtype=float)
        second_half_x = np.arange(3, dtype=float)
        first_half_slope = np.polyfit(first_half_x, drift_values[:3], 1)[0]
        second_half_slope = np.polyfit(second_half_x, drift_values[2:], 1)[0]
        drift_acceleration = float(second_half_slope - first_half_slope)

    if drift_velocity > 0.01:
        direction = "diverging"
    elif drift_velocity < -0.01 and relational_recovery > 0:
        direction = "stabilizing"
    elif abs(drift_velocity) <= 0.01:
        direction = "flat"
    else:
        direction = "ambiguous"

    return {
        "direction": direction,
        "drift_velocity": drift_velocity,
        "drift_acceleration": drift_acceleration,
        "relational_recovery": relational_recovery,
        "cycles_of_evidence": cycles_of_evidence,
    }
