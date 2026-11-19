# Schnittstelle Sensormodul MB2-TEMP-001 ↔ Host

**Systemgrenze (Entscheidung 19.11.2026):** Das Modul ist eine kleine Messplatine mit ADS1220 und Referenzwiderstand. Sie sitzt **direkt am Host** (ESP32, Raspberry Pi o. ä.).
Nach draußen geht nur das 3-adrige Kabel zum PT100 im Strahlungsschutz.
Zeitstempel, Speicherung und Übertragung macht der Host.

## Anschluss Host

| Modul (ADS1220) | Funktion | ESP32 (Arduino-Standard-SPI) | Raspberry Pi (SPI0, Stiftleiste) |
|---|---|---|---|
| SCLK | Takt | GPIO18 | GPIO11 (Pin 23) |
| DIN | Daten zum Modul | GPIO23 | GPIO10 / MOSI (Pin 19) |
| DOUT/DRDY | Daten vom Modul | GPIO19 | GPIO9 / MISO (Pin 21) |
| CS | Auswahl, aktiv low | GPIO5 (Annahme) | CE0 = GPIO8 (Pin 24) |
| DRDY | Daten bereit, aktiv low (optional) | GPIO4 (Annahme) | nicht nötig: feste Wartezeit |
| AVDD, DVDD | 3,3 V | 3V3 | 3,3 V (Pin 1) |
| AVSS, DGND | Masse | GND | GND (Pin 6) |

- **SPI Modus 1** (CPOL = 0, CPHA = 1), MSB zuerst, 1 MHz. Laut SBAS501D (S. 9, t_c(SC) ≥ 150 ns) wären bis 6,6 MHz zulässig.
- **Versorgung 3,3 V** ist Teil der Auslegung. Die IDAC-Compliance (AVDD − 0,9 V) und der PGA-Bereich sind für 3,3 V gerechnet. Bei 5 V muss MK4 neu gerechnet werden.
- **Leitung Host ↔ Modul so kurz wie möglich.** Empfehlung: aufgesteckt oder höchstens etwa 20 cm. SPI ist ein Platinenbus. Das ist eine Erfahrungsregel, nicht aus dem Datenblatt.
- **Fühlerkabel:** 3 gleiche Adern. Die Länge ist durch die 3-Leiter-Schaltung unkritisch, solange die Adern gleich sind. **Kalibriert wird mit dem endgültigen Kabel** (K-KABEL). Danach das Kabel nicht kürzen oder tauschen.

## Software

| Host | Datei | Stand |
|---|---|---|
| alle | `firmware/mb2_temp_001/ads1220.h`, `rtd_rechnung.h`, `config.h` | Treiber und Rechnung, hardwareunabhängig über Rückruffunktionen |
| ESP32 | `firmware/mb2_temp_001/mb2_temp_001.ino` | Beispiel, Zeit = Millisekunden seit Start (für echte Uhrzeit braucht der ESP32 NTP oder eine Uhr) |
| Raspberry Pi | `firmware/mb2_temp_001/rpi_mb2_temp_001.c` | Beispiel mit `/dev/spidev0.0`, Zeitstempel in UTC. Wartet fest 60 ms je Wandlung statt DRDY |

Ausgabe je Messwert, eine Zeile alle 10 s, auch bei Fehlern:
`zeit;code_a;code_b;offset_code;fehlerbits;r_ohm;t_roh_c;t_c`

Fehlerbits:
- 1 = übersteuert
- 2 = unplausibel (Leitungsbruch, Kurzschluss)
- 4 = Tausch-Abweichung
- 16 = Register falsch
- 32 = Zeitüberschreitung
