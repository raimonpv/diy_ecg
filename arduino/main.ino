/**
 * @brief Streams ECG analog readings over Bluetooth and Serial at fixed rate.
 *
 * - Samples ECG signal from ECG_PIN at FS Hz
 * - Sends data as: index,value
 * - Outputs to both Bluetooth module and Serial Monitor
 *
 * Wiring:
 *   - ECG signal -> A0
 *   - BT RX -> pin 4 (TX) (w/ voltage divider)
 */

#include <SoftwareSerial.h>

SoftwareSerial BT(2, 4); 

const int ECG_PIN = A0;

const uint16_t FS = 200;                   // Sampling frequency (Hz)
const uint32_t PERIOD_US = 1000000UL / FS; // Sampling period (microseconds)

uint32_t next_us = 0;
uint32_t i = 0;

void setup() {
  Serial.begin(115200);
  BT.begin(115200);                    
  next_us = micros();
}

void loop() {
  uint32_t now = micros();
  if ((int32_t)(now - next_us) >= 0) {
    next_us += PERIOD_US;

    int v = analogRead(ECG_PIN);
    
    // Send "index,value"
    BT.print(i);
    BT.print(',');
    BT.println(v);

    Serial.print(i);
    Serial.print(',');
    Serial.println(v);

    i++;
  }
}