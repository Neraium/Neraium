#!/usr/bin/env python3
"""
Start Neraium API + frontend dev server together.

Usage:
    python dev.py

Ctrl+C stops both.
"""

import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
FRONTEND = ROOT / "frontend"


def check_deps():
    missing = []
    if not shutil.which("uvicorn"):
        missing.append("uvicorn  (pip install uvicorn)")
    if not shutil.which("npm"):
        missing.append("npm  (install Node.js from https://nodejs.org)")
    if missing:
        print("Missing dependencies:")
        for m in missing:
            print(f"  {m}")
        sys.exit(1)

    node_modules = FRONTEND / "node_modules"
    if not node_modules.exists():
        print("Installing frontend dependencies...")
        subprocess.run(["npm", "install"], cwd=FRONTEND, check=True)


def main():
    check_deps()

    procs = []

    api = subprocess.Popen(
        ["uvicorn", "api.main:app", "--reload", "--port", "8000"],
        cwd=ROOT,
    )
    procs.append(api)
    print("API     → http://127.0.0.1:8000")

    # Give the API a moment to bind before the browser opens
    time.sleep(1)

    frontend = subprocess.Popen(
        ["npm", "run", "dev", "--", "--open"],
        cwd=FRONTEND,
    )
    procs.append(frontend)
    print("UI      → http://localhost:5173")
    print("\nCtrl+C to stop both.\n")

    def shutdown(sig, frame):
        print("\nStopping...")
        for p in procs:
            p.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    for p in procs:
        p.wait()


if __name__ == "__main__":
    main()
