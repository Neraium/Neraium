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


def format_output(cycle, output):
    status = output.get("status")
    pattern = output.get("what_is_happening", {}).get("pattern")
    direction = output.get("trajectory", {}).get("direction")
    drift = round(output.get("drift_score", 0), 2)

    if status in ("CONFIRMED_CHANGE", "CONFIRMED_CHANGE_HELD"):
        held = output.get("held")
        hold_remaining = output.get("hold_cycles_remaining")
        hold_text = (
            f" | held={held} | hold_remaining={hold_remaining}"
            if status == "CONFIRMED_CHANGE_HELD"
            else ""
        )
        return (
            f"cycle {cycle}: {status} | pattern={pattern} "
            f"| direction={direction} | drift={drift}{hold_text}"
        )

    return f"cycle {cycle}: {status} | drift={drift}"


def run_scenario(name, packet_generator, seed):
    print(f"Scenario: {name}")
    config = NeraiumConfig()
    engine = NeraiumEngine(config)
    rng = np.random.default_rng(seed)

    for cycle in range(TOTAL_CYCLES):
        packet = packet_generator(cycle, rng)
        output = engine.update(packet)
        print(format_output(cycle, output))


def main():
    run_scenario("relationship_shift", relationship_shift_packet, seed=367)
    print()
    run_scenario("persistent_multi_family", persistent_multi_family_packet, seed=367)


if __name__ == "__main__":
    main()
