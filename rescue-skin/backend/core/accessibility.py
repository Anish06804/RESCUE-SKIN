"""Accessibility routing profiles for RESCUE SKIN.

The system never assumes anything about a person's identity. It only acts on
an explicitly selected assistance requirement. The ACCESSIBLE profile removes
stairs/inaccessible edges and prefers ramps and accessible corridors.
"""

from __future__ import annotations

STANDARD = "STANDARD"
ACCESSIBLE = "ACCESSIBLE"

ALL_PROFILES = [STANDARD, ACCESSIBLE]


def edge_allowed(edge: dict, profile: str) -> bool:
    """Whether a traversable edge may be used under the given profile."""
    if profile == ACCESSIBLE and not edge.get("accessible", True):
        return False
    return True


def node_allowed(zone: dict, profile: str) -> bool:
    """Whether a zone node may be entered under the given profile."""
    if profile == ACCESSIBLE and zone.get("type") == "stairs":
        return False
    return True
