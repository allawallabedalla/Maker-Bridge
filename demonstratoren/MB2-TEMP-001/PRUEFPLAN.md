# Prüfplan MB2-TEMP-001

Gilt für Anforderung **A-MESS-TEMP**. Bewertet wird mit `mb2/pruefungen/messkette.py`.
Das Ergebnis steht in `pruef/v_matrix.json` und `pruef/messprotokoll.md`.

## 1 Prüfmittel

| Mittel | Pflichtangaben in `messung.json → referenz` |
|---|---|
| Referenzthermometer | `mittel`, `seriennummer`, `kalibrierschein` (Nummer, Labor), `rueckfuehrung` (z. B. DAkkS-Kalibrierung), `U` + `k`, `gueltig_bis`, `einheit`. Gültiger Bereich muss −20 … +100 °C abdecken |
| Temperiermedium | Flüssigkeitsbad oder Blockkalibrator. Homogenität und Stabilität gehören als Beitrag in `pruefunsicherheit` |

Ein Produktangebot oder Datenblatt ist **kein** Kalibriernachweis. Fehlt eine Pflichtangabe, gilt `unbewiesen` mit Grund `nachweisdaten_unvollstaendig`.

## 2 Ablauf je Temperaturpunkt

Punkte: −20, 0, 10, 20, 30, 40, 50, 70, 100 °C.
1. Prüfling und Referenz nebeneinander im Medium. Messspitzen auf gleicher Höhe, Abstand ≤ 10 mm.
2. Einschwingen ≥ 600 s (`einschwingzeit_min_s`). Erst messen, wenn die Referenz über 60 s weniger als 1/10 von U_ref driftet. Einschwingzeit in `bedingungen` eintragen.
3. ≥ 10 Messungen mit 5 Hz. Je Messung: Zeit, Referenzwert, Sensorwert, Rohcodes (`roh_code`). Rohdaten bleiben in der Reihe.
4. Umgebung festhalten: `T_umgebung_C`, `U_versorgung_V`.

## 3 Eigenschaften

| Eigenschaft | Reihe | Verfahren |
|---|---|---|
| Messbereich | R-BER | Punkte −20 und +100 °C angefahren |
| Genauigkeit | R-GEN | alle Punkte, Abweichung Mittelwert − Referenz |
| Linearität | R-LIN | alle 9 Punkte, Restfehler zur Ausgleichsgeraden. Eine Zweipunktkalibrierung reicht nicht |
| Hysterese | R-HYS | Aufheizen −20 → 100 °C (`richtung: auf`), dann Abkühlen 100 → −20 °C (`richtung: ab`), gleiche Punkte |
| Wiederholbarkeit | R-WDH | ≥ 10 Messungen je Punkt, Standardabweichung |
| Drift | R-DRI | **offen**: Zielwert fehlt, Langzeittest ≥ 720 h. Bis dahin `unbewiesen` (`grenze_fehlt` / `ohne_referenzmessung`) |

## 4 Thermische Kopplung (Prüfunsicherheit)

Diese Einflüsse verfälschen die Messabweichung systematisch. Jeden davon bestimmen und als Beitrag in `pruefunsicherheit` der Reihe eintragen, jeweils `{name, wert, verteilung, herkunft}`:
- **Eintauchtiefe und Wärmeableitung über Schaft und Leitung:** Bei 0 und 100 °C die Eintauchtiefe um 20 mm verringern. Halbe Änderung der Anzeige als Rechteck-Halbbreite eintragen.
- **Gradient zwischen den Fühlern:** Prüfling und Referenz tauschen. Halbe Differenz eintragen.
- **Stabilität des Mediums:** Spanne der Referenz über die Messzeit eintragen.
- **Eigenerwärmung:** Prüfling mit 500 µA und, falls möglich, mit kleinerem Strom messen. Daraus den Eigenerwärmungskoeffizienten ableiten (`sensor.eigenerwaermung_mW_K`).

## 5 Entscheidungsregel

ILAC-G8:09/2019, geschütztes Annehmen mit Schutzband w = U_prüf (k = 2):
- konform (`bewiesen`), wenn Kennwert ≤ Grenze − w
- Graubereich (`vorbehalt`), wenn Grenze − w < Kennwert ≤ Grenze
- `verletzt`, wenn Kennwert > Grenze

Das Protokoll zeigt Kennwert, Grenze, U_prüf, Akzeptanzgrenze und Fehlentscheidungsrisiko nebeneinander.
Messtechnisch freigegeben ist erst, wenn alle Eigenschaften bewiesen sind **und** ein Mensch freigegeben hat (`freigabe.json`, an den Kontext-Hash gebunden).

## 6 Datenstatus

`rueckfuehrbar_gemessen` ist der einzige Status, der beweist.
`gemessen_nicht_rueckfuehrbar`, `demonstrationsdaten_nicht_rueckfuehrbar` und `simuliert` werden ausgewertet und angezeigt, bleiben aber `unbewiesen`.
