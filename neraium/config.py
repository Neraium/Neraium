from dataclasses import dataclass


@dataclass
class NeraiumConfig:
    # ── Baseline collection ───────────────────────────────────────────────────
    baseline_window: int = 50       # observations collected before engine activates
    mad_scale: float = 1.4826       # MAD → sigma equivalence (consistency constant)

    # ── Adaptive threshold multipliers ────────────────────────────────────────
    # Thresholds are derived from the baseline drift distribution:
    #   threshold = baseline_drift_median + multiplier × baseline_drift_MAD × mad_scale
    watch_mad_multiplier: float = 3.0    # WATCH  = median + 3 × MAD_scaled
    alert_mad_multiplier: float = 5.0    # ALERT  = median + 5 × MAD_scaled

    # ── Persistence gate (K-of-W rolling window) ──────────────────────────────
    persistence_window: int = 5          # W: rolling window of recent cycles
    persistence_min_hits: int = 3        # K: minimum cycles above alert threshold

    # ── Alert hold (prevent thrashing on brief evidence recovery) ─────────────
    alert_hold_cycles: int = 5

    # ── Numerical stability ───────────────────────────────────────────────────
    cov_epsilon: float = 1e-6

    # ── Contributors ─────────────────────────────────────────────────────────
    top_n: int = 3
    top_n_relationships: int = 5

    # ── DMD spectral window (placeholder, not yet active) ────────────────────
    dmd_min_window: int = 20
