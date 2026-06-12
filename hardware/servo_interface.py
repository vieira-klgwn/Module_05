"""
servo_interface.py
==================

Hardware Abstraction Layer (HAL) for the face-locked servo.

A single :class:`ServoController` exposes one API regardless of what is
physically present:

    ESP8266 / ESP32 (serial)  -> commands sent over USB serial as JSON lines
    SIMULATION                -> drives an in-process :class:`ServoSimulator`

Mode selection (``mode="auto"`` by default):

    if a board is reachable on a serial port  -> use the real board
    else                                       -> use SIMULATION

The controller speaks a *single movement vocabulary* so the rest of the
system never has to know which backend is active::

    controller.apply_movement("MOVE_LEFT" | "MOVE_RIGHT" | "CENTERED" | "NO_FACE")
    controller.update()        # advance simulator / housekeeping
    controller.state()         # -> ServoState (angle, direction, moving, ...)

Note: in the *distributed* architecture the real ESP receives commands over
MQTT (see ``firmware/`` and ``simulated_esp.py``). This HAL additionally
supports a *direct* serial link, which is convenient for bench testing a
board that is plugged into the same PC.
"""

from __future__ import annotations

import json
import time
from enum import Enum
from typing import List, Optional

from .servo_simulator import ServoSimulator, ServoState

try:  # pyserial is optional; only needed for a directly-wired board
    import serial  # type: ignore
    import serial.tools.list_ports as list_ports  # type: ignore
    _SERIAL_AVAILABLE = True
except Exception:  # pragma: no cover - depends on install
    serial = None  # type: ignore
    list_ports = None  # type: ignore
    _SERIAL_AVAILABLE = False


class ServoMode(str, Enum):
    ESP8266 = "esp8266"
    ESP32 = "esp32"
    SIMULATION = "simulation"


# Common USB-serial vendor strings exposed by ESP boards / their USB bridges.
_ESP_HINTS = ("cp210", "ch340", "ch910", "ftdi", "esp", "silicon labs", "wch")


def detect_serial_port() -> Optional[str]:
    """Return the device path of a likely ESP board, or ``None``."""
    if not _SERIAL_AVAILABLE or list_ports is None:
        return None
    try:
        ports = list(list_ports.comports())
    except Exception:
        return None
    for p in ports:
        desc = f"{getattr(p, 'description', '')} {getattr(p, 'manufacturer', '')}".lower()
        if any(h in desc for h in _ESP_HINTS):
            return p.device
    # Fall back to the first port that looks like a USB serial device.
    for p in ports:
        dev = (p.device or "").lower()
        if "ttyusb" in dev or "ttyacm" in dev or "cu.usb" in dev or dev.startswith("com"):
            return p.device
    return None


