import numpy as np

from neraium.config import NeraiumConfig
from neraium.engine import NeraiumEngine


TOTAL_CYCLES = 200
CHANGE_START = 80


def relationship_shift_packet(cycle, rng):
    packet = rng.normal(0.0, 1.0, size=5)
    if cycle >= CHANGE_START:
        shared = rng.normal(0.0, 1.0)
        packet[0] = shared + 0.15 * rng.normal()
        packet[1] = shared + 0.15 * rng.normal()
    return packet


def persistent_multi_family_packet(cycle, rng):
    packet = rng.normal(0.0, 1.0, size=5)
    if cycle >= CHANGE_START:
        shared = rng.normal(0.0, 1.0)
        packet[0] = shared + 3.5 + 0.10 * rng.normal()
        packet[1] = shared + 3.5 + 0.10 * rng.normal()
    return packet


def top_signal_names(output):
    signals = output.get("where", {}).get("top_signals", [])
    return [signal["signal"] for signal in signals]


def top_relationship_pair(output):
    relationships = output.get("where", {}).get("top_relationships", [])
    if not relationships:
        return None
    return relationships[0]["pair"]


def evidence_diagnostics(engine):
    if engine.baseline is None or len(engine.window) < 3:
        return {
            "rel_stability": 0.0,
            "cov_shift": 0.0,
        }

    window = np.asarray(engine.window, dtype=float)
    baseline_cov = np.asarray(engine.baseline["cov"], dtype=float)
    baseline_corr = np.asarray(engine.baseline["correlation"], dtype=float)

    current_cov = np.cov(window.T)
    cov_shift = np.linalg.norm(current_cov - baseline_cov, ord="fro") / (
        np.linalg.norm(baseline_cov, ord="fro") + 1e-8
    )

    current_corr = np.corrcoef(window.T)
    current_corr = np.nan_to_num(current_corr, nan=0.0, posinf=0.0, neginf=0.0)
    mask = ~np.eye(current_corr.shape[0], dtype=bool)
    rel_stability = np.mean(np.abs(current_corr[mask])) / (
        np.mean(np.abs(baseline_corr[mask])) + 1e-8
    )

    return {
        "rel_stability": float(rel_stability),
        "cov_shift": float(cov_shift),
    }


def print_cycle(cycle, output, diagnostics):
    pattern_info = output.get("what_is_happening", {})
    trajectory = output.get("trajectory", {})

    print(
        {
            "cycle": cycle,
            "status": output.get("status"),
            "drift_score": round(output.get("drift_score", 0.0), 2),
            "pattern": pattern_info.get("pattern"),
            "rule_triggered": pattern_info.get("summary"),
            "rel_stability": round(diagnostics.get("rel_stability", 0.0), 3),
            "cov_shift": round(diagnostics.get("cov_shift", 0.0), 3),
            "trajectory_direction": trajectory.get("direction"),
            "top_signals": top_signal_names(output),
            "top_relationship_pair": top_relationship_pair(output),
        }
    )


def run_scenario(name, packet_generator, seed):
    print(f"Scenario: {name}")
    engine = NeraiumEngine(NeraiumConfig())
    rng = np.random.default_rng(seed)

    for cycle in range(TOTAL_CYCLES):
        output = engine.update(packet_generator(cycle, rng))
        if 80 <= cycle <= 120:
            print_cycle(cycle, output, evidence_diagnostics(engine))
    print()


def main():
    run_scenario("relationship_shift", relationship_shift_packet, seed=367)
    run_scenario("persistent_multi_family", persistent_multi_family_packet, seed=367)


if __name__ == "__main__":
    main()
