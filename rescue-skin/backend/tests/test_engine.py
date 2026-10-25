"""Automated tests for the RESCUE SKIN core engines.

Run with:  python -m unittest discover -s backend/tests -v
These tests exercise the engines directly (no server, no hardware).
"""

import sys
import os
import time
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.config.config import Config  # noqa: E402
from backend.core.state_manager import StateManager  # noqa: E402
from backend.core.sensor_fusion import SensorFusion  # noqa: E402
from backend.core.risk_engine import RiskEngine  # noqa: E402
from backend.core.route_engine import RouteEngine  # noqa: E402


class CoreEnginesTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = Config.load()
        cls.state = StateManager(cls.config)
        cls.fusion = SensorFusion(cls.config.thresholds)
        cls.risk = RiskEngine(cls.config.risk_weights,
                              bands={b["label"]: b["max"] for b in cls.config.map_data.get("risk_bands", [])})
        cls.router = RouteEngine(cls.config)

    # ---- 1. Normal route ----
    def test_01_normal_route(self):
        zones = {zid: self._snapshot(zid, "NORMAL", 1.0, 0, False, False, "zone")
                 for zid in self.state.zones}
        res = self.router.calculate(zones, profile="STANDARD", algorithm="A*")
        self.assertTrue(res.feasible, "normal route should be feasible")
        self.assertIn("ExitA", res.nodes or [], "should reach an exit")
        self.assertEqual(res.algorithm, "A*")

    # ---- Dijkstra alternative ----
    def test_dijkstra_route(self):
        zones = {zid: self._snapshot(zid, "NORMAL", 1.0, 0, False, False, "zone")
                 for zid in self.state.zones}
        res = self.router.calculate(zones, profile="STANDARD", algorithm="Dijkstra")
        self.assertTrue(res.feasible)
        self.assertEqual(res.algorithm, "Dijkstra")

    # ---- 2. Restricted zone ----
    def test_02_restricted_zone(self):
        zones = {zid: self._snapshot(zid, "NORMAL", 1.0, 0, False, False, "zone")
                 for zid in self.state.zones}
        zones["C"]["blocked"] = True
        zones["C"]["state"] = "RESTRICTED"
        zones["C"]["risk_score"] = 90.0
        res = self.router.calculate(zones, profile="STANDARD")
        self.assertTrue(res.feasible)
        self.assertNotIn("C", res.nodes, "restricted zone C should not be on the route")

    # ---- 3. Blocked exit ----
    def test_03_blocked_exit(self):
        zones = {zid: self._snapshot(zid, "NORMAL", 1.0, 0, False, False, "zone")
                 for zid in self.state.zones}
        zones["ExitA"]["blocked"] = True
        zones["ExitA"]["state"] = "RESTRICTED"
        res = self.router.calculate(zones, profile="STANDARD")
        self.assertTrue(res.feasible, "should still reach Exit B")
        self.assertEqual(res.exit_id, "ExitB", "should reroute to Exit B when Exit A blocked")

    # ---- 4. Alternative path around blocked intermediate zones ----
    def test_04_alternative_path(self):
        zones = {zid: self._snapshot(zid, "NORMAL", 1.0, 0, False, False, "zone")
                 for zid in self.state.zones}
        # Block the central corridor path through B and C
        for zid in ("B", "C"):
            zones[zid]["blocked"] = True
            zones[zid]["state"] = "RESTRICTED"
        res = self.router.calculate(zones, profile="STANDARD")
        self.assertTrue(res.feasible, "should still reach an exit")
        self.assertNotIn("B", res.nodes, "blocked zone B should not be on the route")
        self.assertNotIn("C", res.nodes, "blocked zone C should not be on the route")

    # ---- 5. Accessibility route (avoid stairs, use ramp to Exit B) ----
    def test_05_accessibility_route(self):
        zones = {zid: self._snapshot(zid, "NORMAL", 1.0, 0, False, False, "zone")
                 for zid in self.state.zones}
        # Exit A unavailable -> must reach Exit B via the ramp (no stairs)
        zones["ExitA"]["blocked"] = True
        zones["ExitA"]["state"] = "RESTRICTED"
        res_acc = self.router.calculate(zones, profile="ACCESSIBLE")
        self.assertTrue(res_acc.feasible, "accessible route to Exit B should exist")
        self.assertEqual(res_acc.exit_id, "ExitB")
        self.assertNotIn("Stairs", res_acc.nodes, "accessible route must avoid stairs")
        self.assertIn("Ramp", res_acc.nodes, "accessible route should use the ramp")

    # ---- 6. Sensor uncertainty (stale data) ----
    def test_06_sensor_uncertainty(self):
        old = time.time() - 20  # far older than stale_seconds (6)
        fused = self.fusion.fuse("C", {"temperature": 26.0, "occupancy": 1}, old)
        self.assertEqual(fused["state"], "UNCERTAIN")
        self.assertEqual(fused["confidence"], 0.0)
        self.assertTrue(fused["stale"])

    # ---- 7. Node failure ----
    def test_07_node_failure(self):
        # Simulate NODE_01 (Zone A) going offline -> zone A stale/uncertain
        import asyncio
        async def run():
            await self.state.set_node_offline("NODE_01", "node failure")
            snap = await self.state.snapshot()
            self.assertFalse(snap["nodes"]["NODE_01"]["online"])
            self.assertTrue(snap["zones"]["A"]["stale"])
            self.assertEqual(snap["zones"]["A"]["state"], "UNCERTAIN")
        asyncio.run(run())

    # ---- 8. Communication failure ----
    def test_08_communication_failure(self):
        import asyncio
        async def run():
            await self.state.set_link_status("NODE_01-NODE_02", False, "simulated")
            snap = await self.state.snapshot()
            self.assertFalse(snap["links"]["NODE_01-NODE_02"]["online"])
            events = [e["type"] for e in snap["events"]]
            self.assertIn("LINK_FAILURE", events)
        asyncio.run(run())

    # ---- 9. Route recalculation ----
    def test_09_route_recalculation(self):
        zones = {zid: self._snapshot(zid, "NORMAL", 1.0, 0, False, False, "zone")
                 for zid in self.state.zones}
        r1 = self.router.calculate(zones, profile="STANDARD")
        zones["ExitA"]["blocked"] = True
        zones["ExitA"]["state"] = "RESTRICTED"
        r2 = self.router.calculate(zones, profile="STANDARD")
        self.assertNotEqual(r1.exit_id, r2.exit_id, "route should change when an exit is blocked")

    # ---- 10. Reset / recovery ----
    def test_10_reset_recovery(self):
        import asyncio
        async def run():
            await self.state.set_node_offline("NODE_03", "node failure")
            await self.state.set_zone_blocked("C", True, "hazard")
            await self.state.set_link_status("NODE_01-NODE_02", False, "fail")
            # recover
            await self.state.set_node_online("NODE_03")
            await self.state.set_zone_blocked("C", False, "cleared")
            await self.state.set_link_status("NODE_01-NODE_02", True, "restored")
            snap = await self.state.snapshot()
            self.assertTrue(snap["nodes"]["NODE_03"]["online"])
            self.assertFalse(snap["zones"]["C"]["blocked"])
            self.assertTrue(snap["links"]["NODE_01-NODE_02"]["online"])
        asyncio.run(run())

    # ---- helpers ----
    def _snapshot(self, zid, state, confidence, occupancy, blocked, stale, ztype):
        return {
            "zone_id": zid, "label": zid, "type": ztype, "x": 0, "y": 0,
            "state": state, "confidence": confidence, "risk_score": 0.0,
            "risk_reasons": [], "blocked": blocked, "stale": stale,
            "temperature": 25.0, "occupancy": occupancy, "presence": False,
            "pressure": 0.6, "proximity": 2.0,
        }


if __name__ == "__main__":
    unittest.main()
