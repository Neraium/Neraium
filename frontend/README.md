# Neraium Operator Console

Lightweight React console for the Neraium FastAPI backend.

## Run Instructions

Start the backend from the repository root:

```bash
python -m uvicorn api.main:app --port 8000
```

Start the frontend in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` requests to `http://127.0.0.1:8000`.

To call a different backend directly:

```bash
VITE_NERAIUM_API_BASE=http://127.0.0.1:8000 npm run dev
```

You can also change the API base URL in the app Settings tab.

## CSV Input

Use the Settings tab to load a local CSV. Required columns:

- `spindle_vibration`
- `spindle_motor_current`
- `coolant_flow_rate`
- `axis_servo_load`
- `cutting_zone_temperature`

After loading a CSV, select `Loaded CSV` as the input source and use the Demo tab to stream rows to the backend.
