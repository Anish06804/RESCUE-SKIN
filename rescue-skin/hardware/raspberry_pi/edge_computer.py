"""
RESCUE SKIN — Raspberry Pi 4 edge computer (placeholder)
VK26-IITH-SC-0046 · Stage 2 prototype

This is a placeholder. In the software prototype the FastAPI backend in
backend/main.py runs on a laptop in simulation mode. When real hardware is
connected, this file shows where the Pi-side integration would live:

- Receive ESP-NOW readings from ESP32 sensor nodes (via an ESP32 gateway
  bridge over UART/SPI/Wi-Fi).
- Run the RESCUE SKIN backend locally (sensor fusion, risk, routing).
- Drive WS2812B LEDs, I2S amplifier + speaker, and DRV2605L haptics.
- Serve the local dashboard on the Pi's network interface.
"""

import asyncio

# from backend.main import app  # the FastAPI backend runs here
# from hardware.interfaces import ESP32SensorProvider, WS2812BController, \
#     I2SAudioController, DRV2605LController


async def main():
    # sensor_provider = ESP32SensorProvider(esp_now_gateway)
    # led = WS2812BController(...)
    # audio = I2SAudioController(...)
    # haptic = DRV2605LController(...)
    # await uvicorn run app on 0.0.0.0:8000
    print("Placeholder: Pi edge computer would run the RESCUE SKIN backend here.")


if __name__ == "__main__":
    asyncio.run(main())
