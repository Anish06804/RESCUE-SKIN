# RESCUE SKIN — Architecture

**VK26-IITH-SC-0046** · Sustainable Cities · Smart Urban Infrastructure & Asset Tracking  
Stage 2 engineering prototype — Distributed Physical AI for Adaptive Emergency Response

---

## 1. Overview

RESCUE SKIN is a distributed intelligent emergency-response layer for indoor
environments. A building is divided into interconnected zones; each zone can
provide occupancy, proximity, temperature/environment, pressure/presence,
hazard/risk, and communication-status information.

The system continuously executes the **SENSE → FUSE → UNDERSTAND → DECIDE →
ACT → ADAPT** loop entirely on the local edge computer (no cloud dependency).

## 2. Logical architecture

```
Sensors (ESP32 nodes)
      ↓  ESP-NOW (simulated in software)
Local node communication (heartbeats)
      ↓
Raspberry Pi / local backend  (FastAPI + asyncio)
      ↓
Risk engine  →  Route engine (A* / Dijkstra)
      ↓
Accessibility-aware routing  →  Guidance (LED / audio / haptic)
      ↓
Local dashboard + WebSocket real-time updates
```

All core logic (sensor fusion, risk, routing, accessibility, failure
handling) runs locally. Cloud integration, if ever added, is optional and is
**not** a required dependency.

## 3. Package layout

```
rescue-skin/
├── backend/
│   ├── main.py                 # FastAPI app, background loops, WebSocket, demo
│   ├── config/config.py        # Map + threshold + weight loader (JSON driven)
│   ├── core/
│   │   ├── state_manager.py    # Live building state, zones, nodes, links, events
│   │   ├── sensor_fusion.py    # Zone state + confidence (NORMAL/WATCH/RESTRICTED/UNCERTAIN)
│   │   ├── risk_engine.py      # Configurable risk score 0-100 with reasons
│   │   ├── route_engine.py     # A* and Dijkstra over the building graph
│   │   └── accessibility.py    # STANDARD / ACCESSIBLE routing profiles
│   ├── simulation/
│   │   ├── sensor_simulator.py # Realistic fluctuating simulated ESP32 nodes
│   │   ├── hazard_simulator.py
│   │   ├── occupancy_simulator.py
│   │   └── network_failure.py
│   ├── communication/
│   │   ├── espnow_adapter.py   # ESP-NOW abstraction (simulation / hardware)
│   │   └── node_manager.py     # Heartbeats, online/offline, link health
│   ├── hardware/
│   │   └── interfaces.py       # Sensor / LED / audio / haptic interfaces + providers
│   └── tests/                  # Automated tests (stdlib unittest)
├── frontend/
│   ├── index.html              # Dark engineering dashboard
│   ├── css/style.css
│   └── js/app.js               # WebSocket client, map rendering, demo controls
├── hardware/
│   ├── esp32/                  # Placeholder ESP32 sensor-node sketch
│   └── raspberry_pi/           # Placeholder edge-computer code
├── docs/
│   ├── ARCHITECTURE.md
│   ├── HARDWARE_INTEGRATION.md
│   ├── DEMO.md
│   └── API.md
├── data/
│   └── map_config.json         # Configurable building graph
├── requirements.txt
├── .env.example
└── README.md
```

## 4. Core engines

### Sensor fusion (`core/sensor_fusion.py`)
Combines temperature, occupancy, pressure and proximity readings into a zone
state with a confidence value:

- **NORMAL** — nominal readings
- **WATCH** — moderate anomaly
- **RESTRICTED** — severe anomaly
- **UNCERTAIN** — stale / missing data

A single noisy reading never flips a zone: evidence is aggregated, and stale
data is downgraded to UNCERTAIN. Thresholds are configurable in
`data/map_config.json`.

### Risk engine (`core/risk_engine.py`)
Computes a configurable risk score (0–100) per zone from hazard, occupancy,
congestion, sensor-confidence and accessibility factors:

| Score | Classification |
|-------|----------------|
| 0–30  | NORMAL         |
| 31–60 | WATCH          |
| 61–80 | HIGH RISK      |
| 81–100| RESTRICTED     |

The formula and band thresholds are configurable. Each score carries a
human-readable reason list (e.g. "temperature anomaly", "high occupancy").

