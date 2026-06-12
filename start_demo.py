"""
start_demo.py
=============

One-command launcher for the full hardware-free demonstration.

Running:
    python start_demo.py

starts, in order:
    1. MQTT broker            (mosquitto, auto-started if not already running)
    2. Backend WS relay       (backend/ws_relay.py)
    3. Simulated ESP + servo  (simulated_esp.py)
    4. Browser dashboard      (dashboard/index.html, opened automatically)
    5. Vision / face tracking (demo_mode.py)

Press Ctrl+C to stop everything cleanly.

Options:
    --target <name>   lock onto a specific enrolled identity (default: first / 'any')
    --no-window       run the vision node headless (dashboard only)
    --no-broker       do not try to start a local broker (use an external one)
"""

from __future__ import annotations

import argparse
import atexit
import shutil
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable
procs: list[subprocess.Popen] = []


def _port_open(host: str, port: int, timeout: float = 0.6) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _spawn(name: str, args: list[str], **kw) -> subprocess.Popen:
    print(f"[start] launching {name}: {' '.join(args)}")
    p = subprocess.Popen(args, cwd=str(ROOT), **kw)
    procs.append(p)
    return p


def _cleanup() -> None:
    for p in reversed(procs):
        if p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass
    t0 = time.time()
    for p in reversed(procs):
        while p.poll() is None and time.time() - t0 < 5:
            time.sleep(0.1)
        if p.poll() is None:
            try:
                p.kill()
            except Exception:
                pass


def main() -> None:
    ap = argparse.ArgumentParser(description="Launch the full Face-Locked Servo demo")
    ap.add_argument("--target", default="", help="enrolled identity to lock onto, or 'any'")
    ap.add_argument("--no-window", action="store_true", help="run vision node headless")
    ap.add_argument("--no-frames", action="store_true", help="do not publish video frames")
    ap.add_argument("--no-broker", action="store_true", help="do not auto-start mosquitto")
    args = ap.parse_args()

    atexit.register(_cleanup)

    def _on_signal(signum, frame):
        _cleanup()
        raise SystemExit(0)

    for _sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(_sig, _on_signal)
        except (ValueError, OSError):
            pass

    # Resolve broker host/port from config without importing heavy deps yet.
    sys.path.insert(0, str(ROOT))
    from src.distributed_config import DistributedConfig
    cfg = DistributedConfig()
    host = "localhost" if cfg.mqtt_host in ("0.0.0.0", "") else cfg.mqtt_host
    port = cfg.mqtt_port

    # 1) MQTT broker -----------------------------------------------------
    if not args.no_broker and not _port_open(host, port):
        mosq = shutil.which("mosquitto")
        if mosq:
            conf = ROOT / "backend" / "mosquitto.conf"
            broker_args = [mosq, "-p", str(port)]
            if conf.exists():
                broker_args += ["-c", str(conf)]
            _spawn("mqtt-broker", broker_args,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(40):
                if _port_open(host, port):
                    break
                time.sleep(0.1)
        else:
            print("[start] mosquitto not found. Install it or run:  docker compose up -d mqtt")
    if _port_open(host, port):
        print(f"[start] broker reachable at {host}:{port}")
    else:
        print(f"[start] WARNING: no broker at {host}:{port}; components will keep retrying")

    # 2) Backend WS relay ------------------------------------------------
    _spawn("backend-relay", [PY, str(ROOT / "backend" / "ws_relay.py")])
    time.sleep(1.0)

    # 3) Simulated ESP + virtual servo -----------------------------------
    _spawn("simulated-esp", [PY, str(ROOT / "simulated_esp.py")])
    time.sleep(0.6)

    # 4) Dashboard -------------------------------------------------------
    dash = ROOT / "dashboard" / "index.html"
    try:
        webbrowser.open(dash.as_uri())
        print(f"[start] dashboard opened: {dash}")
    except Exception:
        print(f"[start] open the dashboard manually: {dash}")

    # 5) Vision node -----------------------------------------------------
    vision_args = [PY, str(ROOT / "demo_mode.py")]
    if args.target:
        vision_args += ["--target", args.target]
    if args.no_window:
        vision_args += ["--no-window"]
    if args.no_frames:
        vision_args += ["--no-frames"]
    vision = _spawn("vision", vision_args)

    print("\n[start] system running. Press Ctrl+C to stop.\n")
    try:
        while True:
            if vision.poll() is not None:
                print("[start] vision node exited; shutting down.")
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[start] stopping...")
    finally:
        _cleanup()


if __name__ == "__main__":
    main()
