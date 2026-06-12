"""
demo_mode.py
============

Examiner-facing demonstration vision node. It runs the full vision pipeline and
publishes everything the dashboard needs over MQTT (never to the browser
directly):

    * vision/<team>/movement  -> {status, confidence, identity, recognized, locked, ...}
    * vision/<team>/frame      -> annotated webcam frame (base64 JPEG)

Behaviour:
    1. Opens the webcam (auto-probes the index).
    2. Detects faces (Haar + 5pt), recognizes them against the enrolled DB
       (ArcFace embeddings), and shows IDENTIFIED <name> / UNKNOWN FACE.
    3. Face Lock: automatically locks onto the chosen target identity when it
       is confidently recognized and follows ONLY that face (TARGET LOCKED).
    4. Computes a debounced MOVE_LEFT / MOVE_RIGHT / CENTERED / NO_FACE state
       (centre dead zone + hysteresis) and publishes it.

Target selection (no typing required for the demo):
    - TARGET env var, or --target argument, or
    - the first enrolled identity, or
    - "any" to lock onto whoever is recognized first.

Run:
    python demo_mode.py                 # auto target = first enrolled id
    TARGET=Vieira python demo_mode.py
"""

from __future__ import annotations

import argparse
import base64
import os
import time
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

from src.camera_utils import open_camera
from src.distributed_config import DistributedConfig
from src.embed import ArcFaceEmbedderONNX
from src.haar_5pt import align_face_5pt
from src.mqtt_pub import MqttPublisher
from src.recognize import FaceDBMatcher, FaceDet, HaarFaceMesh5pt, load_db_npz
from src.tracking import MovementTracker

DB_PATH = Path("data/db/face_db.npz")

LOCK_SIM_THRESHOLD = 0.45
TRACK_SIM_THRESHOLD = 0.38
LOCK_RELEASE_SEC = 4.0
HEARTBEAT_SEC = 3.0

GREEN = (0, 220, 120)
CYAN = (255, 220, 0)
RED = (60, 60, 255)
WHITE = (240, 240, 240)


def _encode_frame(frame: np.ndarray, width: int = 480, quality: int = 60) -> str:
    h, w = frame.shape[:2]
    if w > width:
        frame = cv2.resize(frame, (width, int(h * width / w)))
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        return ""
    return base64.b64encode(buf).decode("ascii")


