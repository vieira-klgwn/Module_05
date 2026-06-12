"""
PC Vision Node (MQTT Publisher)

Implements the required architecture:
- Captures frames on the PC.
- Detects and locks onto a selected enrolled identity (Face Lock).
- Computes a debounced movement state: MOVE_LEFT / MOVE_RIGHT / CENTERED / NO_FACE
  using a centre dead zone + hysteresis (no oscillation).
- Publishes a JSON payload to: vision/<team_id>/movement

Must NOT communicate directly with the ESP or the browser (MQTT only).

Run:
  TEAM_ID=Winners MQTT_HOST=<host> python -m src.pc_vision_node
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np

from .camera_utils import open_camera
from .distributed_config import DistributedConfig
from .embed import ArcFaceEmbedderONNX
from .haar_5pt import align_face_5pt
from .mqtt_pub import MqttPublisher
from .recognize import FaceDBMatcher, HaarFaceMesh5pt, load_db_npz
from .tracking import MovementTracker

DB_PATH = Path("data/db/face_db.npz")

# Lock / track thresholds (cosine similarity; embeddings are L2-normalized).
LOCK_SIM_THRESHOLD = 0.55
TRACK_SIM_THRESHOLD = 0.45
LOCK_RELEASE_SEC = 4.0
HEARTBEAT_SEC = 3.0


@dataclass
class Lock:
    identity: str = ""
    locked: bool = False
    last_seen: float = 0.0
    last_sim: float = 0.0


def _face_center_x(kps: np.ndarray) -> float:
    return float(np.mean(kps[:, 0]))


def main() -> None:
    cfg = DistributedConfig()
    db = load_db_npz(DB_PATH)
    if not db:
        print("No enrolled identities found. Run: python -m src.enroll")
        return

    target = input("Enter identity to lock (enrolled): ").strip()
    if not target or target not in db:
        print("Unknown identity. Available:", ", ".join(sorted(db.keys())))
        return

    publisher = MqttPublisher(cfg, node_name="pc")
    if not publisher.connect():
        print(f"[pc] WARNING: MQTT not connected ({cfg.mqtt_host}:{cfg.mqtt_port}); will retry in background.")
    publisher.publish_heartbeat("ONLINE")
    print(f"[pc] publishing to topic: {cfg.topic_movement}")

    det = HaarFaceMesh5pt(min_size=(70, 70), debug=False)
    embedder = ArcFaceEmbedderONNX(input_size=(112, 112), debug=False)
    matcher = FaceDBMatcher(db=db, dist_thresh=0.34)
    tracker = MovementTracker(
        dead_zone_px=float(cfg.tracking_get("dead_zone_px", 80)),
        smoothing_alpha=float(cfg.tracking_get("smoothing_alpha", 0.6)),
        min_consecutive=int(cfg.tracking_get("min_consecutive_frames", 2)),
    )
    publish_hz = float(cfg.tracking_get("publish_hz", 12.0))

    target_emb = db[target].reshape(-1).astype(np.float32)
    lock = Lock(identity=target)

    cap = open_camera(cfg.camera_index)
    if cap is None:
        raise RuntimeError("Camera not available (tried configured index and auto-probe 0..4)")

    last_pub = 0.0
    last_hb = 0.0
    last_status: Optional[str] = None

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            now = time.time()
            faces = det.detect(frame, max_faces=5)
            h, w = frame.shape[:2]

            best: Optional[Tuple[float, float]] = None  # (sim, center_x)
            for f in faces:
                aligned, _ = align_face_5pt(frame, f.kps, out_size=(112, 112))
                emb = embedder.embed(aligned).embedding
                mr = matcher.match(emb)
                sim = float(np.dot(emb, target_emb))

                if not lock.locked:
                    if mr.name == target and mr.accepted and sim >= LOCK_SIM_THRESHOLD:
                        if best is None or sim > best[0]:
                            best = (sim, _face_center_x(f.kps))
                else:
                    if sim >= TRACK_SIM_THRESHOLD:
                        if best is None or sim > best[0]:
                            best = (sim, _face_center_x(f.kps))

            confidence = 0.0
            center_x: Optional[float] = None

            if best is not None:
                sim, cx = best
                lock.locked = True
                lock.last_seen = now
                lock.last_sim = sim
                confidence = sim
                center_x = cx
            elif lock.locked and (now - lock.last_seen) <= LOCK_RELEASE_SEC:
                # short miss: keep the last committed direction, lower confidence
                confidence = float(lock.last_sim)
                center_x = tracker.smoothed_center_x
            else:
                lock.locked = False
                lock.last_sim = 0.0

            status = tracker.update(center_x, w)

            pub_due = (now - last_pub) >= (1.0 / max(1.0, publish_hz))
            if pub_due or status != last_status:
                publisher.publish_movement(
                    status=status,
                    confidence=confidence,
                    identity=target,
                    locked=lock.locked,
                )
                last_pub = now
                last_status = status

            if (now - last_hb) >= HEARTBEAT_SEC:
                publisher.publish_heartbeat("ONLINE")
                last_hb = now

            vis = frame.copy()
            cv2.putText(
                vis,
                f"team={cfg.team_id} target={target} status={status} conf={confidence:.2f}",
                (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2,
            )
            if lock.locked:
                cv2.putText(vis, "LOCKED", (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.imshow("pc_vision_node", vis)
            if (cv2.waitKey(1) & 0xFF) == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        publisher.publish_heartbeat("OFFLINE")
        publisher.close()


if __name__ == "__main__":
    main()
