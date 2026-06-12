# FINAL_SYSTEM_STATUS.md

**Date:** 2026-06-12  
**Environment:** Kali Linux, Python 3.13.5, `.venv` active  
**Hardware detected:** USB camera (index 2), ESP32 on `/dev/ttyUSB0` (CP2102)

---

## Final Validation Checklist

| Requirement | Status | Notes |
|-------------|--------|-------|
| ✅ Camera detected | **PASS** | Index 2, 640×480, face-aware auto-select |
| ✅ Face enrolled | **PASS** | Identity `User`, 11 samples in `data/db/face_db.npz` |
| ✅ Face recognized | **PASS** | sim≈0.98, IDENTIFIED in live test |
| ✅ Tracking works | **PASS** | CENTERED/MOVE_LEFT/MOVE_RIGHT with ±80px dead zone |
| ✅ MQTT publishing | **PASS** | `vision/Winners/movement` |
| ⚠️ ESP32 receives commands | **LIKELY** | MQTT on broker confirmed; ESP uses Wi-Fi not USB logs |
| ⚠️ Servo responds | **VERIFY ON SITE** | Watch physical camera pan during `start_exam.py` |
| ✅ Dashboard updates | **PASS** | WebSocket: movement + frame + heartbeat |

---

## Issues Found & Fixes Applied

### 1. Missing `config.json`
- **Fix:** Recreated with `team_id=Winners`, `mqtt_host=localhost`, `camera_index` auto-updated

### 2. Empty enrollment database
- **Fix:** Ran `scripts/auto_enroll.py` while user at camera → enrolled `User`

### 3. Wrong camera selected
- **Symptom:** Index 0 = black frame; index 1 = unstable V4L2 reopen; detection 0/40
- **Fix:** `src/camera_utils.py` now scores cameras by **face detection hits**, uses `CAP_V4L2`, warmup frames
- **Result:** Index 2 selected, 20/20 face hits, 40/40 detection

### 4. Pipeline test failures before fix
- **Symptom:** Recognition 0 frames, detection 0/40 on wrong camera
- **Fix:** Face-aware probe + config update
- **Result:** 14/14 tests pass

---

## Files Modified / Created

| File | Change |
|------|--------|
| `config.json` | Created; camera_index=2 |
| `src/camera_utils.py` | Face-aware probe, V4L2, warmup |
| `scripts/probe_camera.py` | Uses face-hit scoring |
| `scripts/auto_enroll.py` | **New** — automated enrollment |
| `scripts/run_pipeline_test.py` | **New** — pipeline test suite |
| `data/db/face_db.npz` | Enrolled `User` |
| `data/enroll/User/*.jpg` | 11 aligned crops |
| `PROJECT_ANALYSIS.md` | **New** |
| `PIPELINE_TEST_REPORT.md` | **New** |
| `FINAL_SYSTEM_STATUS.md` | **New** |

---

## How to Run RIGHT NOW (real exam with ESP32)

```bash
cd /home/klgwn/Documents/Module_05/face-lock-and-servo-rotating
source .venv/bin/activate

# 1. Confirm camera (sit in front of webcam)
python scripts/probe_camera.py

# 2. Re-enroll if needed
python scripts/auto_enroll.py

# 3. Run REAL hardware mode (NOT start_demo.py)
python start_exam.py --target User

# 4. Open dashboard
#    dashboard/index.html  →  WebSocket: ws://localhost:9002
```

Move your head **left** → PC publishes `MOVE_LEFT` → ESP32 MQTT → **servo pans camera left**.

---

## Remaining Risks

1. **ESP32 TEAM_ID / MQTT_HOST mismatch** — must match `config.json` and flashed firmware exactly.
2. **ESP32 on different Wi-Fi** — must reach same MQTT broker as laptop.
3. **Servo direction inverted** — set `INVERT_DIRECTION = true` in firmware and re-flash.
4. **Camera index changes** — run `python scripts/probe_camera.py` if USB replugged.
5. **MediaPipe bbox fallback** — works but lower quality than full FaceMesh on Python 3.11.
6. **Dashboard servo gauge** — may not update with real ESP (firmware doesn't publish `/servo`); watch **physical** camera instead.

---

## Quick Re-Test Command

```bash
source .venv/bin/activate
python scripts/run_pipeline_test.py
```

Expected: `14/14 passed`
