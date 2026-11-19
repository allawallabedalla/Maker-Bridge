# Demonstrator MB2-TEMP-001: PT100-Temperatursensor

> **Projekt abgebrochen (19.11.2026).** Der Stand bleibt als Beispiel und Testgrundlage für die Messtechnik der
> Maker-Bridge erhalten (`tests/test_temp_demonstrator.py`).
> - **Erreicht:** Lastenheft für Außenluft, Messkette mit ADS1220-Datenblattwerten (MK2–MK5 ok), Kalibrierkonzept, Treiber und Rechnung (auf dem PC getestet), Messanleitung.
> - **Nicht erreicht:** kein Fühler gekauft, keine echte Messung, MK1 offen (Eigenerwärmung), Zielwerte für Strahlung und Reaktionszeit offen, Kabellänge offen, SHT31-Feuchte nicht entschieden.

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
| Host (nicht Teil des Moduls) | ESP32 oder Raspberry Pi über SPI, Modul direkt daneben, 3,3 V; nur das PT100-Kabel geht nach draußen | Schnittstelle: `SCHNITTSTELLE.md` |
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
| MK1 informativ (Eigenerwärmung weggelassen) | **ab Werk knapp ohne Reserve**: U = 0,49 °C bei 50 °C (Elektronik drinnen; mit Elektronik draußen waren es 0,54 °C). Darin fehlen noch Eigenerwärmung und Strahlung, deshalb bleibt der Abgleich nötig. Beiträge: Verstärkungsfehler max. 0,1 % mit 47 %, Klasse A mit 44 %, Leitungsdifferenz mit 6 %. Ohne Verstärkungsfehler wäre U = 0,44 °C |
| Firmware | Treiber (`ads1220.h`), Rechnung, ESP32-Sketch und Raspberry-Pi-Programm fertig. Treiber und Rechnung auf dem PC gegen SPI-Attrappe bzw. Python-Modell getestet, Raspberry-Pi-Programm übersetzt. **Nicht** auf ESP32 übersetzt oder am Gerät gelaufen |
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
Stand: MK1 zeigt die Planung (höchstens u = 0,249 °C für die Kalibrierung). Gerechnet wird es erst mit echten Kalibrierwerten.

## Kaufteile

**Strahlungsschutz (passiv, gekauft – Entscheidung 19.11.2026).** Auswahlkriterien:
1. Mehrere übereinanderliegende Lamellen, weiß, UV-beständiger Kunststoff (z. B. ASA) – keine einfache Kappe.
2. Durchführung/Halter passend zum Fühlerdurchmesser; Fühlerspitze in der Mitte, ohne Kontakt zu den Lamellen.
3. Befestigung für Mast oder Wand, Montagehöhe frei wählbar (für Lufttemperatur üblich ca. 2 m über Boden, über Gras).
4. Angaben des Herstellers zum Strahlungsfehler, falls vorhanden, mitnehmen (Herkunft „datenblatt“); sonst gilt
   nur der Feldvergleich (A-STRAHLUNG).
5. Kauf nicht über Amazon (Vorgabe Nutzer).

**PT100-Fühler (noch nicht vorhanden, Stand 19.11.2026).** Anforderungen an den Kauf:
1. PT100 nach IEC 60751, **3-Leiter**. Klasse A wie im Lastenheft. Klasse B würde wegen des Abgleichs auch reichen,
   wichtiger ist die Langzeitstabilität (Drift).
2. **Datenblatt mit Eigenerwärmungskoeffizient** (mW/K) und Ansprechzeit (t0,5/t0,9 in Luft). Ohne den
   Eigenerwärmungswert bleibt das Budget MK1 offen, ohne Ansprechzeit A-REAKTION.
3. Edelstahl-Schutzrohr, **dünn (etwa 3–6 mm)** und kurz (etwa 50–100 mm): dünn reagiert schneller und leitet weniger
   Wärme über den Schaft; Durchmesser muss in den Halter der gekauften Hütte passen.
4. Kabel außentauglich bei −30 °C (Silikon oder PUR, kein Standard-PVC – wird in der Kälte steif), 3 gleiche Adern,
   möglichst geschirmt (Schirm am Host auf Masse); Länge = Weg zum Host + Reserve, später nicht kürzen (K-KABEL).
5. Übergang Rohr/Kabel wasserdicht (z. B. IP67).
6. Nicht über Amazon.

## Nächste Daten, die gebraucht werden

1. Gewähltes PT100-Element: Eigenerwärmungskoeffizient.
3. Referenzthermometer: Seriennummer, Kalibrierschein, U, Gültigkeit.
