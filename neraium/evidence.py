"""
Evidence family analysis.

Determines which evidence families are active for a given observation.
Thresholds are derived from the baseline (passed in from the engine)
so no dataset-specific values are hardcoded here.

Evidence families:
    sensor_deviation          — one or more signals deviate beyond the watch band
    relationship_shift        — covariance structure shifted from baseline
    relational_stability_change — mean correlation strength changed
    trajectory_pressure       — DMD spectral shift (placeholder, not yet active)
"""

import numpy as np

from neraium.config import NeraiumConfig


def compute_evidence_families(
    *,
    z_scores: np.ndarray,
    window: list[np.ndarray],
    baseline_median: np.ndarray,
    baseline_mad: np.ndarray,
    baseline_corr: np.ndarray,
    drift_score: float,
    watch_threshold: float,
    alert_threshold: float,
    config: NeraiumConfig,
) -> dict:
    """
    Return which evidence families are active.

    Parameters are injected from the engine (no hardcoded dataset thresholds).
    Relationship thresholds are expressed as relative changes from baseline.
    """
    families: dict[str, bool] = {}

    # ── 1. Sensor deviation ───────────────────────────────────────────────────
    # Any signal z-score exceeds the watch-band multiplier (e.g. ±3σ).
    z_band = config.watch_mad_multiplier * config.mad_scale
    families["sensor_deviation"] = bool(np.any(np.abs(z_scores) > z_band))

    # ── 2. Relationship shift (covariance) ────────────────────────────────────
    # Current covariance structure has shifted relative to baseline.
    # Threshold: mean relative covariance change > 15 % (relative, not absolute).
    relationship_shift = False
    if len(window) >= 3:
        arr = np.array(window[-20:])
        if arr.shape[0] >= 2:
            sigma_equiv = baseline_mad * config.mad_scale
            norm_arr = (arr - baseline_median) / sigma_equiv
            current_cov = np.cov(norm_arr.T)
            # Baseline normalized cov ≈ identity; relative shift vs identity.
            eye = np.eye(len(baseline_median))
            off_diag_mask = ~np.eye(len(baseline_median), dtype=bool)
            if off_diag_mask.any():
                # Max off-diagonal shift — any single pair above threshold is enough
                shift = float(np.max(np.abs((current_cov - eye)[off_diag_mask])))
                relationship_shift = shift > 0.15          # 15 % relative to z-scored space
    families["relationship_shift"] = relationship_shift

    # ── 3. Relational stability change ────────────────────────────────────────
    # Mean absolute correlation drifted beyond ±25 % of baseline level.
    rel_change = False
    if len(window) >= 3 and baseline_corr is not None:
        arr = np.array(window[-20:])
        if arr.shape[0] >= 2:
            current_corr = np.corrcoef(arr.T)
            np.nan_to_num(current_corr, nan=0.0, copy=False)
            mask = ~np.eye(current_corr.shape[0], dtype=bool)
            if mask.any():
                baseline_mean = float(np.mean(np.abs(baseline_corr[mask])))
                current_mean = float(np.mean(np.abs(current_corr[mask])))
                ratio = current_mean / (baseline_mean + config.cov_epsilon)
                # Flag if correlation strength changed by more than 25 %
                rel_change = ratio < 0.75 or ratio > 1.25
    families["relational_stability_change"] = rel_change

    # ── 4. Trajectory pressure (DMD spectral — not yet active) ────────────────
    families["trajectory_pressure"] = False
    trajectory_pressure = 0.0

    active_families = [k for k, v in families.items() if v]

    return {
        "families": families,
        "active_families": active_families,
        "trajectory_pressure": trajectory_pressure,
    }
