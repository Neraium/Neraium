#!/usr/bin/env python3
"""
Start Neraium API + frontend dev server together.

Usage:
    python dev.py           # localhost only
    python dev.py --lan     # expose on local network (for iPhone, iPad, etc.)

Ctrl+C stops both.
"""

import argparse
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
FRONTEND = ROOT / "frontend"


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "YOUR_COMPUTER_IP"


def check_deps():
    missing = []
    if not shutil.which("uvicorn"):
        missing.append("uvicorn  →  pip install uvicorn")
    if not shutil.which("npm"):
        missing.append("npm  →  install Node.js from https://nodejs.org")
    if missing:
        print("Missing dependencies:")
        for m in missing:
            print(f"  {m}")
        sys.exit(1)

    if not (FRONTEND / "node_modules").exists():
        print("Installing frontend dependencies...")
        subprocess.run(["npm", "install"], cwd=FRONTEND, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lan", action="store_true",
                        help="Bind to 0.0.0.0 so phones/tablets on the same WiFi can connect")
    args = parser.parse_args()

    check_deps()

    host = "0.0.0.0" if args.lan else "127.0.0.1"
    ip   = local_ip() if args.lan else "localhost"

    procs = []

    api = subprocess.Popen(
        ["uvicorn", "api.main:app", "--reload", "--host", host, "--port", "8000"],
        cwd=ROOT,
    )
    procs.append(api)

    time.sleep(1)

    vite_cmd = ["npm", "run", "dev", "--"]
    if args.lan:
        vite_cmd += ["--host"]          # Vite binds to 0.0.0.0
    else:
        vite_cmd += ["--open"]          # open browser automatically on desktop

    frontend = subprocess.Popen(vite_cmd, cwd=FRONTEND)
    procs.append(frontend)

    print()
    if args.lan:
        print("━" * 50)
        print(f"  Desktop  →  http://localhost:5173")
        print(f"  iPhone   →  http://{ip}:5173")
        print()
        print("  Make sure your phone is on the same WiFi.")
        print("  Open Safari and go to the URL above.")
        print("━" * 50)
    else:
        print("  UI   →  http://localhost:5173")
        print("  API  →  http://127.0.0.1:8000")

    print("\n  Ctrl+C to stop\n")

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
