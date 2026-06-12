# PROJECT_ANALYSIS.md

**Date:** 2026-06-12  
**Scope:** Full repository read + live execution testing

---

## 1. Architecture

```
USB Camera (on servo rig)
        ↓
demo_mode.py / pc_vision_node.py
  • Haar + 5pt landmarks → align 112×112 → ArcFace ONNX embedding
  • Face lock + recognition + MovementTracker (dead zone ±80px)
  • Publishes MQTT: vision/<team_id>/movement, /frame, /heartbeat
        ↓
MQTT Broker (mosquitto :1883)
        ↓                           ↓
ESP32 (firmware)              backend/ws_relay.py
  • Subscribes /movement        • Subscribes all team topics
  • Drives physical servo       • WebSocket :9002 → dashboard
        ↓
Physical camera pans
```

**Invariant:** Browser → WebSocket → Backend only. Never MQTT in browser.

---

## 2. File Responsibilities

| File | Role |
|------|------|
| `config.json` | team_id, mqtt_host, camera_index, tracking/servo tunables |
| `src/camera_utils.py` | Auto-probe cameras 0–9; pick index with most face hits |
| `src/haar_5pt.py` | Haar detection + MediaPipe/bbox 5pt + affine alignment |
| `src/embed.py` | ArcFace ONNX embedder (512-D, auto-download) |
| `src/enroll.py` | Interactive enrollment → `data/db/face_db.npz` |
| `src/recognize.py` | Multi-face recognition + `FaceDBMatcher` |
| `src/tracking.py` | Dead zone, EMA smoothing, debounced MOVE_LEFT/RIGHT/CENTERED |
| `src/mqtt_pub.py` | MQTT publisher (movement, heartbeat, frame) |
| `demo_mode.py` | Full vision node + dashboard frame streaming |
| `start_exam.py` | **Real hardware** launcher (no simulator) |
| `start_demo.py` | Practice launcher (with simulator) |
| `simulated_esp.py` | Software ESP for laptop-only demo |
| `backend/ws_relay.py` | MQTT → WebSocket typed relay |
| `dashboard/index.html` | Live video, movement banner, servo gauge, status chips |
| `firmware/esp32_servo_controller.ino` | Real ESP32 MQTT → servo |
| `scripts/probe_camera.py` | Face-aware camera selection |
| `scripts/auto_enroll.py` | Hands-free enrollment |
| `scripts/run_pipeline_test.py` | Automated end-to-end test suite |

---

## 3. Issues Found During Live Testing

| # | Severity | Issue |
|---|----------|-------|
| I1 | **Critical** | `config.json` was missing from repo — system fell back to defaults |
| I2 | **Critical** | `data/db/face_db.npz` empty — no enrolled users |
| I3 | **High** | Camera auto-select picked wrong index (resolution-based); index 0=black, index 2=face |
| I4 | **High** | `open_camera()` reopened unstable V4L2 nodes (`ioctl Bad file descriptor` on index 1) |
| I5 | **Medium** | MediaPipe 0.10.32 on Python 3.13 has no `mp.solutions` — bbox fallback used |
| I6 | **Medium** | ESP32 serial `/dev/ttyUSB0` opens but prints no debug lines (MQTT is over Wi-Fi, not USB) |
| I7 | **Low** | Real ESP firmware does not publish servo angle back to `vision/<team>/servo` |

---

## 4. Missing Pieces (before this session)

- Face-aware camera probing (fixed in `camera_utils.py`)
- Automated enrollment script (added `scripts/auto_enroll.py`)
- Automated pipeline test runner (added `scripts/run_pipeline_test.py`)
- `config.json` in working tree (recreated)

---

## 5. What Works After Fixes

| Stage | Status |
|-------|--------|
| Python venv + dependencies | ✅ |
| Camera index 2 @ 640×480 | ✅ 20/20 face hits |
| Enrollment `User` | ✅ 11 samples, 512-D embedding |
| Face detection | ✅ 40/40 frames |
| Recognition | ✅ IDENTIFIED User, sim≈0.98 |
| Tracking | ✅ CENTERED at cx≈320, dead zone 80px |
| MQTT publish | ✅ `vision/Winners/movement` |
| WebSocket dashboard | ✅ movement + frame + heartbeat |
| ESP32 USB port | ✅ `/dev/ttyUSB0` CP2102 detected |
| ESP32 MQTT receive | ⚠️ Must verify physically (servo moves); serial silent |
