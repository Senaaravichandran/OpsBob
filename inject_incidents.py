#!/usr/bin/env python3
"""
inject_incidents.py
-------------------
Randomly triggers incidents across the OpsBob demo services (ports 3002-3004).
Each service fires its own /trigger-incident endpoint which calls fireWebhook()
internally, pushing an incident into the backend (/webhook → /incidents feed).

Usage:
  python inject_incidents.py                # run indefinitely
  python inject_incidents.py --count 10    # fire exactly 10 incidents then stop
  python inject_incidents.py --min 5 --max 30  # custom interval range (seconds)
  python inject_incidents.py --burst 3     # fire 3 incidents rapidly on each cycle
  python inject_incidents.py --once        # fire one incident per service then exit

Options:
  --min       Minimum seconds between incidents  (default: 8)
  --max       Maximum seconds between incidents  (default: 25)
  --count     Total incidents to fire then exit  (default: unlimited)
  --burst     Number of incidents per cycle      (default: 1)
  --once      Fire each service once then exit
  --port      Backend proxy port                 (default: 8001)
  --services  Comma-separated service ports      (default: 3002,3003,3004)
  --payments  Number of /payment calls to spam after each trigger (default: 0)
  --verbose   Print full response bodies
"""

import argparse
import random
import sys
import time
import urllib.request
import urllib.error
import json
from datetime import datetime

# ── colour helpers (no external deps) ────────────────────────────────────────
def _c(code, text):
    return f"\033[{code}m{text}\033[0m"

RED    = lambda t: _c("91", t)
YELLOW = lambda t: _c("93", t)
GREEN  = lambda t: _c("92", t)
CYAN   = lambda t: _c("96", t)
DIM    = lambda t: _c("2",  t)

# ── service catalogue ─────────────────────────────────────────────────────────
DEFAULT_SERVICES = {
    3002: {"name": "demo-service1", "bug": "MEMORY_LEAK",      "severity": "HIGH"},
    3003: {"name": "demo-service2", "bug": "CPU_SPIKE",        "severity": "CRITICAL"},
    3004: {"name": "demo-service3", "bug": "CONNECTION_LEAK",  "severity": "HIGH"},
}

# ── http helpers ──────────────────────────────────────────────────────────────
def post_json(url: str, payload: dict | None = None, timeout: int = 5):
    body = json.dumps(payload or {}).encode()
    req  = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode())

def check_service(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/health", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False

def trigger_incident(port: int, verbose: bool = False) -> bool:
    url = f"http://localhost:{port}/trigger-incident"
    meta = DEFAULT_SERVICES.get(port, {"name": f"svc:{port}", "bug": "UNKNOWN"})
    ts   = datetime.now().strftime("%H:%M:%S")
    try:
        status, body = post_json(url)
        ok = status == 200
        tag = GREEN("✓ FIRED") if ok else YELLOW("⚠ NON-200")
        print(f"  [{ts}] {tag}  port={CYAN(str(port))}  bug={YELLOW(meta['bug'])}  http={status}")
        if verbose:
            print(f"         {DIM(json.dumps(body))}")
        return ok
    except urllib.error.HTTPError as e:
        label = RED("✗ 404 — restart service") if e.code == 404 else YELLOW(f"⚠ HTTP {e.code}")
        print(f"  [{ts}] {label}  port={port}  ({meta['bug']})")
        return False
    except urllib.error.URLError as e:
        print(f"  [{ts}] {RED('✗ CONN ERR')}  port={port}  — {e.reason}")
        return False
    except Exception as e:
        print(f"  [{ts}] {RED('✗ ERROR')}  port={port}  — {e}")
        return False

def spam_payments(port: int, count: int):
    """Pump /payment calls to push the service past its auto-fire threshold."""
    url = f"http://localhost:{port}/payment"
    ok  = 0
    for i in range(count):
        try:
            status, _ = post_json(url, {"userId": f"inject-{i}", "amount": random.uniform(1, 500)})
            if status == 200:
                ok += 1
        except Exception:
            pass
    print(f"         {DIM(f'spammed {ok}/{count} payments → port {port}')}")

# ── main ──────────────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(description="OpsBob demo-service random incident injector")
    p.add_argument("--min",      type=float, default=8,     help="Min seconds between cycles")
    p.add_argument("--max",      type=float, default=25,    help="Max seconds between cycles")
    p.add_argument("--count",    type=int,   default=0,     help="Stop after N incidents (0 = unlimited)")
    p.add_argument("--burst",    type=int,   default=1,     help="Incidents to fire per cycle")
    p.add_argument("--once",     action="store_true",        help="Fire each service once then exit")
    p.add_argument("--port",     type=int,   default=8001,  help="Backend port (not used directly)")
    p.add_argument("--services", type=str,   default="3002,3003,3004")
    p.add_argument("--payments", type=int,   default=0,     help="Extra /payment calls per trigger")
    p.add_argument("--verbose",  action="store_true")
    return p.parse_args()

def main():
    args = parse_args()
    ports = [int(p.strip()) for p in args.services.split(",") if p.strip()]

    print(CYAN("━" * 55))
    print(CYAN("  OpsBob — Random Incident Injector"))
    print(CYAN("━" * 55))
    print(f"  Services : {ports}")
    print(f"  Interval : {args.min}–{args.max}s  |  Burst: {args.burst}  |  Limit: {args.count or '∞'}")
    print()

    # pre-flight: warn about services that aren't up
    print("  Checking service health…")
    live = []
    for p in ports:
        up = check_service(p)
        sym = GREEN("●") if up else RED("○")
        info = DEFAULT_SERVICES.get(p, {})
        print(f"    {sym} localhost:{p}  ({info.get('bug', '?')})")
        if up:
            live.append(p)
    if not live:
        print(RED("\n  No services reachable — start them first (npm start in each demo-service* folder)"))
        sys.exit(1)
    print()

    fired = 0

    # ── --once mode: fire each live service exactly once ──────────────────────
    if args.once:
        for p in live:
            trigger_incident(p, verbose=args.verbose)
            if args.payments > 0:
                spam_payments(p, args.payments)
            fired += 1
            time.sleep(0.5)
        print(f"\n  Done — fired {fired} incident(s).")
        return

    # ── continuous / count-limited loop ───────────────────────────────────────
    cycle = 0
    try:
        while True:
            cycle += 1
            print(f"{DIM(f'── cycle {cycle} ──')}")

            # pick --burst random services (with replacement for variety)
            targets = random.choices(live, k=args.burst)
            for p in targets:
                ok = trigger_incident(p, verbose=args.verbose)
                if ok and args.payments > 0:
                    spam_payments(p, args.payments)
                if ok:
                    fired += 1
                    if args.count and fired >= args.count:
                        print(f"\n  Reached limit of {args.count} incidents. Done.")
                        return

            delay = random.uniform(args.min, args.max)
            print(DIM(f"  sleeping {delay:.1f}s …\n"))
            time.sleep(delay)

    except KeyboardInterrupt:
        print(f"\n{CYAN('  Stopped.')}  Total incidents fired: {GREEN(str(fired))}")

if __name__ == "__main__":
    main()
