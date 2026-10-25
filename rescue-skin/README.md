# RESCUE SKIN — Distributed Physical AI for Adaptive Emergency Response

**Vishwakarma Application ID:** VK26-IITH-SC-0046  
**Track:** Sustainable Cities · **Sub-theme:** Smart Urban Infrastructure & Asset Tracking  
**Stage:** 2 engineering prototype (software simulation, hardware-ready)

---

> **RESCUE SKIN is a student research prototype demonstrated using controlled,
> non-hazardous simulations. It is not a certified life-safety system.**
> It is **not** a certified fire evacuation system.

## What it is

RESCUE SKIN is a distributed intelligent emergency-response layer for indoor
environments. A building is modelled as a graph of zones. Simulated ESP32
sensor nodes feed temperature, proximity, pressure/presence and occupancy
readings into a local edge backend, which fuses them, estimates zone hazard
state, computes a dynamic risk score per zone, detects restricted zones, and
recalculates evacuation routes (A* / Dijkstra) — including accessibility-aware
routing — and drives visual/audio/haptic guidance, all **locally without cloud
dependency**.

The prototype demonstrates resilience: when one communication link fails,
downstream nodes go uncertain and the rest of the building keeps operating.

## What this prototype does (working software)

1. Configurable miniature building map (graph of zones + exits).
2. Six simulated sensor nodes with realistic fluctuating readings.
3. Live occupancy and live risk levels per zone.
4. Sensor fusion with confidence (NORMAL / WATCH / RESTRICTED / UNCERTAIN).
5. Dynamic risk score (0–100) with reasons per zone.
6. Hazard event → zone becomes RESTRICTED.
7. Automatic route recalculation; Exit A → Exit B rerouting when Exit A is blocked.
8. Accessibility-aware routing (STANDARD vs ACCESSIBLE; ramps instead of stairs).
9. Communication-link failure simulation with continued local operation.
10. Event logging (hazard, restricted, route changed, link failure, …).
11. Visual / audio / haptic guidance simulation (clearly labelled simulated).
12. Full 8-step competition demo with pause/resume and progress indicator.
13. Local REST API + WebSocket real-time dashboard.
14. Automated test suite (11 tests).
15. Hardware abstraction layer ready for real ESP32 / Pi / WS2812B / I2S / DRV2605L.

## Repository layout

```
rescue-skin/
├── backend/            # FastAPI backend (local, cloud-free)
│   ├── main.py
│   ├── config/config.py
│   ├── core/           # state_manager, sensor_fusion, risk_engine, route_engine, accessibility
│   ├── simulation/     # sensor / hazard / occupancy simulators
│   ├── communication/  # ESP-NOW adapter (sim/hardware), node manager
│   ├── hardware/       # sensor / LED / audio / haptic interfaces + providers
│   └── tests/          # automated tests (stdlib unittest)
├── frontend/           # Dark engineering dashboard (index.html, css, js)
├── hardware/           # Placeholder ESP32 sketch + Pi edge-computer code
├── docs/               # ARCHITECTURE.md, HARDWARE_INTEGRATION.md, DEMO.md, API.md
├── data/               # map_config.json (configurable building graph)
├── requirements.txt
├── .env.example
└── README.md
```

## Requirements

- Python 3.9+
- `fastapi`, `uvicorn`, `pydantic`, `python-multipart` (see `requirements.txt`)
- WebSocket support: `websockets` or `wsproto` for the uvicorn server

No cloud account or API key is required. Everything runs on `localhost`.

## Install

```bash
cd rescue-skin
# (optional) python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install websockets   # required for WebSocket real-time updates
```

## Run locally (simulation mode)

```bash
cd rescue-skin
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` in a browser. The dashboard loads, the live map
appears, and simulated sensor readings begin streaming immediately.

No internet connection is needed after installation. The mode is labelled
**SIMULATION MODE** — no real hardware is connected.

## Run the automated tests

```bash
cd rescue-skin
python -m unittest discover -s backend/tests -v
```

11 tests cover: normal route, restricted zone, blocked exit, alternative
path, accessibility route, sensor uncertainty, node failure, communication
failure, route recalculation, and reset/recovery.

## Run the competition demo

Open the dashboard and click **START COMPETITION DEMO**, or:

```bash
curl -X POST http://127.0.0.1:8000/api/demo/start
```

The demo executes Normal → Occupancy → Hazard → Detection → Restricted →
Exit A down → Reroute to Exit B → Link failure → Accessibility → Recovery.
Use Pause / Resume on the dashboard.

## Simulation mode vs hardware mode

`RESCUE_SKIN_MODE=simulation` (default): all sensors, LEDs, audio and haptics
are simulated. Clearly labelled throughout. Use this to demonstrate on a
laptop.

`RESCUE_SKIN_MODE=hardware`: attempts the real hardware providers
(`ESP32SensorProvider`, `WS2812BController`, `I2SAudioController`,
`DRV2605LController`). These are placeholders until physical hardware is
connected. The core routing engine is unchanged.

See `docs/HARDWARE_INTEGRATION.md` and `docs/ARCHITECTURE.md`.

## Configuration

Edit `data/map_config.json` to change the building map, zones, edges,
distances, accessibility flags, communication topology, risk thresholds and
weights. Edit `.env` (copy from `.env.example`) for host/port/intervals.

The map is **not** hard-coded to a single layout.

## Privacy & safety

- Camera processing is edge-first; only `occupancy_count` is retained.
- No video storage, no facial recognition, no individual identification.
- Visible disclaimer: not a certified life-safety system.

## Performance targets (not fabricated)

| Metric | Target | Status |
|--------|--------|--------|
| Route recalculation | ~1–2 s | NOT YET MEASURED |
| Dashboard updates | smooth (1 s cadence) | NOT YET MEASURED |
| Heartbeat | ~1 s | NOT YET MEASURED |
| Supported nodes | 6 | live |
| Guidance modalities | 3 (LED/audio/haptic) | simulated |
| Link failure | one simulated link | simulated |

Measured values are shown only when actually measured.

## License / authorship

Student research prototype for the Vishwakarma Awards 2026-27.
