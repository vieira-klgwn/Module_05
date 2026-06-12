"""
start_exam.py — REAL HARDWARE exam launcher
===========================================

Use this when examiners give you a real ESP8266/ESP32 + servo + camera on the rig.
Do NOT run simulated_esp.py in that case — the physical board replaces it.

Starts:
    1. MQTT broker (optional — skip if examiners host the broker on a VPS)
    2. Backend WebSocket relay (dashboard)
    3. Vision node (webcam on the servo rig → face lock → MQTT movement commands)
    4. Browser dashboard

The REAL ESP (flashed with firmware/*.ino) must already be:
    - powered on
    - on the exam Wi-Fi
    - subscribed to vision/<team_id>/movement

When you move your face left/right, the PC publishes MOVE_LEFT / MOVE_RIGHT over
MQTT and the physical servo rotates the mounted camera.

Run:
    source .venv/bin/activate
    python start_exam.py --target YourName

Options:
    --target NAME     enrolled identity to lock onto
    --no-broker       broker is on the school VPS (set mqtt_host in config.json)
    --no-window       no OpenCV preview window on the PC
    --no-dashboard    do not auto-open the browser
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
    print(f"[exam] launching {name}: {' '.join(args)}")
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
    ap = argparse.ArgumentParser(description="Face-Locked Servo — REAL hardware exam mode")
    ap.add_argument("--target", default="", help="enrolled identity to lock onto")
    ap.add_argument("--no-broker", action="store_true", help="use external/VPS broker (set mqtt_host in config.json)")
    ap.add_argument("--no-window", action="store_true", help="headless vision (dashboard only)")
    ap.add_argument("--no-dashboard", action="store_true", help="do not open browser")
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

    sys.path.insert(0, str(ROOT))
    from src.distributed_config import DistributedConfig

    cfg = DistributedConfig()
    host = "localhost" if cfg.mqtt_host in ("0.0.0.0", "") else cfg.mqtt_host
    port = cfg.mqtt_port

    print("=" * 60)
    print("  REAL HARDWARE EXAM MODE")
    print("  Simulated ESP is NOT started — use your physical ESP board.")
    print(f"  team_id={cfg.team_id}  broker={cfg.mqtt_host}:{cfg.mqtt_port}")
    print("=" * 60)

    # 1) MQTT broker (only if local and not already running)
    if not args.no_broker and not _port_open(host, port):
        mosq = shutil.which("mosquitto")
        if mosq:
            conf = ROOT / "backend" / "mosquitto.conf"
            broker_args = [mosq, "-p", str(port)]
            if conf.exists():
                broker_args += ["-c", str(conf)]
            _spawn("mqtt-broker", broker_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(40):
                if _port_open(host, port):
                    break
                time.sleep(0.1)
    if _port_open(host, port):
        print(f"[exam] MQTT broker reachable at {host}:{port}")
    else:
        print(f"[exam] WARNING: cannot reach broker at {host}:{port}")
        print("[exam] Check config.json mqtt_host OR power on the school VPS broker.")

    # 2) Backend relay (dashboard needs this)
    _spawn("backend-relay", [PY, str(ROOT / "backend" / "ws_relay.py")])
    time.sleep(1.0)

    # 3) Dashboard
    if not args.no_dashboard:
        dash = ROOT / "dashboard" / "index.html"
        try:
            webbrowser.open(dash.as_uri())
            print(f"[exam] dashboard opened: {dash}")
        except Exception:
            print(f"[exam] open manually: {dash}")

    # 4) Vision node — publishes movement to MQTT → REAL ESP moves servo
    vision_args = [PY, str(ROOT / "demo_mode.py")]
    if args.target:
        vision_args += ["--target", args.target]
    if args.no_window:
        vision_args += ["--no-window"]
    vision = _spawn("vision", vision_args)

    print()
    print("[exam] Running. Move your face left/right — the PHYSICAL camera should pan.")
    print("[exam] Ensure the ESP is flashed, powered, and on the same Wi-Fi + team_id.")
    print("[exam] Press Ctrl+C to stop.\n")

    try:
        while True:
            if vision.poll() is not None:
                print("[exam] vision node exited; shutting down.")
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[exam] stopping...")
    finally:
        _cleanup()


if __name__ == "__main__":
    main()
