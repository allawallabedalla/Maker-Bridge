# Prüfplan MB2-TEMP-001

Gilt für Anforderung **A-MESS-TEMP**. Bewertet wird mit `mb2/pruefungen/messkette.py`.
Das Ergebnis steht in `pruef/v_matrix.json` und `pruef/messprotokoll.md`.

## 1 Prüfmittel

| Mittel | Pflichtangaben in `messung.json → referenz` |
|---|---|
| Referenzthermometer | `mittel`, `seriennummer`, `kalibrierschein` (Nummer, Labor), `rueckfuehrung` (z. B. DAkkS-Kalibrierung), `U` + `k`, `gueltig_bis`, `einheit`. Gültiger Bereich muss −20 … +100 °C abdecken |
| Temperiermedium | Flüssigkeitsbad oder Blockkalibrator. Homogenität und Stabilität gehören als Beitrag in `pruefunsicherheit` |

Ein Produktangebot oder Datenblatt ist **kein** Kalibriernachweis. Fehlt eine Pflichtangabe, gilt `unbewiesen` mit Grund `nachweisdaten_unvollstaendig`.

## 1a Kalibrierung (Entscheidung 19.11.2026: ganzer Sensor gegen Referenz)

Reihenfolge, damit kein Zirkelschluss entsteht:
1. **Kalibrierreihe** `R-KAL-1`: Rohtemperatur des Geräts (`t_roh_c`, Firmware mit KAL_K* = 0) gegen Referenz an allen 9 Punkten aufnehmen, ≥ 10 Messungen je Punkt.
2. `kalibrierung_auswerten(projekt, "R-KAL-1")` rechnet das Korrekturpolynom 2. Grades, `u_fit`, `u_referenz` und `u_kopplung`.
   In `soll.json` geschrieben wird nur bei Datenstatus `rueckfuehrbar_gemessen`.
3. KAL_K0 … K2 in `firmware/mb2_temp_001/config.h` eintragen und neu flashen. FW1 prüft die Übereinstimmung.
4. **Nachweisreihen** R-GEN, R-LIN, R-HYS, R-WDH, R-BER **neu messen**, mit Korrektur, an einem anderen Termin. Die Kalibrierreihe zählt nie als Nachweis (`kalibrierdaten_als_nachweis`).

**Budget für die Kalibrierung** (Planungsrechnung MK1, Modus kalibriert, mit den ADS1220-Werten):
- Alles außer Kalibrierung und Eigenerwärmung ergibt u = 0,017 °C, weil die Elektronik drinnen am Host sitzt (15 … 30 °C).
- Für Referenz, Ausgleichsrest, thermische Kopplung und Eigenerwärmung **zusammen** bleiben höchstens u = 0,249 °C, damit U ≤ 0,5 °C.

**Zielwerte (Vorgabe, noch nicht gemessen):** Referenzthermometer U ≤ 0,1 °C (k = 2), Kopplung ≤ 0,05 °C Halbbreite, Ausgleichsrest u_fit ≤ 0,05 °C.
Damit ergäbe sich U ≈ 0,15 °C, mit Reserve für das ILAC-G8-Schutzband beim Nachweis.

**Kalibriert wird mit dem endgültigen Fühlerkabel** (K-KABEL). Ein Foto von Kabel und Beschriftung kommt nach `pruef/kabel_foto.jpg`.

## 2 Ablauf je Temperaturpunkt

Punkte: −30, −20, −10, 0, 10, 20, 30, 40, 50 °C.
1. Prüfling und Referenz nebeneinander im Medium. Messspitzen auf gleicher Höhe, Abstand ≤ 10 mm.
2. Einschwingen ≥ 600 s (`einschwingzeit_min_s`). Erst messen, wenn die Referenz über 60 s weniger als 1/10 von U_ref driftet. Einschwingzeit in `bedingungen` eintragen.
3. ≥ 10 Messungen (Firmware liefert 1 Wert je 10 s, also ≥ 100 s je Punkt). Je Messung: Zeit, Referenzwert, Sensorwert, Rohcodes (`roh_code`). Rohdaten bleiben in der Reihe.
4. Umgebung festhalten: `T_umgebung_C`, `U_versorgung_V`.

## 3 Eigenschaften

| Eigenschaft | Reihe | Verfahren |
|---|---|---|
| Messbereich | R-BER | Punkte −30 und +50 °C angefahren |
| Genauigkeit | R-GEN | alle Punkte, Abweichung Mittelwert − Referenz |
| Linearität | R-LIN | alle 9 Punkte, Restfehler zur Ausgleichsgeraden. Eine Zweipunktkalibrierung reicht nicht |
| Hysterese | R-HYS | Aufheizen −30 → 50 °C (`richtung: auf`), dann Abkühlen 50 → −30 °C (`richtung: ab`), gleiche Punkte |
| Wiederholbarkeit | R-WDH | ≥ 10 Messungen je Punkt, Standardabweichung |
| Drift | R-DRI | **offen**: Zielwert fehlt, Langzeittest ≥ 720 h. Bis dahin `unbewiesen` (`grenze_fehlt` / `ohne_referenzmessung`) |

## 4 Thermische Kopplung (Prüfunsicherheit)

Diese Einflüsse verfälschen die Messabweichung systematisch. Jeden davon bestimmen und als Beitrag in `pruefunsicherheit` der Reihe eintragen, jeweils `{name, wert, verteilung, herkunft}`:
- **Eintauchtiefe und Wärmeableitung über Schaft und Leitung:** Bei −30 und 50 °C die Eintauchtiefe um 20 mm verringern. Halbe Änderung der Anzeige als Rechteck-Halbbreite eintragen.
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
