"""
Shared configuration for the Distributed Vision-Control system.

Resolution order (highest priority first):
    1. Environment variables (TEAM_ID, MQTT_HOST, MQTT_PORT, WS_HOST, WS_PORT, CAMERA_INDEX)
    2. config.json at the project root
    3. Built-in defaults

This keeps VPS / broker / team details out of source code while still
providing a single editable `config.json` for the offline laptop demo.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _PROJECT_ROOT / "config.json"


def _load_file() -> Dict[str, Any]:
    try:
        if _CONFIG_PATH.exists():
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _get(file_cfg: Dict[str, Any], env_key: str, file_key: str, default: Any) -> Any:
    if env_key in os.environ and os.environ[env_key] != "":
        return os.environ[env_key]
    if file_key in file_cfg and file_cfg[file_key] is not None:
        return file_cfg[file_key]
    return default


@dataclass(frozen=True)
class DistributedConfig:
    team_id: str = ""
    mqtt_host: str = ""
    mqtt_port: int = 0
    ws_host: str = ""
    ws_port: int = 0
    camera_index: str = ""
    tracking: Dict[str, Any] = field(default_factory=dict)
    servo: Dict[str, Any] = field(default_factory=dict)
    hardware: Dict[str, Any] = field(default_factory=dict)

    def __init__(self):
        fc = _load_file()
        object.__setattr__(self, "team_id", str(_get(fc, "TEAM_ID", "team_id", "Winners")))
        object.__setattr__(self, "mqtt_host", str(_get(fc, "MQTT_HOST", "mqtt_host", "localhost")))
        object.__setattr__(self, "mqtt_port", int(_get(fc, "MQTT_PORT", "mqtt_port", 1883)))
        object.__setattr__(self, "ws_host", str(_get(fc, "WS_HOST", "ws_host", "0.0.0.0")))
        object.__setattr__(self, "ws_port", int(_get(fc, "WS_PORT", "ws_port", 9002)))
        object.__setattr__(self, "camera_index", str(_get(fc, "CAMERA_INDEX", "camera_index", "auto")))
        object.__setattr__(self, "tracking", dict(fc.get("tracking", {})))
        object.__setattr__(self, "servo", dict(fc.get("servo", {})))
        object.__setattr__(self, "hardware", dict(fc.get("hardware", {})))

    # --- Topic namespace (strict per-team isolation) ---
    @property
    def topic_base(self) -> str:
        return f"vision/{self.team_id}"

    @property
    def topic_movement(self) -> str:
        return f"{self.topic_base}/movement"

    @property
    def topic_heartbeat(self) -> str:
        return f"{self.topic_base}/heartbeat"

    @property
    def topic_servo(self) -> str:
        """Servo-state feedback published by the (simulated) ESP device."""
        return f"{self.topic_base}/servo"

    @property
    def topic_frame(self) -> str:
        """Optional annotated video frames (base64 JPEG) for the dashboard."""
        return f"{self.topic_base}/frame"

    # --- Convenience tunable accessors with safe defaults ---
    def tracking_get(self, key: str, default: Any) -> Any:
        return self.tracking.get(key, default)

    def servo_get(self, key: str, default: Any) -> Any:
        return self.servo.get(key, default)

    def hardware_get(self, key: str, default: Any) -> Any:
        return self.hardware.get(key, default)
