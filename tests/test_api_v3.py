import pytest
from fastapi.testclient import TestClient

from api.main import MACHINES, _engines, _events, _machine_status, app

client = TestClient(app)

SIGNALS_NORMAL = {
    "spindle_vibration": 0.18,
    "spindle_motor_current": 4.7,
    "coolant_flow_rate": 12.1,
    "axis_servo_load": 0.44,
    "cutting_zone_temperature": 71.2,
}

OPEN_EVENT_FIXTURE = {
    "event_id": "CNC-TEST-1",
    "machine_id": "CNC-01",
    "machine_type": "5-axis mill",
    "timestamp": "2026-01-01T00:00:00+00:00",
    "status": "open",
    "summary": "Spindle vibration and motor current are moving together.",
    "urgency": "medium",
    "direction": "diverging",
    "top_signals": ["Spindle Vibration", "Spindle Motor Current"],
    "where_to_look": ["Spindle assembly", "Spindle drive"],
    "recommended_action": "INSPECT",
    "engineer_snapshot": {
        "structural_metrics": {
            "drift_score": 7.2,
            "relational_stability": 0.6,
            "covariance_shift": 0.28,
        },
        "pattern": {"type": "RELATIONSHIP_FORMATION"},
    },
    "acknowledged": False,
    "acknowledged_at": None,
    "notes": [],
    "closed_at": None,
}


@pytest.fixture(autouse=True)
def clear_state():
    _events.clear()
    _engines.clear()
    _machine_status.clear()
    yield
    _events.clear()
    _engines.clear()
    _machine_status.clear()


# ── /machines ────────────────────────────────────────────────────────────────


def test_machines_returns_all_four():
    response = client.get("/machines")
    assert response.status_code == 200
    data = response.json()
    ids = {m["machine_id"] for m in data}
    assert ids == {"CNC-01", "CNC-02", "CNC-03", "CNC-04"}


def test_machines_includes_correct_types():
    response = client.get("/machines")
    data = {m["machine_id"]: m for m in response.json()}
    assert data["CNC-01"]["machine_type"] == "5-axis mill"
    assert data["CNC-02"]["machine_type"] == "horizontal mill"
    assert data["CNC-03"]["machine_type"] == "lathe cell"
    assert data["CNC-04"]["machine_type"] == "grinding cell"


def test_machines_includes_status_fields():
    response = client.get("/machines")
    for machine in response.json():
        assert "status" in machine
        assert "urgency" in machine
        assert "direction" in machine


# ── per-machine engine isolation ─────────────────────────────────────────────


def test_engines_do_not_leak_between_machines():
    """Advancing CNC-01 past init should not affect CNC-02."""
    for _ in range(35):
        client.post("/update", json={"asset_id": "CNC-01", "signals": SIGNALS_NORMAL})

    response = client.post("/update", json={"asset_id": "CNC-02", "signals": SIGNALS_NORMAL})
    assert response.json()["raw_engine"]["status"] == "INITIALIZING"


def test_reset_one_machine_does_not_reset_other():
    """Resetting CNC-01 must not touch CNC-02's engine."""
    for _ in range(35):
        client.post("/update", json={"asset_id": "CNC-01", "signals": SIGNALS_NORMAL})
        client.post("/update", json={"asset_id": "CNC-02", "signals": SIGNALS_NORMAL})

    client.post("/reset?asset_id=CNC-01")

    r1 = client.post("/update", json={"asset_id": "CNC-01", "signals": SIGNALS_NORMAL})
    assert r1.json()["raw_engine"]["status"] == "INITIALIZING"

    r2 = client.post("/update", json={"asset_id": "CNC-02", "signals": SIGNALS_NORMAL})
    assert r2.json()["raw_engine"]["status"] != "INITIALIZING"


def test_reset_all_clears_every_engine():
    for _ in range(35):
        client.post("/update", json={"asset_id": "CNC-01", "signals": SIGNALS_NORMAL})
        client.post("/update", json={"asset_id": "CNC-02", "signals": SIGNALS_NORMAL})

    client.post("/reset")

    for mid in ("CNC-01", "CNC-02"):
        r = client.post("/update", json={"asset_id": mid, "signals": SIGNALS_NORMAL})
        assert r.json()["raw_engine"]["status"] == "INITIALIZING"


# ── /events ──────────────────────────────────────────────────────────────────


