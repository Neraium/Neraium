# Run with:
#   uvicorn api.main:app --reload --port 8000

from datetime import datetime, timezone

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from neraium.config import NeraiumConfig
from neraium.engine import NeraiumEngine
from neraium.system_output import build_system_output

app = FastAPI(title="Neraium API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_config = NeraiumConfig()

MACHINES = {
    "CNC-01": {"machine_id": "CNC-01", "machine_type": "5-axis mill"},
    "CNC-02": {"machine_id": "CNC-02", "machine_type": "horizontal mill"},
    "CNC-03": {"machine_id": "CNC-03", "machine_type": "lathe cell"},
    "CNC-04": {"machine_id": "CNC-04", "machine_type": "grinding cell"},
}

_engines: dict[str, NeraiumEngine] = {}
_machine_status: dict[str, dict] = {}
_events: list[dict] = []


def _get_engine(machine_id: str) -> NeraiumEngine:
    if machine_id not in _engines:
        _engines[machine_id] = NeraiumEngine(_config)
    return _engines[machine_id]


class UpdateRequest(BaseModel):
    asset_id: str
    timestamp: str | None = None
    signals: dict[str, float]


class NoteRequest(BaseModel):
    note: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/machines")
def list_machines():
    result = []
    for machine_id, info in MACHINES.items():
        status_data = _machine_status.get(machine_id, {})
        result.append(
            {
                "machine_id": machine_id,
                "machine_type": info["machine_type"],
                "status": status_data.get("status", "INITIALIZING"),
                "urgency": status_data.get("urgency", "low"),
                "direction": status_data.get("direction", "not established"),
                "last_update": status_data.get("last_update"),
                "summary": status_data.get("summary", "Baseline is being established."),
            }
        )
    return result


@app.post("/reset")
def reset(asset_id: str | None = None):
    if asset_id:
        _engines[asset_id] = NeraiumEngine(_config)
        _machine_status.pop(asset_id, None)
    else:
        _engines.clear()
        _machine_status.clear()
    return {"status": "reset"}


@app.post("/update")
def update(body: UpdateRequest):
    if not body.signals:
        raise HTTPException(status_code=400, detail="signals must be non-empty")

    non_numeric = [k for k, v in body.signals.items() if not isinstance(v, (int, float))]
    if non_numeric:
        raise HTTPException(
            status_code=400,
            detail=f"non-numeric values for signals: {non_numeric}",
        )

    machine_id = body.asset_id
    engine = _get_engine(machine_id)
    packet = np.array(list(body.signals.values()), dtype=float)
    engine_output = engine.update(packet)
    system = build_system_output(engine_output)

    operator = system.get("operator", {})
    engineer = system.get("engineer", {})
    status = operator.get("status", "INITIALIZING")
    now = datetime.now(timezone.utc).isoformat()

    _machine_status[machine_id] = {
        "status": status,
        "urgency": operator.get("trajectory", {}).get("urgency", "low"),
        "direction": operator.get("trajectory", {}).get("direction", "not established"),
        "last_update": now,
        "summary": operator.get("plain_english", {}).get(
            "what_this_means", "Baseline is being established."
        ),
    }

    if status in ("ALERT", "ALERT_HELD"):
        open_events = [
            e for e in _events if e["machine_id"] == machine_id and e["status"] == "open"
        ]
        if not open_events:
            top_signals = operator.get("where", {}).get("top_signals", [])
            where_to_look = operator.get("where_to_look", {}).get("subsystems", [])
            _events.append(
                {
                    "event_id": f"{machine_id}-{len(_events) + 1}",
                    "machine_id": machine_id,
                    "machine_type": MACHINES.get(machine_id, {}).get("machine_type", "unknown"),
                    "timestamp": now,
                    "status": "open",
                    "summary": _machine_status[machine_id]["summary"],
                    "urgency": _machine_status[machine_id]["urgency"],
                    "direction": _machine_status[machine_id]["direction"],
                    "top_signals": top_signals,
                    "where_to_look": where_to_look,
                    "recommended_action": operator.get(
                        "recommended_next_step", "CONTINUE_MONITORING"
                    ),
                    "engineer_snapshot": engineer,
                    "acknowledged": False,
                    "acknowledged_at": None,
                    "notes": [],
                    "closed_at": None,
                }
            )

    return system


@app.get("/events")
def get_events():
    return _events


@app.get("/events/{machine_id}")
def get_machine_events(machine_id: str):
    return [e for e in _events if e["machine_id"] == machine_id]


@app.post("/events/{machine_id}/acknowledge")
def acknowledge_event(machine_id: str):
    open_events = [e for e in _events if e["machine_id"] == machine_id and e["status"] == "open"]
    if not open_events:
        raise HTTPException(status_code=404, detail="No open event found for this machine")
    event = open_events[-1]
    event["acknowledged"] = True
    event["acknowledged_at"] = datetime.now(timezone.utc).isoformat()
    return {"status": "acknowledged", "event_id": event["event_id"]}


@app.post("/events/{machine_id}/note")
def add_note(machine_id: str, body: NoteRequest):
    open_events = [e for e in _events if e["machine_id"] == machine_id and e["status"] == "open"]
    if not open_events:
        raise HTTPException(status_code=404, detail="No open event found for this machine")
    event = open_events[-1]
    event["notes"].append({"text": body.note, "at": datetime.now(timezone.utc).isoformat()})
    return {"status": "note_added", "event_id": event["event_id"]}


@app.post("/events/{machine_id}/close")
def close_event(machine_id: str):
    open_events = [e for e in _events if e["machine_id"] == machine_id and e["status"] == "open"]
    if not open_events:
        raise HTTPException(status_code=404, detail="No open event found for this machine")
    event = open_events[-1]
    event["status"] = "closed"
    event["closed_at"] = datetime.now(timezone.utc).isoformat()
    return {"status": "closed", "event_id": event["event_id"]}


@app.get("/events/{machine_id}/brief")
def get_event_brief(machine_id: str):
    machine_info = MACHINES.get(machine_id)
    if not machine_info:
        raise HTTPException(status_code=404, detail="Machine not found")

    open_events = [e for e in _events if e["machine_id"] == machine_id and e["status"] == "open"]
    if not open_events:
        raise HTTPException(status_code=404, detail="No open event found for this machine")

    event = open_events[-1]
    engineer = event.get("engineer_snapshot", {})
    metrics = engineer.get("structural_metrics", {})

    return {
        "machine_id": machine_id,
        "machine_type": machine_info["machine_type"],
        "what_changed": event["summary"],
        "when_detected": event["timestamp"],
        "current_status": event["status"],
        "primary_signals": event["top_signals"],
        "where_to_inspect": event["where_to_look"],
        "recommended_action": event["recommended_action"],
        "engineer_evidence_summary": {
            "drift_score": metrics.get("drift_score"),
            "relational_stability": metrics.get("relational_stability"),
            "covariance_shift": metrics.get("covariance_shift"),
            "direction": event["direction"],
            "urgency": event["urgency"],
            "pattern": engineer.get("pattern", {}).get("type"),
        },
        "notes": event["notes"],
        "not_claiming": "This does not identify an exact failed component or failure time.",
    }
