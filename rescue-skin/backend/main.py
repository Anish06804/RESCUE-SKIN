"""RESCUE SKIN — backend application (FastAPI).

Stage 2 engineering prototype. Runs entirely in SIMULATION mode by default.
Set RESCUE_SKIN_MODE=hardware to attempt real hardware providers (not wired
until hardware is connected).

Architecture (all local, no cloud dependency):

  Sensors -> SensorProvider -> NodeManager -> StateManager
                                          -> SensorFusion -> RiskEngine
                                                           -> RouteEngine
                                                           -> Guidance (LED/Audio/Haptic)
                                                              -> WebSocket -> Dashboard

Core routing / risk engines never depend on the network or the cloud.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.config.config import Config
from backend.core.state_manager import StateManager
from backend.core.sensor_fusion import SensorFusion
from backend.core.risk_engine import RiskEngine
from backend.core.route_engine import RouteEngine
from backend.simulation.sensor_simulator import SensorSimulator
from backend.communication.espnow_adapter import ESPNowAdapter
from backend.communication.node_manager import NodeManager
from backend.hardware.interfaces import (
    SimulationSensorProvider,
    ESP32SensorProvider,
    SimulatedLEDController,
    WS2812BController,
    SimulatedAudioController,
    I2SAudioController,
    SimulatedHapticController,
    DRV2605LController,
)
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Paths & config
# ---------------------------------------------------------------------------
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
# Resolve the project root robustly: walk up from backend/ until we find a
# directory that contains backend/, frontend/ and data/ (the project layout).
def _find_project_root(start: str) -> str:
    cur = os.path.abspath(start)
    for _ in range(6):
        if (os.path.isdir(os.path.join(cur, "backend"))
                and os.path.isdir(os.path.join(cur, "frontend"))
                and os.path.isdir(os.path.join(cur, "data"))):
            return cur
        nxt = os.path.dirname(cur)
        if nxt == cur:
            break
        cur = nxt
    # Fallback: two levels up from backend/
    return os.path.dirname(os.path.dirname(os.path.abspath(start)))

PROJECT_ROOT = _find_project_root(BACKEND_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
MAP_CONFIG_PATH = os.path.join(DATA_DIR, "map_config.json")
print(f"[INFO] PROJECT_ROOT={PROJECT_ROOT}", flush=True)

MODE = os.environ.get("RESCUE_SKIN_MODE", "simulation").lower()
HOST = os.environ.get("RESCUE_SKIN_HOST", "127.0.0.1")
PORT = int(os.environ.get("RESCUE_SKIN_PORT", "8000"))

SENSOR_INTERVAL = float(os.environ.get("RESCUE_SKIN_SENSOR_INTERVAL_SEC", "1.0"))
HEARTBEAT_INTERVAL = float(os.environ.get("RESCUE_SKIN_HEARTBEAT_INTERVAL_SEC", "1.0"))
RISK_INTERVAL = float(os.environ.get("RESCUE_SKIN_RISK_INTERVAL_SEC", "1.0"))
ROUTE_INTERVAL = float(os.environ.get("RESCUE_SKIN_ROUTE_INTERVAL_SEC", "2.0"))
DEMO_STEP_DELAY = float(os.environ.get("RESCUE_SKIN_DEMO_STEP_DELAY", "3.0"))

# ---------------------------------------------------------------------------
# Components (created in lifespan)
# ---------------------------------------------------------------------------
config: Optional[Config] = None
state: Optional[StateManager] = None
fusion: Optional[SensorFusion] = None
risk_engine: Optional[RiskEngine] = None
route_engine: Optional[RouteEngine] = None
simulator: Optional[SensorSimulator] = None
espnow: Optional[ESPNowAdapter] = None
node_mgr: Optional[NodeManager] = None

led: Optional[Any] = None
audio: Optional[Any] = None
haptic: Optional[Any] = None

# Background task handles
_sensor_task: Optional[asyncio.Task] = None
_staleness_task: Optional[asyncio.Task] = None
_route_task: Optional[asyncio.Task] = None
_demo_task: Optional[asyncio.Task] = None
_demo_pause_event = asyncio.Event()

# Performance measurements (genuine, not fabricated)
_route_calc_times: List[float] = []


# ---------------------------------------------------------------------------
# Internal route dataclass
# ---------------------------------------------------------------------------
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
    algorithm: str = "A*"


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------
class HazardTrigger(BaseModel):
    node_id: str = Field(..., description="Sensor node to heat up")
    delta: float = Field(8.0, description="Temperature delta in C")


class OccupancyTrigger(BaseModel):
    node_id: str = Field(..., description="Sensor node")
    amount: int = Field(3, description="Occupants to add")


class LinkFailure(BaseModel):
    link_id: str = Field(..., description="Communication link id, e.g. NODE_01-NODE_02")


class RouteCalculate(BaseModel):
    algorithm: str = Field("A*", description="A* or Dijkstra")
    profile: str = Field("STANDARD", description="STANDARD or ACCESSIBLE")


class ProfileSelect(BaseModel):
    profile: str = Field(..., description="STANDARD or ACCESSIBLE")


# ---------------------------------------------------------------------------
# WebSocket manager
# ---------------------------------------------------------------------------
class ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active:
            self.active.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]) -> None:
        if not self.active:
            return
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


async def broadcast_snapshot() -> None:
    if state is None:
        return
    snap = await state.snapshot()
    # Add performance block
    snap["performance"] = performance_block()
    await manager.broadcast({"type": "state", "payload": snap})


def performance_block() -> Dict[str, Any]:
    measured_route = "NOT YET MEASURED"
    if _route_calc_times:
        measured_route = f"{sum(_route_calc_times)/len(_route_calc_times)*1000:.0f} ms (avg over {len(_route_calc_times)})"
    return {
        "route_recalculation": {
            "target": "1-2 s",
            "measured": measured_route,
        },
        "dashboard_updates": {
            "target": "smooth (1 s sensor cadence)",
            "measured": "NOT YET MEASURED",
        },
        "communication_heartbeat": {
            "target": "~1 s",
            "measured": "NOT YET MEASURED",
        },
        "supported_nodes": {
            "target": 6,
            "measured": len(state.nodes) if state else 0,
        },
        "guidance_modalities": {
            "target": "visual + audio + haptic",
            "measured": "visual, audio, haptic (simulated)",
        },
        "failure_mode": {
            "target": "one simulated communication link",
            "measured": "NOT YET MEASURED",
        },
    }


# ---------------------------------------------------------------------------
# Engine helpers
# ---------------------------------------------------------------------------
async def recompute_risk_and_route(force_route: bool = False) -> None:
    """Fuse readings, compute risk, recompute route, broadcast on change."""
    if state is None or config is None:
        return

    zone_snapshots: Dict[str, Any] = {}

    # Map each zone to its sensor node so a node that lost its comms link can
    # force its zone into UNCERTAIN even if the last reading is still fresh.
    zone_to_node = {n.zone_id: nid for nid, n in state.nodes.items()}

    for zone_id, zone in state.zones.items():
        readings = {
            "temperature": zone.temperature,
            "occupancy": zone.occupancy,
            "presence": zone.presence,
            "pressure": zone.pressure,
            "proximity": zone.proximity,
        }
        fused = fusion.fuse(zone_id, readings, zone.last_updated)
        node_id = zone_to_node.get(zone_id)
        if node_id is not None and not state.nodes[node_id].online:
            fused = {
                "zone_id": zone_id,
                "state": "UNCERTAIN",
                "confidence": 0.0,
                "reasons": ["node communication link down"],
                "stale": True,
            }
        await state.set_zone_state(zone_id, fused["state"], fused["confidence"], fused["reasons"])

        score, reasons = risk_engine.compute(
            {
                "state": fused["state"],
                "confidence": fused["confidence"],
                "occupancy": zone.occupancy,
                "temperature": zone.temperature,
                "blocked": zone.blocked,
                "stale": zone.stale,
                "type": zone.zone_type,
            },
            profile=state.profile,
        )
        await state.set_risk(zone_id, score, reasons)
        zone_snapshots[zone_id] = await _zone_snapshot_dict(zone_id)

    # Recompute route so it adapts live to risk/blockage changes.
    await recompute_route(zone_snapshots)
    await broadcast_snapshot()


async def recompute_route(zone_snapshots: Optional[Dict[str, Any]] = None,
                          algorithm: str = "A*", profile: Optional[str] = None) -> None:
    if state is None or route_engine is None:
        return
    prof = profile or state.profile
    zones = zone_snapshots if zone_snapshots is not None else {
        zid: await _zone_snapshot_dict(zid) for zid, z in state.zones.items()
    }

    t0 = time.perf_counter()
    result = route_engine.calculate(zones, profile=prof, algorithm=algorithm)
    elapsed = time.perf_counter() - t0
    _route_calc_times.append(elapsed)
    if len(_route_calc_times) > 100:
        _route_calc_times.pop(0)

    if not result.feasible:
        await state.clear_route()
        await broadcast_snapshot()
        return

    route = Route(
        nodes=result.nodes,
        edges=result.edges,
        total_distance=result.total_distance,
        total_risk=result.total_risk,
        exit_id=result.exit_id,
        profile=result.profile,
        reason=result.reason,
        computed_at=time.time(),
        algorithm=result.algorithm,
    )

    # Detect real change.
    changed = True
    if state.current_route is not None:
        old = state.current_route
        changed = (old.nodes != route.nodes or old.exit_id != route.exit_id
                   or old.profile != route.profile)

    await state.set_route(route, result.reason if changed else "")

    # Guidance outputs (simulated hardware).
    await _drive_guidance(route.nodes, result.exit_id, result.reason)

    if changed:
        await broadcast_snapshot()


async def _zone_snapshot_dict(zone_id: str) -> Dict[str, Any]:
    z = state.zones[zone_id]
    return {
        "zone_id": z.zone_id,
        "label": z.label,
        "type": z.zone_type,
        "x": z.x,
        "y": z.y,
        "state": z.state,
        "confidence": z.confidence,
        "risk_score": z.risk_score,
        "risk_reasons": list(z.risk_reasons),
        "blocked": z.blocked,
        "stale": z.stale,
        "temperature": z.temperature,
        "occupancy": z.occupancy,
        "presence": z.presence,
        "pressure": z.pressure,
        "proximity": z.proximity,
    }


async def _drive_guidance(nodes: List[str], exit_id: str, reason: str) -> None:
    """Drive simulated LED / audio / haptic guidance. No real hardware."""
    if led is None:
        return
    await led.set_path(nodes, active=True)
    if state and state.profile == "ACCESSIBLE":
        await audio.speak(f"Accessible route to {exit_id}. Use the ramp.")
        await haptic.vibrate("PATTERN 1")
    else:
        await audio.speak(f"Please proceed to {exit_id}.")
        await haptic.vibrate("PATTERN 2")


# ---------------------------------------------------------------------------
# Background loops
# ---------------------------------------------------------------------------
def _reachable_node_ids() -> set[str]:
    """Node IDs still reachable from the gateway via online comms links.

    Nodes outside this set have a broken communication path to the edge
    computer, so their heartbeats go stale and their zones become uncertain:
    this models resilience when a communication link fails (Section 13).
    """
    if state is None or config is None or simulator is None:
        return set(simulator.nodes) if simulator else set()
    gateway = config.comms_topology.get("gateway")
    adj: Dict[str, List[str]] = {}
    for link in state.links.values():
        if link.online:
            adj.setdefault(link.node_a, []).append(link.node_b)
            adj.setdefault(link.node_b, []).append(link.node_a)
    seen = {gateway} if gateway else set()
    stack = list(seen)
    while stack:
        n = stack.pop()
        for m in adj.get(n, []):
            if m not in seen:
                seen.add(m)
                stack.append(m)
    return seen


async def sensor_loop() -> None:
    """Generate simulated sensor readings and feed the state manager."""
    while True:
        await asyncio.sleep(SENSOR_INTERVAL)
        if state is None or simulator is None or node_mgr is None:
            continue
        readings = simulator.generate_readings()
        reachable = _reachable_node_ids()
        for node_id, reading in readings.items():
            if node_id not in reachable:
                # Comms path broken: heartbeat goes stale -> zone uncertain.
                continue
            await node_mgr.process_reading(node_id, reading)
        await recompute_risk_and_route()


async def staleness_loop() -> None:
    """Mark zones uncertain when node heartbeats go stale."""
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        if state is None:
            continue
        now = time.time()
        for node_id, node in state.nodes.items():
            if not node.online:
                continue
            if now - node.last_heartbeat > HEARTBEAT_INTERVAL * 3:
                await node_mgr.mark_node_offline(node_id, "heartbeat stale")
        await broadcast_snapshot()


async def route_loop() -> None:
    """Periodically re-run the route engine so the route adapts live."""
    while True:
        await asyncio.sleep(ROUTE_INTERVAL)
        await recompute_route(algorithm="A*", profile=state.profile if state else "STANDARD")


# ---------------------------------------------------------------------------
# Demo mode
# ---------------------------------------------------------------------------
DEMO_STEPS = [
    "normal",
    "occupancy",
    "hazard",
    "detection",
    "restricted",
    "exit_a_down",
    "reroute_exit_b",
    "link_failure",
    "accessibility",
    "recovery",
]


async def demo_runner() -> None:
    """Execute the competition demo automatically."""
    global _demo_task
    while True:
        # Wait until demo is active and not paused.
        if not (state and state.demo_active):
            await asyncio.sleep(0.2)
            continue
        if state.demo_paused:
            _demo_pause_event.clear()
            await _demo_pause_event.wait()
            continue

        await _run_demo_sequence()

        # Demo finished: mark inactive and broadcast.
        if state:
            state.demo_active = False
            state.demo_step = len(DEMO_STEPS)
            await broadcast_snapshot()


async def _run_demo_sequence() -> None:
    if not (state and simulator and node_mgr and espnow and led and audio and haptic):
        return

    await state.clear_route()
    simulator.set_scenario("normal")
    simulator.failed_nodes.clear()
    simulator.failed_sensors.clear()
    simulator.overrides.clear()
    for nid in simulator.nodes:
        simulator.restore_node(nid)
    for lid in state.links:
        await node_mgr.report_link_restored(lid)
    await state.set_profile("STANDARD")
    await broadcast_snapshot()
    await _demo_sleep(DEMO_STEP_DELAY)

    # Step 2: three occupants present (Zone C)
    state.demo_step = 1
    simulator.trigger_occupancy_increase("NODE_03", amount=3)
    state.add_event_direct("OCCUPANCY_INCREASE", "C", "Three occupants detected in Zone C")
    await broadcast_snapshot()
    await _demo_sleep(DEMO_STEP_DELAY)

    # Step 3: simulated hazard in Zone C
    state.demo_step = 2
    simulator.trigger_temperature_increase("NODE_03", delta=10.0)
    state.add_event_direct("HAZARD_TRIGGERED", "C", "Simulated heat hazard triggered in Zone C")
    await broadcast_snapshot()
    await _demo_sleep(DEMO_STEP_DELAY)

    # Step 4: system detects abnormal readings (Zone C -> WATCH) happens via fusion
    state.demo_step = 3
    await recompute_risk_and_route()
    await broadcast_snapshot()
    await _demo_sleep(DEMO_STEP_DELAY)

    # Step 5: Zone C becomes RESTRICTED
    state.demo_step = 4
    await state.set_zone_blocked("C", True, "hazard confirmed")
    await led.highlight_zone("C", "RESTRICTED")
    await audio.speak("Zone C is restricted. Do not enter.")
    await broadcast_snapshot()
    await _demo_sleep(DEMO_STEP_DELAY)

    # Step 6: Exit A becomes unavailable
    state.demo_step = 5
    await state.set_zone_blocked("ExitA", True, "exit unsafe")
    await recompute_route(algorithm="A*", profile=state.profile)
    await broadcast_snapshot()
    await _demo_sleep(DEMO_STEP_DELAY)

    # Step 7: route changes to Exit B
    state.demo_step = 6
    await recompute_route(algorithm="A*", profile=state.profile)
    await audio.speak("Route recalculated. Proceed to Exit B.")
    await haptic.vibrate("PATTERN 2")
    await broadcast_snapshot()
    await _demo_sleep(DEMO_STEP_DELAY)

    # Step 8: disable one communication link, continued local operation
    state.demo_step = 7
    await node_mgr.report_link_failure("NODE_01-NODE_02", "simulated link failure")
    await recompute_risk_and_route()
    await broadcast_snapshot()
    await _demo_sleep(DEMO_STEP_DELAY)

    # Accessibility scenario
    state.demo_step = 8
    await state.set_profile("ACCESSIBLE")
    await recompute_route(algorithm="A*", profile="ACCESSIBLE")
    await audio.speak("Accessible route selected. Using ramp, avoiding stairs.")
    await haptic.vibrate("PATTERN 1")
    await broadcast_snapshot()
    await _demo_sleep(DEMO_STEP_DELAY)

    # Recovery
    state.demo_step = 9
    await node_mgr.report_link_restored("NODE_01-NODE_02")
    await state.set_zone_blocked("C", False, "hazard cleared")
    await state.set_zone_blocked("ExitA", False, "exit safe")
    await state.set_profile("STANDARD")
    simulator.restore_node("NODE_03")  # not failed but clear overrides
    simulator.overrides.clear()
    simulator.set_scenario("normal")
    await recompute_risk_and_route()
    await broadcast_snapshot()


async def _demo_sleep(seconds: float) -> None:
    """Sleep that honours pause/resume."""
    end = time.time() + seconds
    while time.time() < end:
        if not (state and state.demo_active):
            return
        if state.demo_paused:
            _demo_pause_event.clear()
            await _demo_pause_event.wait()
        await asyncio.sleep(0.1)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global config, state, fusion, risk_engine, route_engine, simulator
    global espnow, node_mgr, led, audio, haptic
    global _sensor_task, _staleness_task, _route_task, _demo_task

    config = Config.load(MAP_CONFIG_PATH)
    state = StateManager(config)
    state.hardware_mode = (MODE == "hardware")

    fusion = SensorFusion(config.thresholds)
    risk_engine = RiskEngine(config.risk_weights,
                             bands={b["label"]: b["max"] for b in config.map_data.get("risk_bands", [])})
    route_engine = RouteEngine(config)

    simulator = SensorSimulator(scenario="normal")
    espnow = ESPNowAdapter(mode=MODE)
    espnow.connect()
    node_mgr = NodeManager(state, heartbeat_timeout=HEARTBEAT_INTERVAL * 3)

    # Hardware abstractions: simulated by default; real providers only in hardware mode.
    if MODE == "hardware":
        from backend.hardware.interfaces import (  # noqa: F401
            ESP32SensorProvider, WS2812BController, I2SAudioController, DRV2605LController,
        )
        led = WS2812BController()
        audio = I2SAudioController()
        haptic = DRV2605LController()
        sensor_provider = ESP32SensorProvider(espnow)
    else:
        from backend.hardware.interfaces import (
            SimulationSensorProvider, SimulatedLEDController,
            SimulatedAudioController, SimulatedHapticController,
        )
        led = SimulatedLEDController()
        audio = SimulatedAudioController()
        haptic = SimulatedHapticController()
        sensor_provider = SimulationSensorProvider(simulator)

    # Start background loops
    _sensor_task = asyncio.create_task(sensor_loop())
    _staleness_task = asyncio.create_task(staleness_loop())
    _route_task = asyncio.create_task(route_loop())
    _demo_task = asyncio.create_task(demo_runner())

    # Initial risk/route computation
    await recompute_risk_and_route(force_route=True)

    yield

    # Shutdown
    for t in (_sensor_task, _staleness_task, _route_task, _demo_task):
        if t:
            t.cancel()
    if espnow:
        espnow.disconnect()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="RESCUE SKIN",
    description="Distributed Physical AI for Adaptive Emergency Response — Stage 2 Prototype",
    version="0.2.0",
    lifespan=lifespan,
)

app.mount("/css", StaticFiles(directory=os.path.join(FRONTEND_DIR, "css")), name="css")
app.mount("/js", StaticFiles(directory=os.path.join(FRONTEND_DIR, "js")), name="js")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
async def index():
    return HTMLResponse(
        '<html><head><meta http-equiv="refresh" content="0; url=/static/index.html"></head></html>'
    )


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------
@app.get("/api/map")
async def api_map():
    if config is None:
        raise HTTPException(status_code=503, detail="system not initialised")
    return {
        "zones": config.zones(),
        "edges": config.edges(),
        "node_zone_map": config.node_zone_map,
        "comms_topology": config.comms_topology,
    }


@app.get("/api/system/status")
async def system_status():
    if state is None:
        raise HTTPException(status_code=503, detail="system not initialised")
    snap = await state.snapshot()
    return {
        "project": "RESCUE SKIN",
        "application_id": "VK26-IITH-SC-0046",
        "track": "Sustainable Cities",
        "mode": "hardware" if state.hardware_mode else "simulation",
        "label": "SIMULATION MODE — no real hardware connected" if MODE == "simulation" else "HARDWARE MODE",
        "profile": state.profile,
        "demo_active": state.demo_active,
        "demo_paused": state.demo_paused,
        "demo_step": state.demo_step,
        "uptime_seconds": round(time.time() - _start_time, 1),
        "performance": performance_block(),
        "espnow": espnow.status() if espnow else {"mode": MODE, "connected": False},
    }


@app.get("/api/zones")
async def api_zones():
    if state is None:
        raise HTTPException(status_code=503, detail="system not initialised")
    snap = await state.snapshot()
    return {"zones": snap["zones"]}


@app.get("/api/nodes")
async def api_nodes():
    if state is None:
        raise HTTPException(status_code=503, detail="system not initialised")
    snap = await state.snapshot()
    return {"nodes": snap["nodes"], "links": snap["links"]}


@app.get("/api/routes")
async def api_routes():
    if state is None:
        raise HTTPException(status_code=503, detail="system not initialised")
    snap = await state.snapshot()
    return {
        "current_route": snap["current_route"],
        "previous_route": snap["previous_route"],
        "route_change_reason": snap["route_change_reason"],
    }


@app.get("/api/current-route")
async def api_current_route():
    if state is None:
        raise HTTPException(status_code=503, detail="system not initialised")
    snap = await state.snapshot()
    return {"current_route": snap["current_route"], "reason": snap["route_change_reason"]}


@app.get("/api/events")
async def api_events():
    if state is None:
        raise HTTPException(status_code=503, detail="system not initialised")
    snap = await state.snapshot()
    return {"events": snap["events"]}


@app.post("/api/simulation/hazard")
async def sim_hazard(trigger: HazardTrigger):
    if state is None or simulator is None:
        raise HTTPException(status_code=503, detail="system not initialised")
    simulator.trigger_temperature_increase(trigger.node_id, delta=trigger.delta)
    state.add_event_direct("HAZARD_TRIGGERED", trigger.node_id,
                           f"Manual hazard trigger on {trigger.node_id}")
    await recompute_risk_and_route()
    return {"ok": True, "node_id": trigger.node_id}


@app.post("/api/simulation/occupancy")
async def sim_occupancy(trigger: OccupancyTrigger):
    if state is None or simulator is None:
        raise HTTPException(status_code=503, detail="system not initialised")
    simulator.trigger_occupancy_increase(trigger.node_id, amount=trigger.amount)
    state.add_event_direct("OCCUPANCY_INCREASE", trigger.node_id,
                           f"+{trigger.amount} occupants on {trigger.node_id}")
    await recompute_risk_and_route()
    return {"ok": True, "node_id": trigger.node_id}


@app.post("/api/simulation/link-failure")
async def sim_link_failure(failure: LinkFailure):
    if state is None or node_mgr is None:
        raise HTTPException(status_code=503, detail="system not initialised")
    await node_mgr.report_link_failure(failure.link_id, "manual trigger")
    await recompute_risk_and_route()
    return {"ok": True, "link_id": failure.link_id}


class BlockZone(BaseModel):
    zone_id: str = Field(..., description="Zone id to block/unblock")
    blocked: bool = Field(True, description="Whether to restrict the zone")
    reason: str = Field("manual", description="Reason")


@app.post("/api/simulation/block-zone")
async def sim_block_zone(req: BlockZone):
    if state is None:
        raise HTTPException(status_code=503, detail="system not initialised")
    await state.set_zone_blocked(req.zone_id, req.blocked, req.reason)
    await recompute_risk_and_route()
    return {"ok": True, "zone_id": req.zone_id, "blocked": req.blocked}


@app.post("/api/simulation/reset")
async def sim_reset():
    if state is None or simulator is None or node_mgr is None:
        raise HTTPException(status_code=503, detail="system not initialised")
    simulator.set_scenario("normal")
    simulator.failed_nodes.clear()
    simulator.failed_sensors.clear()
    simulator.overrides.clear()
    for nid in simulator.nodes:
        simulator.restore_node(nid)
    for lid in state.links:
        await node_mgr.report_link_restored(lid)
    await state.set_zone_blocked("ExitA", False, "reset")
    await state.set_zone_blocked("ExitB", False, "reset")
    await state.set_zone_blocked("C", False, "reset")
    await state.set_profile("STANDARD")
    await state.clear_route()
    await recompute_risk_and_route(force_route=True)
    return {"ok": True}


@app.post("/api/route/calculate")
async def api_route_calculate(req: RouteCalculate):
    if state is None or route_engine is None:
        raise HTTPException(status_code=503, detail="system not initialised")
    await recompute_route(algorithm=req.algorithm, profile=req.profile)
    snap = await state.snapshot()
    return {"current_route": snap["current_route"], "reason": snap["route_change_reason"]}


@app.post("/api/profile/accessibility")
async def api_profile(req: ProfileSelect):
    if state is None:
        raise HTTPException(status_code=503, detail="system not initialised")
    await state.set_profile(req.profile)
    await recompute_route(profile=req.profile)
    return {"ok": True, "profile": req.profile}


@app.post("/api/demo/start")
async def demo_start():
    if state is None:
        raise HTTPException(status_code=503, detail="system not initialised")
    state.demo_active = True
    state.demo_paused = False
    state.demo_step = 0
    _demo_pause_event.set()
    state.add_event_direct("DEMO_STARTED", "SYSTEM", "Competition demo started")
    await broadcast_snapshot()
    return {"ok": True, "demo_active": state.demo_active}


@app.post("/api/demo/pause")
async def demo_pause():
    if state is None:
        raise HTTPException(status_code=503, detail="system not initialised")
    state.demo_paused = not state.demo_paused
    if not state.demo_paused:
        _demo_pause_event.set()
    await broadcast_snapshot()
    return {"ok": True, "demo_paused": state.demo_paused}


@app.post("/api/demo/reset")
async def demo_reset():
    if state is None:
        raise HTTPException(status_code=503, detail="system not initialised")
    state.demo_active = False
    state.demo_paused = False
    state.demo_step = 0
    await sim_reset()
    return {"ok": True}


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send initial snapshot immediately.
        if state:
            snap = await state.snapshot()
            snap["performance"] = performance_block()
            await websocket.send_json({"type": "state", "payload": snap})
        while True:
            # Keep connection alive; optionally receive client messages.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


_start_time = time.time()

def main():
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
