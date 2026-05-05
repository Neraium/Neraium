# Run with:
#   uvicorn api.main:app --reload --port 8000

import io
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from neraium.adapters.cannabis import (
    build_cannabis_context,
    detect_platform,
    normalise_dataframe,
)
from neraium.config import NeraiumConfig
from neraium.engine import NeraiumEngine
from neraium.engineer import build_engineer_output
from neraium.operator import build_operator_output
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


# ---------------------------------------------------------------------------
# Replay session store
# ---------------------------------------------------------------------------

@dataclass
class ReplaySession:
    session_id: str
    rows: np.ndarray     # shape (n_rows, n_signals) — single contiguous block
    signal_names: list[str]
    signal_labels: dict[str, str]
    platform: str
    engine: NeraiumEngine
    current_row: int = 0

    @property
    def total_rows(self) -> int:
        return len(self.rows)

    @property
    def done(self) -> bool:
        return self.current_row >= self.total_rows


_replay_sessions: dict[str, ReplaySession] = {}


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


# ---------------------------------------------------------------------------
# Cannabis / grow-room CSV ingestion
# ---------------------------------------------------------------------------

@app.post("/ingest/csv")
async def ingest_csv(file: UploadFile = File(...)):
    """
    Upload any grow-room CSV (Aroya, TrolMaster, Growlink, Metrc, etc.).
    Returns the first confirmed structural event found, or a no-event summary.

    The engine processes every row sequentially and stops at the first ALERT,
    returning operator + engineer output plus metadata about which signals
    drove the change.
    """
    contents = await file.read()
    try:
        raw_df = pd.read_csv(io.BytesIO(contents))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {exc}")

    platform = detect_platform(raw_df)
    df = normalise_dataframe(raw_df)

    if df.empty:
        raise HTTPException(
            status_code=422,
            detail="No numeric signals found after normalisation. Check column names.",
        )

    signal_names = df.columns.tolist()
    context      = build_cannabis_context(df)
    engine       = NeraiumEngine(NeraiumConfig(), signal_names=signal_names)

    first_alert: dict | None = None

    for row_idx, (_, row) in enumerate(df.iterrows()):
        packet     = row.to_numpy(dtype=float)
        engine_out = engine.update(packet)
        status     = engine_out.get("status")

        if status in ("ALERT", "ALERT_HELD"):
            operator = build_operator_output(engine_out, sensor_context=context)
            engineer = build_engineer_output(engine_out)
            first_alert = {
                "row": row_idx,
                "status": status,
                "operator": operator,
                "engineer": engineer,
            }
            break

    return {
        "filename": file.filename,
        "platform": platform,
        "rows_processed": row_idx + 1 if first_alert else len(df),
        "signals": signal_names,
        "alert": first_alert,
        "message": (
            "Structural change detected."
            if first_alert
            else "No confirmed structural change found in this dataset."
        ),
    }


# ---------------------------------------------------------------------------
# Historical replay — session-based, step-by-step
# ---------------------------------------------------------------------------

def _parse_replay_csv(file_obj) -> ReplaySession:
    """
    Parse an uploaded CSV into a ReplaySession.
    file_obj may be a bytes object or any file-like object pandas can read.
    Rows are stored as a single contiguous float64 matrix (n_rows × n_signals)
    rather than a list of arrays, so memory is proportional to data size only.
    """
    try:
        raw_df = pd.read_csv(file_obj)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {exc}")

    if raw_df.empty:
        raise HTTPException(status_code=422, detail="Uploaded CSV contains no data rows.")

    platform = detect_platform(raw_df)
    df       = normalise_dataframe(raw_df)

    if df.empty or len(df.columns) == 0:
        raise HTTPException(
            status_code=422,
            detail="No numeric signals found after normalisation. Check column names.",
        )

    signal_names = df.columns.tolist()
    context      = build_cannabis_context(df)
    labels       = {col: ctx["name"] for col, ctx in context.items()}
    # Single contiguous matrix — 8× more memory-efficient than a list of arrays
    rows         = df.to_numpy(dtype=np.float64)
    engine       = NeraiumEngine(NeraiumConfig(), signal_names=signal_names)

    return ReplaySession(
        session_id    = str(uuid.uuid4()),
        rows          = rows,
        signal_names  = signal_names,
        signal_labels = labels,
        platform      = platform,
        engine        = engine,
    )


@app.post("/replay/upload")
async def replay_upload(file: UploadFile = File(...)):
    """
    Upload a CSV and create a persistent replay session.
    Works for any file size — rows are stored as a single numpy matrix.
    Returns session metadata including a recommended tick_n (rows per tick)
    so the frontend can replay any size dataset in ~200 ticks.
    """
    # Pass the underlying SpooledTemporaryFile directly to pandas so the
    # full file body is never duplicated in memory as a Python bytes object.
    session = _parse_replay_csv(file.file)
    _replay_sessions[session.session_id] = session

    # Recommend a batch size that makes any dataset play back in ~200 ticks
    tick_n = max(1, -(-session.total_rows // 200))   # ceiling division

    return {
        "session_id"   : session.session_id,
        "filename"     : file.filename,
        "platform"     : session.platform,
        "total_rows"   : session.total_rows,
        "signals"      : session.signal_names,
        "signal_labels": session.signal_labels,
        "tick_n"       : tick_n,
    }


@app.post("/replay/{session_id}/tick")
def replay_tick(session_id: str, n: int = 1):
    """
    Advance the replay by n rows (default 1).
    Returns engine output in the same shape as /update plus replay progress fields.
    When the dataset is exhausted, returns {done: true} with no engine output.
    """
    session = _replay_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Replay session not found")

    if session.done:
        return {"done": True, "current_row": session.current_row, "total_rows": session.total_rows}

    n = max(1, min(n, session.total_rows - session.current_row))

    # Feed rows to the engine; numpy matrix indexing is O(1) per row
    start = session.current_row
    last_out = None
    for i in range(start, start + n):
        last_out = session.engine.update(session.rows[i])
    session.current_row = start + n

    last_row = session.rows[session.current_row - 1]
    system   = build_system_output(last_out)
    signal_values = {name: float(val) for name, val in zip(session.signal_names, last_row)}

    return {
        **system,
        "replay": {
            "session_id" : session_id,
            "current_row": session.current_row,
            "total_rows" : session.total_rows,
            "n_ticked"   : n,
            "done"       : session.done,
            "platform"   : session.platform,
        },
        "signal_values": signal_values,
    }


@app.get("/replay/{session_id}/status")
def replay_status(session_id: str):
    session = _replay_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Replay session not found")
    return {
        "session_id"   : session_id,
        "platform"     : session.platform,
        "current_row"  : session.current_row,
        "total_rows"   : session.total_rows,
        "done"         : session.done,
        "signals"      : session.signal_names,
        "signal_labels": session.signal_labels,
    }


@app.post("/replay/{session_id}/reset")
def replay_reset(session_id: str):
    session = _replay_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Replay session not found")
    session.engine      = NeraiumEngine(NeraiumConfig(), signal_names=session.signal_names)
    session.current_row = 0
    return {"status": "reset", "session_id": session_id, "total_rows": session.total_rows}


@app.delete("/replay/{session_id}")
def replay_delete(session_id: str):
    _replay_sessions.pop(session_id, None)
    return {"status": "deleted", "session_id": session_id}