def _draw_overlay(
    vis: np.ndarray,
    faces: List[FaceDet],
    labels: List[Tuple[str, float, bool]],
    locked_idx: Optional[int],
    status: str,
    target: str,
) -> None:
    h, w = vis.shape[:2]
    for i, f in enumerate(faces):
        name, sim, accepted = labels[i]
        is_locked = (locked_idx == i)
        color = CYAN if is_locked else (GREEN if accepted else RED)
        thick = 3 if is_locked else 2
        cv2.rectangle(vis, (f.x1, f.y1), (f.x2, f.y2), color, thick)
        tag = ("TARGET LOCKED: " + name) if is_locked else (
            ("IDENTIFIED: " + name) if accepted else "UNKNOWN FACE")
        cv2.putText(vis, tag, (f.x1, max(18, f.y1 - 26)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        cv2.putText(vis, f"conf={sim:.2f}", (f.x1, max(34, f.y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        if is_locked:
            cx = int(np.mean(f.kps[:, 0]))
            cy = int(np.mean(f.kps[:, 1]))
            cv2.drawMarker(vis, (cx, cy), CYAN, cv2.MARKER_CROSS, 26, 2)

    # centre dead-zone guides (±dead_zone_px from frame centre)
    mid = w // 2
    cv2.line(vis, (mid, 0), (mid, h), (90, 90, 90), 1)

    banner = {
        "MOVE_LEFT": ("SERVO MOVING LEFT", CYAN),
        "MOVE_RIGHT": ("SERVO MOVING RIGHT", CYAN),
        "CENTERED": ("CENTERED", GREEN),
        "NO_FACE": ("NO FACE", RED),
    }.get(status, (status, WHITE))
    cv2.rectangle(vis, (0, h - 40), (w, h), (20, 20, 28), -1)
    cv2.putText(vis, banner[0], (12, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.8, banner[1], 2)
    cv2.putText(vis, f"target={target}", (w - 220, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.55, WHITE, 1)


def run(target: str = "", show_window: bool = True, publish_frames: bool = True) -> None:
    cfg = DistributedConfig()
    db = load_db_npz(DB_PATH)

    if not target:
        target = os.getenv("TARGET", "").strip()
    if not target:
        target = sorted(db.keys())[0] if db else "any"

    lock_to_any = (target.lower() == "any") or (target not in db)
    target_emb = None if lock_to_any else db[target].reshape(-1).astype(np.float32)

    publisher = MqttPublisher(cfg, node_name="demo")
    publisher.connect()
    publisher.publish_heartbeat("ONLINE")

    det = HaarFaceMesh5pt(min_size=(70, 70), debug=False)
    embedder = ArcFaceEmbedderONNX(input_size=(112, 112), debug=False)
    matcher = FaceDBMatcher(db=db, dist_thresh=0.34)
    tracker = MovementTracker(
        dead_zone_px=float(cfg.tracking_get("dead_zone_px", 80)),
        smoothing_alpha=float(cfg.tracking_get("smoothing_alpha", 0.6)),
        min_consecutive=int(cfg.tracking_get("min_consecutive_frames", 2)),
        release_margin=float(cfg.tracking_get("release_margin", 1.25)),
    )
    track_hz = float(cfg.tracking_get("publish_hz", 6.0))
    center_hz = float(cfg.tracking_get("center_publish_hz", 2.0))

    cap = open_camera(cfg.camera_index)
    if cap is None:
        raise RuntimeError("Camera not available (tried configured index and auto-probe 0..4)")

    print(
        f"[demo] team={cfg.team_id} target={target} | "
        f"MQTT {cfg.mqtt_host}:{cfg.mqtt_port} -> {cfg.topic_movement}"
    )
    print(f"[demo] open the dashboard: dashboard/index.html (ws://localhost:{cfg.ws_port})")

    locked = False
    locked_name = target
    last_seen = 0.0
    last_sim = 0.0
    last_pub = 0.0
    last_hb = 0.0
    last_status: Optional[str] = None
    can_show = show_window

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            now = time.time()
            faces = det.detect(frame, max_faces=5)
            h, w = frame.shape[:2]

            labels: List[Tuple[str, float, bool]] = []
            best_idx: Optional[int] = None
            best_sim = -1.0
            best_cx: Optional[float] = None

            for i, f in enumerate(faces):
                aligned, _ = align_face_5pt(frame, f.kps, out_size=(112, 112))
                emb = embedder.embed(aligned).embedding
                mr = matcher.match(emb)
                name = mr.name if mr.name else "Unknown"
                if lock_to_any:
                    sim_t = mr.similarity
                    is_candidate = mr.accepted
                else:
                    sim_t = float(np.dot(emb, target_emb))
                    is_candidate = (mr.name == target and mr.accepted) or (locked and sim_t >= TRACK_SIM_THRESHOLD)
                labels.append((name, mr.similarity, mr.accepted))

                thresh = TRACK_SIM_THRESHOLD if locked else LOCK_SIM_THRESHOLD
                if is_candidate and sim_t >= thresh and sim_t > best_sim:
                    best_sim = sim_t
                    best_idx = i
                    best_cx = float(np.mean(f.kps[:, 0]))

            confidence = 0.0
            center_x: Optional[float] = None
            if best_idx is not None:
                locked = True
                if lock_to_any:
                    locked_name = labels[best_idx][0]
                last_seen = now
                last_sim = best_sim
                confidence = best_sim
                center_x = best_cx
            elif locked and faces and (now - last_seen) <= LOCK_RELEASE_SEC:
                confidence = last_sim
                center_x = tracker.smoothed_center_x
            else:
                if locked:
                    tracker.reset()
                locked = False
                last_sim = 0.0

            # ESP firmware: NO_FACE enables sweep search; MOVE_* steps 3° per message.
            if locked:
                status = tracker.update(center_x, w)
            else:
                status = "NO_FACE"

            track_due = (now - last_pub) >= (1.0 / max(1.0, track_hz))
            center_due = (now - last_pub) >= (1.0 / max(1.0, center_hz))
            if status in ("MOVE_LEFT", "MOVE_RIGHT"):
                # Slow track commands — each MQTT message steps the servo on the ESP.
                need_pub = (status != last_status) or track_due
            elif status == "CENTERED":
                # Hold: tell ESP to stop; repeat slowly so search mode stays off.
                need_pub = (status != last_status) or center_due
            else:
                # NO_FACE once enables ESP sweep; occasional repeat keeps it searching.
                need_pub = (status != last_status) or center_due
            if need_pub:
                publisher.publish_movement(
                    status=status,
                    confidence=confidence,
                    esp_compatible=True,
                )
                last_pub = now
                last_status = status

            if (now - last_hb) >= HEARTBEAT_SEC:
                publisher.publish_heartbeat("ONLINE")
                last_hb = now

            vis = frame.copy()
            _draw_overlay(vis, faces, labels, best_idx if locked else None, status, locked_name)

            if publish_frames and need_pub:
                b64 = _encode_frame(vis)
                if b64:
                    publisher.publish_frame(b64)

            if can_show:
                try:
                    cv2.imshow("Face-Locked Servo - Vision", vis)
                    if (cv2.waitKey(1) & 0xFF) == ord("q"):
                        break
                except cv2.error:
                    can_show = False  # headless environment
    finally:
        cap.release()
        if can_show:
            try:
                cv2.destroyAllWindows()
            except cv2.error:
                pass
        publisher.publish_heartbeat("OFFLINE")
        publisher.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="Face-Locked Servo demonstration vision node")
    ap.add_argument("--target", default="", help="enrolled identity to lock onto, or 'any'")
    ap.add_argument("--no-window", action="store_true", help="run headless (dashboard only)")
    ap.add_argument("--no-frames", action="store_true", help="do not publish video frames")
    args = ap.parse_args()
    run(target=args.target, show_window=not args.no_window, publish_frames=not args.no_frames)


if __name__ == "__main__":
    main()