def test_events_list_returns_200():
    response = client.get("/events")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_events_per_machine_returns_200():
    response = client.get("/events/CNC-01")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_events_per_machine_filters_by_machine():
    _events.append({**OPEN_EVENT_FIXTURE, "machine_id": "CNC-01", "event_id": "A"})
    _events.append(
        {
            **OPEN_EVENT_FIXTURE,
            "machine_id": "CNC-02",
            "event_id": "B",
            "machine_type": "horizontal mill",
        }
    )

    r1 = client.get("/events/CNC-01")
    assert all(e["machine_id"] == "CNC-01" for e in r1.json())

    r2 = client.get("/events/CNC-02")
    assert all(e["machine_id"] == "CNC-02" for e in r2.json())


# ── acknowledge ──────────────────────────────────────────────────────────────


def test_acknowledge_no_event_returns_404():
    response = client.post("/events/CNC-01/acknowledge")
    assert response.status_code == 404


def test_acknowledge_sets_acknowledged_flag():
    _events.append({**OPEN_EVENT_FIXTURE, "notes": []})
    response = client.post("/events/CNC-01/acknowledge")
    assert response.status_code == 200
    assert response.json()["status"] == "acknowledged"
    assert _events[0]["acknowledged"] is True
    assert _events[0]["acknowledged_at"] is not None


# ── note ─────────────────────────────────────────────────────────────────────


def test_note_no_event_returns_404():
    response = client.post("/events/CNC-01/note", json={"note": "test"})
    assert response.status_code == 404


def test_note_appends_to_event():
    _events.append({**OPEN_EVENT_FIXTURE, "notes": []})
    response = client.post("/events/CNC-01/note", json={"note": "Spindle bearing checked"})
    assert response.status_code == 200
    assert response.json()["status"] == "note_added"
    assert len(_events[0]["notes"]) == 1
    assert _events[0]["notes"][0]["text"] == "Spindle bearing checked"


def test_multiple_notes_accumulate():
    _events.append({**OPEN_EVENT_FIXTURE, "notes": []})
    client.post("/events/CNC-01/note", json={"note": "First note"})
    client.post("/events/CNC-01/note", json={"note": "Second note"})
    assert len(_events[0]["notes"]) == 2


# ── close ────────────────────────────────────────────────────────────────────


def test_close_no_event_returns_404():
    response = client.post("/events/CNC-01/close")
    assert response.status_code == 404


def test_close_sets_status_to_closed():
    _events.append({**OPEN_EVENT_FIXTURE, "notes": []})
    response = client.post("/events/CNC-01/close")
    assert response.status_code == 200
    assert response.json()["status"] == "closed"
    assert _events[0]["status"] == "closed"
    assert _events[0]["closed_at"] is not None


def test_close_prevents_second_acknowledge():
    _events.append({**OPEN_EVENT_FIXTURE, "notes": []})
    client.post("/events/CNC-01/close")
    response = client.post("/events/CNC-01/acknowledge")
    assert response.status_code == 404


# ── brief ────────────────────────────────────────────────────────────────────


def test_brief_unknown_machine_returns_404():
    response = client.get("/events/UNKNOWN-99/brief")
    assert response.status_code == 404


def test_brief_no_event_returns_404():
    response = client.get("/events/CNC-01/brief")
    assert response.status_code == 404


def test_brief_returns_bounded_claims():
    _events.append({**OPEN_EVENT_FIXTURE, "notes": []})
    response = client.get("/events/CNC-01/brief")
    assert response.status_code == 200
    brief = response.json()
    assert "not_claiming" in brief
    text = brief["not_claiming"].lower()
    assert "exact" in text or "failure time" in text


def test_brief_has_required_fields():
    _events.append({**OPEN_EVENT_FIXTURE, "notes": []})
    brief = client.get("/events/CNC-01/brief").json()
    for field in (
        "machine_id",
        "machine_type",
        "what_changed",
        "when_detected",
        "current_status",
        "primary_signals",
        "where_to_inspect",
        "recommended_action",
        "engineer_evidence_summary",
        "notes",
        "not_claiming",
    ):
        assert field in brief, f"Missing field: {field}"


def test_brief_machine_id_and_type_match():
    _events.append({**OPEN_EVENT_FIXTURE, "notes": []})
    brief = client.get("/events/CNC-01/brief").json()
    assert brief["machine_id"] == "CNC-01"
    assert brief["machine_type"] == "5-axis mill"
