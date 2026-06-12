"""
simulated_esp.py
================

A software stand-in for the ESP8266 / ESP32 edge controller, for use when no
physical board is available.

It behaves exactly like the real firmware (see ``firmware/``):
    1. Connects to the MQTT broker.
    2. Subscribes to ``vision/<team_id>/movement``.
    3. On each movement command it drives a *virtual* servo (smooth motion,
       0..180 deg, jitter-free) via the Hardware Abstraction Layer.
    4. Publishes the resulting servo state to ``vision/<team_id>/servo`` so the
       backend can relay it to the dashboard in real time.

This closes the loop end-to-end with zero hardware:
    PC vision -> MQTT -> simulated ESP -> virtual servo -> MQTT -> backend -> browser

Run:
    python simulated_esp.py
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.distributed_config import DistributedConfig
from hardware.servo_interface import from_config


def _make_client(client_id: str) -> mqtt.Client:
    try:
        return mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    except (AttributeError, TypeError):
        return mqtt.Client(client_id=client_id)


class SimulatedESP:
    def __init__(self, cfg: DistributedConfig) -> None:
        self.cfg = cfg
        self.controller = from_config(cfg)
        self.board = cfg.hardware.get("board", "esp8266")
        self._last_status = "NO_FACE"
        self._running = False

        self.client = _make_client(f"{cfg.team_id}_simesp_{int(time.time())}")
        self.client.reconnect_delay_set(min_delay=1, max_delay=16)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        rc = int(getattr(reason_code, "value", reason_code))
        if rc == 0:
            client.subscribe(self.cfg.topic_movement, qos=0)
            print(f"[sim-esp:{self.board}] connected; subscribed to {self.cfg.topic_movement}")
        else:
            print(f"[sim-esp] connect failed rc={rc}")

    def _on_disconnect(self, client, userdata, *args):
        print("[sim-esp] disconnected; reconnecting...")

    def _on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8", errors="replace"))
        except Exception:
            return
        status = str(data.get("status", "NO_FACE")).upper()
        self._last_status = status
        self.controller.apply_movement(status)

    def _publish_state(self) -> None:
        st = self.controller.state()
        payload = st.to_dict()
        payload["board"] = self.board
        payload["sim"] = self.controller.is_simulation
        payload["last_command"] = self._last_status
        try:
            self.client.publish(self.cfg.topic_servo, json.dumps(payload), qos=0, retain=False)
        except Exception:
            pass

    def run(self, hz: float = 30.0) -> None:
        self._running = True
        self.client.connect_async(self.cfg.mqtt_host, self.cfg.mqtt_port, keepalive=30)
        self.client.loop_start()
        print(f"[sim-esp:{self.board}] virtual servo online (mode={self.controller.mode.value})")
        period = 1.0 / max(1.0, hz)
        try:
            while self._running:
                # Keep advancing the virtual servo even with no new command so
                # smooth motion / search sweep continues between messages.
                if self._last_status == "NO_FACE":
                    self.controller.apply_movement("NO_FACE")
                self.controller.update()
                self._publish_state()
                time.sleep(period)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def run_in_thread(self, hz: float = 30.0) -> threading.Thread:
        t = threading.Thread(target=self.run, args=(hz,), daemon=True)
        t.start()
        return t

    def stop(self) -> None:
        self._running = False
        self.controller.close()
        for fn in (self.client.loop_stop, self.client.disconnect):
            try:
                fn()
            except Exception:
                pass


def main() -> None:
    cfg = DistributedConfig()
    SimulatedESP(cfg).run()


if __name__ == "__main__":
    main()
