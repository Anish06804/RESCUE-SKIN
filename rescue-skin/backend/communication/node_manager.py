"""Node manager for RESCUE SKIN.

Tracks sensor-node heartbeats, online/offline status and communication-link
health. In simulation mode it drives the link-failure demo. In hardware mode
it would monitor real ESP-NOW heartbeats from the ESP32 nodes.
"""

from __future__ import annotations

from typing import Any, Dict

from backend.core.state_manager import StateManager


class NodeManager:
    def __init__(self, state: StateManager, heartbeat_timeout: float = 6.0):
        self.state = state
        self.heartbeat_timeout = heartbeat_timeout

    # ------------------------------------------------------------------
    async def process_reading(self, node_id: str, reading: Dict[str, Any]) -> None:
        """Called whenever a node reading arrives (simulation or hardware)."""
        await self.state.update_node_reading(node_id, reading)

    async def report_link_failure(self, link_id: str, reason: str = "simulated") -> None:
        await self.state.set_link_status(link_id, False, reason)

    async def report_link_restored(self, link_id: str) -> None:
        await self.state.set_link_status(link_id, True)

    async def mark_node_offline(self, node_id: str, reason: str = "node failure") -> None:
        await self.state.set_node_offline(node_id, reason)

    async def mark_node_online(self, node_id: str) -> None:
        await self.state.set_node_online(node_id)
