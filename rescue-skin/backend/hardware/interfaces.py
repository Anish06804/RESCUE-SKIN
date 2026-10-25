"""Hardware abstraction interfaces for RESCUE SKIN.

These interfaces let the core routing / risk engines stay identical when
moving from simulation mode to hardware mode. Providers for real hardware
(ESP32 sensor provider, WS2812B LED controller, etc.) implement the same
ABCs as the simulated providers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Sensors
# ---------------------------------------------------------------------------

class SensorInterface(ABC):
    @abstractmethod
    async def read_node(self, node_id: str) -> Dict[str, Any]:
        """Return a single sensor reading dict for a node."""
        ...

    @abstractmethod
    async def read_all(self) -> Dict[str, Dict[str, Any]]:
        """Return readings for every node."""
        ...

    @abstractmethod
    async def is_online(self, node_id: str) -> bool:
        ...


class SimulationSensorProvider(SensorInterface):
    def __init__(self, simulator):
        self.simulator = simulator

    async def read_node(self, node_id: str) -> Dict[str, Any]:
        readings = await self.read_all()
        return readings.get(node_id, {"error": "unknown node"})

    async def read_all(self) -> Dict[str, Dict[str, Any]]:
        return self.simulator.generate_readings()

    async def is_online(self, node_id: str) -> bool:
        reading = await self.read_node(node_id)
        return reading.get("online", False)


class ESP32SensorProvider(SensorInterface):
    """Placeholder for real ESP32 + ESP-NOW sensor hardware.

    Not implemented in simulation mode. Instantiate only when hardware is
    connected and configured (RESCUE_SKIN_MODE=hardware).
    """

    def __init__(self, adapter):
        self.adapter = adapter

    async def read_node(self, node_id: str) -> Dict[str, Any]:
        raise NotImplementedError("ESP32 hardware provider not wired yet")

    async def read_all(self) -> Dict[str, Dict[str, Any]]:
        raise NotImplementedError("ESP32 hardware provider not wired yet")

    async def is_online(self, node_id: str) -> bool:
        return False


# ---------------------------------------------------------------------------
# Guidance outputs
# ---------------------------------------------------------------------------

class LEDGuidanceInterface(ABC):
    @abstractmethod
    async def set_path(self, nodes: List[str], active: bool = True) -> None:
        ...

    @abstractmethod
    async def highlight_zone(self, zone_id: str, state: str) -> None:
        ...

    @abstractmethod
    async def clear(self) -> None:
        ...


class SimulatedLEDController(LEDGuidanceInterface):
    """Simulation-mode WS2812B LED controller. No real LEDs are driven."""

    async def set_path(self, nodes: List[str], active: bool = True) -> None:
        print(f"[SIM LED] path {'active' if active else 'cleared'}: {' -> '.join(nodes)}")

    async def highlight_zone(self, zone_id: str, state: str) -> None:
        print(f"[SIM LED] zone {zone_id} -> {state}")

    async def clear(self) -> None:
        print("[SIM LED] cleared")


class WS2812BController(LEDGuidanceInterface):
    """Placeholder for real WS2812B LED driver. Not implemented in sim."""

    async def set_path(self, nodes: List[str], active: bool = True) -> None:
        raise NotImplementedError("WS2812B hardware not wired yet")

    async def highlight_zone(self, zone_id: str, state: str) -> None:
        raise NotImplementedError("WS2812B hardware not wired yet")

    async def clear(self) -> None:
        raise NotImplementedError("WS2812B hardware not wired yet")


class AudioGuidanceInterface(ABC):
    @abstractmethod
    async def speak(self, text: str) -> None:
        ...

    @abstractmethod
    async def stop(self) -> None:
        ...


class SimulatedAudioController(AudioGuidanceInterface):
    """Simulation-mode audio guidance. Emits the would-be spoken text."""

    async def speak(self, text: str) -> None:
        print(f"[SIM AUDIO] {text}")

    async def stop(self) -> None:
        print("[SIM AUDIO] stopped")


class I2SAudioController(AudioGuidanceInterface):
    """Placeholder for real I2S amplifier + speaker."""

    async def speak(self, text: str) -> None:
        raise NotImplementedError("I2S audio hardware not wired yet")

    async def stop(self) -> None:
        raise NotImplementedError("I2S audio hardware not wired yet")


class HapticGuidanceInterface(ABC):
    @abstractmethod
    async def vibrate(self, pattern: str) -> None:
        ...

    @abstractmethod
    async def stop(self) -> None:
        ...


class SimulatedHapticController(HapticGuidanceInterface):
    """Simulation-mode haptic actuator (DRV2605L-compatible)."""

    async def vibrate(self, pattern: str) -> None:
        print(f"[SIM HAPTIC] pattern {pattern}")

    async def stop(self) -> None:
        print("[SIM HAPTIC] stopped")


class DRV2605LController(HapticGuidanceInterface):
    """Placeholder for real DRV2605L haptic driver."""

    async def vibrate(self, pattern: str) -> None:
        raise NotImplementedError("DRV2605L hardware not wired yet")

    async def stop(self) -> None:
        raise NotImplementedError("DRV2605L hardware not wired yet")
