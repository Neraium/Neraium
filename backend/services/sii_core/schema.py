from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class SIIPacket:
    asset_id: str
    timestamp: str
    signals: Dict[str, float]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SIIDriver:
    signal: str
    value: float
    baseline_center: float
    baseline_scale: float
    z_score: float


@dataclass
class SIIEvent:
    event_type: str
    sample_index: int
    state: str
    severity: str
    reason: str


@dataclass
class SIIAudit:
    sample_index: int
    baseline_ready: bool
    baseline_samples: int
    missing_signal_count: int
    missing_signal_rate: float
    signal_count: int


@dataclass
class SIIResult:
    asset_id: str
    timestamp: str
    sample_index: int

    state: str
    regime: str

    structural_drift_score: float
    drift_velocity: float
    trajectory_pressure: float
    relational_stability_score: float

    drivers: List[SIIDriver]
    events: List[SIIEvent]
    audit: SIIAudit

    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
