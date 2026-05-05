from __future__ import annotations

from collections import defaultdict, deque
from statistics import median
from typing import Any, Dict, List, Optional, Tuple
import math

from backend.services.sii_core.schema import (
    SIIPacket,
    SIIAudit,
    SIIDriver,
    SIIEvent,
    SIIResult,
)


class SIIEngine:
    """
    Canonical Neraium SII engine.

    Every dataset should be converted into SIIPacket objects and sent through:
        result = engine.update(packet)

    Runners/adapters should not create states, regimes, drift scores, or events.
    """

    def __init__(
        self,
        baseline_window: int = 30,
        min_baseline: int = 20,
        watch_threshold: float = 1.25,
        transition_threshold: float = 2.0,
        unstable_threshold: float = 3.0,
        lock_in_threshold: float = 4.0,
        escalation_velocity_threshold: float = 0.20,
        onset_persistence: int = 5,
        lock_in_persistence: int = 30,
    ):
        self.baseline_window = baseline_window
        self.min_baseline = min_baseline

        self.watch_threshold = watch_threshold
        self.transition_threshold = transition_threshold
        self.unstable_threshold = unstable_threshold
        self.lock_in_threshold = lock_in_threshold

        self.escalation_velocity_threshold = escalation_velocity_threshold
        self.onset_persistence = onset_persistence
        self.lock_in_persistence = lock_in_persistence

        self.asset_buffers: Dict[str, Dict[str, deque]] = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=self.baseline_window))
        )

        self.asset_sample_index: Dict[str, int] = defaultdict(int)
        self.asset_prev_drift: Dict[str, float] = defaultdict(float)
        self.asset_prev_state: Dict[str, str] = defaultdict(lambda: "STABLE")

        self.asset_unstable_streak: Dict[str, int] = defaultdict(int)
        self.asset_lock_streak: Dict[str, int] = defaultdict(int)

        self.asset_onset_emitted: Dict[str, bool] = defaultdict(bool)
        self.asset_escalation_emitted: Dict[str, bool] = defaultdict(bool)
        self.asset_lock_emitted: Dict[str, bool] = defaultdict(bool)

    def update(self, packet: SIIPacket | Dict[str, Any]) -> SIIResult:
        if isinstance(packet, dict):
            packet = SIIPacket(**packet)

        asset_id = packet.asset_id
        sample_index = self.asset_sample_index[asset_id]

        numeric_signals, missing_count = self._clean_signals(packet.signals)

        baseline_ready = self._baseline_ready(asset_id)

        if not baseline_ready:
            self._update_baseline(asset_id, numeric_signals)

            audit = self._audit(
                sample_index=sample_index,
                baseline_ready=False,
                baseline_samples=self._baseline_sample_count(asset_id),
                missing_count=missing_count,
                signal_count=len(packet.signals),
            )

            result = SIIResult(
                asset_id=asset_id,
                timestamp=packet.timestamp,
                sample_index=sample_index,
                state="STABLE",
                regime="BASELINE_FORMING",
                structural_drift_score=0.0,
                drift_velocity=0.0,
                trajectory_pressure=0.0,
                relational_stability_score=1.0,
                drivers=[],
                events=[],
                audit=audit,
                metadata=packet.metadata,
            )

            self.asset_sample_index[asset_id] += 1
            return result

        baseline_stats = self._baseline_stats(asset_id)
        drivers = self._drivers(numeric_signals, baseline_stats)

        drift_score = self._structural_drift_score(drivers)
        prev_drift = self.asset_prev_drift[asset_id]
        drift_velocity = drift_score - prev_drift

        trajectory_pressure = self._trajectory_pressure(
            drift_score=drift_score,
            drift_velocity=drift_velocity,
        )

        relational_stability_score = self._relational_stability_score(drivers)

        state, regime = self._classify_state_and_regime(
            drift_score=drift_score,
            drift_velocity=drift_velocity,
            trajectory_pressure=trajectory_pressure,
            relational_stability_score=relational_stability_score,
        )

        events = self._events(
            asset_id=asset_id,
            sample_index=sample_index,
            state=state,
            drift_score=drift_score,
            drift_velocity=drift_velocity,
            trajectory_pressure=trajectory_pressure,
        )

        audit = self._audit(
            sample_index=sample_index,
            baseline_ready=True,
            baseline_samples=self._baseline_sample_count(asset_id),
            missing_count=missing_count,
            signal_count=len(packet.signals),
        )

        result = SIIResult(
            asset_id=asset_id,
            timestamp=packet.timestamp,
            sample_index=sample_index,
            state=state,
            regime=regime,
            structural_drift_score=round(drift_score, 6),
            drift_velocity=round(drift_velocity, 6),
            trajectory_pressure=round(trajectory_pressure, 6),
            relational_stability_score=round(relational_stability_score, 6),
            drivers=drivers,
            events=events,
            audit=audit,
            metadata=packet.metadata,
        )

        self._update_baseline(asset_id, numeric_signals)

        self.asset_prev_drift[asset_id] = drift_score
        self.asset_prev_state[asset_id] = state
        self.asset_sample_index[asset_id] += 1

        return result

    def _clean_signals(self, signals: Dict[str, Any]) -> Tuple[Dict[str, float], int]:
        cleaned = {}
        missing = 0

        for key, value in signals.items():
            try:
                v = float(value)
                if math.isnan(v) or math.isinf(v):
                    missing += 1
                    continue
                cleaned[key] = v
            except Exception:
                missing += 1

        return cleaned, missing

    def _baseline_ready(self, asset_id: str) -> bool:
        return self._baseline_sample_count(asset_id) >= self.min_baseline

    def _baseline_sample_count(self, asset_id: str) -> int:
        buffers = self.asset_buffers[asset_id]

        if not buffers:
            return 0

        return min(len(values) for values in buffers.values())

    def _update_baseline(self, asset_id: str, signals: Dict[str, float]) -> None:
        for signal, value in signals.items():
            self.asset_buffers[asset_id][signal].append(value)

    def _baseline_stats(self, asset_id: str) -> Dict[str, Tuple[float, float]]:
        stats = {}

        for signal, values in self.asset_buffers[asset_id].items():
            arr = list(values)

            if not arr:
                stats[signal] = (0.0, 1.0)
                continue

            center = median(arr)
            deviations = [abs(x - center) for x in arr]
            mad = median(deviations) if deviations else 0.0

            if mad <= 1e-9:
                mean = sum(arr) / len(arr)
                variance = sum((x - mean) ** 2 for x in arr) / max(len(arr), 1)
                scale = math.sqrt(variance)
            else:
                scale = 1.4826 * mad

            if scale <= 1e-9:
                scale = 1.0

            stats[signal] = (center, scale)

        return stats

    def _drivers(
        self,
        signals: Dict[str, float],
        baseline_stats: Dict[str, Tuple[float, float]],
    ) -> List[SIIDriver]:
        drivers = []

        for signal, value in signals.items():
            if signal not in baseline_stats:
                continue

            center, scale = baseline_stats[signal]
            z = (value - center) / max(scale, 1e-9)

            drivers.append(
                SIIDriver(
                    signal=signal,
                    value=round(value, 6),
                    baseline_center=round(center, 6),
                    baseline_scale=round(scale, 6),
                    z_score=round(z, 6),
                )
            )

        drivers.sort(key=lambda d: abs(d.z_score), reverse=True)
        return drivers[:8]

    def _structural_drift_score(self, drivers: List[SIIDriver]) -> float:
        if not drivers:
            return 0.0

        z_values = [abs(d.z_score) for d in drivers]
        return sum(z_values) / len(z_values)

    def _trajectory_pressure(self, drift_score: float, drift_velocity: float) -> float:
        return (0.70 * drift_score) + (0.30 * max(0.0, drift_velocity))

    def _relational_stability_score(self, drivers: List[SIIDriver]) -> float:
        if not drivers:
            return 1.0

        high_driver_count = sum(1 for d in drivers if abs(d.z_score) >= 2.0)
        score = 1.0 - min(0.9, high_driver_count * 0.12)

        return max(0.0, score)

    def _classify_state_and_regime(
        self,
        drift_score: float,
        drift_velocity: float,
        trajectory_pressure: float,
        relational_stability_score: float,
    ) -> Tuple[str, str]:
        if trajectory_pressure >= self.lock_in_threshold and drift_velocity >= self.escalation_velocity_threshold:
            return "LOCK_IN", "LOCK_IN"

        if trajectory_pressure >= self.unstable_threshold:
            if relational_stability_score <= 0.55:
                return "UNSTABLE", "RELATIONAL_BREAKDOWN"
            return "UNSTABLE", "STRUCTURAL_INSTABILITY"

        if trajectory_pressure >= self.transition_threshold:
            if drift_velocity > 0:
                return "TRANSITION", "EARLY_STRUCTURAL_DRIFT"
            return "TRANSITION", "SUSTAINED_STRUCTURAL_DRIFT"

        if trajectory_pressure >= self.watch_threshold:
            return "WATCH", "WATCH_DRIFT"

        return "STABLE", "STABLE"

    def _events(
        self,
        asset_id: str,
        sample_index: int,
        state: str,
        drift_score: float,
        drift_velocity: float,
        trajectory_pressure: float,
    ) -> List[SIIEvent]:
        events = []

        unstableish = state in ["WATCH", "TRANSITION", "UNSTABLE", "LOCK_IN"]
        confirmed_unstable = state in ["UNSTABLE", "LOCK_IN"]

        if unstableish:
            self.asset_unstable_streak[asset_id] += 1
        else:
            self.asset_unstable_streak[asset_id] = 0
            self.asset_lock_streak[asset_id] = 0

        if confirmed_unstable:
            self.asset_lock_streak[asset_id] += 1
        else:
            self.asset_lock_streak[asset_id] = 0

        if (
            not self.asset_onset_emitted[asset_id]
            and self.asset_unstable_streak[asset_id] >= self.onset_persistence
        ):
            events.append(
                SIIEvent(
                    event_type="INITIAL_INSTABILITY",
                    sample_index=sample_index - self.onset_persistence + 1,
                    state=state,
                    severity="WATCH",
                    reason="First persistent departure from baseline.",
                )
            )
            self.asset_onset_emitted[asset_id] = True

        if (
            self.asset_onset_emitted[asset_id]
            and not self.asset_escalation_emitted[asset_id]
            and state in ["UNSTABLE", "LOCK_IN"]
            and drift_velocity >= self.escalation_velocity_threshold
        ):
            events.append(
                SIIEvent(
                    event_type="ESCALATION",
                    sample_index=sample_index,
                    state=state,
                    severity="ALERT",
                    reason="Drift velocity increased while system was in confirmed instability.",
                )
            )
            self.asset_escalation_emitted[asset_id] = True

        if (
            self.asset_onset_emitted[asset_id]
            and not self.asset_lock_emitted[asset_id]
            and self.asset_lock_streak[asset_id] >= self.lock_in_persistence
        ):
            events.append(
                SIIEvent(
                    event_type="LOCK_IN",
                    sample_index=sample_index - self.lock_in_persistence + 1,
                    state=state,
                    severity="ACTIONABLE",
                    reason="Confirmed instability persisted long enough to indicate lock-in behavior.",
                )
            )
            self.asset_lock_emitted[asset_id] = True

        return events

    def _audit(
        self,
        sample_index: int,
        baseline_ready: bool,
        baseline_samples: int,
        missing_count: int,
        signal_count: int,
    ) -> SIIAudit:
        missing_rate = missing_count / signal_count if signal_count else 0.0

        return SIIAudit(
            sample_index=sample_index,
            baseline_ready=baseline_ready,
            baseline_samples=baseline_samples,
            missing_signal_count=missing_count,
            missing_signal_rate=round(missing_rate, 6),
            signal_count=signal_count,
        )
