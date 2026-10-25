/*
 * RESCUE SKIN — ESP32-WROOM-32 sensor node (placeholder sketch)
 * VK26-IITH-SC-0046 · Stage 2 prototype
 *
 * This is a placeholder. It is NOT compiled or uploaded in the software
 * prototype. The SensorSimulator stands in for this node in simulation mode.
 *
 * Intended behaviour (to be implemented when hardware is connected):
 *  - Read VL53L0X (proximity), BME280 (temperature/pressure), FSR (presence)
 *  - Estimate occupancy locally (edge-first, no video, no faces)
 *  - Publish a JSON reading via ESP-NOW to the edge computer (Raspberry Pi)
 *  - Report node health and communication status
 */

#include <ESP32 h=0>

const char* NODE_ID = "NODE_01";
const char* ZONE    = "A";

// Placeholder pin assignments
#define PIN_VL53_SDA 21
#define PIN_VL53_SCL 22
#define PIN_BME_SDA  23
#define PIN_BME_SCL  19
#define PIN_FSR      34  // ADC

void setup() {
  Serial.begin(115200);
  // Init I2C, VL53L0X, BME280, ESP-NOW
}

void loop() {
  /*
   float temp = bme.readTemperature();
   float pres = bme.readPressure() / 100.0F;
   float prox = vl53.readRange();
   uint16_t fsr = analogRead(PIN_FSR);
   bool presence = fsr > FSR_THRESHOLD;
   int occupancy = estimateOccupancy(presence, prox);
   
   StaticJsonDocument<200> doc;
   doc["node_id"] = NODE_ID;
   doc["zone"] = ZONE;
   doc["temperature"] = temp;
   doc["pressure"] = pres;
   doc["proximity"] = prox;
   doc["presence"] = presence;
   doc["occupancy"] = occupancy;
   doc["timestamp"] = now();
   
   String payload;
   serializeJson(doc, payload);
   esp_now_send(broadcastAddr, (uint8_t*)payload.c_str(), payload.length());
   */
  delay(1000);
}