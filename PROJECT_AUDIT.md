# PROJECT_AUDIT.md

**Project:** Distributed Vision-Control System (Face-Locked Servo)
**Audited:** 2026-06-12
**Auditor role:** Robotics / Computer-Vision / Embedded / MQTT / QA Engineer

---

## 1. Folder Structure (as audited, before changes)

```
face-lock-and-servo-rotating/
├── arduino/
│   └── esp8266_servo/
│       └── esp8266_servo.ino        # ESP8266 firmware (Wi-Fi + MQTT + Servo)
├── backend/
│   ├── mosquitto.conf               # Broker config (anonymous allowed)
│   └── ws_relay.py                  # MQTT -> WebSocket relay for browser
├── dashboard/
│   └── index.html                   # Minimal browser dashboard (WS client)
├── data/
│   ├── db/
│   │   ├── face_db.npz              # Enrolled identity embeddings (name -> 512d)
│   │   └── face_db.json             # Enrollment metadata
│   ├── enroll/Vieira/*.jpg          # 66 aligned 112x112 enrollment crops
│   └── lock_history/*.txt           # Recorded lock action timelines
├── models/
│   └── embedder_arcface.onnx        # ArcFace ONNX embedder (~137 MB, NHWC, 512d)
├── src/
│   ├── __init__.py
│   ├── camera.py                    # Webcam smoke test
│   ├── detect.py                    # Haar face detection demo
│   ├── landmarks.py                 # Haar + FaceMesh 5pt demo
│   ├── align.py                     # 5pt alignment demo
│   ├── haar_5pt.py                  # Detector: Haar + FaceMesh(or bbox) 5pt + alignment
│   ├── embed.py                     # ArcFace ONNX embedder (+ auto-download)
│   ├── enroll.py                    # Enrollment tool (capture -> embeddings -> DB)
│   ├── recognize.py                 # Multi-face recognition + DB matcher
│   ├── evaluate.py                  # Threshold/FAR-FRR evaluation
│   ├── lock.py                      # Face-lock + action detection + history
│   ├── distributed_config.py        # Shared config (env-driven)
│   ├── mqtt_pub.py                  # MQTT publisher (movement / heartbeat)
│   └── pc_vision_node.py            # PC vision node: lock -> movement -> MQTT
├── docker-compose.yml               # Mosquitto broker container
├── init_project.py                  # Scaffolding helper
├── readSerial.py                    # Serial monitor for ESP
├── readTopic.py                     # MQTT topic subscriber (debug)
├── fix_push_no_large_file.ps1       # Git helper (Windows)
├── requirements.txt
└── Readme.md
```

## 2. Architecture (as designed in the original repo)

```
PC Vision Node ── MQTT(publish movement) ─┐
                                          ▼
                                    MQTT Broker (1883)
                                    ┌──────┴───────┐
                              (subscribe)      (subscribe)
                                    ▼               ▼
                              ESP8266/Servo     Backend Relay
                                                    │ WebSocket(9002)
                                                    ▼
                                              Browser Dashboard
```

The intended data flow is correct and matches the assignment:
`PC → MQTT → ESP → Servo` and `MQTT → Backend → WebSocket → Browser`.
The browser never touches MQTT directly. **This separation is preserved in all fixes.**

## 3. Purpose of Every File
See section 1 inline comments. All `src/*` modules form a CPU-friendly pipeline:
Haar detection → 5-point landmarks (MediaPipe FaceMesh, else bbox fallback) →
affine alignment to 112×112 → ArcFace ONNX embedding → cosine-similarity matching.

## 4. Detected Bugs

