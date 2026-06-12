"""Hardware Abstraction Layer for the face-locked servo system.

Exposes a unified servo controller that transparently drives either a real
ESP8266 / ESP32 board or an in-process virtual servo (simulation mode).
"""

from .servo_simulator import ServoSimulator, ServoState
from .servo_interface import ServoController, ServoMode, detect_serial_port, from_config

__all__ = [
    "ServoSimulator",
    "ServoState",
    "ServoController",
    "ServoMode",
    "detect_serial_port",
    "from_config",
]
