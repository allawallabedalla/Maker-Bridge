# Offene Entscheidungen (aus dem Review vom 19.11.2026)

| # | Frage | Stand | Risiko bis zur Entscheidung |
|---|---|---|---|
| 1 | Wer darf Abnahme-, Feld- und Messwerte und die messtechnische Freigabe eintragen? a) Kennwort-Sperre, b) nur Regel | **vertagt** (Nutzer 19.11.2026) | Eine KI kann Ist-Werte eintragen, Reihen als `rueckfuehrbar_gemessen` markieren und `freigabe.json` schreiben. Nur die Anleitung verbietet es. |
| 2 | Genauigkeit für jeden Einzelwert oder für den Mittelwert je Punkt? | **erledigt 19.11.2026:** je Anforderung `genauigkeit.bezug`, Voreinstellung `einzelwert` (streng) | – |
| 3 | Sicherheitsziel aus `soll.json`/M26 auch in FEM-Bewertung, M1, M4, M7, M9, D9, D11 verwenden? | offen | Diese Prüfungen rechnen fest mit S = 2,0 (M1 1,5, M4 3) und ohne Abminderung (M7, M9). |
| 4 | PETG-E-Modul 2000 MPa (material.py) gegen die eigene Quelle 1500 MPa (kennwerte.py, Prusament)? | offen | Durchbiegungen zu klein, Eigenfrequenzen zu hoch, nicht konservativ. |
| 5 | Kommunikationsregeln: Kürze gegen „jede Angabe hinterfragen“ und „jeden Widerspruch einzeln fragen“; Begriffe fertig/Freigabe vereinheitlichen | offen | Regeln sind nicht gleichzeitig erfüllbar. |
| 6 | E15: Größe und Lage der Antennen-Sperrfläche je Modul in die Bauteildatenbank aufnehmen? | offen | E15 wird schon mit irgendeiner Sperrfläche „ok“. |
