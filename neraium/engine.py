import numpy as np

from neraium.contributors import decompose_contributors
from neraium.evidence import compute_structural_evidence
from neraium.patterns import classify_pattern
from neraium.trajectory import compute_trajectory_direction


class NeraiumEngine:
    def __init__(self, config):
        self.config = config
        self.baseline = None
        self.window = []
        self.history = []
        self._drift_history = []
        self._max_window = 30
        self._max_history = 100
        self._confirmed_hold_remaining = 0
        self._slope_history = []

    def update(self, packet):
        x = self._as_array(packet)
        self.window.append(x)
        self.window = self.window[-self._max_window:]

        if self.baseline is None:
            if len(self.window) >= self._max_window:
                self.baseline = self._make_baseline(self.window)
            return {"status": "INITIALIZING"}

        window = np.asarray(self.window, dtype=float)
        evidence = compute_structural_evidence(
            packet=x,
            window=window,
            baseline=self.baseline,
            history=self._drift_history,
            config=self.config,
        )
        self._drift_history.append(evidence["drift_score"])
        self._drift_history = self._drift_history[-self._max_history:]

        if (
            evidence["status"] == "TRANSIENT"
            and self._confirmed_hold_remaining <= 0
        ):
            return {
                "status": "TRANSIENT",
                "drift_score": evidence["drift_score"],
            }

        contributors = decompose_contributors(
            packet=x,
            window=window,
            baseline=self.baseline,
            config=self.config,
        )

        scores = {
            "drift_score": evidence["drift_score"],
            "rel_stability": evidence["diagnostics"]["rel_stability"],
            "cov_shift": evidence["diagnostics"]["cov_shift"],
            "trajectory_pressure": 0.0,
        }
        previous_scores = (
            {
                **self.history[-1],
                "recent_history": self.history[-5:],
            }
            if self.history
            else None
        )
        pattern = classify_pattern(scores, previous_scores)
        trajectory = compute_trajectory_direction(self.history, scores)
        self._slope_history.append(trajectory["drift_velocity"])
        self._slope_history = self._slope_history[-50:]
        trajectory = {
            **trajectory,
            "recent_slopes": list(self._slope_history),
        }

        self.history.append(scores)
        self.history = self.history[-self._max_history:]

        if evidence["status"] == "CONFIRMED_CHANGE":
            self._confirmed_hold_remaining = int(
                getattr(self.config, "confirmed_hold_cycles", 5)
            )
            status = "CONFIRMED_CHANGE"
            held = False
            hold_cycles_remaining = self._confirmed_hold_remaining
        else:
            status = "CONFIRMED_CHANGE_HELD"
            held = True
            hold_cycles_remaining = self._confirmed_hold_remaining
            self._confirmed_hold_remaining = max(
                0,
                self._confirmed_hold_remaining - 1,
            )

        return {
            "status": status,
            "confidence_score": pattern["confidence_score"],
            "what_is_happening": {
                "pattern": pattern["pattern"],
                "summary": pattern["rule_triggered"],
            },
            "relational_stability": evidence["diagnostics"]["rel_stability"],
            "covariance_drift": evidence["diagnostics"]["cov_shift"],
            "persistence_satisfied": evidence["persistence_satisfied"],
            "supporting_families": evidence["supporting_families"],
            "active_families": evidence["active_families"],
            "rule_triggered": pattern["rule_triggered"],
            "where": contributors,
            "trajectory": trajectory,
            "drift_score": evidence["drift_score"],
            "held": held,
            "hold_cycles_remaining": hold_cycles_remaining,
        }

    @staticmethod
    def _as_array(packet):
        if isinstance(packet, dict):
            return np.array(list(packet.values()), dtype=float)
        return np.asarray(packet, dtype=float)

    @staticmethod
    def _make_baseline(window):
        data = np.asarray(window, dtype=float)
        median = np.median(data, axis=0)
        mad = np.median(np.abs(data - median), axis=0) + 1e-6
        cov = np.cov(data.T)
        correlation = np.corrcoef(data.T)
        correlation = np.nan_to_num(correlation, nan=0.0, posinf=0.0, neginf=0.0)
        np.fill_diagonal(correlation, 1.0)

        return {
            "mean": np.mean(data, axis=0),
            "mad": mad,
            "cov": cov,
            "correlation": correlation,
        }