| # | Severity | Location | Bug |
|---|----------|----------|-----|
| B1 | High | `src/*` | **Hardcoded, inconsistent camera indices** (`VideoCapture(0/1/2)`). Demo breaks on machines where that index is absent. |
| B2 | High | env | **`.venv` is a Windows venv** (`Lib/Scripts`, no `bin/`) committed/left on a Linux box → unusable; real interpreter is anaconda py3.13. |
| B3 | High | `haar_5pt.py`, `recognize.py` | **MediaPipe 0.10.32 on Python 3.13 has no `mp.solutions`** → silently falls back to coarse bbox-based 5pt. Functional but lower alignment quality; never surfaced to the user. |
| B4 | Med | `mqtt_pub.py`, `ws_relay.py`, `readTopic.py` | **paho-mqtt 2.x deprecation**: uses Callback API v1 implicitly. Works now but emits warnings; brittle for future. |
| B5 | Med | `ws_relay.py` | **No MQTT reconnection** (`loop_start` once, no `reconnect`/`on_disconnect`). Broker restart kills the relay silently. |
| B6 | Med | `mqtt_pub.py` | **No reconnect / no `on_disconnect`**; publisher dies on broker blip. Connect timeout hard-raises. |
| B7 | Med | `pc_vision_node.py` | **Movement uses static frame-fraction thresholds (0.40/0.60)**, no dead zone tuning, prone to oscillation near boundary; no smoothing/hysteresis. |
| B8 | Med | `pc_vision_node.py:96` | Camera **hardcoded to index 2**; `enroll.py` index 2; `lock.py` index 0; `recognize/embed/align/landmarks` index 1 → chaos. |
| B9 | Low | `lock.py:181` | Unknown-identity branch silently `return`s with the error print commented out → confusing UX. |
| B10 | Low | `evaluate.py:187` | Mismatched markdown header `"--- Threshold Sweep ==="`. Cosmetic. |
| B11 | Low | `ws_relay.py` | `asyncio.Future()` created without explicit loop; fragile on some Python versions. |
| B12 | Med | firmware | `esp8266_servo.ino` has **hardcoded Wi-Fi SSID/PASS and VPS IP** committed in source (secret leak) and `TEAM_ID="Winners"` while `distributed_config` defaults to `"team01"` → **topic mismatch**. |

## 5. Missing Features (required by assignment / task)

- **No Hardware Abstraction Layer** (ESP8266 / ESP32 / SIMULATION switching).
- **No servo simulator** (virtual servo, smooth motion, limits, history, jitter prevention).
- **No simulated ESP device** (subscribe MQTT, drive virtual servo).
- **No ESP32 firmware** (only ESP8266 present).
- **No professional dashboard** (current one is a plain text panel; no gauge, no live video, no statuses).
- **No demo mode / startup orchestrator** to run the whole system hardware-free.
- **No automated tests / TEST_REPORT.**
- **No central settings file** for `team_id`.
- **No servo-state feedback channel** to the dashboard.

## 6. Broken / Risky Dependencies

- `requirements.txt` is unpinned and omits `pyserial` (used by `readSerial.py`), `fastapi`/`uvicorn` (listed in task), and pins nothing.
- `mediapipe>=0.10.21` resolves to 0.10.32 which **lacks `solutions` on py3.13** (silent degrade).
- `numpy 2.1.3` OK with onnxruntime 1.23.2 (verified embedding works).

## 7. Security Issues

- **Wi-Fi credentials and broker IP hardcoded** in `esp8266_servo.ino` and `readTopic.py` / `readSerial.py`. Should be parameterized; never commit real secrets.
- Broker `allow_anonymous true` — acceptable for a local lab demo only; document it.
- No topic ACLs / auth — fine for offline demo, risky on a public VPS.

## 8. Performance Issues

- `recognize.py` / `lock.py` run ArcFace embedding on **every** detected face every frame (CPU heavy). For locked tracking, only the target needs embedding once locked → optimization opportunity.
- No frame downscaling before Haar; large frames slow detection.
- No FPS cap / publish rate is bounded (good) but heartbeat & movement both publish.

## 9. Recommended Fixes (implemented in this pass)

1. Add `hardware/` HAL: `servo_interface.py` (auto ESP8266 / ESP32 / SIMULATION) + `servo_simulator.py`.
2. Add `simulated_esp.py` (MQTT-subscribed virtual ESP driving the simulator + publishing servo state).
3. Rewrite `dashboard/index.html` as a modern robotics control panel (gauge, statuses, live annotated video, movement indicators).
4. Harden `backend/ws_relay.py`: reconnection, multi-topic relay, typed messages, paho v2 API.
5. Harden `mqtt_pub.py`: reconnect, paho v2 API, safe publish.
6. Add dead-zone + hysteresis + smoothing to movement logic; resolve camera-index chaos with a shared config + auto-probe.
7. Add `firmware/esp32_servo_controller.ino` and a cleaned `esp8266_servo_controller.ino` (secrets parameterized, team_id unified, shared JSON payload).
8. Add `demo_mode.py` (rich integrated vision UI + MQTT) and `start_demo.py` (one-command orchestrator: broker + relay + ESP sim + dashboard + vision).
9. Add automated tests (`tests/`) + `TEST_REPORT.md`.
10. Add central `settings.py` + `config.json` for `team_id` and tunables; unify default `team_id`.
11. Generate `requirements_verified.txt` (pinned, validated on this machine).

> No existing, working module behavior is removed — all original entry points (`src.enroll`, `src.recognize`, `src.lock`, `src.pc_vision_node`) keep working; new capabilities are additive.
