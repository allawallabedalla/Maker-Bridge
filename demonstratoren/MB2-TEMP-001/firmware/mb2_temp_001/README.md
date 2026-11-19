# Firmware MB2-TEMP-001 (ESP32 + ADS1220)

| Datei | Inhalt | Stand |
|---|---|---|
| `config.h` | Konstanten mit Prüfwirkung (Verstärkung, R_ref, IDAC-Strom, IDAC-Tausch, Messrate). FW1 vergleicht sie mit `cad/soll.json` | fertig |
| `rtd_rechnung.h` | Rohwert → Widerstand → Temperatur (IEC 60751), Fehlerbits (Übersteuerung, unplausibel, Tausch-Abweichung) | fertig, auf dem PC getestet |
| `ads1220.h` | Treiber: RESET, Register schreiben und gegenlesen, Offsetkalibrierung (MUX 1110b), Messung mit IDAC-Tausch. Jeder Code mit Seite in SBAS501D | fertig, auf dem PC mit SPI-Attrappe getestet |
| `mb2_temp_001.ino` | ESP32-Sketch (Arduino): SPI Modus 1, 5 Hz, Ausgabe `zeit_ms;code_a;code_b;offset_code;fehlerbits;r_ohm;t_c` | geschrieben, **nicht übersetzt** (kein ESP32-Toolchain im Container) |

## Register (SBAS501D S. 42–46)

| Register | Wert | Bedeutung |
|---|---|---|
| 00h | 68h | AINP = AIN1, AINN = AIN0, Verstärkung 16, PGA aktiv (Offset: E8h = Eingänge kurz) |
| 01h | 00h | 20 SPS, Normalmodus, Einzelwandlung |
| 02h | 55h | externe Referenz REFP0/REFN0, 50 + 60 Hz FIR, IDAC 500 µA |
| 03h | 70h / 8Ch | IDAC1 → AIN2, IDAC2 → AIN3 / getauscht |

Ablauf je Messwert: WREG 03h (startet eine Wandlung), warten `EINSCHWING_US`, START/SYNC (startet neu, S. 38), auf DRDY warten, RDATA. Dann das Gleiche mit getauschten IDACs, Mittelwert, Offset abziehen.

Zwei Wandlungen à 50,06 ms (S. 30, Tab. 8-4) plus Einschwingen passen in 200 ms (MK5).
Nachgewiesen wird die Messrate am Gerät mit AB-MESSRATE.
