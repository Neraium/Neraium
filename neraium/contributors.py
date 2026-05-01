import numpy as np


def _as_array(packet):
    if isinstance(packet, dict):
        return np.array(list(packet.values()), dtype=float)
    return np.asarray(packet, dtype=float)


def _get(baseline, key):
    if isinstance(baseline, dict):
        return baseline[key]
    return getattr(baseline, key)


def _signal_names(baseline, n_signals):
    for key in ("signal_names", "signals", "columns"):
        if isinstance(baseline, dict) and key in baseline:
            return [str(name) for name in baseline[key]]
        if not isinstance(baseline, dict) and hasattr(baseline, key):
            return [str(name) for name in getattr(baseline, key)]

    return [f"sensor_{idx}" for idx in range(n_signals)]


def _corrcoef(window, n_signals):
    std = np.std(window, axis=0)
    if np.any(std <= 1e-12):
        corr = np.zeros((n_signals, n_signals), dtype=float)
        variable = std > 1e-12
        if np.any(variable):
            variable_corr = np.corrcoef(window[:, variable].T)
            corr[np.ix_(variable, variable)] = variable_corr
        np.fill_diagonal(corr, 1.0)
        return corr

    return np.corrcoef(window.T)


def decompose_contributors(packet, window, baseline, config):
    x = _as_array(packet)
    window = np.asarray(window, dtype=float)

    mean = np.asarray(_get(baseline, "mean"), dtype=float)
    mad = np.asarray(_get(baseline, "mad"), dtype=float)
    cov = np.asarray(_get(baseline, "cov"), dtype=float)
    baseline_corr = np.asarray(_get(baseline, "correlation"), dtype=float)

    n_signals = x.shape[0]
    names = _signal_names(baseline, n_signals)
    top_n = min(int(getattr(config, "top_n", 3)), n_signals)
    top_n_relationships = int(getattr(config, "top_n_relationships", 5))

    z = (x - mean) / (mad * config.mad_scale + 1e-8)

    cov_reg = cov + np.eye(cov.shape[0]) * config.cov_epsilon
    inv_cov = np.linalg.pinv(cov_reg)

    contrib = np.abs(z) * np.abs(inv_cov @ z)
    contrib = contrib / (np.sum(contrib) + 1e-8)

    ranked_signal_indices = np.argsort(-contrib, kind="mergesort")
    top_signal_indices = ranked_signal_indices[:top_n]

    top_signals = [
        {
            "signal": names[idx],
            "contribution": float(contrib[idx]),
        }
        for idx in top_signal_indices
    ]

    if len(window) >= 2:
        current_cov = np.cov(window.T)
        current_corr = _corrcoef(window, n_signals)
        current_corr = np.nan_to_num(current_corr, nan=0.0, posinf=0.0, neginf=0.0)
    else:
        current_cov = np.zeros_like(cov)
        current_corr = np.eye(n_signals)

    abs_baseline_cov = np.abs(cov)
    baseline_cov_scale = float(np.median(abs_baseline_cov))
    if baseline_cov_scale <= 1e-8:
        nonzero_cov = abs_baseline_cov[abs_baseline_cov > 1e-8]
        baseline_cov_scale = float(np.median(nonzero_cov)) if len(nonzero_cov) else 1.0
    baseline_cov_scale += 1e-8
    cov_shift_abs = np.abs(current_cov - cov)
    cov_shift_norm = cov_shift_abs / baseline_cov_scale
    corr_shift = np.abs(current_corr - baseline_corr)

    relationships = []
    for left_pos, left_idx in enumerate(top_signal_indices):
        for right_idx in top_signal_indices[left_pos + 1:]:
            relationships.append(
                {
                    "pair": [names[left_idx], names[right_idx]],
                    "covariance_shift_abs": float(
                        cov_shift_abs[left_idx, right_idx]
                    ),
                    "covariance_shift_norm": float(
                        cov_shift_norm[left_idx, right_idx]
                    ),
                    "correlation_shift": float(corr_shift[left_idx, right_idx]),
                    "current_correlation": float(current_corr[left_idx, right_idx]),
                    "baseline_correlation": float(baseline_corr[left_idx, right_idx]),
                }
            )

    relationships.sort(key=lambda item: item["covariance_shift_norm"], reverse=True)

    return {
        "top_signals": top_signals,
        "top_relationships": relationships[:top_n_relationships],
    }
