# Exam Guide — Face-Locked Servo Project

**How to configure, run, and demonstrate this project during the exam.**

---

## READ THIS FIRST — Real exam vs practice at home

| | **REAL EXAM** (examiners give you hardware) | **PRACTICE AT HOME** (no hardware) |
|---|---------------------------------------------|-------------------------------------|
| What you have | Real ESP + real servo + camera on rig | Laptop + webcam only |
| What moves | **Physical camera pans left/right** | Virtual gauge on dashboard |
| Command to run | **`python start_exam.py`** | `python start_demo.py` |
| Do **NOT** run | `simulated_esp.py`, `start_demo.py` | — |

**On exam day you want the REAL camera on the servo to move while your face is locked.**  
Use **`start_exam.py`**, not `start_demo.py`.

---

## 1. What the system does (plain words)

1. The **USB camera** (mounted on the servo) sends video to your **laptop**.
2. The PC **detects your face**, **recognises** you, and **locks** onto you.
3. If your face is left/right of centre → PC sends `MOVE_LEFT` or `MOVE_RIGHT` over **MQTT**.
4. The **real ESP board** receives MQTT and drives the **real servo**.
5. The **physical camera** turns to follow your face.
6. The **dashboard** (optional) shows live video and status via WebSocket.

```
Your face
    ↓
USB camera (on servo) → Laptop
    ↓
demo_mode.py  →  MQTT  vision/<team_id>/movement
    ↓
REAL ESP8266/ESP32  →  REAL SERVO  →  CAMERA MOVES PHYSICALLY
    ↓
backend/ws_relay.py  →  WebSocket  →  dashboard (monitoring)
```

**Assignment rule:** the browser never talks to MQTT. It only uses WebSocket through the backend.

---

## 2. REAL EXAM — step by step (physical hardware)

### 2.1 What examiners will give you

Write these down before editing anything:

| Item | Example | Where to put it |
|------|---------|-----------------|
| **Team ID** | `team01`, `Winners` | `config.json` + ESP firmware |
| **MQTT broker IP** | `157.173.101.159` | `config.json` + ESP firmware |
| **MQTT port** | `1883` | `config.json` + ESP firmware |
| **Wi-Fi SSID + password** | exam network | ESP firmware only |
| **ESP8266 or ESP32** | board + USB cable | flash firmware |
| **Servo + camera rig** | mounted together | wire servo to ESP |

Everyone on your team must use the **same `team_id`**.

MQTT topics (never use generic topics):
```
vision/<team_id>/movement
vision/<team_id>/heartbeat
vision/<team_id>/frame
vision/<team_id>/servo
```

---

### 2.2 Before the exam — flash the ESP (once)

1. Open Arduino IDE.
2. Open **`firmware/esp8266_servo_controller.ino`** (or **`firmware/esp32_servo_controller.ino`** for ESP32).
3. Edit the top of the file:

```cpp
static const char* WIFI_SSID = "ExamWiFiName";
static const char* WIFI_PASS = "ExamPassword";
static const char* MQTT_HOST = "157.173.101.159";   // broker IP from examiners
static const uint16_t MQTT_PORT = 1883;
static const char* TEAM_ID   = "team01";              // YOUR team — same as config.json
```

4. Install libraries: **PubSubClient**, **ArduinoJson**, **ESP32Servo** (ESP32 only).
5. Flash to the board.
6. Wiring:
   - **ESP8266:** servo signal → **D4** (GPIO2)
   - **ESP32:** servo signal → **GPIO 18**
   - Servo power: **5V supply** (do not power a large servo only from the ESP pin).

---

### 2.3 Before the exam — edit `config.json` on your laptop

Open **`config.json`** in the project root:

```json
{
  "team_id": "team01",
  "mqtt_host": "157.173.101.159",
  "mqtt_port": 1883,
  "camera_index": "auto"
}
```

`team_id` and `mqtt_host` **must match** the ESP firmware.

---

### 2.4 Before the exam — enroll your face (once)

