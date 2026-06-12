#!/usr/bin/env python3
"""Automated face enrollment — captures samples while user sits in front of camera."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.camera_utils import open_camera
from src.distributed_config import DistributedConfig
from src.embed import ArcFaceEmbedderONNX
from src.enroll import EnrollConfig, ensure_dirs, load_db, mean_embedding, save_db
from src.haar_5pt import Haar5ptDetector, align_face_5pt

import os

NAME = os.getenv("ENROLL_NAME", "User")
SAMPLES_TARGET = int(os.getenv("ENROLL_SAMPLES", "20"))
TIMEOUT_SEC = float(os.getenv("ENROLL_TIMEOUT", "90.0"))


def main() -> int:
    cfg_app = DistributedConfig()
    ecfg = EnrollConfig()
    ensure_dirs(ecfg)

    cap = open_camera(cfg_app.camera_index, max_probe=10)
    if cap is None:
        print("FAIL: no camera")
        return 1

    det = Haar5ptDetector(min_size=(70, 70), smooth_alpha=0.80, debug=False)
    emb = ArcFaceEmbedderONNX(input_size=(112, 112), debug=False)
    samples: list[np.ndarray] = []
    person_dir = ecfg.crops_dir / NAME
    person_dir.mkdir(parents=True, exist_ok=True)

    print(f"Auto-enrolling '{NAME}' — sit in front of camera ({SAMPLES_TARGET} samples)...")
    t0 = time.time()
    last_cap = 0.0

    while len(samples) < SAMPLES_TARGET and (time.time() - t0) < TIMEOUT_SEC:
        ok, frame = cap.read()
        if not ok:
            continue
        faces = det.detect(frame, max_faces=1)
        now = time.time()
        if faces and (now - last_cap) >= 0.25:
            f = faces[0]
            aligned, _ = align_face_5pt(frame, f.kps, out_size=(112, 112))
            r = emb.embed(aligned)
            samples.append(r.embedding)
            fn = person_dir / f"{int(now * 1000)}.jpg"
            cv2.imwrite(str(fn), aligned)
            last_cap = now
            print(f"  captured {len(samples)}/{SAMPLES_TARGET}  sim_hint={r.embedding[:3]}")
        time.sleep(0.02)

    cap.release()
    if len(samples) < 5:
        print(f"FAIL: only {len(samples)} samples captured")
        return 1

    template = mean_embedding(samples)
    db = load_db(ecfg)
    db[NAME] = template
    meta = {
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "embedding_dim": int(template.size),
        "names": sorted(db.keys()),
        "samples_total_used": len(samples),
        "method": "auto_enroll.py",
    }
    save_db(ecfg, db, meta)
    print(f"OK: enrolled '{NAME}' with {len(samples)} samples")
    print(f"  db: {ecfg.out_db_npz}")
    print(f"  crops: {person_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
