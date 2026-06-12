"""
camera_utils.py
===============

Robust webcam opening. Probes indices 0-9, prefers cameras that produce
frames AND can detect a face (when the user is in front of the camera).
"""

from __future__ import annotations

from typing import Optional

import cv2


def _open_index(idx: int) -> Optional["cv2.VideoCapture"]:
    """Open a single camera index with V4L2 and minimal buffering."""
    cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
    if cap is None or not cap.isOpened():
        if cap is not None:
            cap.release()
        return None
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass
    return cap


def _warmup(cap: "cv2.VideoCapture", n: int = 8) -> bool:
    for _ in range(n):
        ok, frame = cap.read()
        if ok and frame is not None and frame.size > 0:
            return True
    return False


def probe_cameras(max_index: int = 10, face_check: bool = True) -> list[dict]:
    """
    Probe camera indexes and return metadata for each working device.
    If ``face_check`` is True, also counts face detections (user should be visible).
    """
    from .haar_5pt import Haar5ptDetector

    det = Haar5ptDetector(min_size=(40, 40), debug=False) if face_check else None
    results: list[dict] = []

    for idx in range(max_index):
        cap = _open_index(idx)
        entry = {"index": idx, "ok": False, "width": 0, "height": 0, "frames": 0, "face_hits": 0}
        if cap is None:
            results.append(entry)
            continue
        if not _warmup(cap, 8):
            cap.release()
            results.append(entry)
            continue
        frames = 0
        face_hits = 0
        for _ in range(20):
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            frames += 1
            entry["height"], entry["width"] = frame.shape[:2]
            if det and det.detect(frame, max_faces=1):
                face_hits += 1
        cap.release()
        entry["ok"] = frames >= 10
        entry["frames"] = frames
        entry["face_hits"] = face_hits
        results.append(entry)
    return results


def pick_camera_index(max_index: int = 10, face_check: bool = True) -> Optional[int]:
    """Return the best camera index, preferring devices that detect a face."""
    results = probe_cameras(max_index=max_index, face_check=face_check)
    working = [r for r in results if r["ok"]]
    if not working:
        return None
    if face_check and any(r["face_hits"] > 0 for r in working):
        working.sort(key=lambda r: r["face_hits"], reverse=True)
    else:
        working.sort(key=lambda r: r["frames"], reverse=True)
    return int(working[0]["index"])


def open_camera(preferred: object = "auto", max_probe: int = 10) -> Optional["cv2.VideoCapture"]:
    """
    Open a working camera. ``preferred`` may be int, numeric string, or ``"auto"``.
    When auto, picks the index with the most face detections.
    """
    candidates: list[int] = []
    if isinstance(preferred, str) and preferred.isdigit():
        candidates.append(int(preferred))
    elif isinstance(preferred, int):
        candidates.append(preferred)

    if preferred in ("auto", "", None) or not candidates:
        best = pick_camera_index(max_index=max_probe, face_check=True)
        if best is not None:
            candidates = [best]
        else:
            candidates = list(range(max_probe))

    for idx in candidates:
        cap = _open_index(idx)
        if cap is None:
            continue
        if _warmup(cap, 5):
            return cap
        cap.release()
    return None
