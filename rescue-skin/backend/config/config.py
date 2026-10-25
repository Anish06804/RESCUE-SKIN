"""Configuration loader for RESCUE SKIN.

Loads the building map, risk thresholds, routing weights and simulation
parameters from JSON/YAML configuration files so the application is not
hard-coded to a single map.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List

CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))


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
    # Fallback: three levels up from config/ (config -> backend -> root)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(start))))


PROJECT_ROOT = _find_project_root(CONFIG_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
MAP_CONFIG_PATH = os.path.join(DATA_DIR, "map_config.json")


@dataclass
class RiskBands:
    normal_max: float = 30.0
    watch_max: float = 60.0
    high_risk_max: float = 80.0
    restricted_max: float = 100.0


@dataclass
class Config:
    map_data: Dict[str, Any] = field(default_factory=dict)
    thresholds: Dict[str, Any] = field(default_factory=dict)
    risk_weights: Dict[str, Any] = field(default_factory=dict)
    risk_bands: RiskBands = field(default_factory=RiskBands)
    routing: Dict[str, Any] = field(default_factory=dict)
    simulation: Dict[str, Any] = field(default_factory=dict)
    node_zone_map: Dict[str, str] = field(default_factory=dict)
    comms_topology: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str = MAP_CONFIG_PATH) -> "Config":
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        building = data.get("building", {})
        cfg = cls()
        cfg.map_data = building
        cfg.node_zone_map = data.get("node_zone_map", {})
        cfg.comms_topology = data.get("comms_topology", {})
        cfg.thresholds = data.get("thresholds", {})
        cfg.risk_weights = data.get("risk_weights", {})
        cfg.routing = data.get("routing", {})
        cfg.simulation = data.get("simulation", {})

        bands = data.get("risk_bands", [])
        band_map = {b["label"]: b["max"] for b in bands}
        cfg.risk_bands = RiskBands(
            normal_max=band_map.get("NORMAL", 30),
            watch_max=band_map.get("WATCH", 60),
            high_risk_max=band_map.get("HIGH RISK", 80),
            restricted_max=band_map.get("RESTRICTED", 100),
        )
        return cfg

    def zones(self) -> List[Dict[str, Any]]:
        return self.map_data.get("zones", [])

    def edges(self) -> List[Dict[str, Any]]:
        return self.map_data.get("edges", [])

    def zone_by_id(self, zone_id: str) -> Dict[str, Any] | None:
        for z in self.zones():
            if z["id"] == zone_id:
                return z
        return None

    def exit_zones(self) -> List[Dict[str, Any]]:
        return [z for z in self.zones() if z.get("type") == "exit"]

    def start_zone(self) -> Dict[str, Any] | None:
        for z in self.zones():
            if z.get("type") == "start":
                return z
        return None