```bash
cd /home/klgwn/Documents/Module_05/face-lock-and-servo-rotating
source .venv/bin/activate
python -m src.enroll
```

- Type your name when asked.
- Press **SPACE** ~15 times (slightly different angles).
- Press **s** to save, **q** to quit.

Creates `data/db/face_db.npz`.

---

### 2.5 Exam day — physical setup

1. Mount **camera on servo** (as provided).
2. Plug camera **USB into your laptop**.
3. Power **ESP** and **servo**.
4. ESP must join **exam Wi-Fi** and reach the **MQTT broker**.

---

### 2.6 Exam day — run on your laptop

```bash
cd /home/klgwn/Documents/Module_05/face-lock-and-servo-rotating
source .venv/bin/activate
python start_exam.py --target YourName
```

**`start_exam.py` starts:**
- MQTT broker (if local and not running)
- Backend WebSocket relay
- Vision node (`demo_mode.py`) — reads camera, locks face, publishes movement
- Opens dashboard in browser

**`start_exam.py` does NOT start:**
- `simulated_esp.py` ← the real ESP does this job

If the broker is only on the school VPS (not your laptop):

```bash
python start_exam.py --target YourName --no-broker
```

Stop everything: **Ctrl+C**.

---

### 2.7 What to show examiners

1. Sit in front of the **mounted camera**.
2. System recognises and locks your face.
3. Move head **left** → **physical camera/servo turns left**.
4. Move head **right** → **camera turns right**.
5. Centre your face → servo **holds still** (`CENTERED`).
6. Step away → `NO_FACE` (servo may sweep to search).
7. Explain: *"PC publishes movement to MQTT; ESP drives the servo; browser uses WebSocket only."*

**The proof is physical camera movement — not the virtual gauge.**

---

### 2.8 If camera moves the wrong way

In **`firmware/esp8266_servo_controller.ino`** (or ESP32 version):

```cpp
static const bool INVERT_DIRECTION = true;   // flip left/right
static const int TRACK_STEP = 4;             // faster steps if too slow
```

Re-flash the ESP.

---

### 2.9 Manual start (if examiner wants each part shown)

**Terminal 1 — backend:**
```bash
source .venv/bin/activate
TEAM_ID=team01 MQTT_HOST=157.173.101.159 python backend/ws_relay.py
```

**Terminal 2 — vision:**
```bash
source .venv/bin/activate
TEAM_ID=team01 MQTT_HOST=157.173.101.159 python demo_mode.py --target YourName
```

**ESP:** already running from flashed firmware (no Python on the board).

**Do not run:** `simulated_esp.py` or `start_demo.py`.

---

### 2.10 Real exam checklist

- [ ] ESP flashed: Wi-Fi, MQTT_HOST, TEAM_ID correct
- [ ] `config.json`: same team_id and mqtt_host
- [ ] Camera USB plugged into laptop
- [ ] Servo wired (D4 / GPIO18) and powered
- [ ] Face enrolled
- [ ] Run **`python start_exam.py --target YourName`**
- [ ] **Do not** run `simulated_esp.py`
- [ ] Confirm **real camera** pans when you move your head

---

## 3. PRACTICE AT HOME — simulation (no hardware)

Use this only when you **do not** have ESP/servo. **Not for the real exam.**

```bash
source .venv/bin/activate
python start_demo.py --target YourName
```

This starts `simulated_esp.py` and a **virtual** servo on the dashboard.

| Real exam | Practice at home |
|-----------|------------------|
| `start_exam.py` | `start_demo.py` |
| Physical servo moves | Virtual gauge moves |
| No `simulated_esp.py` | `simulated_esp.py` runs |

---

## 4. How to view VIDEO in the dashboard

### Where the video appears

1. Run `start_exam.py` (or `start_demo.py` at home).
2. Browser opens **Face-Locked Servo · Control Dashboard**.
3. **Left panel: "Live Vision Feed"** shows your camera with face box and name.
4. Bottom banner: CENTERED / SERVO MOVING LEFT / SERVO MOVING RIGHT / NO FACE.

