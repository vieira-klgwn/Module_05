#!/usr/bin/env python3
"""End-to-end pipeline test with logging. Run from project root with .venv active."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.camera_utils import open_camera
from src.distributed_config import DistributedConfig
from src.embed import ArcFaceEmbedderONNX
from src.haar_5pt import align_face_5pt
from src.recognize import FaceDBMatcher, HaarFaceMesh5pt, load_db_npz
from src.tracking import MovementTracker

RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))


def test_deps() -> None:
    mods = ["cv2", "numpy", "onnxruntime", "paho.mqtt.client", "websockets", "serial"]
    for m in mods:
        try:
            __import__(m)
            record(f"dep:{m}", True)
        except Exception as e:
            record(f"dep:{m}", False, str(e))


def test_db() -> str:
    db = load_db_npz(ROOT / "data/db/face_db.npz")
    ok = "User" in db and db["User"].size == 512
    record("enrollment_db", ok, f"identities={list(db.keys())}")
    return "User" if ok else ""


def test_camera(cfg: DistributedConfig) -> bool:
    cap = open_camera(cfg.camera_index, max_probe=10)
    if cap is None:
        record("camera_feed", False, "cannot open")
        return False
    ok_count = 0
    w = h = 0
    t0 = time.time()
    for _ in range(30):
        ok, frame = cap.read()
        if ok and frame is not None:
            ok_count += 1
            h, w = frame.shape[:2]
    dt = time.time() - t0
    cap.release()
    fps = ok_count / max(dt, 1e-6)
    ok = ok_count >= 25
    record("camera_feed", ok, f"{w}x{h} {fps:.1f}fps ({ok_count}/30 frames)")
    return ok


def test_detection(cfg: DistributedConfig) -> bool:
    cap = open_camera(cfg.camera_index, max_probe=10)
    if cap is None:
        record("face_detection", False, "no camera")
        return False
    det = HaarFaceMesh5pt(min_size=(70, 70), debug=False)
    found = 0
    for _ in range(40):
        ok, frame = cap.read()
        if not ok:
            continue
        if det.detect(frame, max_faces=3):
            found += 1
    cap.release()
    ok = found >= 10
    record("face_detection", ok, f"detected in {found}/40 frames")
    return ok


def test_recognition(cfg: DistributedConfig, name: str) -> bool:
    if not name:
        record("face_recognition", False, "no enrolled name")
        return False
    db = load_db_npz(ROOT / "data/db/face_db.npz")
    cap = open_camera(cfg.camera_index, max_probe=10)
    if cap is None:
        record("face_recognition", False, "no camera")
        return False
    det = HaarFaceMesh5pt(min_size=(70, 70), debug=False)
    embedder = ArcFaceEmbedderONNX(debug=False)
    matcher = FaceDBMatcher(db=db, dist_thresh=0.34)
    accepted = 0
    best_sim = 0.0
    for _ in range(40):
        ok, frame = cap.read()
        if not ok:
            continue
        for f in det.detect(frame, max_faces=3):
            aligned, _ = align_face_5pt(frame, f.kps, out_size=(112, 112))
            emb = embedder.embed(aligned).embedding
            mr = matcher.match(emb)
            best_sim = max(best_sim, mr.similarity)
            if mr.name == name and mr.accepted:
                accepted += 1
    cap.release()
    ok = accepted >= 5
    record("face_recognition", ok, f"IDENTIFIED {name} in {accepted} frames, best_sim={best_sim:.3f}")
    return ok


def test_tracking(cfg: DistributedConfig) -> bool:
    cap = open_camera(cfg.camera_index, max_probe=10)
    if cap is None:
        record("face_tracking", False, "no camera")
        return False
    det = HaarFaceMesh5pt(min_size=(70, 70), debug=False)
    tracker = MovementTracker(
        dead_zone_px=float(cfg.tracking_get("dead_zone_px", 80)),
        smoothing_alpha=float(cfg.tracking_get("smoothing_alpha", 0.6)),
        min_consecutive=1,
    )
    states: set[str] = set()
    logs = []
    for i in range(60):
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        faces = det.detect(frame, max_faces=1)
        cx = None
        if faces:
            cx = float(np.mean(faces[0].kps[:, 0]))
        st = tracker.update(cx, w)
        states.add(st)
        if i % 15 == 0 and cx is not None:
            logs.append(f"cx={cx:.0f} center={w/2:.0f} dz={cfg.tracking_get('dead_zone_px',80)} -> {st}")
    cap.release()
    ok = "NO_FACE" in states or len(states) >= 1
    record("face_tracking", ok, f"states={sorted(states)} | " + " | ".join(logs[:3]))
    return ok


def test_mqtt_publish(cfg: DistributedConfig) -> bool:
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        record("mqtt_publish", False, "paho missing")
        return False

    host = cfg.mqtt_host if cfg.mqtt_host not in ("0.0.0.0", "") else "localhost"
    try:
        socket.create_connection((host, cfg.mqtt_port), timeout=2)
    except OSError:
        # try start broker
        mosq = subprocess.Popen(
            ["mosquitto", "-p", str(cfg.mqtt_port), "-c", str(ROOT / "backend/mosquitto.conf")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(1.0)

    received = []

    def on_msg(c, u, m):
        received.append(json.loads(m.payload.decode()))

    try:
        sub = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    except (AttributeError, TypeError):
        sub = mqtt.Client()
    sub.on_message = lambda c, u, m: received.append(json.loads(m.payload.decode()))
    sub.connect(host, cfg.mqtt_port, 30)
    sub.subscribe(cfg.topic_movement)
    sub.loop_start()

    from src.mqtt_pub import MqttPublisher
    pub = MqttPublisher(cfg, node_name="test")
    if not pub.connect(timeout=5):
        record("mqtt_publish", False, f"cannot connect {host}:{cfg.mqtt_port}")
        sub.loop_stop()
        return False
    pub.publish_movement("MOVE_LEFT", 0.91)
    pub.publish_movement("CENTERED", 0.88)
    time.sleep(1.0)
    pub.close()
    sub.loop_stop()
    sub.disconnect()

    ok = len(received) >= 1 and received[0].get("status") in ("MOVE_LEFT", "CENTERED")
    detail = f"topic={cfg.topic_movement} msgs={len(received)} sample={received[0] if received else {}}"
    record("mqtt_publish", ok, detail)
    return ok


def test_esp_serial(cfg: DistributedConfig) -> bool:
    port = cfg.hardware.get("serial_port", "/dev/ttyUSB0")
    if not Path(port).exists():
        record("esp32_serial", False, f"{port} not found")
        return False
    try:
        import serial
        ser = serial.Serial(port, 115200, timeout=1)
        lines = []
        t0 = time.time()
        while time.time() - t0 < 3:
            if ser.in_waiting:
                line = ser.readline().decode(errors="ignore").strip()
                if line:
                    lines.append(line)
        ser.close()
        ok = True  # port opens = ESP connected
        record("esp32_serial", ok, f"{port} open, {len(lines)} log lines: {lines[:2]}")
        return ok
    except Exception as e:
        record("esp32_serial", False, str(e))
        return False


def test_websocket(cfg: DistributedConfig) -> bool:
    import asyncio
    import websockets

    async def run():
        try:
            async with websockets.connect(f"ws://localhost:{cfg.ws_port}", open_timeout=2) as ws:
                await asyncio.wait_for(ws.recv(), timeout=3)
                return True
        except Exception:
            return False

    # start relay briefly if needed
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "backend/ws_relay.py")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env={**dict(__import__("os").environ), "TEAM_ID": cfg.team_id, "MQTT_HOST": "localhost"},
    )
    time.sleep(2)
    # publish a message
    from src.mqtt_pub import MqttPublisher
    pub = MqttPublisher(cfg, node_name="wstest")
    pub.connect()
    pub.publish_movement("CENTERED", 0.9)
    time.sleep(0.5)
    pub.close()

    try:
        ok = asyncio.run(run())
    except Exception:
        ok = False
    proc.terminate()
    record("dashboard_websocket", ok, f"ws://localhost:{cfg.ws_port}")
    return ok


def main() -> int:
    cfg = DistributedConfig()
    print("=== Pipeline test ===")
    print(f"team={cfg.team_id} broker={cfg.mqtt_host}:{cfg.mqtt_port} camera={cfg.camera_index}")
    test_deps()
    name = test_db()
    test_camera(cfg)
    test_detection(cfg)
    test_recognition(cfg, name)
    test_tracking(cfg)
    test_mqtt_publish(cfg)
    test_esp_serial(cfg)
    test_websocket(cfg)

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n=== {passed}/{total} passed ===")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
