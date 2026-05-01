import numpy as np


def _as_array(packet):
    if isinstance(packet, dict):
        return np.array(list(packet.values()), dtype=float)
    return np.asarray(packet, dtype=float)


def _get(baseline, key):
    if isinstance(baseline, dict):
        return baseline[key]
    return getattr(baseline, key)


def check_persistence(history, current, threshold, cycles):
    if cycles <= 1:
        return current > threshold

    recent = history[-(cycles - 1):]

    return (
        len(recent) == cycles - 1
        and all(float(h) > threshold for h in recent)
        and float(current) > threshold
    )


def compute_dmd_spectral_shift(window, baseline):
    # Placeholder for Phase 1.
    # Do not let missing DMD block the evidence gate.
    return 0.0


def compute_structural_evidence(packet, window, baseline, history, config):
    x = _as_array(packet)
    window = np.asarray(window, dtype=float)

    mean = np.asarray(_get(baseline, "mean"), dtype=float)
    mad = np.asarray(_get(baseline, "mad"), dtype=float)
    cov = np.asarray(_get(baseline, "cov"), dtype=float)
    baseline_corr = np.asarray(_get(baseline, "correlation"), dtype=float)

    z = (x - mean) / (mad * config.mad_scale + 1e-8)

    cov_reg = cov + np.eye(cov.shape[0]) * config.cov_epsilon
    inv_cov = np.linalg.pinv(cov_reg)

    drift_score = float(z @ inv_cov @ z)

    sensor_family = bool(np.any(np.abs(z) > config.sensor_threshold))

    if len(window) >= 3:
        current_cov = np.cov(window.T)
        cov_shift = np.linalg.norm(current_cov - cov, ord="fro") / (
            np.linalg.norm(cov, ord="fro") + 1e-8
        )

        current_corr = np.corrcoef(window.T)

        mask = ~np.eye(current_corr.shape[0], dtype=bool)
        current_abs_corr = np.abs(current_corr[mask])

        rel_stability = np.mean(current_abs_corr) / (
            np.mean(np.abs(baseline_corr[mask])) + 1e-8
        )

        max_relationship_strength = float(np.max(current_abs_corr))
        stability_upper_threshold = (
            config.rel_stability_threshold
            if config.rel_stability_threshold > 1.0
            else 1.0 / (config.rel_stability_threshold + 1e-8)
        )
        strong_pair_threshold = min(
            0.75,
            max(
                0.5,
                min(config.rel_stability_threshold, stability_upper_threshold) * 0.75,
            ),
        )
        strong_pair_relationship = max_relationship_strength > strong_pair_threshold
        relationship_family = bool(
            cov_shift > config.cov_shift_threshold
            and strong_pair_relationship
        )
        relational_family = bool(
            strong_pair_relationship
            and (
                rel_stability < config.rel_stability_threshold
                or rel_stability > stability_upper_threshold
            )
        )
    else:
        cov_shift = 0.0
        rel_stability = 1.0
        relationship_family = False
        relational_family = False

    if len(window) >= config.dmd_min_window:
        spectral_shift = compute_dmd_spectral_shift(window, baseline)
        trajectory_family = bool(spectral_shift > config.trajectory_threshold)
    else:
        trajectory_family = False

    supporting_families = {
        "sensor_deviation": sensor_family,
        "relationship_shift": relationship_family,
        "relational_stability_change": relational_family,
        "trajectory_pressure": trajectory_family,
    }

    active_families = int(sum(supporting_families.values()))
    non_sensor_families = int(
        sum(
            value
            for family, value in supporting_families.items()
            if family != "sensor_deviation"
        )
    )
    has_relationship_evidence = bool(relationship_family or relational_family)

    persistence_satisfied = check_persistence(
        history,
        drift_score,
        config.drift_threshold,
        config.persistence_cycles,
    )

    confirmed = (
        drift_score > config.drift_threshold
        and persistence_satisfied
        and active_families >= 2
        and has_relationship_evidence
    )

    return {
        "status": "CONFIRMED_CHANGE" if confirmed else "TRANSIENT",
        "drift_score": drift_score,
        "supporting_families": supporting_families,
        "active_families": active_families,
        "has_relationship_evidence": has_relationship_evidence,
        "non_sensor_families": non_sensor_families,
        "persistence_satisfied": bool(persistence_satisfied),
        "diagnostics": {
            "cov_shift": float(cov_shift),
            "rel_stability": float(rel_stability),
        },
    }
