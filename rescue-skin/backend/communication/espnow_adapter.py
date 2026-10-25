"""ESP-NOW communication adapter (simulation + hardware abstraction).

In simulation mode this adapter does NOT use real ESP-NOW. It mimics the
behaviour of ESP-NOW broadcast/unicast between sensor nodes and the edge
computer so the rest of the system can be developed and demonstrated on a
laptop. When real hardware is connected, an ESP32SensorProvider replaces
this adapter without changing the core routing engine.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional


class ESPNowAdapter:
    """Simulation-mode ESP-NOW adapter.

    mode: "simulation" (default) or "hardware"
    """

    def __init__(self, mode: str = "simulation"):
        self.mode = mode
        self.is_connected = False
        self._on_receive: Optional[Callable[[Dict[str, Any]], None]] = None
        self.sent_packets: list[dict] = []
        self.last_error: Optional[str] = None

    def connect(self) -> bool:
        if self.mode == "hardware":
            # Real ESP-NOW initialisation happens in the hardware provider.
            self.is_connected = True
            return True
        # Simulation: no real radio, but we pretend the interface is up.
        self.is_connected = True
        self.last_error = None
        return True

    def disconnect(self) -> None:
        self.is_connected = False

    def send(self, node_id: str, payload: Dict[str, Any]) -> bool:
        if not self.is_connected:
            self.last_error = "ESP-NOW interface not connected"
            return False
        packet = {
            "to": node_id,
            "payload": payload,
            "sent_at": time.time(),
            "mode": self.mode,
        }
        self.sent_packets.append(packet)
        if len(self.sent_packets) > 1000:
            self.sent_packets = self.sent_packets[-1000:]
        return True

    def broadcast(self, payload: Dict[str, Any]) -> int:
        """Broadcast to all nodes. Returns number of packets 'sent'."""
        if not self.is_connected:
            self.last_error = "ESP-NOW interface not connected"
            return 0
        packet = {
            "to": "broadcast",
            "payload": payload,
            "sent_at": time.time(),
            "mode": self.mode,
        }
        self.sent_packets.append(packet)
        return 1

    def set_receive_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        self._on_receive = callback

    def simulate_receive(self, packet: Dict[str, Any]) -> None:
        """Inject a received packet (simulation only)."""
        if self._on_receive:
            self._on_receive(packet)

    def status(self) -> Dict[str, Any]:
        return {
            "protocol": "ESP-NOW",
            "mode": self.mode,
            "connected": self.is_connected,
            "packets_sent": len(self.sent_packets),
            "last_error": self.last_error,
            "hardware_connected": self.mode == "hardware" and self.is_connected,
        }
