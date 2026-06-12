"""
MQTT publisher for the PC vision node.

Hardened for paho-mqtt 2.x:
- Uses the explicit Callback API v2 (no deprecation warnings).
- Automatic reconnection (``reconnect_delay_set`` + background loop).
- Non-blocking, fault-tolerant publishing (never crashes the vision loop).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict

import paho.mqtt.client as mqtt

from .distributed_config import DistributedConfig


@dataclass
class MovementPayload:
    status: str  # MOVE_LEFT | MOVE_RIGHT | CENTERED | NO_FACE
    confidence: float
    timestamp: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": str(self.status),
            "confidence": float(self.confidence),
            "timestamp": int(self.timestamp),
        }


def _make_client(client_id: str) -> mqtt.Client:
    """Create a paho client compatible with both 1.x and 2.x."""
    try:  # paho-mqtt >= 2.0
        return mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            clean_session=True,
        )
    except (AttributeError, TypeError):  # paho-mqtt 1.x
        return mqtt.Client(client_id=client_id, clean_session=True)


class MqttPublisher:
    def __init__(self, cfg: DistributedConfig, node_name: str = "pc"):
        self.cfg = cfg
        self.node_name = str(node_name)
        self.connected = False

        self.client = _make_client(f"{cfg.team_id}_{self.node_name}_{int(time.time())}")
        self.client.reconnect_delay_set(min_delay=1, max_delay=16)

        # VERSION2 signatures carry an extra `properties` argument.
        def _on_connect(client, userdata, flags, reason_code, properties=None):
            self.connected = (int(getattr(reason_code, "value", reason_code)) == 0)

        def _on_disconnect(client, userdata, *args):
            self.connected = False

        self.client.on_connect = _on_connect
        self.client.on_disconnect = _on_disconnect

    def connect(self, keepalive: int = 30, timeout: float = 5.0) -> bool:
        """Connect and start the network loop. Returns True if connected in time."""
        self.client.connect_async(self.cfg.mqtt_host, self.cfg.mqtt_port, keepalive=keepalive)
        self.client.loop_start()
        t0 = time.time()
        while not self.connected and (time.time() - t0) < timeout:
            time.sleep(0.05)
        return self.connected

    def close(self) -> None:
        for fn in (self.client.loop_stop, self.client.disconnect):
            try:
                fn()
            except Exception:
                pass

    def _safe_publish(self, topic: str, payload: str) -> None:
        try:
            self.client.publish(topic, payload, qos=0, retain=False)
        except Exception:
            pass

    def publish_movement(self, status: str, confidence: float, **extra: Any) -> None:
        payload = MovementPayload(status=status, confidence=float(confidence), timestamp=int(time.time())).to_dict()
        if extra:
            payload.update(extra)
        self._safe_publish(self.cfg.topic_movement, json.dumps(payload))

    def publish_heartbeat(self, status: str = "ONLINE") -> None:
        payload = {"node": self.node_name, "status": str(status), "timestamp": int(time.time())}
        self._safe_publish(self.cfg.topic_heartbeat, json.dumps(payload))

    def publish_frame(self, b64_jpeg: str) -> None:
        """Publish an annotated video frame (base64 JPEG) for the dashboard."""
        payload = {"data": b64_jpeg, "timestamp": int(time.time())}
        self._safe_publish(self.cfg.topic_frame, json.dumps(payload))
