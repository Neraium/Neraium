# Run with:
#   uvicorn api.main:app --reload --port 8000

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from neraium.config import NeraiumConfig
from neraium.engine import NeraiumEngine
from neraium.system_output import build_system_output

app = FastAPI(title="Neraium API")

_config = NeraiumConfig()
_engine = NeraiumEngine(_config)


class UpdateRequest(BaseModel):
    asset_id: str
    timestamp: str | None = None
    signals: dict[str, float]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/reset")
def reset():
    global _engine
    _engine = NeraiumEngine(_config)
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

    packet = np.array(list(body.signals.values()), dtype=float)
    engine_output = _engine.update(packet)
    return build_system_output(engine_output)
