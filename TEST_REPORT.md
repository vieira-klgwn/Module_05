# TEST_REPORT.md

**System:** Distributed Vision-Control (Face-Locked Servo)
**Environment:** Linux (kali) · Python 3.13.5 (anaconda) · 2026-06-12
**Test runner:** `python -m pytest tests/ -v` (also runnable via `python tests/test_system.py`)

---

## 1. Summary

| Result | Count |
|--------|-------|
| **Passed** | **18 / 18** |
| Failed | 0 |
| Skipped | 0 (model present, broker auto-started) |

All automated tests pass, including the end-to-end MQTT round-trip that starts
a real broker, drives the simulated ESP, and confirms the virtual servo moves.

```
tests/test_system.py::TestServoSimulator::test_direction_reporting PASSED
tests/test_system.py::TestServoSimulator::test_history_recorded PASSED
tests/test_system.py::TestServoSimulator::test_jitter_deadband PASSED
tests/test_system.py::TestServoSimulator::test_limits_enforced PASSED
tests/test_system.py::TestServoSimulator::test_rate_limited_smooth_motion PASSED
tests/test_system.py::TestHAL::test_auto_falls_back_to_simulation PASSED
tests/test_system.py::TestHAL::test_movement_vocabulary PASSED
tests/test_system.py::TestHAL::test_simulation_mode_selected PASSED
tests/test_system.py::TestTracking::test_dead_zone_centered PASSED
tests/test_system.py::TestTracking::test_debounce_requires_consecutive PASSED
tests/test_system.py::TestTracking::test_move_left_right PASSED
tests/test_system.py::TestTracking::test_no_face PASSED
tests/test_system.py::TestConfig::test_topic_isolation PASSED
tests/test_system.py::TestPayload::test_movement_payload_schema PASSED
tests/test_system.py::TestMatcher::test_matcher_accepts_self_rejects_other PASSED
tests/test_system.py::TestEnrollMath::test_mean_embedding_is_unit_norm PASSED
tests/test_system.py::TestEmbedder::test_embed_dim_and_norm PASSED
tests/test_system.py::TestEndToEndMQTT::test_movement_drives_simulated_servo PASSED
============================= 18 passed in 13.59s ==============================
```

## 2. Coverage by Component

| Component | Test(s) | What is verified |
|-----------|---------|------------------|
| **Servo simulator** | `TestServoSimulator` | 0–180° limits, rate-limited smooth motion (deg/s), jitter dead-band hold, LEFT/RIGHT/HOLD direction, movement history. |
| **Hardware Abstraction Layer** | `TestHAL` | Explicit simulation mode, `auto` mode graceful fallback to simulation when no board, movement vocabulary (`MOVE_LEFT/RIGHT` change angle correctly). |
| **Face tracking** | `TestTracking` | Centre dead zone → `CENTERED`, off-centre → `MOVE_LEFT/RIGHT`, `None` → `NO_FACE`, debounce requires N consecutive frames (anti-oscillation). |
| **Config / topic isolation** | `TestConfig` | `team_id` env override, strict `vision/<team>/…` topic namespacing. |
| **MQTT payload** | `TestPayload` | Movement payload schema + JSON-serialisability. |
| **Recognition** | `TestMatcher` | ArcFace cosine matcher accepts the enrolled vector, rejects a random impostor. |
| **Enrollment maths** | `TestEnrollMath` | Mean embedding is L2-unit-norm. |
| **ArcFace embedder** | `TestEmbedder` | ONNX model loads; output is 512-D and L2-normalised. |
| **End-to-end MQTT** | `TestEndToEndMQTT` | Publish `MOVE_RIGHT` → simulated ESP → virtual servo angle **increases**; servo state is published back over MQTT. |

## 3. Manual / Integration Verification (beyond unit tests)

These were executed live during the audit and **passed**:

1. **Backend relay round-trip** — published `movement` + `servo` to MQTT; a
   WebSocket client received correctly-typed envelopes
   (`{"type":"movement",…}`, `{"type":"servo",…}`). ✅
2. **Full system via `start_demo.py`** (real webcam, headless vision):
   the live WebSocket stream delivered all message types —
   `servo`×210, `movement`×14, `frame`×14, `heartbeat`×3 over 8 s. ✅
   The vision node **recognised and locked onto the enrolled identity**
   (`recognized=true, locked=true, confidence≈0.69`), the simulated servo
   tracked (angle 98→142°), and annotated JPEG frames (~18 KB) streamed to the
   dashboard. ✅
3. **Module import sanity** — every new/edited module imports without error. ✅
4. **ArcFace + camera** — model loads (NHWC, 512-D); webcam auto-probe finds the
   device at index 0. ✅

## 4. Fixes Applied During Testing

| Issue found while testing | Fix |
|---------------------------|-----|
| `start_demo.py` lacked `--no-frames` passthrough → arg error | Added `--no-frames` flag forwarded to `demo_mode.py`. |
| `start_demo.py` children survived SIGTERM | Added SIGTERM/SIGINT handlers that run cleanup. |
| paho-mqtt 2.x deprecation warnings | Switched all clients to Callback API v2 with a v1 fallback shim. |
| websockets 16 deprecated relay handler/imports | Rewrote relay using the modern `websockets.serve` handler + `asyncio.Future()` run-forever. |
| Hardcoded, conflicting camera indices broke startup | Added `open_camera()` auto-probe used by all entry points. |
| `lock.py` silently returned on unknown identity | Restored an informative message. |

## 5. Known Environmental Notes (not failures)

- **MediaPipe `solutions` missing on Python 3.13** → pipeline auto-falls back to
  bbox-based 5-point landmarks; recognition still works (verified live). For
  best alignment use Python 3.11 + `mediapipe==0.10.21`.
- The committed `.venv` is a stale **Windows** environment; use the system
  interpreter or recreate a Linux venv with `requirements_verified.txt`.

## How to Reproduce

```bash
pip install -r requirements_verified.txt
python -m pytest tests/ -v
```
