"""Central application state for RESCUE SKIN.

Holds the live building representation: zones, sensor nodes, communication
links, computed risk scores, the current route, routing profile and the event
log. All access is guarded by an asyncio lock so the background simulation
tasks and the API/WebSocket layer never observe inconsistent state.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.config.config import Config


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ZoneState:
    zone_id: str
    label: str
    zone_type: str
    x: float
    y: float
    state: str = "NORMAL"          # NORMAL | WATCH | RESTRICTED | UNCERTAIN
    confidence: float = 1.0        # 0.0 - 1.0
    risk_score: float = 0.0        # 0 - 100
    risk_reasons: List[str] = field(default_factory=list)
    blocked: bool = False          # manually restricted / blocked
    stale: bool = False            # no recent sensor reading

    # Latest fused sensor values
    temperature: Optional[float] = None
    occupancy: int = 0
    presence: bool = False
    pressure: Optional[float] = None
    proximity: Optional[float] = None

    last_updated: float = 0.0


@dataclass
class NodeState:
    node_id: str
    zone_id: str
    online: bool = True
    communication: str = "online"  # online | offline | degraded
    health: float = 1.0            # 0.0 - 1.0
    last_heartbeat: float = 0.0
    last_reading: float = 0.0

    temperature: Optional[float] = None
    occupancy: int = 0
    presence: bool = False
    pressure: Optional[float] = None
    proximity: Optional[float] = None


@dataclass
class LinkState:
    link_id: str
    node_a: str
    node_b: str
    online: bool = True


@dataclass
class Route:
    nodes: List[str]
    edges: List[Dict[str, Any]]
    total_distance: float
    total_risk: float
    exit_id: str
    profile: str
    reason: str = ""
    computed_at: float = 0.0


@dataclass
class SystemEvent:
    timestamp: str
    zone: str
    event_type: str
    message: str


# ---------------------------------------------------------------------------
# State manager
# ---------------------------------------------------------------------------

class StateManager:
    def __init__(self, config: Config):
        self.config = config
        self._lock = asyncio.Lock()

        # --- zones ---
        self.zones: Dict[str, ZoneState] = {}
        for z in config.zones():
            self.zones[z["id"]] = ZoneState(
                zone_id=z["id"],
                label=z.get("label", z["id"]),
                zone_type=z.get("type", "zone"),
                x=float(z.get("x", 0)),
                y=float(z.get("y", 0)),
            )

        # --- nodes ---
        self.nodes: Dict[str, NodeState] = {}
        for node_id, zone_id in config.node_zone_map.items():
            self.nodes[node_id] = NodeState(
                node_id=node_id,
                zone_id=zone_id,
                last_heartbeat=time.time(),
                last_reading=time.time(),
            )

        # --- communication links ---
        self.links: Dict[str, LinkState] = {}
        for link in config.comms_topology.get("links", []):
            a, b = link[0], link[1]
            link_id = f"{a}-{b}"
            self.links[link_id] = LinkState(link_id=link_id, node_a=a, node_b=b)

        # --- routing ---
        self.profile: str = "STANDARD"   # STANDARD | ACCESSIBLE
        self.current_route: Optional[Route] = None
        self.previous_route: Optional[Route] = None
        self.route_change_reason: str = ""

        # --- events ---
        self.events: List[SystemEvent] = []
        self.max_events = 200

        # --- simulation / demo ---
        self.demo_active: bool = False
        self.demo_paused: bool = False
        self.demo_step: int = 0
        self.hardware_mode: bool = False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _now(self) -> float:
        return time.time()

    def _iso(self) -> str:
        return time.strftime("%H:%M:%S", time.localtime())

    def _add_event(self, event_type: str, zone: str, message: str) -> None:
        self.events.append(
            SystemEvent(timestamp=self._iso(), zone=zone, event_type=event_type, message=message)
        )
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]

    # ------------------------------------------------------------------
    # Public API (all guarded by self._lock)
    # ------------------------------------------------------------------
    async def update_node_reading(self, node_id: str, reading: Dict[str, Any]) -> None:
        async with self._lock:
            node = self.nodes.get(node_id)
            if node is None:
                return
            now = self._now()
            node.last_reading = now
            node.last_heartbeat = now
            node.online = True
            node.communication = "online"
            node.health = min(1.0, node.health + 0.05)

            node.temperature = reading.get("temperature", node.temperature)
            node.occupancy = reading.get("occupancy", node.occupancy)
            node.presence = reading.get("presence", node.presence)
            node.pressure = reading.get("pressure", node.pressure)
            node.proximity = reading.get("proximity", node.proximity)

            zone_id = node.zone_id
            zone = self.zones.get(zone_id)
            if zone:
                zone.temperature = node.temperature
                zone.occupancy = node.occupancy
                zone.presence = node.presence
                zone.pressure = node.pressure
                zone.proximity = node.proximity
                zone.last_updated = now
                zone.stale = False

    async def set_node_offline(self, node_id: str, reason: str = "node failure") -> None:
        async with self._lock:
            node = self.nodes.get(node_id)
            if node is None:
                return
            node.online = False
            node.communication = "offline"
            node.health = 0.0
            zone_id = node.zone_id
            zone = self.zones.get(zone_id)
            if zone:
                zone.stale = True
                zone.state = "UNCERTAIN"
            self._add_event("NODE_OFFLINE", zone_id, f"{node_id} offline: {reason}")

    async def set_node_online(self, node_id: str) -> None:
        async with self._lock:
            node = self.nodes.get(node_id)
            if node is None:
                return
            node.online = True
            node.communication = "online"
            node.health = min(1.0, node.health + 0.2)
            node.last_heartbeat = time.time()
            node.last_reading = time.time()
            zone_id = node.zone_id
            zone = self.zones.get(zone_id)
            if zone:
                zone.stale = False
            self._add_event("NODE_ONLINE", zone_id, f"{node_id} back online")

    async def set_link_status(self, link_id: str, online: bool, reason: str = "") -> None:
        async with self._lock:
            link = self.links.get(link_id)
            if link is None:
                return
            link.online = online
            if not online:
                self._add_event("LINK_FAILURE", link_id,
                                f"Communication link {link_id} down: {reason or 'simulated'}")
            else:
                self._add_event("LINK_RESTORED", link_id,
                                f"Communication link {link_id} restored")

    async def set_zone_blocked(self, zone_id: str, blocked: bool, reason: str = "") -> None:
        async with self._lock:
            zone = self.zones.get(zone_id)
            if zone is None:
                return
            zone.blocked = blocked
            if blocked:
                zone.state = "RESTRICTED"
                self._add_event("ZONE_RESTRICTED", zone_id,
                                f"{zone.label} restricted: {reason or 'manual'}")
            else:
                if zone.state == "RESTRICTED":
                    zone.state = "NORMAL"

    async def set_zone_state(self, zone_id: str, state: str, confidence: float,
                             reasons: List[str]) -> None:
        async with self._lock:
            zone = self.zones.get(zone_id)
            if zone is None:
                return
            zone.state = state
            zone.confidence = max(0.0, min(1.0, confidence))
            zone.risk_reasons = list(reasons)
            if state == "UNCERTAIN":
                zone.stale = True

    async def set_risk(self, zone_id: str, score: float, reasons: List[str]) -> None:
        async with self._lock:
            zone = self.zones.get(zone_id)
            if zone is None:
                return
            zone.risk_score = max(0.0, min(100.0, score))
            zone.risk_reasons = list(reasons)

    async def set_profile(self, profile: str) -> None:
        async with self._lock:
            if profile not in ("STANDARD", "ACCESSIBLE"):
                return
            self.profile = profile
            self._add_event("ACCESSIBILITY_ROUTE_SELECTED", "SYSTEM",
                            f"Routing profile set to {profile}")

    def add_event_direct(self, event_type: str, zone: str, message: str) -> None:
        """Synchronous event logger used by the demo orchestrator."""
        self._add_event(event_type, zone, message)

    async def set_route(self, route: Route, reason: str = "") -> None:
        async with self._lock:
            if self.current_route is not None:
                self.previous_route = self.current_route
            self.current_route = route
            if reason:
                self.route_change_reason = reason
                self._add_event("ROUTE_CHANGED", route.exit_id,
                                f"Route recalculated: {reason}")

    async def clear_route(self) -> None:
        async with self._lock:
            self.current_route = None
            self.previous_route = None

    # ------------------------------------------------------------------
    # Read-only snapshots (guard with lock for consistency)
    # ------------------------------------------------------------------
    async def snapshot(self) -> Dict[str, Any]:
        async with self._lock:
            return {
                "mode": "hardware" if self.hardware_mode else "simulation",
                "profile": self.profile,
                "zones": {zid: self._zone_dict(z) for zid, z in self.zones.items()},
                "nodes": {nid: self._node_dict(n) for nid, n in self.nodes.items()},
                "links": {lid: self._link_dict(l) for lid, l in self.links.items()},
                "current_route": self._route_dict(self.current_route),
                "previous_route": self._route_dict(self.previous_route),
                "route_change_reason": self.route_change_reason,
                "events": [self._event_dict(e) for e in self.events[-50:]],
                "demo_active": self.demo_active,
                "demo_paused": self.demo_paused,
                "demo_step": self.demo_step,
            }

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------
    def _zone_dict(self, z: ZoneState) -> Dict[str, Any]:
        return {
            "zone_id": z.zone_id,
            "label": z.label,
            "type": z.zone_type,
            "x": z.x,
            "y": z.y,
            "state": z.state,
            "confidence": round(z.confidence, 2),
            "risk_score": round(z.risk_score, 1),
            "risk_reasons": list(z.risk_reasons),
            "blocked": z.blocked,
            "stale": z.stale,
            "temperature": z.temperature,
            "occupancy": z.occupancy,
            "presence": z.presence,
            "pressure": z.pressure,
            "proximity": z.proximity,
            "last_updated": z.last_updated,
        }

    def _node_dict(self, n: NodeState) -> Dict[str, Any]:
        return {
            "node_id": n.node_id,
            "zone_id": n.zone_id,
            "online": n.online,
            "communication": n.communication,
            "health": round(n.health, 2),
            "last_heartbeat": n.last_heartbeat,
            "temperature": n.temperature,
            "occupancy": n.occupancy,
            "presence": n.presence,
            "pressure": n.pressure,
            "proximity": n.proximity,
        }

    def _link_dict(self, l: LinkState) -> Dict[str, Any]:
        return {
            "link_id": l.link_id,
            "node_a": l.node_a,
            "node_b": l.node_b,
            "online": l.online,
        }

    def _route_dict(self, route: Optional[Route]) -> Optional[Dict[str, Any]]:
        if route is None:
            return None
        return {
            "nodes": list(route.nodes),
            "edges": list(route.edges),
            "total_distance": round(route.total_distance, 1),
            "total_risk": round(route.total_risk, 1),
            "exit_id": route.exit_id,
            "profile": route.profile,
            "reason": route.reason,
            "computed_at": route.computed_at,
        }

    def _event_dict(self, e: SystemEvent) -> Dict[str, Any]:
        return {
            "timestamp": e.timestamp,
            "zone": e.zone,
            "type": e.event_type,
            "message": e.message,
        }
