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
| Sensorelement | PT100, 3-Leiter, Klasse A, IEC 60751, −20 … +100 °C | Norm. Element nicht gewählt, Eigenerwärmung **offen** |
| ADC | TI ADS1220, 24 Bit, PGA, 2 × IDAC, SPI | **alle Kennwerte offen**: Datenblatt in dieser Sitzung nicht abrufbar |
| Erregung | 2 × 500 µA IDAC, ratiometrisch, IDAC-Tausch je Messwert | Auslegung |
| Referenzwiderstand | 1,65 kΩ, 0,01 %, ≤ 10 ppm/K (Low-Side, beide IDACs) → V_ref = 1,65 V | Vorgabe, Bauteil nicht beschafft |
| Verstärkung | 16 → Vollausschlag ±103,1 mV, V_in 46,1 … 69,3 mV (45–67 %) | berechnet (MK3) |
| Mikrocontroller | ESP32, 3,3 V, SPI | Funk aus angenommen |
| Referenzthermometer | kalibriert, rückführbar | **nicht vorhanden** |

## Stand der Nachweise (ehrlich)

| Nachweis | Stand |
|---|---|
| PT100-Kennlinie, Messgleichung, Aussteuerung (MK3) | gerechnet, getestet |
| Unsicherheitsbudget MK1, Auflösung MK2 | **nicht gerechnet**: ADS1220-Werte fehlen (Rauschen, Verstärkungsfehler, Offset, INL, IDAC-Fehlanpassung) |
| Bauteilgrenzen MK4 (Referenz, IDAC-Compliance, PGA) | **nicht geprüft**: Grenzwerte fehlen |
| Firmware | Rechnung fertig (auf dem PC getestet). ADS1220-Treiber blockiert, siehe `firmware/mb2_temp_001/README.md` |
| Messreihen | nur **Demonstrationsdaten** (`datenstatus: demonstrationsdaten_nicht_rueckfuehrbar`), synthetisch nach Formel |
| Messtechnische Freigabe | `nicht_freigegeben` |

## Nächste Daten, die gebraucht werden

1. ADS1220-Datenblatt: die Werte unter `messkette.bauteile.adc` mit Tabelle und Seite in `_herkunft` eintragen.
2. Gewähltes PT100-Element: Eigenerwärmungskoeffizient.
3. Referenzthermometer: Seriennummer, Kalibrierschein, U, Gültigkeit.
