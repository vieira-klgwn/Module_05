"""
servo_simulator.py
==================

A faithful virtual servo motor used when no physical servo / ESP board is
available. It mimics the mechanical behaviour of a hobby servo (e.g. SG90):

* Virtual angle constrained to [min_angle, max_angle] (default 0..180).
* Smooth, rate-limited motion (degrees-per-second speed control) instead of
  teleporting to the target.
* Jitter prevention via a small dead-band around the target.
* Movement history (bounded ring buffer) for plotting / debugging.
* Direction reporting (LEFT / RIGHT / HOLD) derived from the last motion.

Movement semantics (matches the vision node):
    face moves left  -> target angle decreases
    face moves right -> target angle increases
    centered         -> hold current target

The simulator is *time-driven*: call :meth:`update` repeatedly (the elapsed
wall-clock time is measured automatically) and read :meth:`state`.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple


@dataclass
class ServoState:
    angle: float
    target: float
    moving: bool
    direction: str            # "LEFT" | "RIGHT" | "HOLD"
    speed_dps: float
    min_angle: float
    max_angle: float
    timestamp: float

    def to_dict(self) -> Dict[str, object]:
        return {
            "angle": round(self.angle, 2),
            "target": round(self.target, 2),
            "moving": bool(self.moving),
            "direction": self.direction,
            "speed_dps": round(self.speed_dps, 1),
            "min_angle": self.min_angle,
            "max_angle": self.max_angle,
            "timestamp": self.timestamp,
        }


class ServoSimulator:
    """Thread-safe virtual servo with smooth, rate-limited motion."""

    def __init__(
        self,
        min_angle: float = 0.0,
        max_angle: float = 180.0,
        center_angle: float = 90.0,
        max_speed_dps: float = 240.0,
        jitter_deadband: float = 1.0,
        history_size: int = 600,
    ) -> None:
        if min_angle >= max_angle:
            raise ValueError("min_angle must be < max_angle")
        self.min_angle = float(min_angle)
        self.max_angle = float(max_angle)
        self.max_speed_dps = float(max_speed_dps)
        self.jitter_deadband = float(jitter_deadband)

        center = self._clamp(center_angle)
        self._angle = center
        self._target = center
        self._direction = "HOLD"
        self._moving = False
        self._last_update = time.time()

        self._history: Deque[Tuple[float, float]] = deque(maxlen=history_size)
        self._history.append((self._last_update, self._angle))
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _clamp(self, value: float) -> float:
        return max(self.min_angle, min(self.max_angle, float(value)))

    # ------------------------------------------------------------------ #
    # Public control API
    # ------------------------------------------------------------------ #
    def set_target(self, angle: float) -> None:
        """Set an absolute target angle (clamped to limits)."""
        with self._lock:
            self._target = self._clamp(angle)

    def nudge(self, delta: float) -> None:
        """Move the target by a relative amount (clamped to limits)."""
        with self._lock:
            self._target = self._clamp(self._target + float(delta))

    def set_speed(self, max_speed_dps: float) -> None:
        with self._lock:
            self._max_speed_dps_override = None
            self.max_speed_dps = max(1.0, float(max_speed_dps))

    def center(self) -> None:
        self.set_target((self.min_angle + self.max_angle) / 2.0)

    def update(self, now: Optional[float] = None) -> ServoState:
        """
        Advance the virtual servo toward its target based on elapsed time.

        Returns the resulting :class:`ServoState`. Call this every loop tick.
        """
        with self._lock:
            now = time.time() if now is None else float(now)
            dt = max(0.0, now - self._last_update)
            self._last_update = now

            error = self._target - self._angle

            if abs(error) <= self.jitter_deadband:
                # Inside dead-band: snap and hold (prevents micro-jitter).
                self._angle = self._target
                self._moving = False
                self._direction = "HOLD"
            else:
                max_step = self.max_speed_dps * dt if dt > 0 else abs(error)
                step = max(-max_step, min(max_step, error))
                prev = self._angle
                self._angle = self._clamp(self._angle + step)
                moved = self._angle - prev
                self._moving = abs(moved) > 1e-6
                if moved < -1e-6:
                    self._direction = "LEFT"
                elif moved > 1e-6:
                    self._direction = "RIGHT"
                else:
                    self._direction = "HOLD"

            self._history.append((now, self._angle))
            return self._snapshot(now)

    # ------------------------------------------------------------------ #
    # Read-only accessors
    # ------------------------------------------------------------------ #
    def _snapshot(self, now: float) -> ServoState:
        return ServoState(
            angle=self._angle,
            target=self._target,
            moving=self._moving,
            direction=self._direction,
            speed_dps=self.max_speed_dps,
            min_angle=self.min_angle,
            max_angle=self.max_angle,
            timestamp=now,
        )

    def state(self) -> ServoState:
        with self._lock:
            return self._snapshot(time.time())

    @property
    def angle(self) -> float:
        with self._lock:
            return self._angle

    @property
    def target(self) -> float:
        with self._lock:
            return self._target

    def history(self) -> List[Tuple[float, float]]:
        with self._lock:
            return list(self._history)


if __name__ == "__main__":
    # Tiny self-demo: sweep the virtual servo and print its smooth motion.
    sim = ServoSimulator(max_speed_dps=120.0)
    sim.set_target(150.0)
    t0 = time.time()
    while time.time() - t0 < 2.0:
        st = sim.update()
        print(f"angle={st.angle:6.1f}  target={st.target:6.1f}  dir={st.direction:5s}  moving={st.moving}")
        time.sleep(0.1)
    sim.set_target(30.0)
    t0 = time.time()
    while time.time() - t0 < 2.0:
        st = sim.update()
        print(f"angle={st.angle:6.1f}  target={st.target:6.1f}  dir={st.direction:5s}  moving={st.moving}")
        time.sleep(0.1)
