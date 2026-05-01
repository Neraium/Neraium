# Neraium Operator Console

Lightweight React console for the Neraium FastAPI backend.

## Backend

```bash
python -m uvicorn api.main:app --port 8000
```

## Frontend

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
