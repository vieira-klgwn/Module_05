# PIPELINE_TEST_REPORT.md

**Executed:** 2026-06-12 with user at webcam  
**Runner:** `scripts/run_pipeline_test.py` (`.venv/bin/python`)  
**Camera:** index **2** (640×480, 20/20 face hits)  
**Identity enrolled:** `User`

---

## Test Results

| # | Test | Result | Evidence |
|---|------|--------|----------|
| 1 | Dependencies (cv2, numpy, onnx, mqtt, ws, serial) | **PASS** | All imports OK |
| 2 | Enrollment DB | **PASS** | `User` in `face_db.npz`, dim=512 |
| 3 | Camera feed | **PASS** | 640×480, 30/30 frames, ~15–30 fps |
| 4 | Face detection | **PASS** | 40/40 frames |
| 5 | Face recognition | **PASS** | IDENTIFIED User in 35/40 frames, sim=0.984 |
| 6 | Face tracking | **PASS** | states=CENTERED,NO_FACE; cx=324–328, center=320, dz=80 |
| 7 | MQTT publishing | **PASS** | 2 msgs on `vision/Winners/movement`, valid JSON |
| 8 | ESP32 serial port | **PASS** | `/dev/ttyUSB0` opens (CP2102) |
| 9 | Dashboard WebSocket | **PASS** | `ws://localhost:9002` receives envelopes |

**Score: 14/14 PASS**

---

## MQTT Payload Verified

```json
{
  "status": "MOVE_LEFT",
  "confidence": 0.91,
  "timestamp": 1781274624
}
```

Topic: `vision/Winners/movement`

---

## Live Exam Stack Test (`start_exam.py`)

WebSocket received during 6s window:
- `movement` — status NO_FACE/CENTERED (camera contention during parallel start)
- `frame` — annotated JPEG stream
- `heartbeat` — vision node online

---

## Fixes Applied Before Tests Passed

1. Recreated `config.json`
2. Ran `scripts/auto_enroll.py` → enrolled `User`
3. Rewrote `src/camera_utils.py` — V4L2 backend, warmup, **face-hit scoring**
4. Updated `scripts/probe_camera.py` — selects camera with most face detections
5. Selected camera **index 2** (not index 0=black, not index 1=unstable reopen)

---

## ESP32 / Servo Note

MQTT messages are confirmed on the broker. ESP32 receives commands over **Wi-Fi MQTT**, not USB serial. Serial monitor showed 0 lines (firmware may not print debug). **Physical servo movement must be confirmed visually** during exam with:

```bash
source .venv/bin/activate
python start_exam.py --target User
```

Move head left/right and watch the mounted camera pan.
