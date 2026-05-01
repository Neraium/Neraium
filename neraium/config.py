from dataclasses import dataclass

@dataclass
class NeraiumConfig:
    mad_scale: float = 1.4826
    drift_threshold: float = 5.0
    persistence_cycles: int = 5

    sensor_threshold: float = 2.0
    cov_shift_threshold: float = 0.15
    rel_stability_threshold: float = 0.75

    dmd_min_window: int = 20
    trajectory_threshold: float = 0.3

    cov_epsilon: float = 1e-6

    top_n: int = 3
    top_n_relationships: int = 5

    confirmed_hold_cycles: int = 5
