"""
camera_utils.py
===============

Robust webcam opening that fixes the project-wide "hardcoded camera index"
bug. Tries the configured index first, then auto-probes common indices so the
demo works on any laptop regardless of which device node the webcam uses.
"""

from __future__ import annotations

from typing import Optional

import cv2


def open_camera(preferred: object = "auto", max_probe: int = 5) -> Optional["cv2.VideoCapture"]:
    """
    Open a working camera and return the ``VideoCapture`` (or ``None``).

    ``preferred`` may be an int, a numeric string, or ``"auto"``.
    """
    candidates = []
    if isinstance(preferred, str) and preferred.isdigit():
        candidates.append(int(preferred))
    elif isinstance(preferred, int):
        candidates.append(preferred)

    # Always fall back to probing 0..max_probe-1.
    for i in range(max_probe):
        if i not in candidates:
            candidates.append(i)

    for idx in candidates:
        cap = cv2.VideoCapture(idx)
        if cap is not None and cap.isOpened():
            ok, _ = cap.read()
            if ok:
                return cap
            cap.release()
        elif cap is not None:
            cap.release()
    return None