class ServoController:
    """Unified servo controller that auto-selects a real board or simulation."""

    def __init__(
        self,
        mode: str = "auto",
        board: str = "esp8266",
        serial_port: str = "auto",
        serial_baud: int = 115200,
        min_angle: float = 0.0,
        max_angle: float = 180.0,
        center_angle: float = 90.0,
        track_step: float = 3.0,
        search_step: float = 4.0,
        max_speed_dps: float = 240.0,
        jitter_deadband: float = 1.0,
        invert_direction: bool = False,
    ) -> None:
        self.track_step = float(track_step)
        self.search_step = float(search_step)
        self.invert_direction = bool(invert_direction)
        self.min_angle = float(min_angle)
        self.max_angle = float(max_angle)

        # The simulator always exists: it mirrors the (assumed) servo state and
        # is the visual source of truth for the dashboard, even with real HW.
        self.sim = ServoSimulator(
            min_angle=min_angle,
            max_angle=max_angle,
            center_angle=center_angle,
            max_speed_dps=max_speed_dps,
            jitter_deadband=jitter_deadband,
        )

        self._serial = None
        self._search_dir = 1.0
        self.mode = self._resolve_mode(mode, board, serial_port, serial_baud)

    # ------------------------------------------------------------------ #
    # Mode resolution / connection
    # ------------------------------------------------------------------ #
    def _resolve_mode(self, mode: str, board: str, serial_port: str, serial_baud: int) -> ServoMode:
        mode = (mode or "auto").lower()
        board = (board or "esp8266").lower()
        board_mode = ServoMode.ESP32 if board == "esp32" else ServoMode.ESP8266

        if mode in ("simulation", "sim"):
            return ServoMode.SIMULATION

        if mode in ("esp8266", "esp32", "auto"):
            if mode in ("esp8266", "esp32"):
                board_mode = ServoMode(mode)
            port = serial_port
            if port in ("auto", "", None):
                port = detect_serial_port()
            if port and self._open_serial(port, serial_baud):
                return board_mode
            # No board reachable -> graceful fallback.
            return ServoMode.SIMULATION

        return ServoMode.SIMULATION

    def _open_serial(self, port: str, baud: int) -> bool:
        if not _SERIAL_AVAILABLE or serial is None:
            return False
        try:
            self._serial = serial.Serial(port, baud, timeout=0.2)
            time.sleep(2.0)  # allow board reset after opening the port
            return True
        except Exception:
            self._serial = None
            return False

    @property
    def is_simulation(self) -> bool:
        return self.mode == ServoMode.SIMULATION

    # ------------------------------------------------------------------ #
    # Movement vocabulary
    # ------------------------------------------------------------------ #
    def apply_movement(self, status: str) -> None:
        """
        Translate a high-level movement command into a servo target change.

        face left  -> angle decreases ; face right -> angle increases
        (optionally inverted to match a mirrored mechanical mount).
        """
        status = (status or "NO_FACE").upper()
        step = self.track_step
        if self.invert_direction:
            step = -step

        if status == "MOVE_LEFT":
            self.sim.nudge(-step)
        elif status == "MOVE_RIGHT":
            self.sim.nudge(+step)
        elif status == "CENTERED":
            pass  # hold current target
        elif status == "NO_FACE":
            # gentle search sweep so the rig "looks around" for a face
            self._search_sweep()

        if self._serial is not None:
            self._send_serial(status)

    def _search_sweep(self) -> None:
        target = self.sim.target + self._search_dir * self.search_step
        if target >= self.max_angle:
            target = self.max_angle
            self._search_dir = -1.0
        elif target <= self.min_angle:
            target = self.min_angle
            self._search_dir = 1.0
        self.sim.set_target(target)

    def _send_serial(self, status: str) -> None:
        try:
            line = json.dumps({"status": status}) + "\n"
            self._serial.write(line.encode("utf-8"))  # type: ignore[union-attr]
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def update(self) -> ServoState:
        """Advance the (virtual) servo. Returns the current state."""
        return self.sim.update()

    def state(self) -> ServoState:
        return self.sim.state()

    def history(self) -> List:
        return self.sim.history()

    def close(self) -> None:
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None


def from_config(cfg) -> "ServoController":
    """Build a :class:`ServoController` from a DistributedConfig instance."""
    s = getattr(cfg, "servo", {}) or {}
    h = getattr(cfg, "hardware", {}) or {}
    return ServoController(
        mode=h.get("mode", "auto"),
        board=h.get("board", "esp8266"),
        serial_port=h.get("serial_port", "auto"),
        serial_baud=int(h.get("serial_baud", 115200)),
        min_angle=float(s.get("min_angle", 0)),
        max_angle=float(s.get("max_angle", 180)),
        center_angle=float(s.get("center_angle", 90)),
        track_step=float(s.get("track_step", 3)),
        search_step=float(s.get("search_step", 4)),
        max_speed_dps=float(s.get("max_speed_dps", 240)),
        jitter_deadband=float(s.get("jitter_deadband", 1.0)),
        invert_direction=bool(s.get("invert_direction", False)),
    )


if __name__ == "__main__":
    ctrl = ServoController(mode="simulation", track_step=5)
    print("Mode:", ctrl.mode.value, "| simulation:", ctrl.is_simulation)
    for cmd in ["MOVE_RIGHT"] * 10 + ["CENTERED"] * 3 + ["MOVE_LEFT"] * 6:
        ctrl.apply_movement(cmd)
        st = ctrl.update()
        print(f"{cmd:10s} -> angle={st.angle:6.1f} dir={st.direction}")
        time.sleep(0.05)
    ctrl.close()
