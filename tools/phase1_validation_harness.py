"""Phase 1 validation harness for structural evidence.

Run with:
    python tools/phase1_validation_harness.py
"""

from itertools import product

import numpy as np

from neraium.config import NeraiumConfig
from neraium.evidence import compute_structural_evidence


N_SENSORS = 5
BASELINE_SAMPLES = 500
TOTAL_CYCLES = 200
WINDOW_SIZE = 30
STRUCTURAL_START = 80


def make_baseline(seed):
    rng = np.random.default_rng(seed)
    data = rng.normal(0.0, 1.0, size=(BASELINE_SAMPLES, N_SENSORS))

    return {
        "mean": np.mean(data, axis=0),
        "mad": np.median(np.abs(data - np.median(data, axis=0)), axis=0) + 1e-6,
        "cov": np.cov(data.T),
        "correlation": np.corrcoef(data.T),
    }


def healthy_packet(rng):
    return rng.normal(0.0, 1.0, size=N_SENSORS)


def healthy_noise_packet(cycle, rng, state):
    return healthy_packet(rng)


def single_sensor_spike_packet(cycle, rng, state):
    packet = healthy_packet(rng)
    if cycle in (45, 110, 165):
        packet[0] += 7.0
    return packet


def two_sensor_spike_no_structure_packet(cycle, rng, state):
    packet = healthy_packet(rng)
    if cycle in (55, 125, 175):
        packet[0] += 6.0
        packet[1] += 6.0
    return packet


def relationship_shift_packet(cycle, rng, state):
    if cycle < STRUCTURAL_START:
        return healthy_packet(rng)

    packet = healthy_packet(rng)
    shared = rng.normal(0.0, 1.0)
    packet[0] = shared + 0.15 * rng.normal()
    packet[1] = shared + 0.15 * rng.normal()
    return packet


def persistent_multi_family_packet(cycle, rng, state):
    if cycle < STRUCTURAL_START:
        packet = healthy_packet(rng)
        state["previous_sensor_2"] = packet[2]
        return packet

    packet = healthy_packet(rng)
    shared = rng.normal(0.0, 1.0)
    previous_sensor_2 = state.get("previous_sensor_2", 0.0)

    packet[0] = shared + 3.5 + 0.10 * rng.normal()
    packet[1] = shared + 3.5 + 0.10 * rng.normal()
    packet[2] = 0.35 * previous_sensor_2 + 1.25 + 0.45 * rng.normal()

    state["previous_sensor_2"] = packet[2]
    return packet


SCENARIOS = [
    {
        "name": "healthy_noise",
        "expected": "TRANSIENT",
        "kind": "noise",
        "packet_generator": healthy_noise_packet,
        "seed": 101,
    },
    {
        "name": "single_sensor_spike",
        "expected": "TRANSIENT",
        "kind": "noise",
        "packet_generator": single_sensor_spike_packet,
        "seed": 102,
    },
    {
        "name": "two_sensor_spike_no_structure",
        "expected": "TRANSIENT",
        "kind": "noise",
        "packet_generator": two_sensor_spike_no_structure_packet,
        "seed": 103,
    },
    {
        "name": "relationship_shift",
        "expected": "CONFIRMED_CHANGE",
        "kind": "structural",
        "packet_generator": relationship_shift_packet,
        "seed": 367,
        "change_start_cycle": STRUCTURAL_START,
    },
    {
        "name": "persistent_multi_family",
        "expected": "CONFIRMED_CHANGE",
        "kind": "structural",
        "packet_generator": persistent_multi_family_packet,
        "seed": 367,
        "change_start_cycle": STRUCTURAL_START,
    },
]


