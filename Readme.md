# Edge ArcFace Face Recognition with 5-Point Alignment

A lightweight, real-time face recognition pipeline optimized for embedded and edge systems (Jetson, Raspberry Pi, edge PCs). It combines classical computer vision with deep learning: Haar Cascade for fast face detection, MediaPipe FaceMesh for 5-point landmark extraction, a 5-point affine alignment to a canonical 112×112 pose, and an ArcFace ONNX embedder to produce identity-preserving embeddings.

This repository focuses on accuracy and efficiency for constrained hardware while keeping the pipeline modular and easy to extend.

---

## Table of Contents

- [Project Overview](#project-overview)
- [Key Features](#key-features)
- [Why 5-Point Alignment?](#why-5-point-alignment)
- [System Architecture](#system-architecture)
- [Project Structure](#project-structure)
- [Core Components](#core-components)
  - [Face Detection (Haar Cascade)](#face-detection-haar-cascade)
  - [Facial Landmark Detection (MediaPipe FaceMesh)](#facial-landmark-detection-mediapipe-facemesh)
  - [5-Point Face Alignment](#5-point-face-alignment)
  - [ArcFace Embedding (ONNX Runtime)](#arcface-embedding-onnx-runtime)
  - [L2 Normalization & Similarity](#l2-normalization--similarity)
- [Visualization & Demo Features](#visualization--demo-features)
- [Face Locking (Behavior Tracking)](#face-locking-behavior-tracking)
- [Requirements](#requirements)
- [Installation & Run](#installation--run)
- [Usage / Controls](#usage--controls)
- [Target Use Cases](#target-use-cases)
- [Roadmap / Future Improvements](#roadmap--future-improvements)
- [License](#license)
- [Acknowledgments](#acknowledgments)
- [Contact / Next Steps](#contact--next-steps)

---

## Project Overview

The pipeline (real-time) performs:

1. Capture frames from a camera
2. Detect faces with Haar Cascade
3. Extract 5 facial landmarks using MediaPipe FaceMesh
4. Align face to canonical pose (112×112)
5. Generate ArcFace embeddings via an ONNX model
6. L2-normalize embeddings
7. Compute cosine similarity between embeddings and visualize results

Designed for:
- Low compute budgets
- Modular experimentation
- Educational clarity

---

## Key Features

- Real-time face detection + embedding extraction
- 5-point landmark-based affine alignment for stable embeddings
- ArcFace embedding using ONNX Runtime for portability
- Lightweight detection (Haar) suitable for edge devices
- Embedding heatmap and similarity visualization for debugging

---

## Why 5-Point Alignment?

ArcFace and similar models expect consistently aligned, frontal faces. Using 5 landmarks (left eye, right eye, nose, left mouth corner, right mouth corner) allows us to:

- Reduce pose variation
- Normalize scale and rotation
- Improve embedding stability and recognition accuracy
- Keep computation minimal (important for embedded devices)

---

## System Architecture

Camera Frame  
↓  
Haar Face Detection  
↓  
MediaPipe FaceMesh (5-point extraction)  
↓  
5-Point Face Alignment (Affine Transform → 112×112)  
↓  
ArcFace ONNX Embedding (embedder_arcface.onnx)  
↓  
L2 Normalization  
↓  
Cosine Similarity + Visualization

---

## Project Structure

ArcFace-based Face Recognition with 5-Point Facial Alignment/
│
├── src/
│   ├── __init__.py
│   ├── embed.py          # Main pipeline (camera → embedding)
│   └── haar_5pt.py       # Haar detection + 5-point extraction & alignment
│
├── models/
│   └── embedder_arcface.onnx
│
├── requirements.txt
└── README.md

---

## Core Components

### Face Detection (Haar Cascade)
- Fast, classical detector (OpenCV)
- Provides a rough bounding box for where to run the landmark detector
- Low computational cost — ideal for real-time performance on edge devices

### Facial Landmark Detection (MediaPipe FaceMesh)
- High-precision landmark detector
- From the full mesh only 5 key points are extracted
- Provides stable landmark positions even with small head movements

### 5-Point Face Alignment
- Affine transformation that maps detected landmarks to a fixed template
- Produces 112×112 aligned RGB face images required by ArcFace
- Normalizes pose, scale, and rotation

### ArcFace Embedding (ONNX Runtime)
- Pretrained ArcFace model loaded via ONNX Runtime
- Input: aligned 112×112 RGB face
- Output: embedding vector (identity-preserving, discriminative)

### L2 Normalization & Similarity
- Embeddings are L2-normalized to unit length
- Cosine similarity computed as dot(embedding_1, embedding_2)
  - Values near 1.0 suggest the same identity
  - Lower values suggest different identities

---

## Visualization & Demo Features

The demo includes:
- Live face bounding box
- 5-point landmark overlay
- Real-time aligned face preview (112×112)
- Embedding heatmap visualization
- FPS counter and real-time similarity display between consecutive frames

These make the system both educational and debuggable.

---

## Face Locking (Behavior Tracking)

On top of basic recognition, this project implements a **Face Locking** behavior (see `src/lock.py`) as described in the Term‑02 Week‑04 assignment:

- **Manual selection of identity**
  - You first enroll one or more identities using `src.enroll`.
  - Then you choose exactly **one** enrolled identity (e.g. `Alice`) to lock onto when running `src.lock`.

- **Face locking & stable tracking**
  - When the selected identity appears and is **confidently recognized**, the system:
    - Locks onto that face (no jumping to other faces).
    - Keeps tracking the **same person** across frames, even if recognition briefly fails.
  - The lock is only released if the face has not been seen for a configurable time window.

- **Actions detected while locked**
  - **Face moved left** / **face moved right**  
    - Based on horizontal motion of the 5-point landmarks over time.
  - **Eye blink**  
    - Detected as a brief drop in the eye‑to‑nose distance ratio.
  - **Smile / laugh (simple heuristic)**  
    - Detected when the mouth‑width to eye‑distance ratio rises above a smoothed baseline.
  - All logic is intentionally simple and explainable, and runs on CPU only.

- **Action history recording**
  - While the face is locked, the system writes a timeline of actions to `data/lock_history/`.
  - File naming strictly follows the required format:
    - `<face>_history_<timestamp>.txt` (e.g. `gabi_history_20260129112099.txt`)
  - Each line of the history file has:
    - **timestamp** (local time)
    - **action type** (e.g. `moved_left`, `blink`, `smile`, `lock_acquired`)
    - **brief description or value**

This moves the pipeline from pure recognition to **behavior tracking over time** for a chosen identity.

---

## Exam day (REAL hardware — ESP + servo + camera on rig)

**Use this when examiners give you physical hardware.** Full instructions: **`EXAM_GUIDE.md`**.

```bash
source .venv/bin/activate
# Edit config.json: team_id, mqtt_host (from examiners)
# Flash firmware/esp8266_servo_controller.ino with same Wi-Fi + TEAM_ID + MQTT_HOST
python -m src.enroll                    # first time only
python start_exam.py --target YourName  # real ESP moves camera — NOT simulation
```

Do **not** run `start_demo.py` or `simulated_esp.py` on exam day.

---

## Practice at home (no ESP / no servo — simulation only)

For rehearsing without hardware. See `EXAM_GUIDE.md` section 3.

```bash
source .venv/bin/activate
pip install -r requirements_verified.txt
python -m src.enroll
python start_demo.py --target Vieira
```

Useful flags: `--no-window` (headless), `--no-broker` (external broker).

Run the tests:

```bash
python -m pytest tests/ -v
```

The simulation pieces:
- `hardware/servo_simulator.py` — virtual servo (0–180°, smooth, jitter-free, history).
- `hardware/servo_interface.py` — HAL: auto-selects **ESP8266 / ESP32 / SIMULATION**.
- `simulated_esp.py` — software ESP: subscribes MQTT, drives the virtual servo.
- `demo_mode.py` — vision node that publishes movement + annotated frames.

---

## Distributed Vision-Control System (Face-Locked Servo)

This repository also implements the **Distributed Vision-Control** architecture (Face‑Locked Servo):

- **PC (Vision Node)**: `src/pc_vision_node.py`
  - Captures frames, locks onto a selected enrolled identity, computes a movement state:
    - `MOVE_LEFT`, `MOVE_RIGHT`, `CENTERED`, `NO_FACE`
  - Publishes JSON messages via MQTT to: `vision/<team_id>/movement`
  - **Must not** talk directly to ESP8266 or browser (no HTTP / WebSocket device comms).

- **ESP8266 (Edge Controller)**: `arduino/esp8266_servo/esp8266_servo.ino`
  - Connects to Wi‑Fi **RCA** and subscribes to `vision/<team_id>/movement`
  - Drives a servo motor smoothly based on movement messages (jitter‑reduced target chasing).

- **Backend API Service (VPS relay)**: `backend/ws_relay.py`
  - Subscribes to `vision/<team_id>/movement` on the MQTT broker (port **1883**)
  - Serves a WebSocket API on port **9002** and pushes movement updates to browsers in real time.

- **Web Dashboard (Browser)**: `dashboard/index.html`
  - Connects to the backend WebSocket (no polling, no MQTT in browser)
  - Displays last movement status, confidence, and timestamp.

### MQTT Topic Isolation (Critical)

All nodes use the team namespace:

- Base: `vision/<team_id>/`
- Movement topic: `vision/<team_id>/movement`
- Optional heartbeat topic: `vision/<team_id>/heartbeat`

Set `TEAM_ID` consistently across PC, backend, and ESP8266.

### Movement payload format

Published by the PC node:

```json
{
  "status": "MOVE_LEFT",
  "confidence": 0.87,
  "timestamp": 1730000000
}
```

### Run the distributed system

1) **Start the backend relay** (on VPS or any machine that can reach the broker):

```bash
TEAM_ID=team01 MQTT_HOST=<VPS_IP> python backend/ws_relay.py
```

2) **Open the dashboard**:
- Open `dashboard/index.html`
- Set WebSocket URL to: `ws://<VPS_IP>:9002`

3) **Run the PC vision node**:

```bash
TEAM_ID=team01 MQTT_HOST=<VPS_IP> python -m src.pc_vision_node
```

4) **Flash ESP8266 servo sketch**:
- Edit `MQTT_HOST` in `arduino/esp8266_servo/esp8266_servo.ino` to your VPS IP/host
- Flash to ESP8266
- Wire servo signal to `D4` (GPIO2) and provide adequate 5V power for servo

---

## Requirements

- Python 3.10 or 3.11 (MediaPipe may be unstable on 3.12+)
- See `requirements.txt` for exact packages. Typical dependencies include:
  - opencv-python
  - mediapipe
  - onnxruntime
  - numpy
  - matplotlib (optional for heatmap visualization)

---

## Installation & Run

1. Create and activate a virtual environment
```bash
python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows (Command Prompt / PowerShell)
.venv\Scripts\activate
```

2. Install dependencies
```bash
pip install -r requirements.txt
```

3. Run demos from the project root:
```bash
# Embedding demo (camera → aligned face → embedding + visualization)
python -m src.embed

# Enroll an identity into the DB (creates data/db/face_db.npz)
python -m src.enroll

# Multi-face recognition demo (labels all visible faces)
python -m src.recognize

# Face Locking: select one enrolled identity and track its actions
python -m src.lock
```

Notes:
- Ensure `models/embedder_arcface.onnx` exists (place your ONNX model there).
- Test camera index or video file path if you have multiple cameras.

---

## Usage / Controls

**Embedding demo (`python -m src.embed`)**
- `q` → Quit
- `p` → Print embedding statistics to terminal

**Enrollment (`python -m src.enroll`)**
- `SPACE` → Capture one aligned sample (if a face is detected)
- `a` → Toggle auto‑capture
- `s` → Save enrollment to `data/db/face_db.npz`
- `r` → Reset only the new (current-session) samples
- `q` → Quit

**Multi-face recognition (`python -m src.recognize`)**
- `q` → Quit
- `r` → Reload DB from disk
- `+` / `-` → Adjust distance threshold
- `d` → Toggle debug overlay

**Face Locking (`python -m src.lock`)**
- At start: type the **enrolled identity name** (e.g. `Alice`) when prompted.
- While running:
  - `q` → Quit
  - `r` → Reload DB from disk
  - `l` → Manually release the current lock
  - The window overlay shows:
    - Current FPS and target identity
    - Lock status (`LOCKED`) and similarity to the locked template
    - Visual 5‑point landmarks used for action detection

---

## Target Use Cases

- Embedded face recognition systems
- Edge AI identity verification
- Attendance and access control systems
- Research and learning about face recognition pipelines

---

## Roadmap / Future Improvements

- Replace Haar with a lightweight CNN detector (for better multi-face robustness)
- Add an embedding database + matching pipeline
- Quantize ArcFace model for reduced power & faster inference
- Support multi-face tracking
- Hardware acceleration backends (TensorRT, NNAPI, etc.)
- Packaging for specific platforms (Jetson, Raspberry Pi)

---

## License

This project is intended for educational and research purposes. (Add a specific license file like `LICENSE` if you want to choose an OSI-approved license.)

---

## Acknowledgments

- ArcFace / InsightFace
- MediaPipe
- OpenCV
- ONNX Runtime

---