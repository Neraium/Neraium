import json

import numpy as np

from neraium.config import NeraiumConfig
from neraium.engine import NeraiumEngine
from neraium.system_output import build_system_output

TOTAL_CYCLES = 200
CHANGE_START = 80
SEED = 42


def packet_for_cycle(cycle, rng):
    if cycle < CHANGE_START:
        return rng.normal(0.0, 1.0, size=5)

    progress = (cycle - CHANGE_START) / 120.0
    shared = rng.normal(0, 1)
    coupling = 0.3 + 1.2 * progress
    drift = 0.02 * (cycle - CHANGE_START)

    sensor_0 = coupling * shared + drift
    sensor_1 = coupling * shared + rng.normal(0, 0.05) + drift
    sensor_2 = rng.normal(0, 1)
    sensor_3 = rng.normal(0, 1)
    sensor_4 = rng.normal(0, 1)

    return np.array([sensor_0, sensor_1, sensor_2, sensor_3, sensor_4])


def _is_preferred(engine_output):
    pattern = engine_output.get("what_is_happening", {}).get("pattern")
    direction = engine_output.get("trajectory", {}).get("direction")
    relationships = engine_output.get("where", {}).get("top_relationships", [])
    if not relationships:
        return False
    top_pair = set(relationships[0].get("pair", []))
    return (
        pattern == "RELATIONSHIP_FORMATION"
        and direction == "diverging"
        and {"sensor_0", "sensor_1"}.issubset(top_pair)
    )


def main():
    rng = np.random.default_rng(SEED)
    engine = NeraiumEngine(NeraiumConfig())

    first_fallback = None
    preferred = None

    for cycle in range(TOTAL_CYCLES):
        engine_output = engine.update(packet_for_cycle(cycle, rng))
        status = engine_output.get("status")

        if status not in ("CONFIRMED_CHANGE", "CONFIRMED_CHANGE_HELD"):
            continue

        if first_fallback is None:
            first_fallback = (cycle, engine_output)

        if preferred is None and _is_preferred(engine_output):
            preferred = (cycle, engine_output)
            break

    result = preferred or first_fallback
    if result is None:
        print("No confirmed output detected in 200 cycles.")
        return

    cycle, engine_output = result
    system_output = build_system_output(engine_output)

    print(f"cycle: {cycle}")
    print("operator:")
    print(json.dumps(system_output["operator"], indent=2))
    print("engineer:")
    print(json.dumps(system_output["engineer"], indent=2))


if __name__ == "__main__":
    main()
