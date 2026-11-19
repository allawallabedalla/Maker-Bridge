/* MB2-TEMP-001: ESP32 (Arduino) + ADS1220 + PT100 3-Leiter. Ausgabe je Messwert ueber USB-Seriell:
 *   zeit_ms;code_a;code_b;offset_code;fehlerbits;r_ohm;t_c
 * Rohwerte und Rechnung stehen getrennt in der Zeile; die Auswertung ist nachtraeglich wiederholbar.
 * Pinbelegung ist eine ANNAHME (Schaltplan fehlt noch) - vor dem Aufbau anpassen.
 */
#include <Arduino.h>
#include <SPI.h>
#include "ads1220.h"

static const int PIN_CS = 5;     /* Annahme */
static const int PIN_DRDY = 4;   /* Annahme */
static const SPISettings SPI_ADS(1000000, MSBFIRST, SPI_MODE1);   /* nur Modus 1 (SBAS501D S. 36) */

static void hw_transfer(void *, const uint8_t *tx, uint8_t *rx, int n)
{
    SPI.beginTransaction(SPI_ADS);
    digitalWrite(PIN_CS, LOW);
    for (int i = 0; i < n; i++) {
        uint8_t r = SPI.transfer(tx[i]);
        if (rx)
            rx[i] = r;
    }
    digitalWrite(PIN_CS, HIGH);
    SPI.endTransaction();
}

static int hw_drdy(void *, uint32_t timeout_ms)
{
    uint32_t t0 = millis();
    while (digitalRead(PIN_DRDY) == HIGH)
        if (millis() - t0 > timeout_ms)
            return 0;
    return 1;
}

static void hw_us(void *, uint32_t us) { delayMicroseconds(us); }
static uint32_t hw_ms(void *) { return millis(); }

static ads1220_t adc = {hw_transfer, hw_drdy, hw_us, hw_ms, 0, 0};
static uint32_t naechster = 0;

void setup()
{
    Serial.begin(115200);
    pinMode(PIN_CS, OUTPUT);
    digitalWrite(PIN_CS, HIGH);
    pinMode(PIN_DRDY, INPUT);
    SPI.begin();
    int f = ads1220_start(&adc);
    f |= ads1220_offset_kalibrieren(&adc, OFFSET_MITTEL);
    Serial.printf("# MB2-TEMP-001 gain=%d rref=%.1f idac_ua=%d tausch=%d offset_code=%ld start_fehler=%d\n",
                  PGA_GAIN, RREF_OHM, IDAC_UA, IDAC_TAUSCH, (long)adc.offset_code, f);
    Serial.println("# zeit_ms;code_a;code_b;offset_code;fehlerbits;r_ohm;t_c");
}

void loop()
{
    if ((int32_t)(millis() - naechster) < 0)
        return;
    naechster += 1000 / MESSRATE_HZ;
    ads1220_messwert_t m = ads1220_messen(&adc);
    Serial.printf("%lu;%ld;%ld;%ld;%d;%.5f;%.4f\n", (unsigned long)m.zeit_ms, (long)m.code_a, (long)m.code_b,
                  (long)m.offset_code, m.fehler, m.r_ohm, m.t_c);
}
