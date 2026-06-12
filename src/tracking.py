"""
tracking.py
===========

Stable movement-decision logic shared by the vision node and demo mode.

Goals (per assignment task 6):
- Dead zone around the frame centre (default +/- 80 px) -> CENTERED.
- Hysteresis + temporal debouncing to stop oscillation and rapid flips.
- EMA smoothing of the face centre to reject jitter.
- Require N consecutive agreeing frames before emitting a new direction.

The decision vocabulary is exactly: MOVE_LEFT | MOVE_RIGHT | CENTERED | NO_FACE.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class MovementTracker:
    dead_zone_px: float = 80.0
    smoothing_alpha: float = 0.6      # weight of the new sample (0..1)
    min_consecutive: int = 2          # frames a new state must persist
    release_margin: float = 1.25      # hysteresis: must exit dead zone * margin

    _smoothed_cx: Optional[float] = None
    _committed: str = "NO_FACE"
    _candidate: str = "NO_FACE"
    _candidate_count: int = 0

    def reset(self) -> None:
        self._smoothed_cx = None
        self._committed = "NO_FACE"
        self._candidate = "NO_FACE"
        self._candidate_count = 0

    def _raw_state(self, cx: float, frame_w: int) -> str:
        if frame_w <= 0:
            return "NO_FACE"
        center = frame_w / 2.0
        offset = cx - center
        # Hysteresis: widen the dead zone when currently CENTERED so we do not
        # flip on tiny movements right at the boundary.
        dz = self.dead_zone_px
        if self._committed == "CENTERED":
            dz *= self.release_margin
        if offset < -dz:
            return "MOVE_LEFT"
        if offset > dz:
            return "MOVE_RIGHT"
        return "CENTERED"

    def update(self, center_x: Optional[float], frame_w: int) -> str:
        """
        Feed the current face centre (or ``None`` if no face) and get the
        debounced, smoothed movement state.
        """
        if center_x is None:
            self._smoothed_cx = None
            self._candidate = "NO_FACE"
            self._candidate_count = self.min_consecutive
            self._committed = "NO_FACE"
            return self._committed

        # EMA smoothing of the horizontal face position.
        if self._smoothed_cx is None:
            self._smoothed_cx = float(center_x)
        else:
            a = self.smoothing_alpha
            self._smoothed_cx = a * float(center_x) + (1.0 - a) * self._smoothed_cx

        raw = self._raw_state(self._smoothed_cx, frame_w)

        if raw == self._committed:
            self._candidate = raw
            self._candidate_count = 0
            return self._committed

        # New state must persist for `min_consecutive` frames before commit.
        if raw == self._candidate:
            self._candidate_count += 1
        else:
            self._candidate = raw
            self._candidate_count = 1

        if self._candidate_count >= self.min_consecutive:
            self._committed = self._candidate
            self._candidate_count = 0

        return self._committed

    @property
    def smoothed_center_x(self) -> Optional[float]:
        return self._smoothed_cx
