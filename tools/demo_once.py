import json

import numpy as np

from neraium.config import NeraiumConfig
from neraium.engine import NeraiumEngine
from neraium.system_output import build_system_output


TOTAL_CYCLES = 200
CHANGE_START = 80


def packet_for_cycle(cycle, rng):
    packet = rng.normal(0.0, 1.0, size=5)
    if cycle >= CHANGE_START:
        packet[2:] = rng.normal(0.0, 0.6, size=3)
        shared = 2.5 * rng.normal(0.0, 1.0)
        packet[0] = shared + 0.05
        packet[1] = shared + 0.001 * rng.normal() + 0.05
    return packet


def main():
    rng = np.random.default_rng(367)
    engine = NeraiumEngine(NeraiumConfig())
    first_confirmed = None

    for cycle in range(TOTAL_CYCLES):
        engine_output = engine.update(packet_for_cycle(cycle, rng))
        if engine_output.get("status") in (
            "CONFIRMED_CHANGE",
            "CONFIRMED_CHANGE_HELD",
        ):
            if first_confirmed is None:
                first_confirmed = (cycle, engine_output)

            if engine_output.get("trajectory", {}).get("direction") != "ambiguous":
                print_output(cycle, engine_output)
                return

    if first_confirmed is not None:
        cycle, engine_output = first_confirmed
        print_output(cycle, engine_output)


def print_output(cycle, engine_output):
    system_output = build_system_output(engine_output)
    print(f"cycle: {cycle}")
    print("operator:")
    print(json.dumps(system_output["operator"], indent=2))
    print("engineer:")
    print(json.dumps(system_output["engineer"], indent=2))


if __name__ == "__main__":
    main()
