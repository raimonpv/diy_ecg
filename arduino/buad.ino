/**
 * Bridge between Arduino Serial Monitor and JDY-31 Bluetooth module.
 *
 * Wiring:
 *   - JDY-31 TX -> Arduino pin 2 (RX)
 *   - JDY-31 RX -> Arduino pin 4 (TX)
 *
 * Usage:
 *   1. Open Serial Monitor at 9600 baud.
 *   2. Test connection with: AT+VERSION
 *   3. Change baud rate with: AT+BAUDx  (see module manual: https://myosuploads3.banggood.com/products/20190129/20190129043725SKUA87502.pdf)
 *   4. Power-cycle the module after changing baud rate.
 *   5. Update BT.begin() below to match the new baud rate.
 */

 #include <SoftwareSerial.h>

SoftwareSerial BT(2, 4); // RX, TX

void setup() {
  Serial.begin(9600);
  BT.begin(115200);  // Must match current JDY-31 baud rate
  Serial.println("JDY-31 Test Ready");
}

void loop() {
  // Forward data from Serial Monitor -> Bluetooth module
  while (Serial.available()) {
    BT.write(Serial.read());
  }

  // Forward data from Bluetooth module -> Serial Monitor
  while (BT.available()) {
    Serial.write(BT.read());
  }
}
