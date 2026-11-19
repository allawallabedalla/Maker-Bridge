# MB2-TEMP-001

## Idee
Temperatursensor als erster messtechnischer Demonstrator von maker-bridge 2:
PT100 (3-Leiter, Klasse A, IEC 60751) → ADS1220 (24 Bit, PGA, IDAC) → SPI → ESP32 → Messwerte an die vorhandene Software.

## Anforderungen
Außenluft −30 … +50 °C, Genauigkeit ±0,5 °C, Linearität ≤ 0,2 °C, Hysterese ≤ 0,2 °C, Wiederholbarkeit ≤ 0,1 °C,
Auflösung ≤ 0,05 °C, 1 Wert je 10 s mit Zeitstempel. Drift, Strahlungsfehler, Reaktionszeit: Zielwerte offen. Als Daten in `anforderungen.json` (A-MESS-TEMP, A-MESSRATE, S-*, K-*).

## Ziele (KPIs)
- stueckzahl: 1 (Nutzer 19.11.2026)
- zielkosten_eur_stueck, termin, aufwand_h_stueck, fehlerfolge, prioritaet, pruefmittel: **offen**
- Folge von Stückzahl 1: Alle Nachweise gelten nur für dieses eine Gerät (Seriennummer). Exemplarstreuung und
  Reproduzierbarkeit zwischen Geräten sind damit nicht nachweisbar – für eine Serie wäre ein neuer Nachweis nötig.

## Anwendung (Nutzer 19.11.2026)
Außenlufttemperatur als Trainingsdaten für Machine Learning.

Kritik am bisherigen Lastenheft (vom Nutzer am 19.11.2026 angenommen, umgesetzt):
- Messbereich −20 … +100 °C passt nicht zu Außenluft. +100 °C kommt nicht vor, unter −20 °C schon. Vorschlag: −30 … +50 °C.
- Größter Fehler draußen ist nicht die Elektronik, sondern Sonne und Strahlung. Ohne Strahlungsschutz (belüftete
  Wetterhütte bzw. Lamellenschirm) zeigt ein Fühler bei Sonne mehrere Grad zu viel – weit mehr als ±0,5 °C.
- Dieser Fehler hängt am Wetter (Sonne, Wind) und damit an den Merkmalen, die das ML-Modell lernt: Das Modell lernt
  dann einen Messfehler statt der Temperatur. Für ML zählen Stabilität (Drift, Sprünge), saubere Zeitstempel und
  markierte Lücken oft mehr als die absolute Genauigkeit.
- 5 Messwerte/s haben keine Quelle: Außenluft ändert sich langsam, der Fühler im Strahlungsschutz reagiert erst in
  Sekunden bis Minuten. Vorschlag: 1 Wert je 10 s (spart Daten und Strom).
- Elektronik steht draußen: Temperaturbereich der Elektronik −30 … +50 °C statt 10 … 40 °C, dadurch größere
  Driftbeiträge; Gehäuse UV-fest (ASA), Feuchte und Betauung beachten.

## Einsatzbedingungen
- Laborbetrieb 10 … 40 °C (angenommen)
- Datenübertragung: USB-Seriell angenommen, Funk des ESP32 aus (vom Nutzer bestätigen, sonst E15/E16 rechnen)

## Entscheidungen
- 19.11.2026: Verstärkung 16 (MK3: 58 % Aussteuerung bei 50 °C; 32 würde übersteuern).
- 19.11.2026: IDAC-Tausch je Messwert, damit die Fehlanpassung der Stromquellen herausfällt (ohne Tausch wirkt sie als Verstärkungsfehler m/2).

- 19.11.2026: ADS1220-Werte aus SBAS501D eingetragen. MK2 bis MK5 ok. MK1 ab Werk verfehlt (0,61 °C), weil der maximale Verstärkungsfehler dominiert → Kalibrierkonzept nötig.

- 19.11.2026: Stückzahl 1 → Kalibrierung des ganzen Sensors im Bad (Variante b) bestätigt; Aufwand fällt einmal an.

- 19.11.2026: Lastenheft auf Außenluft umgestellt: −30 … +50 °C, 1 Wert/10 s, neu A-STRAHLUNG, A-REAKTION, A-DATEN.

## Audit
