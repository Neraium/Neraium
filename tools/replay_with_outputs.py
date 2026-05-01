import json

import numpy as np

from neraium.config import NeraiumConfig
from neraium.engine import NeraiumEngine
from neraium.engineer import build_engineer_output
from neraium.operator import build_operator_output


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


def run_scenario(name, packet_generator, seed):
    print(f"Scenario: {name}")
    engine = NeraiumEngine(NeraiumConfig())
    rng = np.random.default_rng(seed)

    for cycle in range(TOTAL_CYCLES):
        output = engine.update(packet_generator(cycle, rng))
        if (
            80 <= cycle <= 110
            and output.get("status") in ("CONFIRMED_CHANGE", "CONFIRMED_CHANGE_HELD")
        ):
            print(f"--- CYCLE {cycle} ---")
            print("OPERATOR OUTPUT:")
            print(json.dumps(build_operator_output(output), indent=2))
            print()
            print("ENGINEER OUTPUT:")
            print(json.dumps(build_engineer_output(output), indent=2))
            print()


def main():
    run_scenario("relationship_shift", relationship_shift_packet, seed=367)
    run_scenario("persistent_multi_family", persistent_multi_family_packet, seed=367)


if __name__ == "__main__":
    main()
