# MB2-TEMP-001

## Idee
Temperatursensor als erster messtechnischer Demonstrator von maker-bridge 2:
PT100 (3-Leiter, Klasse A, IEC 60751) → ADS1220 (24 Bit, PGA, IDAC) → SPI → ESP32 → Messwerte an die vorhandene Software.

## Anforderungen
Messbereich −20 … +100 °C, Genauigkeit ±0,5 °C, Linearität ≤ 0,2 °C, Hysterese ≤ 0,2 °C, Wiederholbarkeit ≤ 0,1 °C,
Auflösung ≤ 0,05 °C, 5 Messungen/s. Drift: offen. Als Daten in `anforderungen.json` (A-MESS-TEMP, A-MESSRATE, S-*, K-*).

## Einsatzbedingungen
- Laborbetrieb 10 … 40 °C (angenommen)
- Datenübertragung: USB-Seriell angenommen, Funk des ESP32 aus (vom Nutzer bestätigen, sonst E15/E16 rechnen)

## Entscheidungen
- 19.11.2026: Verstärkung 16 (MK3: 67 % Aussteuerung bei 100 °C; 32 würde übersteuern).
- 19.11.2026: IDAC-Tausch je Messwert, damit die Fehlanpassung der Stromquellen herausfällt (ohne Tausch wirkt sie als Verstärkungsfehler m/2).

- 19.11.2026: ADS1220-Werte aus SBAS501D eingetragen. MK2 bis MK5 ok. MK1 ab Werk verfehlt (0,61 °C), weil der maximale Verstärkungsfehler dominiert → Kalibrierkonzept nötig.

## Audit
