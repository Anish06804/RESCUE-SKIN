"""Realistic simulated sensor nodes for RESCUE SKIN.

Produces fluctuating sensor readings for each simulated ESP32 node. Values
drift around baselines with small random noise so the dashboard is alive
even when no scenario is running. Supports manual triggers:

  * occupancy increase
  * temperature increase
  * zone restriction
  * sensor failure (a node stops reporting)
  * node failure (a node goes offline)

This is simulation data only. It is clearly labelled as such everywhere it
appears.
"""

from __future__ import annotations

import math
import random
import time
from typing import Any, Dict, List

from backend.core.accessibility import STANDARD, ACCESSIBLE


class SensorSimulator:
    def __init__(self, seed: int | None = None, scenario: str = "normal"):
        self.rng = random.Random(seed)
        self.scenario = scenario
        self.now = time.time()

        # Per-node baselines and drift state.
        self.nodes: Dict[str, Dict[str, Any]] = {
            "NODE_01": {"zone": "A", "temp_base": 25.5, "occ_base": 1, "press_base": 0.62, "prox_base": 2.1},
            "NODE_02": {"zone": "B", "temp_base": 26.0, "occ_base": 2, "press_base": 0.60, "prox_base": 1.8},
            "NODE_03": {"zone": "C", "temp_base": 26.5, "occ_base": 1, "press_base": 0.61, "prox_base": 2.5},
            "NODE_04": {"zone": "D", "temp_base": 25.8, "occ_base": 0, "press_base": 0.59, "prox_base": 3.0},
            "NODE_05": {"zone": "E", "temp_base": 26.2, "occ_base": 1, "press_base": 0.60, "prox_base": 2.2},
            "NODE_06": {"zone": "Corridor", "temp_base": 25.0, "occ_base": 2, "press_base": 0.63, "prox_base": 1.5},
        }

        # Manual override state (set by scenario/demo).
        self.overrides: Dict[str, Dict[str, Any]] = {}
        self.failed_nodes: set[str] = set()
        self.failed_sensors: set[str] = set()  # node_ids whose sensors are dead

    # ------------------------------------------------------------------
    def set_scenario(self, scenario: str) -> None:
        self.scenario = scenario

    def trigger_occupancy_increase(self, node_id: str, amount: int = 3) -> None:
        self.overrides.setdefault(node_id, {})["occupancy_boost"] = amount

    def trigger_temperature_increase(self, node_id: str, delta: float = 8.0) -> None:
        self.overrides.setdefault(node_id, {})["temp_boost"] = delta

    def trigger_zone_restriction(self, node_id: str) -> None:
        self.overrides.setdefault(node_id, {})["restricted"] = True

    def trigger_sensor_failure(self, node_id: str) -> None:
        self.failed_sensors.add(node_id)
        self.overrides.pop(node_id, None)

    def trigger_node_failure(self, node_id: str) -> None:
        self.failed_nodes.add(node_id)
        self.failed_sensors.discard(node_id)
        self.overrides.pop(node_id, None)

    def restore_node(self, node_id: str) -> None:
        self.failed_nodes.discard(node_id)
        self.failed_sensors.discard(node_id)
        self.overrides.pop(node_id, None)

    # ------------------------------------------------------------------
    def generate_readings(self) -> Dict[str, Dict[str, Any]]:
        """Return {node_id: reading} for every simulated node."""
        readings: Dict[str, Dict[str, Any]] = {}
        self.now = time.time()

        for node_id, base in self.nodes.items():
            reading = self._reading_for_node(node_id, base)
            readings[node_id] = reading
        return readings

    def _reading_for_node(self, node_id: str, base: Dict[str, Any]) -> Dict[str, Any]:
        now = self.now
        t = now

        if node_id in self.failed_nodes:
            return {
                "node_id": node_id,
                "zone": base["zone"],
                "online": False,
                "communication": "offline",
                "health": 0.0,
                "timestamp": now,
                "error": "node offline",
            }

        ovr = self.overrides.get(node_id, {})

        # Temperature drift around baseline (+ optional boost).
        temp = base["temp_base"] + 0.6 * math.sin(t * 0.7) + self.rng.uniform(-0.5, 0.5)
        if "temp_boost" in ovr:
            temp += ovr["temp_boost"]
        if self.scenario == "hazard" and base["zone"] in ("C", "D"):
            temp += 6.0

        # Occupancy drift (+ optional boost).
        occ = base["occ_base"]
        if self.scenario == "occupancy":
            occ += 3
        if "occupancy_boost" in ovr:
            occ += ovr["occupancy_boost"]
        occ = max(0, int(occ + self.rng.uniform(-1, 1)))
        occ = min(occ, 12)

        # Pressure / presence.
        pressure = base["press_base"] + self.rng.uniform(-0.05, 0.05)
        presence = occ > 0 and self.rng.random() > 0.15

        # Proximity (metres); lower when occupied.
        prox = base["prox_base"]
        if occ > 0:
            prox *= 0.4
        prox += self.rng.uniform(-0.2, 0.2)
        prox = max(0.1, prox)

        health = 1.0
        if node_id in self.failed_sensors:
            health = 0.0
            return {
                "node_id": node_id,
                "zone": base["zone"],
                "online": True,
                "communication": "online",
                "health": 0.0,
                "temperature": None,
                "occupancy": None,
                "presence": None,
                "pressure": None,
                "proximity": None,
                "timestamp": now,
                "error": "sensor failure",
            }

        if ovr.get("restricted"):
            temp = max(temp, 36.0)
            occ = max(occ, 9)

        return {
            "node_id": node_id,
            "zone": base["zone"],
            "online": True,
            "communication": "online",
            "health": round(health, 2),
            "temperature": round(temp, 1),
            "occupancy": occ,
            "presence": bool(presence),
            "pressure": round(pressure, 2),
            "proximity": round(prox, 1),
            "timestamp": now,
        }

    def all_online(self) -> bool:
        return not any(nid in self.failed_nodes for nid in self.nodes)
