def compute_trajectory_direction(history, current):
    cycles_of_evidence = len(history) + 1

    if cycles_of_evidence < 3:
        return {
            "direction": "ambiguous",
            "drift_velocity": 0.0,
            "drift_acceleration": 0.0,
            "relational_recovery": 0.0,
            "cycles_of_evidence": cycles_of_evidence,
        }

    prev = history[-1]
    prev2 = history[-2]

    drift_velocity = float(current["drift_score"] - prev["drift_score"])
    prev_velocity = float(prev["drift_score"] - prev2["drift_score"])
    drift_acceleration = float(drift_velocity - prev_velocity)
    relational_recovery = float(current["rel_stability"] - prev["rel_stability"])

    if drift_velocity > 0.01 and drift_acceleration > 0:
        direction = "diverging"
    elif drift_velocity > 0.01 and drift_acceleration <= 0:
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