### If you see "Waiting for vision node stream…"

- Vision node not running → run `start_exam.py`.
- Backend disconnected → set WebSocket to **`ws://localhost:9002`**.
- Top-right **BACKEND** chip must be **green**.

### How video reaches the dashboard

```
demo_mode.py  →  MQTT vision/<team>/frame  →  backend/ws_relay.py  →  WebSocket  →  dashboard
```

The browser does **not** open the webcam itself.

### WebSocket URL

| Backend on same laptop | `ws://localhost:9002` |
| Backend on school VPS | `ws://<VPS_IP>:9002` |

### Open dashboard manually

```bash
xdg-open dashboard/index.html
```

### Dashboard during REAL exam

| Panel | Works? |
|-------|--------|
| Live video (left) | Yes — from mounted USB camera |
| Movement banner | Yes — from vision node |
| Face ID / confidence | Yes |
| Servo gauge (right) | May not update — real ESP does not publish angle back. **Watch the physical camera.** |

---

## 5. `config.json` reference

```json
{
  "team_id": "team01",
  "mqtt_host": "157.173.101.159",
  "mqtt_port": 1883,
  "camera_index": "auto",

  "tracking": {
    "dead_zone_px": 80,
    "smoothing_alpha": 0.6,
    "publish_hz": 12.0
  },

  "servo": {
    "invert_direction": false
  }
}
```

| Setting | Purpose |
|---------|---------|
| `team_id` | MQTT topic namespace — must match ESP |
| `mqtt_host` | Broker IP (VPS or `localhost`) |
| `camera_index` | `"auto"` or `0` / `1` if webcam not found |
| `dead_zone_px` | Centre zone where status = CENTERED (default 80 px) |

Environment override (temporary):
```bash
TEAM_ID=team01 MQTT_HOST=157.173.101.159 python start_exam.py
```

---

## 6. Troubleshooting

| Problem | Fix |
|---------|-----|
| `pip` / Python 2.7 errors | `source .venv/bin/activate` first |
| Servo does not move | ESP powered? Same Wi-Fi? Same team_id? MQTT broker reachable? |
| Wrong left/right | `INVERT_DIRECTION = true` in firmware, re-flash |
| UNKNOWN FACE | `python -m src.enroll`, then `--target YourName` |
| No video in dashboard | Run `start_exam.py`; WebSocket = `ws://localhost:9002` |
| Running simulation by mistake | Use **`start_exam.py`**, not `start_demo.py` |
| Camera not found | Set `"camera_index": "0"` or `"1"` in config.json |

### Verify before exam

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

---

## 7. File cheat sheet

| File | Real exam | Practice at home |
|------|-----------|------------------|
| **`start_exam.py`** | **USE THIS** | — |
| `start_demo.py` | Do not use | Use this |
| `config.json` | Edit team_id, mqtt_host | Same |
| `firmware/*.ino` | Flash to ESP | Not needed |
| `demo_mode.py` | Vision + MQTT (auto via start_exam) | Same |
| `simulated_esp.py` | **Do not run** | Auto via start_demo |
| `backend/ws_relay.py` | Auto via start_exam | Same |
| `dashboard/index.html` | Browser monitoring | Same |
| `src/enroll.py` | Enroll face once | Same |

---

## 8. Minimum commands — REAL EXAM (copy-paste)

```bash
cd /home/klgwn/Documents/Module_05/face-lock-and-servo-rotating
source .venv/bin/activate

# 1. Edit config.json (team_id, mqtt_host from examiners)
# 2. ESP already flashed with same Wi-Fi, MQTT_HOST, TEAM_ID
# 3. Camera USB plugged in, servo powered

python start_exam.py --target YourName

# Watch PHYSICAL camera move when you move your head.
# Dashboard video: left panel "Live Vision Feed"
# WebSocket: ws://localhost:9002
```
