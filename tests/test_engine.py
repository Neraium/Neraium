import numpy as np

from neraium.config import NeraiumConfig
from neraium.engine import NeraiumEngine


def healthy_packet(rng):
    return rng.normal(0.0, 1.0, size=5)


def warm_engine(engine, rng):
    outputs = []
    for _ in range(30):
        outputs.append(engine.update(healthy_packet(rng)))
    return outputs


def test_initializing_returns_initializing():
    engine = NeraiumEngine(NeraiumConfig())

    result = engine.update(np.zeros(5))

    assert result == {"status": "INITIALIZING"}


def test_stable_stream_returns_transient_after_initialization():
    rng = np.random.default_rng(10)
    engine = NeraiumEngine(NeraiumConfig())
    warm_engine(engine, rng)

    results = [engine.update(healthy_packet(rng)) for _ in range(50)]

    assert all(result["status"] == "TRANSIENT" for result in results)


def test_structural_shift_eventually_confirms_change():
    rng = np.random.default_rng(367)
    engine = NeraiumEngine(NeraiumConfig())
    warm_engine(engine, rng)

    confirmed = None
    for _ in range(120):
        shared = rng.normal(0.0, 1.0)
        packet = healthy_packet(rng)
        packet[0] = shared + 3.5 + 0.10 * rng.normal()
        packet[1] = shared + 3.5 + 0.10 * rng.normal()
        packet[2] = 1.25 + 0.45 * rng.normal()

        result = engine.update(packet)
        if result["status"] == "CONFIRMED_CHANGE":
            confirmed = result
            break

    assert confirmed is not None
    assert confirmed["status"] == "CONFIRMED_CHANGE"


def test_confirmed_output_contains_pattern_contributors_and_trajectory():
    rng = np.random.default_rng(367)
    engine = NeraiumEngine(NeraiumConfig())
    warm_engine(engine, rng)

    confirmed = None
    for _ in range(120):
        shared = rng.normal(0.0, 1.0)
        packet = healthy_packet(rng)
        packet[0] = shared + 3.5 + 0.10 * rng.normal()
        packet[1] = shared + 3.5 + 0.10 * rng.normal()
        packet[2] = 1.25 + 0.45 * rng.normal()

        result = engine.update(packet)
        if result["status"] == "CONFIRMED_CHANGE":
            confirmed = result
            break

    assert confirmed is not None
    assert "pattern" in confirmed["what_is_happening"]
    assert "summary" in confirmed["what_is_happening"]
    assert "top_signals" in confirmed["where"]
    assert "top_relationships" in confirmed["where"]
    assert "direction" in confirmed["trajectory"]
