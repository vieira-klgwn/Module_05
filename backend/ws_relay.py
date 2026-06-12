"""
Backend API Service (MQTT -> WebSocket relay)

Architecture (strict):
    MQTT broker  ->  THIS backend  ->  WebSocket  ->  Browser dashboard
The browser NEVER connects to MQTT directly.

This relay:
- Subscribes to the team's movement / servo / heartbeat / frame topics.
- Wraps every MQTT message into a typed JSON envelope and pushes it to all
  connected WebSocket clients in real time.
- Reconnects automatically to the broker (paho 2.x reconnect backoff).
- Caches the last message of each type so a freshly-opened dashboard is
  populated immediately.

Run:
    TEAM_ID=Winners MQTT_HOST=<host> python backend/ws_relay.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Dict, Set

import paho.mqtt.client as mqtt
import websockets

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.distributed_config import DistributedConfig  # noqa: E402


def _make_client(client_id: str) -> mqtt.Client:
    try:
        return mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    except (AttributeError, TypeError):
        return mqtt.Client(client_id=client_id)


async def main() -> None:
    cfg = DistributedConfig()
    clients: Set[websockets.WebSocketServerProtocol] = set()
    last_by_type: Dict[str, str] = {}
    loop = asyncio.get_running_loop()

    topic_types = {
        cfg.topic_movement: "movement",
        cfg.topic_servo: "servo",
        cfg.topic_heartbeat: "heartbeat",
        cfg.topic_frame: "frame",
    }

    def _broadcast(raw: str) -> None:
        for ws in list(clients):
            try:
                asyncio.run_coroutine_threadsafe(ws.send(raw), loop)
            except Exception:
                pass

    def _on_connect(client, userdata, flags, reason_code, properties=None):
        rc = int(getattr(reason_code, "value", reason_code))
        if rc != 0:
            print(f"[relay] MQTT connect failed rc={rc}")
            return
        for topic in topic_types:
            client.subscribe(topic, qos=0)
        print(f"[relay] subscribed: {', '.join(topic_types)}")

    def _on_disconnect(client, userdata, *args):
        print("[relay] MQTT disconnected; auto-reconnecting...")

    def _on_message(client, userdata, msg):
        msg_type = topic_types.get(msg.topic, "unknown")
        try:
            raw = msg.payload.decode("utf-8", errors="replace")
        except Exception:
            return
        try:
            data = json.loads(raw)
        except Exception:
            data = {"raw": raw, "timestamp": int(time.time())}
        envelope = json.dumps({"type": msg_type, **data})
        last_by_type[msg_type] = envelope
        if msg_type != "frame":  # avoid flooding the console with base64
            print(f"[{msg_type}] {raw[:120]}")
        _broadcast(envelope)

    mqttc = _make_client(f"{cfg.team_id}_relay_{int(time.time())}")
    mqttc.reconnect_delay_set(min_delay=1, max_delay=16)
    mqttc.on_connect = _on_connect
    mqttc.on_disconnect = _on_disconnect
    mqttc.on_message = _on_message
    try:
        mqttc.connect_async(cfg.mqtt_host, cfg.mqtt_port, keepalive=30)
        mqttc.loop_start()
    except Exception as e:
        print(f"[relay] initial MQTT connect error: {e}")

    async def ws_handler(ws):
        clients.add(ws)
        peer = getattr(ws, "remote_address", "?")
        print(f"[relay] WS client connected: {peer} (total={len(clients)})")
        try:
            for envelope in last_by_type.values():  # prime the new client
                await ws.send(envelope)
            await ws.wait_closed()
        finally:
            clients.discard(ws)
            print(f"[relay] WS client disconnected: {peer} (total={len(clients)})")

    print(f"[relay] team={cfg.team_id} | broker={cfg.mqtt_host}:{cfg.mqtt_port}")
    print(f"[relay] WebSocket listening on ws://{cfg.ws_host}:{cfg.ws_port}")
    async with websockets.serve(ws_handler, cfg.ws_host, cfg.ws_port):
        try:
            await asyncio.Future()  # run forever
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass

    mqttc.loop_stop()
    mqttc.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[relay] stopped")
