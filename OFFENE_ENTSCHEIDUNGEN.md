# Offene Entscheidungen (aus dem Review vom 19.11.2026)

| # | Frage | Stand | Risiko bis zur Entscheidung |
|---|---|---|---|
| 1 | Wer darf Abnahme-, Feld- und Messwerte und die messtechnische Freigabe eintragen? a) Kennwort-Sperre, b) nur Regel | **vertagt** (Nutzer 19.11.2026) | Eine KI kann Ist-Werte eintragen, Reihen als `rueckfuehrbar_gemessen` markieren und `freigabe.json` schreiben. Nur die Anleitung verbietet es. |
| 2 | Genauigkeit für jeden Einzelwert oder für den Mittelwert je Punkt? | **erledigt 19.11.2026:** je Anforderung `genauigkeit.bezug`, Voreinstellung `einzelwert` (streng) | – |
| 3 | Sicherheitsziel aus `soll.json`/M26 auch in FEM-Bewertung, M1, M4, M7, M9, D9, D11 verwenden? | **erledigt 19.11.2026:** `mb2/sicherheit.py`, ein Ziel für alle, bisherige feste Werte als Minimum; M7/M9 mit Abminderung | – |
| 4 | PETG-E-Modul 2000 MPa (material.py) gegen die eigene Quelle 1500 MPa (kennwerte.py, Prusament)? | **erledigt 19.11.2026:** 1500 MPa | – |
| 5 | Kommunikationsregeln: Kürze gegen „jede Angabe hinterfragen“ und „jeden Widerspruch einzeln fragen“; Begriffe fertig/Freigabe vereinheitlichen | offen | Regeln sind nicht gleichzeitig erfüllbar. |
| 6 | E15: Größe und Lage der Antennen-Sperrfläche je Modul in die Bauteildatenbank aufnehmen? | offen | E15 wird schon mit irgendeiner Sperrfläche „ok“. |
