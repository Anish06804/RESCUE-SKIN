"""Sensor fusion layer for RESCUE SKIN.

Combines raw per-node readings into a zone-level state with an associated
confidence value. A single noisy reading must not flip a zone into a
dangerous state: evidence is accumulated and stale data is downgraded to
UNCERTAIN.

This is a prototype decision-support mechanism, not a certified
life-safety algorithm.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

# Fusion states
NORMAL = "NORMAL"
WATCH = "WATCH"
RESTRICTED = "RESTRICTED"
UNCERTAIN = "UNCERTAIN"


class SensorFusion:
    def __init__(self, thresholds: Dict[str, Any]):
        self.t_normal_max = float(thresholds.get("temperature_normal_max", 27.0))
        self.t_watch_max = float(thresholds.get("temperature_watch_max", 31.0))
        self.t_restricted_min = float(thresholds.get("temperature_restricted_min", 35.0))
        self.o_normal_max = int(thresholds.get("occupancy_normal_max", 2))
        self.o_watch_max = int(thresholds.get("occupancy_watch_max", 5))
        self.o_restricted_min = int(thresholds.get("occupancy_restricted_min", 8))
        self.pressure_presence_min = float(thresholds.get("pressure_presence_min", 0.45))
        self.stale_seconds = float(thresholds.get("stale_seconds", 6.0))
        self.confidence_decay = float(thresholds.get("confidence_decay_per_second", 0.2))

    # ------------------------------------------------------------------
    def fuse(self, zone_id: str, readings: Dict[str, Any],
             last_updated: float, now: Optional[float] = None) -> Dict[str, Any]:
        """Produce a fused zone state.

        readings: dict with optional keys temperature, occupancy, presence,
                  pressure, proximity.
        last_updated: timestamp of the most recent raw reading.
        now: current timestamp (defaults to time.time()).
        """
        if now is None:
            now = time.time()

        age = now - last_updated

        # Stale data -> UNCERTAIN regardless of the last values.
        if age > self.stale_seconds:
            return {
                "zone_id": zone_id,
                "state": UNCERTAIN,
                "confidence": 0.0,
                "reasons": ["stale sensor data (no recent reading)"],
                "stale": True,
            }

        temperature = readings.get("temperature")
        occupancy = readings.get("occupancy", 0)
        presence = readings.get("presence", False)
        pressure = readings.get("pressure")
        proximity = readings.get("proximity")

        reasons: List[str] = []

        # ---- Evidence scoring (0.0 - 1.0 each) ----
        temp_score = self._temperature_score(temperature)
        occ_score = self._occupancy_score(occupancy)
        press_score = self._pressure_score(pressure)
        prox_score = self._proximity_score(proximity)

        # ---- Build reasons ----
        if temperature is not None and temperature >= self.t_restricted_min:
            reasons.append(f"temperature anomaly ({temperature:.1f}C)")
        elif temperature is not None and temperature > self.t_watch_max:
            reasons.append(f"elevated temperature ({temperature:.1f}C)")

        if occupancy >= self.o_restricted_min:
            reasons.append(f"high occupancy ({occupancy})")
        elif occupancy > self.o_watch_max:
            reasons.append(f"rising occupancy ({occupancy})")

        if presence and occupancy > 0:
            reasons.append("presence detected")

        if pressure is not None and pressure < self.pressure_presence_min:
            reasons.append("low pressure (possible absence/seal loss)")

        # ---- Aggregate hazard score (0.0 - 1.0) ----
        # Presence is deliberately excluded: people being present is normal and
        # must not by itself push a zone into a dangerous state.
        hazard = max(temp_score, occ_score, press_score, prox_score)
        hazard = min(1.0, hazard)

        # ---- Confidence: decays with age, boosted by multiple agreeing sensors ----
        sensor_count = sum(1 for v in (temperature, pressure, proximity) if v is not None)
        base_confidence = min(1.0, 0.5 + 0.15 * sensor_count)
        age_penalty = self.confidence_decay * age
        confidence = max(0.0, min(1.0, base_confidence - age_penalty))

        # ---- State machine ----
        if hazard >= 0.75 or temperature is not None and temperature >= self.t_restricted_min \
                or occupancy >= self.o_restricted_min:
            state = RESTRICTED
        elif hazard >= 0.4 or temperature is not None and temperature > self.t_watch_max \
                or occupancy > self.o_watch_max:
            state = WATCH
        else:
            state = NORMAL

        # A manually blocked zone stays RESTRICTED.
        # (Blocked override is handled by the state manager; here we only
        #  report the sensor-derived state.)

        return {
            "zone_id": zone_id,
            "state": state,
            "confidence": round(confidence, 2),
            "reasons": reasons if reasons else ["nominal readings"],
            "stale": False,
        }

    # ------------------------------------------------------------------
    # Individual evidence scorers
    # ------------------------------------------------------------------
    def _temperature_score(self, temperature: Optional[float]) -> float:
        if temperature is None:
            return 0.0
        if temperature >= self.t_restricted_min:
            return 1.0
        if temperature > self.t_watch_max:
            return 0.6
        if temperature > self.t_normal_max:
            return 0.3
        return 0.0

    def _occupancy_score(self, occupancy: int) -> float:
        if occupancy >= self.o_restricted_min:
            return 1.0
        if occupancy > self.o_watch_max:
            return 0.6
        if occupancy > self.o_normal_max:
            return 0.3
        return 0.0

    def _pressure_score(self, pressure: Optional[float]) -> float:
        if pressure is None:
            return 0.0
        if pressure < self.pressure_presence_min:
            return 0.4
        return 0.0

    def _proximity_score(self, proximity: Optional[float]) -> float:
        # proximity in metres; very close = possible crowding / obstruction
        if proximity is None:
            return 0.0
        if proximity < 0.5:
            return 0.5
        if proximity < 1.0:
            return 0.25
        return 0.0
