"""
Signal and relationship contributor decomposition.

Ranks which signals and signal-pairs are driving the current structural change
using weighted absolute deviations from the robust baseline.
"""

import numpy as np


def _as_array(packet):
    if isinstance(packet, dict):
        return np.array(list(packet.values()), dtype=float)
    return np.asarray(packet, dtype=float)


def _get(baseline, key, fallback=None):
    if isinstance(baseline, dict):
        return baseline.get(key, fallback)
    return getattr(baseline, key, fallback)


def _signal_names(baseline, n_signals):
    for key in ("signal_names", "signals", "columns"):
        val = _get(baseline, key)
        if val is not None:
            return [str(name) for name in val]
    return [f"sensor_{idx}" for idx in range(n_signals)]


def _corrcoef_safe(window, n_signals):
    std = np.std(window, axis=0)
    if np.any(std <= 1e-12):
        corr = np.zeros((n_signals, n_signals), dtype=float)
        variable = std > 1e-12
        if np.any(variable):
            corr[np.ix_(variable, variable)] = np.corrcoef(window[:, variable].T)
        np.fill_diagonal(corr, 1.0)
        return corr
    return np.corrcoef(window.T)


def decompose_contributors(packet, window, baseline, config):
    """
    Decompose which signals and relationships contribute most to current drift.

    baseline dict keys accepted:
        median  — per-signal median (preferred, robust)
        mean    — per-signal mean (fallback for legacy callers)
        mad     — per-signal MAD × mad_scale (sigma-equivalent)
        cov     — baseline covariance matrix
        correlation — baseline correlation matrix
    """
    x = _as_array(packet)
    window = np.asarray(window, dtype=float)

    # Support both new (median) and legacy (mean) baseline dicts
    center = _get(baseline, "median")
    if center is None:
        center = _get(baseline, "mean")
    center = np.asarray(center, dtype=float)
    mad = np.asarray(_get(baseline, "mad"), dtype=float)
    cov = np.asarray(_get(baseline, "cov"), dtype=float)

    corr_raw = _get(baseline, "correlation")
    baseline_corr = np.asarray(corr_raw, dtype=float) if corr_raw is not None else np.eye(x.shape[0])

    n_signals = x.shape[0]
    names = _signal_names(baseline, n_signals)
    top_n = min(int(getattr(config, "top_n", 3)), n_signals)
    top_n_relationships = int(getattr(config, "top_n_relationships", 5))

    epsilon = float(getattr(config, "cov_epsilon", 1e-6))
    z = (x - center) / (mad + epsilon)

    cov_reg = cov + np.eye(cov.shape[0]) * epsilon
    inv_cov = np.linalg.pinv(cov_reg)

    contrib = np.abs(z) * np.abs(inv_cov @ z)
    contrib = contrib / (np.sum(contrib) + epsilon)

    ranked = np.argsort(-contrib, kind="mergesort")
    top_idx = ranked[:top_n]

    top_signals = [
        {"signal": names[i], "contribution": float(contrib[i])}
        for i in top_idx
    ]

    if len(window) >= 2:
        current_cov = np.cov(window.T) if window.shape[0] > 1 else np.eye(n_signals)
        current_corr = _corrcoef_safe(window, n_signals)
        np.nan_to_num(current_corr, nan=0.0, copy=False)
    else:
        current_cov = np.zeros_like(cov)
        current_corr = np.eye(n_signals)

    abs_baseline_cov = np.abs(cov)
    baseline_scale = float(np.median(abs_baseline_cov))
    nonzero = abs_baseline_cov[abs_baseline_cov > 1e-8]
    if baseline_scale <= 1e-8 and len(nonzero):
        baseline_scale = float(np.median(nonzero))
    baseline_scale = max(baseline_scale, 1e-8)

    cov_shift_abs = np.abs(current_cov - cov)
    cov_shift_norm = cov_shift_abs / baseline_scale
    corr_shift = np.abs(current_corr - baseline_corr)

    relationships = []
    for li, left_idx in enumerate(top_idx):
        for right_idx in top_idx[li + 1:]:
            relationships.append(
                {
                    "pair": [names[left_idx], names[right_idx]],
                    "covariance_shift_abs": float(cov_shift_abs[left_idx, right_idx]),
                    "covariance_shift_norm": float(cov_shift_norm[left_idx, right_idx]),
                    "correlation_shift": float(corr_shift[left_idx, right_idx]),
                    "current_correlation": float(current_corr[left_idx, right_idx]),
                    "baseline_correlation": float(baseline_corr[left_idx, right_idx]),
                }
            )

    relationships.sort(key=lambda r: r["covariance_shift_norm"], reverse=True)

    return {
        "top_signals": top_signals,
        "top_relationships": relationships[:top_n_relationships],
    }
