"""
Dataset-agnostic structural change detection engine.

Self-calibrates from the first `baseline_window` observations using
median + MAD normalization and derives adaptive thresholds from the
baseline drift distribution. No dataset-specific parameters.

State machine: INITIALIZING → STABLE / WATCH / ALERT / ALERT_HELD
"""

from collections import deque

import numpy as np

from neraium.config import NeraiumConfig
from neraium.contributors import decompose_contributors
from neraium.evidence import compute_evidence_families
from neraium.patterns import classify_pattern
from neraium.trajectory import compute_trajectory_direction


class NeraiumEngine:
    def __init__(self, config: NeraiumConfig | None = None, signal_names: list[str] | None = None):
        self._config = config or NeraiumConfig()
        self._signal_names: list[str] | None = signal_names
        self._cycle: int = 0

        # ── Baseline collection ───────────────────────────────────────────────
        self._baseline_buffer: list[np.ndarray] = []
        self._baseline_formed: bool = False

        # ── Baseline statistics (populated after baseline_window samples) ─────
        self._baseline_median: np.ndarray | None = None
        self._baseline_mad: np.ndarray | None = None      # scaled MAD (σ-equiv)
        self._baseline_inv_cov: np.ndarray | None = None
        self._baseline_corr: np.ndarray | None = None
        self._watch_threshold: float = 0.0
        self._alert_threshold: float = 0.0

        # ── State machine ─────────────────────────────────────────────────────
        self._state: str = "INITIALIZING"
        self._time_in_state: int = 0
        self._alert_hold_remaining: int = 0

        # ── Persistence gate: K-of-W rolling window ───────────────────────────
        self._alert_hits: deque[bool] = deque(
            maxlen=self._config.persistence_window
        )

        # ── History ───────────────────────────────────────────────────────────
        self._drift_history: deque[float] = deque(maxlen=100)
        self._stability_history: deque[float] = deque(maxlen=100)
        self._raw_window: deque[np.ndarray] = deque(maxlen=100)

        # For trajectory computation across timesteps
        self._score_history: list[dict] = []
        self._previous_scores: dict | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def update(self, packet) -> dict:
        """
        Process one observation. Returns a per-timestep output dict with:
            state, structural_drift_score, relational_stability_score,
            evidence_count, time_in_state, confidence_score, drift_velocity,
            watch_threshold, alert_threshold, active_families, …
        """
        self._cycle += 1
        packet = self._as_array(packet)

        # ── Phase 1: Baseline collection ──────────────────────────────────────
        if not self._baseline_formed:
            self._baseline_buffer.append(packet.copy())
            if len(self._baseline_buffer) >= self._config.baseline_window:
                self._make_baseline()
                self._baseline_formed = True
            n = len(packet)
            return {
                "status": "INITIALIZING",
                "state": "INITIALIZING",
                "cycle": self._cycle,
                "structural_drift_score": 0.0,
                "drift_score": 0.0,
                "relational_stability_score": 1.0,
                "relational_stability": 1.0,
                "covariance_shift": 0.0,
                "evidence_count": 0,
                "time_in_state": self._time_in_state,
                "confidence_score": 0.0,
                "drift_velocity": 0.0,
                "watch_threshold": 0.0,
                "alert_threshold": 0.0,
                "persistence_satisfied": False,
                "active_families": [],
                "supporting_families": {},
                "top_signals": [],
                "relationships": [],
                "pattern": {"type": "NONE", "pattern": "NONE", "confidence_score": 0.0, "rule_triggered": ""},
                "trajectory": {
                    "direction": "ambiguous",
                    "drift_velocity": 0.0,
                    "drift_acceleration": 0.0,
                    "relational_recovery": 0.0,
                    "cycles_of_evidence": 0,
                },
                "trajectory_pressure": 0.0,
                "signal_names": self._signal_names or [f"sensor_{i}" for i in range(n)],
            }

        # ── Phase 2: Active monitoring ─────────────────────────────────────────
        self._raw_window.append(packet.copy())

        drift_score = self._compute_drift(packet)
        self._drift_history.append(drift_score)

        rel_stability = self._compute_relational_stability()
        self._stability_history.append(rel_stability)

        cov_shift = self._compute_cov_shift()

        evidence_count = self._update_state(drift_score)
        drift_velocity = self._compute_drift_velocity()
        confidence_score = min(
            evidence_count / max(self._config.persistence_min_hits, 1), 1.0
        )

        n_sensors = len(packet)
        sigma_equiv = self._baseline_mad * self._config.mad_scale
        z_scores = (packet - self._baseline_median) / sigma_equiv

        evidence = compute_evidence_families(
            z_scores=z_scores,
            window=list(self._raw_window),
            baseline_median=self._baseline_median,
            baseline_mad=self._baseline_mad,
            baseline_corr=self._baseline_corr,
            drift_score=drift_score,
            watch_threshold=self._watch_threshold,
            alert_threshold=self._alert_threshold,
            config=self._config,
        )

        signal_names = self._signal_names or [f"sensor_{i}" for i in range(n_sensors)]
        baseline_for_contrib = {
            "median": self._baseline_median,
            "mad": self._baseline_mad * self._config.mad_scale,
            "cov": np.linalg.inv(self._baseline_inv_cov + self._config.cov_epsilon * np.eye(n_sensors)),
            "correlation": self._baseline_corr,
            "signal_names": signal_names,
        }
        contrib = decompose_contributors(
            packet=packet,
            window=np.array(list(self._raw_window)),
            baseline=baseline_for_contrib,
            config=self._config,
        )

        current_scores = {
            "drift_score": drift_score,
            "relational_stability": rel_stability,
            "covariance_shift": cov_shift,
            "trajectory_pressure": evidence.get("trajectory_pressure", 0.0),
        }
        pattern = classify_pattern(
            scores=current_scores,
            previous_scores=(
                {**self._previous_scores, "recent_history": self._score_history[-5:]}
                if self._previous_scores else None
            ),
            alert_threshold=self._alert_threshold,
        )
        self._score_history.append(current_scores)
        self._score_history = self._score_history[-100:]
        self._previous_scores = current_scores

        trajectory = compute_trajectory_direction(
            history=self._score_history[:-1],
            current=current_scores,
        )

        # ── Assemble output ────────────────────────────────────────────────────
        top_signals = contrib.get("top_signals", [])
        relationships = contrib.get("top_relationships", [])

        return {
            # Primary fields (per spec)
            "status": self._state,
            "state": self._state,
            "cycle": self._cycle,
            "structural_drift_score": drift_score,
            "relational_stability_score": float(np.clip(1.0 - abs(1.0 - rel_stability), 0.0, 1.0)),
            "evidence_count": evidence_count,
            "time_in_state": self._time_in_state,
            "confidence_score": confidence_score,
            "drift_velocity": drift_velocity,
            "watch_threshold": self._watch_threshold,
            "alert_threshold": self._alert_threshold,
            # Secondary fields (backward-compatible / output layer)
            "drift_score": drift_score,
            "relational_stability": rel_stability,
            "covariance_shift": cov_shift,
            "covariance_drift": cov_shift,
            "persistence_satisfied": evidence_count >= self._config.persistence_min_hits,
            "active_families": evidence.get("active_families", []),
            "supporting_families": evidence.get("families", {}),
            "top_signals": top_signals,
            "relationships": relationships,
            "where": {"top_signals": top_signals, "top_relationships": relationships},
            "what_is_happening": {
                "pattern": pattern.get("pattern", "STRUCTURAL_CHANGE_UNCERTAIN"),
                "summary": pattern.get("rule_triggered", ""),
            },
            "pattern": pattern,
            "rule_triggered": pattern.get("rule_triggered", ""),
            "trajectory": trajectory,
            "trajectory_pressure": evidence.get("trajectory_pressure", 0.0),
            "signal_names": signal_names,
            # Hold-state metadata
            "held": self._state == "ALERT_HELD",
            "hold_cycles_remaining": self._alert_hold_remaining,
        }

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _as_array(packet) -> np.ndarray:
        if isinstance(packet, dict):
            return np.array(list(packet.values()), dtype=float)
        return np.asarray(packet, dtype=float)

    def _make_baseline(self) -> None:
        """Compute robust statistics and derive adaptive thresholds from baseline."""
        window = np.array(self._baseline_buffer, dtype=float)  # (N, D)
        n_dim = window.shape[1]

        # Per-signal robust statistics
        self._baseline_median = np.median(window, axis=0)
        raw_mad = np.median(np.abs(window - self._baseline_median), axis=0)
        raw_mad = np.maximum(raw_mad, self._config.cov_epsilon)
        # Store unscaled MAD; multiply by mad_scale when computing sigma-equiv
        self._baseline_mad = raw_mad

        sigma_equiv = raw_mad * self._config.mad_scale

        # Baseline correlation (for relational stability)
        self._baseline_corr = np.corrcoef(window.T)
        np.nan_to_num(self._baseline_corr, nan=0.0, copy=False)
        np.fill_diagonal(self._baseline_corr, 1.0)

        # Covariance of z-scored signals → use as Mahalanobis metric
        normalized = (window - self._baseline_median) / sigma_equiv
        if window.shape[0] > 1:
            baseline_cov = np.cov(normalized.T)
            if n_dim == 1:
                baseline_cov = np.atleast_2d(baseline_cov)
        else:
            baseline_cov = np.eye(n_dim)

        reg_cov = baseline_cov + self._config.cov_epsilon * np.eye(n_dim)
        try:
            self._baseline_inv_cov = np.linalg.inv(reg_cov)
        except np.linalg.LinAlgError:
            self._baseline_inv_cov = np.eye(n_dim)

        # Compute drift for every baseline sample → derive adaptive thresholds
        drift_scores = np.array([self._compute_drift(s) for s in window])
        drift_median = float(np.median(drift_scores))
        drift_mad = float(np.median(np.abs(drift_scores - drift_median)))
        drift_mad = max(drift_mad, self._config.cov_epsilon)

        self._watch_threshold = drift_median + (
            self._config.watch_mad_multiplier * drift_mad * self._config.mad_scale
        )
        self._alert_threshold = drift_median + (
            self._config.alert_mad_multiplier * drift_mad * self._config.mad_scale
        )

        # Seed raw window with baseline so relational stability has data
        for s in window:
            self._raw_window.append(s)

        self._state = "STABLE"

    def _compute_drift(self, packet: np.ndarray) -> float:
        """Mahalanobis distance from baseline in normalized space."""
        if self._baseline_median is None:
            return 0.0
        sigma_equiv = self._baseline_mad * self._config.mad_scale
        z = (packet - self._baseline_median) / sigma_equiv
        mahal_sq = float(z @ self._baseline_inv_cov @ z)
        return float(np.sqrt(max(mahal_sq, 0.0)))

    def _compute_relational_stability(self) -> float:
        """
        Ratio of current mean |correlation| to baseline mean |correlation|.
        1.0 = same strength; <1.0 = weaker; >1.0 = stronger.
        """
        window = list(self._raw_window)
        if len(window) < 2:
            return 1.0
        arr = np.array(window[-20:])
        if arr.shape[0] < 2:
            return 1.0
        current_corr = np.corrcoef(arr.T)
        np.nan_to_num(current_corr, nan=0.0, copy=False)
        mask = ~np.eye(current_corr.shape[0], dtype=bool)
        baseline_mean = float(np.mean(np.abs(self._baseline_corr[mask])))
        current_mean = float(np.mean(np.abs(current_corr[mask])))
        return current_mean / (baseline_mean + self._config.cov_epsilon)

    def _compute_cov_shift(self) -> float:
        """Mean relative covariance shift vs baseline."""
        window = list(self._raw_window)
        if len(window) < 2:
            return 0.0
        arr = np.array(window[-20:])
        if arr.shape[0] < 2:
            return 0.0
        sigma_equiv = self._baseline_mad * self._config.mad_scale
        norm_arr = (arr - self._baseline_median) / sigma_equiv
        current_cov = np.cov(norm_arr.T) if norm_arr.shape[0] > 1 else np.eye(norm_arr.shape[1])
        baseline_cov = np.linalg.inv(self._baseline_inv_cov)
        shift = np.abs(current_cov - baseline_cov)
        denom = np.abs(baseline_cov) + self._config.cov_epsilon
        return float(np.mean(shift / denom))

    def _update_state(self, drift_score: float) -> int:
        """Update persistence gate and state machine. Returns evidence_count."""
        above_alert = drift_score >= self._alert_threshold
        self._alert_hits.append(above_alert)
        evidence_count = int(sum(self._alert_hits))

        old_state = self._state

        if self._state in ("ALERT", "ALERT_HELD"):
            if evidence_count >= self._config.persistence_min_hits:
                new_state = "ALERT"
                self._alert_hold_remaining = self._config.alert_hold_cycles
            elif self._alert_hold_remaining > 0:
                self._alert_hold_remaining -= 1
                new_state = "ALERT_HELD"
            else:
                new_state = "WATCH" if drift_score >= self._watch_threshold else "STABLE"
        elif self._state == "WATCH":
            if evidence_count >= self._config.persistence_min_hits:
                new_state = "ALERT"
                self._alert_hold_remaining = self._config.alert_hold_cycles
            elif drift_score >= self._watch_threshold:
                new_state = "WATCH"
            else:
                new_state = "STABLE"
        else:  # STABLE
            new_state = "WATCH" if drift_score >= self._watch_threshold else "STABLE"

        if new_state != old_state:
            self._time_in_state = 0
            self._state = new_state
        else:
            self._time_in_state += 1

        return evidence_count

    def _compute_drift_velocity(self) -> float:
        """Slope of drift score over the last 5 cycles (first derivative)."""
        history = list(self._drift_history)
        if len(history) < 5:
            return 0.0
        recent = history[-5:]
        x = np.arange(len(recent), dtype=float)
        return float(np.polyfit(x, recent, 1)[0])