### Route engine (`core/route_engine.py`)
A* (default) and Dijkstra pathfinding from the START zone to the nearest safe
exit. Edge/node cost considers distance, risk, congestion, blocked zones,
stale/uncertain zones, and exit availability. Blocked or RESTRICTED zones are
**non-traversable** (removed from route calculation). The route recalculates
automatically whenever risk, blockage, or the routing profile changes.

### Accessibility routing (`core/accessibility.py`)
Two explicitly-selected profiles (never inferred from a person's identity):

- **STANDARD** — all traversable edges.
- **ACCESSIBLE** — removes stairs/inaccessible edges, avoids stairs nodes,
  prefers ramps and accessible corridors.

The profile is selected explicitly by the operator (e.g. "wheelchair /
mobility assistance").

## 5. Communication & resilience

- ESP-NOW is abstracted behind `ESPNowAdapter`. In **simulation mode** no real
  radio is used; the adapter is clearly labelled `SIMULATION MODE`.
- Node heartbeats are tracked. A communication-link failure can be simulated;
  downstream nodes miss heartbeats, go stale, and their zones become UNCERTAIN.
  The route engine avoids uncertain information. The rest of the building
  keeps operating locally.
- A "RESTORE LINK" action brings nodes back online.

## 6. Edge-first operation

The backend binds to `127.0.0.1` by default and needs no internet access. All
sensing, fusion, risk, routing and dashboard updates happen locally. Camera
processing (not implemented beyond occupancy count) is edge-first: no video is
stored, no facial recognition, no individual identification.

## 7. Hardware abstraction

Interfaces (`backend/hardware/interfaces.py`) let simulated hardware be
replaced by real hardware without touching the core engines:

| Interface                  | Simulation provider           | Hardware provider (placeholder)     |
|----------------------------|------------------------------|-------------------------------------|
| SensorInterface            | SimulationSensorProvider     | ESP32SensorProvider                 |
| LEDGuidanceInterface       | SimulatedLEDController       | WS2812BController                   |
| AudioGuidanceInterface     | SimulatedAudioController     | I2SAudioController                  |
| HapticGuidanceInterface    | SimulatedHapticController    | DRV2605LController                  |

Set `RESCUE_SKIN_MODE=hardware` to attempt hardware providers (not wired until
real hardware is connected).

## 8. Real-time dashboard

A single-page dark engineering dashboard (`frontend/index.html`) served by the
backend:

- Header: RESCUE SKIN, application id VK26-IITH-SC-0046, simulation-mode badge
- Left: live building map with zone states and animated route
- Center: current/previous/new route, risk metrics, guidance (LED/audio/haptic)
- Right: system status, communication topology, targets vs measured performance
- Bottom: sensor telemetry table and event log
- Controls: competition demo start/pause/reset, manual triggers, profile select

Updates stream over WebSocket (`/ws`).

## 9. Demo mode

An 8-step competition demo runs automatically:

1. Normal building
2. Occupants present
3. Simulated hazard
4. Abnormal readings detected
5. Zone restricted
6. Exit A unavailable
7. Automatic reroute to Exit B
8. Communication-link failure with continued local operation

Plus an accessibility scenario (ramp instead of stairs) and recovery. Triggered
via "START COMPETITION DEMO" (POST `/api/demo/start`) with pause/resume and a
progress indicator.

## 10. Safety disclaimer

> RESCUE SKIN is a student research prototype demonstrated using controlled,
> non-hazardous simulations. It is not a certified life-safety system.

This disclaimer is rendered in the dashboard. The prototype is **not** a
certified fire/evacuation system.

## 11. Performance targets (not fabricated measurements)

| Metric               | Target              | Measured                        |
|----------------------|---------------------|---------------------------------|
| Route recalculation  | 1–2 s               | NOT YET MEASURED / live avg     |
| Dashboard updates    | smooth (1 s cadence)| NOT YET MEASURED                |
| Communication heartbeat| ~1 s              | NOT YET MEASURED                |
| Supported nodes      | 6                   | live count                      |
| Guidance modalities  | 3 (LED/audio/haptic)| simulated                       |
| Failure mode         | one link failure    | simulated                       |

Measured values are populated only when actually measured; otherwise the UI
shows `NOT YET MEASURED`.
