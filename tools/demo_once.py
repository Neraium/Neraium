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
        shared = rng.normal(0.0, 1.0)
        packet[0] = shared + 0.75 + 0.15 * rng.normal()
        packet[1] = shared + 0.15 * rng.normal()
    return packet


def main():
    rng = np.random.default_rng(367)
    engine = NeraiumEngine(NeraiumConfig())

    for cycle in range(TOTAL_CYCLES):
        engine_output = engine.update(packet_for_cycle(cycle, rng))
        if engine_output.get("status") in (
            "CONFIRMED_CHANGE",
            "CONFIRMED_CHANGE_HELD",
        ):
            system_output = build_system_output(engine_output)
            print(f"cycle: {cycle}")
            print("operator:")
            print(json.dumps(system_output["operator"], indent=2))
            print("engineer:")
            print(json.dumps(system_output["engineer"], indent=2))
            return


if __name__ == "__main__":
    main()
