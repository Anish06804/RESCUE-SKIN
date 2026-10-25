"""Routing engine for RESCUE SKIN.

Implements A* (default) and Dijkstra pathfinding over the building graph,
considering distance, risk, congestion, blocked/uncertain zones, exit
availability and the selected accessibility profile.

The engine returns the lowest-cost path from the START zone to the nearest
safe exit. Route recalculation is triggered whenever risk, blockage or the
routing profile changes.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from backend.config.config import Config
from backend.core.accessibility import ACCESSIBLE, STANDARD, edge_allowed, node_allowed


@dataclass
class RouteResult:
    nodes: List[str]
    edges: List[Dict[str, Any]]
    total_distance: float
    total_risk: float
    exit_id: str
    profile: str
    reason: str = ""
    algorithm: str = "A*"
    feasible: bool = True


class RouteEngine:
    def __init__(self, config: Config):
        self.config = config
        routing = config.routing or {}
        self.risk_multiplier = float(routing.get("risk_cost_multiplier", 2.5))
        self.blocked_penalty = float(routing.get("blocked_cost_penalty", 2000.0))
        self.uncertain_penalty = float(routing.get("uncertain_cost_penalty", 1200.0))
        self.accessible_bonus = float(routing.get("accessible_preference_bonus", -0.6))
        self.stairs_penalty = float(routing.get("stairs_penalty", 2000.0))

        self._adj: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
        self._coords: Dict[str, Tuple[float, float]] = {}
        self._edge_lookup: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._build_graph()

    # ------------------------------------------------------------------
    def _build_graph(self) -> None:
        for z in self.config.zones():
            self._coords[z["id"]] = (float(z.get("x", 0)), float(z.get("y", 0)))
        for e in self.config.edges():
            a, b = e["from"], e["to"]
            self._adj.setdefault(a, []).append((b, e))
            self._adj.setdefault(b, []).append((a, e))
            self._edge_lookup[(a, b)] = e
            self._edge_lookup[(b, a)] = e

    # ------------------------------------------------------------------
    def _heuristic(self, a: str, b: str) -> float:
        xa, ya = self._coords.get(a, (0.0, 0.0))
        xb, yb = self._coords.get(b, (0.0, 0.0))
        return math.hypot(xa - xb, ya - yb)

    def _edge_between(self, a: str, b: str) -> Optional[Dict[str, Any]]:
        return self._edge_lookup.get((a, b))

    # ------------------------------------------------------------------
    def _node_cost(self, node_id: str, zones: Dict[str, Any], profile: str) -> float:
        """Cost to enter a zone node.

        Blocked or RESTRICTED zones are non-traversable (removed from route
        calculation) per the safety requirements: a restricted exit/zone must
        never be part of an evacuation route.
        """
        zone = zones.get(node_id)
        if zone is None:
            return 0.0
        if zone.get("blocked") or zone.get("state") == "RESTRICTED":
            return math.inf
        if zone.get("stale"):
            return self.uncertain_penalty
        if profile == ACCESSIBLE and zone.get("type") == "stairs":
            return self.stairs_penalty
        risk = float(zone.get("risk_score", 0) or 0)
        return risk * self.risk_multiplier

    def _edge_cost(self, a: str, b: str, edge: Dict[str, Any],
                   profile: str, zones: Dict[str, Any]) -> float:
        cost = float(edge.get("distance", 1))
        if not edge_allowed(edge, profile):
            cost += self.stairs_penalty
        if profile == ACCESSIBLE and edge.get("accessible", True):
            cost *= (1.0 + self.accessible_bonus)  # prefer accessible edges
        # Congestion/risk of the destination node is charged in _node_cost,
        # but a high-risk edge still adds a small distance premium.
        return max(cost, 0.01)

    # ------------------------------------------------------------------
    def _search(self, start: str, goal: str, zones: Dict[str, Any],
                profile: str, use_astar: bool) -> Tuple[Optional[List[str]], float]:
        if start not in self._adj or goal not in self._adj:
            return None, math.inf

        open_set: List[Tuple[float, float, str, List[str]]] = []
        h0 = self._heuristic(start, goal) if use_astar else 0.0
        heapq.heappush(open_set, (h0, 0.0, start, [start]))
        g_score: Dict[str, float] = {start: 0.0}
        visited: set[str] = set()

        while open_set:
            _f, g, node, path = heapq.heappop(open_set)
            if node == goal:
                return path, g
            if node in visited:
                continue
            visited.add(node)

            for neighbor, edge in self._adj.get(node, []):
                if neighbor in visited:
                    continue
                if not edge_allowed(edge, profile):
                    continue
                if not node_allowed(self.config.zone_by_id(neighbor) or {}, profile):
                    continue
                tentative_g = (g
                               + self._edge_cost(node, neighbor, edge, profile, zones)
                               + self._node_cost(neighbor, zones, profile))
                if tentative_g < g_score.get(neighbor, math.inf):
                    g_score[neighbor] = tentative_g
                    h = self._heuristic(neighbor, goal) if use_astar else 0.0
                    heapq.heappush(open_set, (tentative_g + h, tentative_g,
                                              neighbor, path + [neighbor]))
        return None, math.inf

    # ------------------------------------------------------------------
    def _path_edges(self, nodes: List[str]) -> List[Dict[str, Any]]:
        edges: List[Dict[str, Any]] = []
        for i in range(len(nodes) - 1):
            edge = self._edge_between(nodes[i], nodes[i + 1])
            if edge:
                edges.append({
                    "from": nodes[i],
                    "to": nodes[i + 1],
                    "distance": edge.get("distance", 0),
                    "accessible": edge.get("accessible", True),
                })
        return edges

    def _path_risk(self, nodes: List[str], zones: Dict[str, Any]) -> float:
        return sum(float(zones.get(n, {}).get("risk_score", 0) or 0) for n in nodes)

    # ------------------------------------------------------------------
    def calculate(self, zones: Dict[str, Any], profile: str = STANDARD,
                  algorithm: str = "A*") -> RouteResult:
        """Compute the best route from START to the nearest safe exit.

        zones: dict of zone_id -> zone snapshot (must include risk_score,
               blocked, stale, type, label).
        """
        start_zone = self.config.start_zone()
        exits = self.config.exit_zones()
        start_id = start_zone["id"] if start_zone else "START"

        use_astar = algorithm.upper() in ("ASTAR", "A*")
        algo_name = "A*" if use_astar else "Dijkstra"

        best: Optional[RouteResult] = None
        best_cost_val: float = math.inf

        for exit_zone in exits:
            exit_id = exit_zone["id"]
            # Skip exits that are fully blocked/restricted unless no other
            # exit exists (in which case the high node cost still applies).
            path, cost = self._search(start_id, exit_id, zones, profile, use_astar)
            if path is None:
                continue

            distance = 0.0
            for i in range(len(path) - 1):
                e = self._edge_between(path[i], path[i + 1])
                if e:
                    distance += float(e.get("distance", 0))
            total_risk = self._path_risk(path, zones)

            result = RouteResult(
                nodes=path,
                edges=self._path_edges(path),
                total_distance=round(distance, 1),
                total_risk=round(total_risk, 1),
                exit_id=exit_id,
                profile=profile,
                algorithm=algo_name,
                feasible=True,
            )
            if best is None or cost < best_cost_val:
                best = result
                best_cost_val = cost

        if best is None:
            # No feasible path to any exit.
            return RouteResult(
                nodes=[start_id],
                edges=[],
                total_distance=0.0,
                total_risk=0.0,
                exit_id="",
                profile=profile,
                reason="No feasible route to any exit.",
                algorithm=algo_name,
                feasible=False,
            )

        best.reason = self._reason_string(best, zones)
        return best

    # ------------------------------------------------------------------
    @staticmethod
    def _reason_string(route: RouteResult, zones: Dict[str, Any]) -> str:
        parts = [f"{route.algorithm} route to {route.exit_id}"]
        parts.append(f"{len(route.nodes)} nodes, {route.total_distance}m")
        if route.total_risk:
            parts.append(f"cumulative risk {route.total_risk}")
        if route.profile == ACCESSIBLE:
            parts.append("accessibility-aware (ramps, no stairs)")
        return "; ".join(parts)
