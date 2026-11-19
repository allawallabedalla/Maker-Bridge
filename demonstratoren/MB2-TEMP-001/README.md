# Demonstrator MB2-TEMP-001: PT100-Temperatursensor

Erster messtechnischer Demonstrator. Er läuft durch die bestehende Architektur, ohne eigene Subsysteme:
- V-Matrix (`mb2/anforderungen.py`)
- Messkette MK1–MK4 (`mb2/pruefungen/messkette.py`, Profil `mb2/sensorprofile/rtd.py`)
- FW1

## Benutzen

```
cp -r demonstratoren/MB2-TEMP-001 projects/MB2-TEMP-001
uv run python -m mb2 anforderungen_pruefen '{"projekt": "MB2-TEMP-001"}'
uv run python -m mb2 messkette_rechnen '{"projekt": "MB2-TEMP-001"}'
```
Ergebnis: `pruef/v_matrix.json` (Feld `messtechnische_freigabe`), `pruef/messprotokoll.md`, `pruef/katalog.json`.

## Hardware

| Baugruppe | Festlegung | Stand der Daten |
|---|---|---|
| Sensorelement | PT100, 3-Leiter, Klasse A, IEC 60751, Außenluft −30 … +50 °C, im belüfteten Strahlungsschutz | Norm. Element nicht gewählt, Eigenerwärmung **offen** |
| ADC | TI ADS1220, 24 Bit, PGA, 2 × IDAC, SPI, 20 SPS Einzelwandlung, 50/60-Hz-FIR | Datenblatt SBAS501D (Rev. Mai 2026), Seite/Tabelle je Wert in `cad/soll.json → _herkunft` |
| Erregung | 2 × 500 µA IDAC, ratiometrisch, IDAC-Tausch je Messwert | Auslegung |
| Referenzwiderstand | 1,65 kΩ, 0,01 %, ≤ 10 ppm/K (Low-Side, beide IDACs) → V_ref = 1,65 V | Vorgabe, Bauteil nicht beschafft |
| Verstärkung | 16 → Vollausschlag ±103,1 mV, V_in 44,1 … 59,7 mV (43–58 %) | berechnet (MK3) |
| Mikrocontroller | ESP32, 3,3 V, SPI Modus 1, CS = GPIO5, DRDY = GPIO4 | Pins angenommen, Funk aus angenommen |
| Pinbelegung ADS1220 | AINP = AIN1, AINN = AIN0, IDAC1 → AIN2, IDAC2 → AIN3 (Tausch: umgekehrt), REFP0/REFN0 an R_ref | nach SBAS501D S. 55–58, Abb. 9-6 |
| Referenzthermometer | kalibriert, rückführbar | **nicht vorhanden** |

## Stand der Nachweise (ehrlich)

| Nachweis | Stand |
|---|---|
| MK2 Auflösung | **ok**: kleinste unterscheidbare Änderung 0,009 °C (6,6 σ), RMS 0,0013 °C. Effektiv 19,7 Bit von 24 nominal. Rauschwert 0,35 µVrms ist ein TYP-Wert (Tab. 7-1) |
| MK3 Aussteuerung | **ok**: 58 % bei 50 °C. Verstärkung 32 würde übersteuern |
| MK4 Referenz / IDAC-Compliance / PGA-Gleichtakt | **ok**: V_ref 1,65 V (0,75 … 3,3 V); IDAC-Pin 1,72 V ≤ 2,4 V; V_CM 1,674 … 1,685 V in 0,825 … 2,546 V |
| MK5 Zeitbudget | **ok**: 2 × (50,06 ms + 1 ms) = 102 ms je Wert, Periode 10 s |
| MK4-SELBST, MK1 | **offen**: Eigenerwärmungskoeffizient des PT100-Elements fehlt |
| MK1 informativ (Eigenerwärmung weggelassen) | **verfehlt ab Werk**: U = 0,54 °C bei 50 °C > 0,5 °C (Stand Außenluft; vorher 0,61 °C bei 100 °C). Beiträge: Verstärkungsfehler max. 0,1 % mit 47 %, Klasse A mit 44 %, Leitungsdifferenz mit 6 %. Ohne Verstärkungsfehler wäre U = 0,44 °C |
| Firmware | Treiber (`ads1220.h`), Rechnung und ESP32-Sketch fertig. Treiber und Rechnung auf dem PC gegen SPI-Attrappe bzw. Python-Modell getestet. **Nicht** auf ESP32 übersetzt oder am Gerät gelaufen |
| Messreihen | nur **Demonstrationsdaten**, deshalb `nicht_freigegeben` |

## Befunde aus dem Datenblatt

1. **Ab Werk sind ±0,5 °C nicht nachweisbar.** Bei 50 °C allein ergibt der maximale Verstärkungsfehler (0,1 %, S. 7) eine Halbbreite von 0,31 °C.
   Abhilfe: Systemkalibrierung der Verstärkung, zum Beispiel mit zwei Präzisionswiderständen anstelle des Fühlers, oder Kalibrierung des ganzen Sensors gegen das Referenzthermometer (`modus: kalibriert`).
   Das TI-Beispiel erreicht ±0,2 °C nur typisch und nur mit Offsetkalibrierung (S. 55, 61).
2. **50/60-Hz-Unterdrückung** gilt laut S. 7 und S. 30 nur mit externem 4,096-MHz-Takt. Der interne Oszillator (±2 %) verschiebt die Kerben. Entweder Takt vorsehen oder die Unterdrückung am Gerät messen.
3. **Offset** ±4 µV ist nur typisch angegeben (kein Max für Verstärkung 2–128). Die Firmware kalibriert ihn beim Start (MUX 1110b, S. 32).
4. **Einschwingzeit nach dem IDAC-Tausch** ist mit 1 ms angenommen. Nach Auslegung des Eingangsfilters neu berechnen (`EINSCHWING_US`).

## Kalibrierkonzept (entschieden 19.11.2026)

Der ganze Sensor wird im Temperaturbad gegen ein rückführbares Referenzthermometer abgeglichen (`modus: kalibriert`).
Die Korrektur steckt als Polynom in der Firmware (KAL_K0 … K2) und gleicht Klassentoleranz, Verstärkungs- und Offsetfehler, R_ref-Toleranz und Leitungen aus.
Ablauf und Zielwerte stehen im PRUEFPLAN, Abschnitt 1a.
Stand: MK1 zeigt die Planung (höchstens u = 0,223 °C für die Kalibrierung). Gerechnet wird es erst mit echten Kalibrierwerten.

## Nächste Daten, die gebraucht werden

1. Gewähltes PT100-Element: Eigenerwärmungskoeffizient.
3. Referenzthermometer: Seriennummer, Kalibrierschein, U, Gültigkeit.
