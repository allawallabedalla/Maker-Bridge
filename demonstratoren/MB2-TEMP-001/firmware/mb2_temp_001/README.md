# Firmware MB2-TEMP-001 (ESP32 + ADS1220)

| Datei | Inhalt | Stand |
|---|---|---|
| `config.h` | Konstanten mit Prüfwirkung (Verstärkung, R_ref, IDAC-Strom, IDAC-Tausch, Messrate). FW1 vergleicht sie mit `cad/soll.json` | fertig |
| `rtd_rechnung.h` | Rohwert → Widerstand → Temperatur (IEC 60751), Fehlerbits (Übersteuerung, unplausibel, Tausch-Abweichung) | fertig, auf dem PC getestet |
| ADS1220-Treiber (Register, SPI, IDAC-Routing) | **blockiert** | siehe unten |

## Warum der Treiber fehlt

Die Registerbelegung des ADS1220 (MUX-, GAIN-, DR-, MODE-, VREF-, IDAC-, I1MUX/I2MUX-Codes, SPI-Befehle und SPI-Modus)
muss aus dem TI-Datenblatt übernommen werden. Das Datenblatt war in dieser Sitzung nicht abrufbar.
Registerwerte aus dem Gedächtnis wären eine unbelegte Bauteilspezifikation. Das verbietet die Qualitätsregel des Demonstrators.

Vorgesehener Ablauf je Messwert (5 Hz):
1. Wandlung A: IDAC1 → Leitung 1 (RTD), IDAC2 → Leitung 2 (Kompensation), Einzelwandlung, Rohcode speichern.
2. Wandlung B: IDACs getauscht, Rohcode speichern.
3. `rtd_rechnen(code_a, code_b, IDAC_TAUSCH, RREF_OHM, PGA_GAIN, RTD_R0_OHM, &r, &t)`.
4. Ausgabe je Zeile: `zeitstempel_ms;code_a;code_b;fehlerbits;r_ohm;t_c`. Rohwerte und Rechnung stehen getrennt in der Zeile.

Ob zwei Wandlungen je 200 ms möglich sind, hängt von der Wandlungszeit im Einzelwandlungsbetrieb ab. Diesen Wert liefert das Datenblatt.
Nachgewiesen wird die Messrate am Gerät mit AB-MESSRATE.
