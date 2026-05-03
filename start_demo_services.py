#!/usr/bin/env python3
"""
start_demo_services.py — Start all OpsBob demo services

Services:
  demo-service1  →  port 3002  (bug: MEMORY_LEAK)
  demo-service2  →  port 3003  (bug: CPU_SPIKE)
  demo-service3  →  port 3004  (bug: CONNECTION_LEAK)
  demo-service4  →  port 3005  (clean — no bugs)

Usage:
  python start_demo_services.py
  Ctrl+C to stop all services.
"""

import os
import sys
import signal
import subprocess
from pathlib import Path

BASE = Path(__file__).parent

SERVICES = [
    {"dir": "demo-service1", "port": 3002},
    {"dir": "demo-service2", "port": 3003},
    {"dir": "demo-service3", "port": 3004},
    {"dir": "demo-service4", "port": 3005},
]

processes = []


def start_services():
    for svc in SERVICES:
        svc_dir = BASE / svc["dir"]
        if not (svc_dir / "server.js").exists():
            print(f"[SKIP] {svc['dir']}: server.js not found")
            continue
        env = {**os.environ, "PORT": str(svc["port"])}
        proc = subprocess.Popen(
            ["node", "server.js"],
            cwd=str(svc_dir),
            env=env,
        )
        processes.append(proc)
        print(f"[START] {svc['dir']}  port={svc['port']}  pid={proc.pid}")


def stop_all(sig=None, frame=None):
    print("\n[STOP] Shutting down all demo services...")
    for proc in processes:
        proc.terminate()
    for proc in processes:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    print("[DONE] All services stopped.")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, stop_all)
    signal.signal(signal.SIGTERM, stop_all)

    print("=" * 50)
    print("  OpsBob Demo Services")
    print("=" * 50)
    start_services()

    if not processes:
        print("[ERROR] No services started.")
        sys.exit(1)

    print(f"\n{len(processes)} service(s) running. Press Ctrl+C to stop.\n")

    # Wait for all processes; restart any that exit unexpectedly
    for proc in processes:
        proc.wait()
