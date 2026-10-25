# RESCUE SKIN — Hardware Integration

**VK26-IITH-SC-0046** · Stage 2 prototype

## Target hardware

| Role | Hardware |
|------|----------|
| Sensor node | ESP32-WROOM-32 |
| Proximity | VL53L0X Time-of-Flight |
| Environment | BME280 (temperature, humidity, pressure) |
| Presence | FSR (force-sensitive resistor) |
| Edge computer | Raspberry Pi 4 |
| Camera | Pi Camera module (occupancy only, edge-first) |
| Node comms | ESP-NOW |
| Visual guidance | WS2812B addressable LEDs |
| Audio | I2S amplifier + speaker |
| Haptic | DRV2605L-compatible actuator |

## Software ⇔ hardware mapping

The backend abstracts hardware behind interfaces in
`backend/hardware/interfaces.py`. To move from simulation to hardware:

1. Set `RESCUE_SKIN_MODE=hardware` in `.env`.
2. Wire the real providers:
   - `ESP32SensorProvider` ← real ESP32 + ESP-NOW sensor readings
   - `WS2812BController` ← real WS2812B LED strip
   - `I2SAudioController` ← real I2S amp + speaker
   - `DRV2605LController` ← real haptic actuator
3. The core engines (risk, route, accessibility) do **not** change.

## ESP32 sensor node (`hardware/esp32/`)

The placeholder sketch `esp32_sensor_node.ino` shows where the real firmware
would live: read VL53L0X, BME280, FSR; package a JSON reading; broadcast via
ESP-NOW to the Raspberry Pi edge computer; blink a status LED.

It is **not compiled or uploaded** in this prototype. In software-only mode the
`SensorSimulator` stands in for these nodes.

## Raspberry Pi edge computer (`hardware/raspberry_pi/`)

The placeholder `edge_computer.py` shows where the real backend would run on
the Pi: receive ESP-NOW packets, run the FastAPI backend, drive WS2812B LEDs,
I2S audio, and DRV2605L haptics, and serve the dashboard locally.

## Camera / privacy

The Pi Camera is intended for edge-only occupancy counting:
- Process frames locally on the Pi.
- Keep only `occupancy_count` and derived information.
- Do **not** store video. Do **not** run facial recognition. Do **not**
  identify individuals.

## Transition checklist

- [ ] Backend runs in `simulation` on a laptop (this prototype).
- [ ] Real ESP32 nodes publish readings over ESP-NOW to the Pi.
- [ ] `ESP32SensorProvider` replaces `SimulationSensorProvider`.
- [ ] `WS2812BController`, `I2SAudioController`, `DRV2605LController`
  replace their simulated counterparts.
- [ ] Verify route/risk engines behave identically with real inputs.

## Notes

ESP-NOW is an Espressif proprietary protocol between ESP32 devices. The Pi
does not natively speak ESP-NOW; the target design uses an ESP32 as a
gateway/bridge to the Pi (UART, SPI, or Wi-Fi), or an ESP32-based edge node.
This bridge is not implemented in the software prototype.
