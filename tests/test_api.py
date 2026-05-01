import pytest
from fastapi.testclient import TestClient

from api.main import app, _config
from neraium.engine import NeraiumEngine

client = TestClient(app)

SIGNALS = {
    "spindle_vibration": 0.18,
    "spindle_motor_current": 4.7,
    "coolant_flow_rate": 12.1,
    "axis_servo_load": 0.44,
    "cutting_zone_temperature": 71.2,
}


def test_health_returns_200():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_update_with_valid_signals_returns_200():
    client.post("/reset")
    response = client.post(
        "/update",
        json={"asset_id": "cnc_01", "signals": SIGNALS},
    )
    assert response.status_code == 200


def test_update_response_contains_operator_and_engineer():
    client.post("/reset")
    response = client.post(
        "/update",
        json={"asset_id": "cnc_01", "signals": SIGNALS},
    )
    body = response.json()
    assert "operator" in body
    assert "engineer" in body


def test_update_empty_signals_returns_400():
    response = client.post(
        "/update",
        json={"asset_id": "cnc_01", "signals": {}},
    )
    assert response.status_code == 400


def test_reset_returns_reset_status():
    response = client.post("/reset")
    assert response.status_code == 200
    assert response.json() == {"status": "reset"}


def test_reset_clears_engine_state():
    for _ in range(35):
        client.post("/update", json={"asset_id": "cnc_01", "signals": SIGNALS})

    client.post("/reset")

    response = client.post(
        "/update",
        json={"asset_id": "cnc_01", "signals": SIGNALS},
    )
    body = response.json()
    assert body["raw_engine"]["status"] == "INITIALIZING"