def run_scenario(scenario, config):
    baseline = make_baseline(seed=scenario["seed"] + 10_000)
    rng = np.random.default_rng(scenario["seed"])
    generator_state = {}
    history = []
    rolling_packets = []
    statuses = []
    active_families = []

    first_confirmed_cycle = None
    confirmed_cycles = []

    for cycle in range(TOTAL_CYCLES):
        packet = scenario["packet_generator"](cycle, rng, generator_state)
        rolling_packets.append(packet)
        window = np.asarray(rolling_packets[-WINDOW_SIZE:], dtype=float)

        result = compute_structural_evidence(
            packet=packet,
            window=window,
            baseline=baseline,
            history=history,
            config=config,
        )

        statuses.append(result["status"])
        active_families.append(result["active_families"])

        if result["status"] == "CONFIRMED_CHANGE" and first_confirmed_cycle is None:
            first_confirmed_cycle = cycle
        if result["status"] == "CONFIRMED_CHANGE":
            confirmed_cycles.append(cycle)

        history.append(result["drift_score"])

    confirmed_count = sum(status == "CONFIRMED_CHANGE" for status in statuses)

    if scenario["kind"] == "noise":
        change_start_cycle = None
        early_false_confirmations = 0
        false_positive_rate = confirmed_count / TOTAL_CYCLES
        detection_delay = None
        passed = confirmed_count == 0
    else:
        change_start_cycle = scenario["change_start_cycle"]
        early_false_confirmations = sum(
            cycle < change_start_cycle for cycle in confirmed_cycles
        )
        false_positive_rate = 0.0
        detection_delay = (
            first_confirmed_cycle - change_start_cycle
            if first_confirmed_cycle is not None
            else None
        )
        post_change_confirmations = sum(
            cycle >= change_start_cycle for cycle in confirmed_cycles
        )
        passed = (
            early_false_confirmations == 0
            and post_change_confirmations > 0
            and detection_delay is not None
            and detection_delay >= config.persistence_cycles - 1
        )

    return {
        "total_cycles": TOTAL_CYCLES,
        "confirmed_count": confirmed_count,
        "early_false_confirmations": early_false_confirmations,
        "first_confirmed_cycle": first_confirmed_cycle,
        "change_start_cycle": change_start_cycle,
        "false_positive_rate": false_positive_rate,
        "detection_delay": detection_delay,
        "statuses": statuses,
        "active_families": active_families,
        "passed": passed,
    }


def print_scenario_result(scenario, result):
    first_detection = (
        result["first_confirmed_cycle"]
        if result["first_confirmed_cycle"] is not None
        else "None"
    )
    detection_delay = (
        result["detection_delay"] if result["detection_delay"] is not None else "None"
    )

    print(f"Scenario: {scenario['name']}")
    print(f"Expected: {scenario['expected']}")
    print(f"Total cycles: {result['total_cycles']}")
    print(f"Confirmed count: {result['confirmed_count']}")
    print(f"early_false_confirmations: {result['early_false_confirmations']}")
    print(f"first_confirmed_cycle: {first_detection}")
    print(f"change_start_cycle: {result['change_start_cycle']}")
    print(f"False positive rate: {result['false_positive_rate']:.3f}")
    print(f"detection_delay: {detection_delay}")
    print(f"{'PASS' if result['passed'] else 'FAIL'}")
    print()


def score_config(config):
    true_detections = 0
    false_positives = 0
    early_detections = 0
    scenario_results = {}

    for scenario in SCENARIOS:
        result = run_scenario(scenario, config)
        scenario_results[scenario["name"]] = result

        if scenario["kind"] == "structural":
            if result["passed"]:
                true_detections += 1
            early_detections += result["early_false_confirmations"]
        else:
            false_positives += result["confirmed_count"]

    score = true_detections - (false_positives * 3) - early_detections

    return {
        "score": score,
        "true_detections": true_detections,
        "false_positives": false_positives,
        "early_detections": early_detections,
        "config": config,
        "scenario_results": scenario_results,
    }


def format_config_score(item):
    config = item["config"]
    return (
        f"score={item['score']} "
        f"true_detections={item['true_detections']} "
        f"false_positives={item['false_positives']} "
        f"early_detections={item['early_detections']} "
        f"drift_threshold={config.drift_threshold} "
        f"cov_shift_threshold={config.cov_shift_threshold} "
        f"rel_stability_threshold={config.rel_stability_threshold} "
        f"persistence_cycles={config.persistence_cycles}"
    )


def print_config_sweep():
    drift_thresholds = [2.0, 3.0, 5.0]
    cov_shift_thresholds = [0.15, 0.25, 0.4]
    rel_stability_thresholds = [0.75, 0.85, 0.95]
    persistence_cycles_values = [2, 3, 5]

    scored = []

    for drift, cov_shift, rel_stability, persistence in product(
        drift_thresholds,
        cov_shift_thresholds,
        rel_stability_thresholds,
        persistence_cycles_values,
    ):
        config = NeraiumConfig(
            drift_threshold=drift,
            cov_shift_threshold=cov_shift,
            rel_stability_threshold=rel_stability,
            persistence_cycles=persistence,
        )
        scored.append(score_config(config))

    scored.sort(
        key=lambda item: (
            item["score"],
            item["true_detections"],
            -item["false_positives"],
            -item["early_detections"],
        ),
        reverse=True,
    )

    print("Score per config:")
    for item in scored:
        print(format_config_score(item))
    print()

    print("Top 5 configs:")
    for rank, item in enumerate(scored[:5], start=1):
        print(f"{rank}. {format_config_score(item)}")
    print()

    print("Recommended config:")
    print(format_config_score(scored[0]))


def main():
    config = NeraiumConfig()

    print("Phase 1 validation harness")
    print("==========================")
    print()

    for scenario in SCENARIOS:
        result = run_scenario(scenario, config)
        print_scenario_result(scenario, result)

    print_config_sweep()


if __name__ == "__main__":
    main()
