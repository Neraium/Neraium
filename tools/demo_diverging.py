import json

import numpy as np

from neraium.config import NeraiumConfig
from neraium.engine import NeraiumEngine
from neraium.system_output import build_system_output


TOTAL_CYCLES = 200
CHANGE_START = 80
SPINDLE_PAIR = {"Spindle Vibration", "Spindle Motor Current"}


def packet_for_cycle(cycle, rng):
    packet = rng.normal(0.0, 1.0, size=5)
    if cycle >= CHANGE_START:
        progress = (cycle - CHANGE_START) / 120.0
        shared = rng.normal(0.0, 1.0)
        coupling = 0.3 + 1.2 * progress
        drift = 0.02 * (cycle - CHANGE_START)

        packet[0] = coupling * shared + drift
        packet[1] = coupling * shared + rng.normal(0.0, 0.05) + drift
        packet[2] = rng.normal(0.0, 1.0)
        packet[3] = rng.normal(0.0, 1.0)
        packet[4] = rng.normal(0.0, 1.0)
    return packet


def is_preferred(system_output):
    operator = system_output["operator"]
    engineer = system_output["engineer"]
    relationship_pair = set(operator["where"]["top_relationship_pair"] or [])
    return (
        engineer["pattern"]["type"] == "RELATIONSHIP_FORMATION"
        and operator["trajectory"]["direction"] == "diverging"
        and engineer["trajectory_metrics"]["drift_velocity"] > 0.0
        and relationship_pair == SPINDLE_PAIR
    )


def print_output(cycle, system_output):
    print(f"cycle: {cycle}")
    print("operator:")
    print(json.dumps(system_output["operator"], indent=2))
    print("engineer:")
    print(json.dumps(system_output["engineer"], indent=2))


def main():
    rng = np.random.default_rng(367)
    engine = NeraiumEngine(NeraiumConfig())
    fallback = None

    for cycle in range(TOTAL_CYCLES):
        engine_output = engine.update(packet_for_cycle(cycle, rng))
        if engine_output.get("status") in (
            "CONFIRMED_CHANGE",
            "CONFIRMED_CHANGE_HELD",
        ):
            system_output = build_system_output(engine_output)
            if fallback is None:
                fallback = (cycle, system_output)

            if is_preferred(system_output):
                print_output(cycle, system_output)
                return

    if fallback is not None:
        cycle, system_output = fallback
        print_output(cycle, system_output)


if __name__ == "__main__":
    main()
