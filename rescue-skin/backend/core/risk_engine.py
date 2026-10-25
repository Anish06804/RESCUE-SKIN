"""Dynamic risk engine for RESCUE SKIN.

Computes a configurable risk score (0-100) for every zone and classifies it:

  0-30   NORMAL
  31-60  WATCH
  61-80  HIGH RISK
  81-100 RESTRICTED

The score and its reasons are exposed to the routing engine and the
dashboard. This is a prototype decision-support mechanism.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

NORMAL_MAX = 30
WATCH_MAX = 60
HIGH_RISK_MAX = 80


class RiskEngine:
    def __init__(self, weights: Dict[str, Any], bands: Dict[str, float] | None = None):
        self.w_hazard = float(weights.get("hazard_weight", 0.30))
        self.w_occupancy = float(weights.get("occupancy_weight", 0.25))
        self.w_congestion = float(weights.get("congestion_weight", 0.20))
        self.w_confidence = float(weights.get("confidence_weight", 0.15))
        self.w_accessibility = float(weights.get("accessibility_weight", 0.10))

        bands = bands or {}
        self.normal_max = float(bands.get("normal_max", NORMAL_MAX))
        self.watch_max = float(bands.get("watch_max", WATCH_MAX))
        self.high_risk_max = float(bands.get("high_risk_max", HIGH_RISK_MAX))

    # ------------------------------------------------------------------
    def compute(self, zone_state: Dict[str, Any], profile: str = "STANDARD") -> Tuple[float, List[str]]:
        """Return (risk_score 0-100, reasons)."""
        score = 0.0
        reasons: List[str] = []

        state = zone_state.get("state", "NORMAL")
        confidence = float(zone_state.get("confidence", 1.0))
        occupancy = int(zone_state.get("occupancy", 0) or 0)
        temperature = zone_state.get("temperature")
        blocked = bool(zone_state.get("blocked", False))
        stale = bool(zone_state.get("stale", False))
        zone_type = zone_state.get("type", "zone")

        # --- Hazard component (from fused state + raw readings) ---
        hazard_score = 0.0
        if state == "RESTRICTED":
            hazard_score = 90.0
        elif state == "WATCH":
            hazard_score = 50.0
        elif state == "UNCERTAIN":
            hazard_score = 40.0
        else:
            hazard_score = 10.0

        if temperature is not None and temperature >= 35.0:
            hazard_score = max(hazard_score, 95.0)
            reasons.append("temperature anomaly")

        score += hazard_score * self.w_hazard

        # --- Occupancy component ---
        occ_score = 0.0
        if occupancy >= 8:
            occ_score = 100.0
            reasons.append("high occupancy")
        elif occupancy > 5:
            occ_score = 70.0
            reasons.append("rising occupancy")
        elif occupancy > 2:
            occ_score = 35.0
        score += occ_score * self.w_occupancy

        # --- Congestion component (occupancy density proxy) ---
        congestion_score = min(100.0, occ_score * 0.9)
        score += congestion_score * self.w_congestion

        # --- Confidence component: low confidence raises risk ---
        conf_penalty = (1.0 - confidence) * 100.0
        score += conf_penalty * self.w_confidence
        if confidence < 0.5:
            reasons.append("low sensor confidence")

        # --- Accessibility constraints ---
        acc_penalty = 0.0
        if profile == "ACCESSIBLE":
            if zone_type == "stairs":
                acc_penalty = 60.0
                reasons.append("inaccessible (stairs)")
            elif zone_type in ("zone", "corridor") and blocked:
                acc_penalty = 30.0
        score += acc_penalty * self.w_accessibility

        # --- Hard overrides ---
        if blocked:
            score = max(score, 85.0)
            if "manually restricted" not in reasons:
                reasons.append("manually restricted")
        if stale:
            score = max(score, 50.0)
            reasons.append("stale sensor data")

        score = max(0.0, min(100.0, score))
        return round(score, 1), reasons

    # ------------------------------------------------------------------
    def classify(self, score: float) -> str:
        if score <= self.normal_max:
            return "NORMAL"
        if score <= self.watch_max:
            return "WATCH"
        if score <= self.high_risk_max:
            return "HIGH RISK"
        return "RESTRICTED"
