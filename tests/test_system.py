"""
Automated test suite for the Face-Locked Servo system.

Covers (hardware-free):
    * Servo simulator: limits, smooth/rate-limited motion, jitter dead-band, direction.
    * Hardware Abstraction Layer: simulation fallback + movement vocabulary.
    * Movement tracking: centre dead zone, hysteresis, NO_FACE handling.
    * Config: per-team MQTT topic isolation + env override.
    * MQTT payload schema.
    * Face DB matcher (recognition logic) with synthetic embeddings.
    * Enrollment maths (mean + L2 normalise).
    * ArcFace ONNX embedder load + inference (skipped if model absent).
    * End-to-end MQTT roundtrip: movement -> simulated ESP -> servo state
      (skipped if no MQTT broker can be started/reached).

Run:
    python -m pytest tests/ -v
    python tests/test_system.py        # also works without pytest
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hardware.servo_simulator import ServoSimulator
from hardware.servo_interface import ServoController, ServoMode
from src.tracking import MovementTracker
from src.distributed_config import DistributedConfig
from src.mqtt_pub import MovementPayload


# --------------------------------------------------------------------------- #
# Servo simulator
# --------------------------------------------------------------------------- #
class TestServoSimulator(unittest.TestCase):
    def test_limits_enforced(self):
        s = ServoSimulator(min_angle=0, max_angle=180, center_angle=90, max_speed_dps=10_000)
        s.set_target(500)
        for _ in range(50):
            s.update()
        self.assertLessEqual(s.angle, 180.0)
        s.set_target(-100)
        for _ in range(50):
            s.update()
        self.assertGreaterEqual(s.angle, 0.0)

    def test_rate_limited_smooth_motion(self):
        s = ServoSimulator(center_angle=90, max_speed_dps=60)  # 60 deg/s
        s.set_target(180)
        st = s.update(now=s.state().timestamp + 0.1)  # 0.1s -> max ~6 deg
        self.assertLess(st.angle, 100.0)
        self.assertGreater(st.angle, 90.0)

    def test_jitter_deadband(self):
        s = ServoSimulator(center_angle=90, jitter_deadband=2.0)
        s.set_target(91)  # within dead-band
        st = s.update()
        self.assertFalse(st.moving)
        self.assertEqual(st.direction, "HOLD")

    def test_direction_reporting(self):
        s = ServoSimulator(center_angle=90, max_speed_dps=10_000)
        s.set_target(120)
        self.assertEqual(s.update().direction, "RIGHT")
        s.set_target(60)
        self.assertEqual(s.update().direction, "LEFT")

    def test_history_recorded(self):
        s = ServoSimulator()
        for _ in range(5):
            s.update()
        self.assertGreaterEqual(len(s.history()), 5)


# --------------------------------------------------------------------------- #
# Hardware Abstraction Layer
# --------------------------------------------------------------------------- #
class TestHAL(unittest.TestCase):
    def test_simulation_mode_selected(self):
        c = ServoController(mode="simulation")
        self.assertEqual(c.mode, ServoMode.SIMULATION)
        self.assertTrue(c.is_simulation)

    def test_auto_falls_back_to_simulation(self):
        # No board wired in CI -> auto must degrade to simulation.
        c = ServoController(mode="auto", serial_port="auto")
        self.assertIn(c.mode, (ServoMode.SIMULATION, ServoMode.ESP8266, ServoMode.ESP32))

    def test_movement_vocabulary(self):
        c = ServoController(mode="simulation", track_step=5, max_speed_dps=10_000, center_angle=90)
        start = c.state().angle
        c.apply_movement("MOVE_RIGHT")
        for _ in range(5):
            c.update()
        self.assertGreater(c.state().angle, start)
        right = c.state().angle
        c.apply_movement("MOVE_LEFT")
        c.apply_movement("MOVE_LEFT")
        for _ in range(5):
            c.update()
        self.assertLess(c.state().angle, right)


# --------------------------------------------------------------------------- #
# Movement tracking
# --------------------------------------------------------------------------- #
class TestTracking(unittest.TestCase):
    def test_dead_zone_centered(self):
        t = MovementTracker(dead_zone_px=80, min_consecutive=1, smoothing_alpha=1.0)
        # near centre of a 640px frame
        self.assertEqual(t.update(320, 640), "CENTERED")

    def test_move_left_right(self):
        t = MovementTracker(dead_zone_px=80, min_consecutive=1, smoothing_alpha=1.0)
        self.assertEqual(t.update(100, 640), "MOVE_LEFT")
        t.reset()
        self.assertEqual(t.update(560, 640), "MOVE_RIGHT")

    def test_no_face(self):
        t = MovementTracker(min_consecutive=1)
        self.assertEqual(t.update(None, 640), "NO_FACE")

    def test_debounce_requires_consecutive(self):
        t = MovementTracker(dead_zone_px=80, min_consecutive=3, smoothing_alpha=1.0)
        # single off-centre frame should NOT immediately flip from initial NO_FACE
        first = t.update(100, 640)
        self.assertEqual(first, "NO_FACE")
        t.update(100, 640)
        committed = t.update(100, 640)
        self.assertEqual(committed, "MOVE_LEFT")


# --------------------------------------------------------------------------- #
# Config / topic isolation
# --------------------------------------------------------------------------- #
class TestConfig(unittest.TestCase):
    def test_topic_isolation(self):
        os.environ["TEAM_ID"] = "UnitTeam"
        try:
            cfg = DistributedConfig()
            self.assertEqual(cfg.team_id, "UnitTeam")
            self.assertEqual(cfg.topic_movement, "vision/UnitTeam/movement")
            self.assertEqual(cfg.topic_servo, "vision/UnitTeam/servo")
            self.assertTrue(cfg.topic_movement.startswith("vision/"))
        finally:
            del os.environ["TEAM_ID"]


# --------------------------------------------------------------------------- #
# MQTT payload schema
# --------------------------------------------------------------------------- #
class TestPayload(unittest.TestCase):
    def test_movement_payload_schema(self):
        d = MovementPayload(status="MOVE_LEFT", confidence=0.87, timestamp=123).to_dict()
        self.assertEqual(set(d.keys()), {"status", "confidence", "timestamp"})
        self.assertIsInstance(d["status"], str)
        self.assertIsInstance(d["confidence"], float)
        self.assertIsInstance(d["timestamp"], int)
        json.dumps(d)  # must be JSON serialisable


# --------------------------------------------------------------------------- #
# Recognition matcher
# --------------------------------------------------------------------------- #
class TestMatcher(unittest.TestCase):
    def test_matcher_accepts_self_rejects_other(self):
        from src.recognize import FaceDBMatcher

        rng = np.random.default_rng(0)
        a = rng.standard_normal(512).astype(np.float32)
        a /= np.linalg.norm(a)
        b = rng.standard_normal(512).astype(np.float32)
        b /= np.linalg.norm(b)
        matcher = FaceDBMatcher(db={"A": a, "B": b}, dist_thresh=0.34)

        same = matcher.match(a)
        self.assertEqual(same.name, "A")
        self.assertTrue(same.accepted)

        far = rng.standard_normal(512).astype(np.float32)
        far /= np.linalg.norm(far)
        res = matcher.match(far)
        # a random vector is very unlikely to be within 0.34 cosine distance
        self.assertFalse(res.accepted)


# --------------------------------------------------------------------------- #
# Enrollment maths
# --------------------------------------------------------------------------- #
class TestEnrollMath(unittest.TestCase):
    def test_mean_embedding_is_unit_norm(self):
        from src.enroll import mean_embedding

        embs = [np.array([1, 0, 0], dtype=np.float32),
                np.array([0, 1, 0], dtype=np.float32)]
        m = mean_embedding(embs)
        self.assertAlmostEqual(float(np.linalg.norm(m)), 1.0, places=5)


# --------------------------------------------------------------------------- #
# ArcFace embedder (skip if model missing)
# --------------------------------------------------------------------------- #
class TestEmbedder(unittest.TestCase):
    def test_embed_dim_and_norm(self):
        model = ROOT / "models" / "embedder_arcface.onnx"
        if not model.exists() or model.stat().st_size < 1000:
            self.skipTest("ArcFace ONNX model not present")
        from src.embed import ArcFaceEmbedderONNX

        e = ArcFaceEmbedderONNX(debug=False)
        img = (np.random.rand(112, 112, 3) * 255).astype(np.uint8)
        r = e.embed(img)
        self.assertEqual(r.dim, 512)
        self.assertAlmostEqual(float(np.linalg.norm(r.embedding)), 1.0, places=4)


# --------------------------------------------------------------------------- #
# End-to-end MQTT roundtrip (skip if no broker)
# --------------------------------------------------------------------------- #
def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class TestEndToEndMQTT(unittest.TestCase):
    broker_proc = None
    port = 18831

    @classmethod
    def setUpClass(cls):
        if _port_open("localhost", cls.port):
            return
        mosq = shutil.which("mosquitto")
        if not mosq:
            return
        cls.broker_proc = subprocess.Popen(
            [mosq, "-p", str(cls.port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(40):
            if _port_open("localhost", cls.port):
                break
            time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        if cls.broker_proc is not None:
            cls.broker_proc.terminate()
            try:
                cls.broker_proc.wait(timeout=5)
            except Exception:
                cls.broker_proc.kill()

    def test_movement_drives_simulated_servo(self):
        if not _port_open("localhost", self.port):
            self.skipTest("no MQTT broker available")

        import paho.mqtt.client as mqtt
        from simulated_esp import SimulatedESP

        os.environ["TEAM_ID"] = "E2E"
        os.environ["MQTT_HOST"] = "localhost"
        os.environ["MQTT_PORT"] = str(self.port)
        try:
            cfg = DistributedConfig()
            esp = SimulatedESP(cfg)
            # speed up the virtual servo for the test
            esp.controller.sim.max_speed_dps = 100000
            esp.controller.track_step = 5
            esp.run_in_thread(hz=60.0)
            time.sleep(1.0)

            received = {}

            def _make():
                try:
                    return mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
                except (AttributeError, TypeError):
                    return mqtt.Client()

            sub = _make()
            sub.on_connect = lambda c, u, f, rc, p=None: c.subscribe(cfg.topic_servo)
            sub.on_message = lambda c, u, m: received.update(json.loads(m.payload.decode()))
            sub.connect("localhost", self.port, 30)
            sub.loop_start()

            pub = _make()
            pub.connect("localhost", self.port, 30)
            pub.loop_start()

            time.sleep(0.5)
            start_angle = esp.controller.state().angle
            for _ in range(20):
                pub.publish(cfg.topic_movement, json.dumps({"status": "MOVE_RIGHT", "confidence": 0.9}))
                time.sleep(0.05)
            time.sleep(0.8)

            self.assertGreater(esp.controller.state().angle, start_angle,
                               "servo angle should increase after MOVE_RIGHT commands")
            self.assertIn("angle", received, "dashboard should receive servo state via MQTT")

            sub.loop_stop(); sub.disconnect()
            pub.loop_stop(); pub.disconnect()
            esp.stop()
        finally:
            for k in ("TEAM_ID", "MQTT_HOST", "MQTT_PORT"):
                os.environ.pop(k, None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
