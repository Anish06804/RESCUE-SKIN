# RESCUE SKIN — API reference

**VK26-IITH-SC-0046** · Stage 2 prototype

The backend runs locally on `http://127.0.0.1:8000` (configurable via
`RESCUE_SKIN_HOST` / `RESCUE_SKIN_PORT`). All endpoints are local; no cloud
API is required.

## Base URL

```
http://127.0.0.1:8000
```

## Endpoints

### GET /api/map
Return the configurable building graph: zones, edges, node↔zone map, and
communication topology.

### GET /api/system/status
System overview: project id, mode (simulation/hardware), profile, demo state,
uptime, performance targets vs measured, ESP-NOW adapter status.

### GET /api/zones
All zones with state, confidence, risk score, risk reasons, occupancy, and
sensor values.

### GET /api/nodes
All sensor nodes with online/communication/health and latest readings, plus
communication links.

### GET /api/routes
Current route, previous route, and the route-change reason.

### GET /api/current-route
The currently active route (or null).

### GET /api/events
Recent event log (HAZARD_DETECTED, ZONE_RESTRICTED, ROUTE_CHANGED,
NODE_OFFLINE, LINK_FAILURE, LINK_RESTORED,
ACCESSIBILITY_ROUTE_SELECTED, SENSOR_UNCERTAIN, …).

### POST /api/simulation/hazard
Body: `{"node_id": "NODE_03", "delta": 8.0}`  
Inject a temperature increase on a node (simulated hazard).

### POST /api/simulation/occupancy
Body: `{"node_id": "NODE_03", "amount": 3}`  
Add occupants to a node's zone.

### POST /api/simulation/link-failure
Body: `{"link_id": "NODE_01-NODE_02"}`  
Break a communication link (simulation only).

### POST /api/simulation/block-zone
Body: `{"zone_id": "ExitA", "blocked": true, "reason": "exit unsafe"}`  
Block/unblock a zone (makes it non-traversable).

### POST /api/simulation/reset
Return to a clean normal state (clear hazards, blockages, link failures,
demo state).

### POST /api/route/calculate
Body: `{"algorithm": "A*", "profile": "STANDARD"}`  
Force a route recalculation (`A*` or `Dijkstra`; `STANDARD` or `ACCESSIBLE`).

### POST /api/profile/accessibility
Body: `{"profile": "ACCESSIBLE"}`  
Select the routing profile.

### POST /api/demo/start
Start the automatic competition demo.

### POST /api/demo/pause
Pause / resume the demo.

### POST /api/demo/reset
Stop the demo and reset the system.

### WebSocket: GET /ws
Real-time state stream. The server pushes the full system snapshot (zones,
nodes, links, routes, events, performance) whenever it changes, and an initial
snapshot on connect.

## Responses

All JSON endpoints return objects; errors return standard HTTP status codes
with `{"detail": "..."}`. The API validates input via Pydantic models.

## Notes

- This is a prototype. Endpoints prefixed `/api/simulation/` affect simulated
  state only and are labelled `SIMULATION MODE`.
- No authentication, no cloud calls, no video storage, no facial recognition.
