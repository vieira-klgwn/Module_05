# ARCHITECTURE.md

**Distributed Vision-Control System — Face-Locked Servo**

This document describes the system architecture and how the hardware-free
simulation layer maps onto the real distributed deployment.

---

## 1. High-Level Architecture

```
                         ┌───────────────────────────────────────────────┐
                         │                MQTT  BROKER                     │
                         │              (mosquitto :1883)                  │
                         │   topics:  vision/<team_id>/movement            │
                         │            vision/<team_id>/servo               │
                         │            vision/<team_id>/heartbeat           │
                         │            vision/<team_id>/frame               │
                         └───────────────────────────────────────────────┘
                              ▲                 │                 │
              publish movement│        subscribe│        subscribe│
                              │         movement │         all     │
          ┌───────────────────┴──┐   ┌──────────┴───────┐   ┌─────┴──────────────┐
          │   PC VISION NODE      │   │ ESP8266 / ESP32   │   │  BACKEND RELAY      │
          │ (demo_mode.py /       │   │  (firmware/*.ino) │   │ (backend/ws_relay)  │
          │  pc_vision_node.py)   │   │       OR          │   │                     │
          │                       │   │ simulated_esp.py  │   │  MQTT subscriber    │
          │ camera → detect →     │   │   → virtual servo │   │       │             │
          │ ArcFace recognize →   │   │   (HAL + sim)     │   │   WebSocket :9002   │
          │ lock → dead-zone      │   │   → publish servo │   │       ▼             │
          │ movement decision     │   │     state         │   └─────────────────────┘
          └───────────────────────┘   └───────────────────┘            │
                                                                        ▼
                                                            ┌───────────────────────┐
                                                            │   BROWSER DASHBOARD    │
                                                            │  dashboard/index.html  │
                                                            │  gauge · video · state │
                                                            └───────────────────────┘
```

**Invariants (enforced):**

- The **PC vision node** talks *only* to MQTT — never to the ESP or the browser.
- The **browser** talks *only* to the backend WebSocket — never to MQTT.
- All topics are namespaced `vision/<team_id>/…` for strict per-team isolation.

## 2. Data Flow (one tracking cycle)

1. **Capture** — `demo_mode.py` grabs a webcam frame (`camera_utils.open_camera`).
2. **Detect** — Haar cascade finds faces; 5-point landmarks via MediaPipe
  FaceMesh (or a bbox fallback on Python 3.13).
3. **Align + Embed** — affine-align to 112×112, ArcFace ONNX → 512-D L2-normalised embedding.
4. **Recognize** — cosine match against `data/db/face_db.npz` → `IDENTIFIED <name>` / `UNKNOWN FACE`.
5. **Lock** — if the target identity is confidently recognised, lock onto it and
  follow ONLY that face (`TARGET LOCKED`); tolerate brief misses for `LOCK_RELEASE_SEC`.
6. **Decide** — `MovementTracker` applies a centre **dead zone (±80 px)** + hysteresis
  - EMA smoothing + N-frame debounce → `MOVE_LEFT | MOVE_RIGHT | CENTERED | NO_FACE`.
7. **Publish** — movement JSON to `vision/<team>/movement`; annotated JPEG to `…/frame`.
8. **Actuate** — the ESP (real or `simulated_esp.py`) consumes movement and drives
  the servo through the **HAL** (`hardware/`): left↓ / right↑ angle, smooth & jitter-free.
9. **Feedback** — the ESP publishes servo state to `…/servo`.
10. **Relay** — the backend wraps every message in a typed envelope and pushes it
  to all dashboard clients over WebSocket.
11. **Render** — the dashboard animates the servo gauge, shows the live video,
  face ID, confidence, recognition/MQTT/ESP/backend status and movement banner.

## 3. Hardware Abstraction Layer (`hardware/`)


| Mode                | Backend                               | Selected when                                    |
| ------------------- | ------------------------------------- | ------------------------------------------------ |
| `ESP8266` / `ESP32` | JSON over USB serial to a wired board | a board is detected on a serial port             |
| `SIMULATION`        | in-process `ServoSimulator`           | no board reachable (default for the laptop demo) |


`ServoController.apply_movement(status)` is the single API used everywhere; the
caller never needs to know which backend is active. `mode="auto"` probes for a
board and **gracefully falls back to simulation**.

The `**ServoSimulator`** models a real servo: 0–180° clamping, deg/s
rate-limited smooth motion, a jitter dead-band, direction reporting and a bounded
movement history.

## 4. Message Schemas

**Movement** (`vision/<team>/movement`)

```json
{ "status": "MOVE_LEFT", "confidence": 0.87, "timestamp": 1730000000,
  "identity": "Vieira", "recognized": true, "locked": true, "faces": 1 }
```

**Servo state** (`vision/<team>/servo`)

```json
{ "angle": 122.0, "target": 122.0, "moving": true, "direction": "RIGHT",
  "min_angle": 0.0, "max_angle": 180.0, "board": "esp8266", "sim": true,
  "last_command": "MOVE_RIGHT", "timestamp": 1730000000 }
```

**Heartbeat** (`vision/<team>/heartbeat`) · **Frame** (`vision/<team>/frame`, base64 JPEG)

The backend re-emits each as `{ "type": "<movement|servo|heartbeat|frame>", …payload }`.

## 5. Components & Files


| Layer           | File(s)                                                                                                                         |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Config          | `config.json`, `src/distributed_config.py`                                                                                      |
| Vision pipeline | `src/haar_5pt.py`, `src/embed.py`, `src/recognize.py`, `src/enroll.py`, `src/lock.py`, `src/tracking.py`, `src/camera_utils.py` |
| MQTT            | `src/mqtt_pub.py`                                                                                                               |
| PC node         | `src/pc_vision_node.py`, `demo_mode.py`                                                                                         |
| HAL / Simulator | `hardware/servo_interface.py`, `hardware/servo_simulator.py`                                                                    |
| Simulated ESP   | `simulated_esp.py`                                                                                                              |
| Real firmware   | `firmware/esp8266_servo_controller.ino`, `firmware/esp32_servo_controller.ino`                                                  |
| Backend         | `backend/ws_relay.py`, `backend/mosquitto.conf`, `docker-compose.yml`                                                           |
| Dashboard       | `dashboard/index.html`                                                                                                          |
| Orchestration   | `start_demo.py`                                                                                                                 |
| Tests           | `tests/test_system.py`                                                                                                          |


## 6. Configuration

All tunables live in `config.json` (overridable by env vars):
`team_id`, broker host/port, WS host/port, camera index, tracking dead-zone &
smoothing, and servo limits/speed/steps. `team_id` defaults to `**Winners`** to
match the firmware; change it in one place to re-namespace the whole system.

## 7. Real-Hardware Deployment (when boards are available)

1. Flash `firmware/esp8266_servo_controller.ino` (or the ESP32 variant); set
  Wi-Fi creds, broker IP, and the same `TEAM_ID`.
2. Run the broker + `backend/ws_relay.py` on a reachable host/VPS.
3. Run `python -m src.pc_vision_node` on the PC.
4. Open `dashboard/index.html`, point it at `ws://<host>:9002`.

The Python `simulated_esp.py` is a drop-in replacement for the board — the rest
of the system is identical, which is exactly why the demo is faithful.