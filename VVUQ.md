# VVUQ in der Maker-Bridge: Begriffe, Quellen, Stand

Damit alle dieselben Wörter verwenden. Die Begriffe folgen dem Sprachgebrauch der ASME-VVUQ-Reihe (VVUQ 1, V&V 10/20/40).
Die Normtexte selbst lagen **nicht** vor. Grundlage sind öffentliche Quellen, und jede Stelle sagt, woher sie stammt.

## Begriffe

| Begriff (VVUQ) | Bedeutung | In der Bridge |
|---|---|---|
| Fragestellung (question of interest) | Was soll das Modell beantworten? | `modell.frage` |
| Einsatzzweck (context of use) | Was entscheidet das Modell, unter welchen Bedingungen? | `modell.einsatz` |
| Modelleinfluss | Wie stark hängt die Entscheidung am Modell? | `modell.einfluss` (gering/mittel/hoch) |
| Entscheidungsfolge | Was richtet eine falsche Entscheidung an? | `modell.folge` |
| Modellrisiko | Einfluss und Folge zusammen | `glaubwuerdigkeit.risiko` (1–5) |
| Code-Verifikation | Rechnet der Löser die Gleichungen richtig? | Faktor `code` (Abgleich gegen bekannte Lösung in `tests/`) |
| Lösungsverifikation | Wie groß ist der numerische Fehler dieses Laufs? | Faktor `loesung` (F20 Netzkonvergenz, F21 Richardson) |
| Validierung | Stimmt das Modell mit der Wirklichkeit überein, für diesen Einsatzzweck? | Faktor `vergleich`, Metrik nach V&V 20 |
| Validierungsmetrik | E = S − D; u_val = √(u_num² + u_input² + u_D²); validiert bei \|E\| ≤ k·u_val | `glaubwuerdigkeit.vv20_metrik` |
| Unsicherheitsquantifizierung (UQ) | Wie unsicher ist das Ergebnis wegen unsicherer Eingaben und Numerik? | Sensitivität (`fem_sensitivitaet`), GUM-Budget (`messkette`), u_input/u_num |
| Anwendbarkeit (applicability) | Passt die Validierung zum Einsatzzweck (Material, Lastbereich)? | Faktor `anwendbarkeit` |
| Glaubwürdigkeit (credibility) | Vertrauen in die Modellaussage für den Einsatzzweck | Status bewiesen/vorbehalt/unbewiesen je Modell |
| **Kalibrierung ≠ Validierung** | Kalibrierung passt Parameter an Daten an. Validierung prüft mit **unabhängigen** Daten | Kalibrierreihe zählt nie als Nachweis (`kalibrierdaten_als_nachweis`) |
| Digitaler Zwilling | Modell, das laufend mit Daten des echten Objekts abgeglichen wird | Feldabgleich: Widerspricht eine Feldmessung, verliert die Vorhersage ihre Beweiskraft |

## Quellen und was davon umgesetzt ist

| Quelle | Umgesetzt | Nicht umgesetzt, Grund |
|---|---|---|
| ASME VVUQ 1-2022 (Begriffe) | dieses Glossar | Normtext nicht eingesehen, Begriffe aus dem Sprachgebrauch |
| ASME V&V 40-2018 (risikobasierte Glaubwürdigkeit) | `mb2/glaubwuerdigkeit.py` (über den FDA-Leitfaden 2023) | Normtext nicht eingesehen |
| ASME V&V 20 / V&V 10 (Validierungsmetrik CFD/Wärme bzw. Festkörper) | `vv20_metrik`; Stufe 3/4 nur mit gerechneter Metrik | Normtexte nicht eingesehen, Formel aus der Literatur |
| ASME VVUQ 20.1-2024 (multivariate Metrik) | **nein**. Mehrere Größen werden einzeln geprüft, die schlechteste zählt (konservativ) | Normtext nicht eingesehen, Inhalt nicht prüfbar |
| ASME VVUQ 70 (KI/ML), in Arbeit | **selbst abgeleitet**: `ml_bewerte`, Nachweisart `ml_modell` | Norm noch nicht veröffentlicht, im Auge behalten |
| ASME MBE-1 (Model-Based Enterprise) | – | Die Bridge ist bereits modellbasiert (CAD-Skript ist die Quelle). Ohne Normtext keine weitere Ableitung |
| ASME PHM-1-2025 (Prognostik/Health Monitoring) | – | Kein Bridge-Projekt überwacht laufende Anlagen. Nicht eingesehen |
| DNV-RP-A204 (Qualifizierung digitaler Zwillinge) | nur der Grundgedanke „Validierung erlischt bei Abweichung im Feld“ | Text nicht eingesehen |
| ISO/IEC 30186 (Reifegrad digitaler Zwillinge) | – | Text und Stand nicht geprüft. Erfundene Reifegrade wären Scheinsicherheit |

## Stichproben-Validierung (`mb2/stichproben.py`, `stichproben.json`)

Einzelne Realmessungen lassen sich jederzeit gegen eine Modellvorhersage einstreuen, egal ob aus dem Katalog oder aus der FEM:
1. **Jeder Punkt einzeln** nach V&V 20 (|E| ≤ k·u_val). Ohne Messunsicherheit u_D und ohne echte Messung zählt er nicht.
2. **Ein durchgefallener Punkt** genügt: Das Modell ist widerlegt und kein Nachweis mehr, bis es nachkalibriert ist.
3. **Validiert ist nur der gemessene Bereich.** Liegt der Entwurf außerhalb, gilt das als Extrapolation, also höchstens `vorbehalt`.
4. **FEM ohne eigenen Validierungsblock:** Die Stichproben zählen als Vergleich in der Glaubwürdigkeit.
5. **`messpunkte_vorschlagen`** nennt die Stellen, an denen die nächste Messung am meisten bringt: kleinste Reserve, empfindlichste Eingabe, Extrapolation.

## KI/ML-Modelle als Nachweis (selbst abgeleitet)

Ausgaben eines KI-**Agenten** sind nie ein Nachweis. Ein trainiertes ML-**Modell**, etwa ein Ersatzmodell für FEM, darf Nachweis sein, wenn alle diese Bedingungen erfüllt sind:
1. **Reproduzierbar:** Die Modellversion ist festgehalten (`version`).
2. **Unabhängig getestet:** Die Testdaten kamen im Training nicht vor (`testdaten.unabhaengig`).
3. **Keine Extrapolation:** Jede Eingabe liegt im Trainingsbereich (`trainingsdaten.bereich`).
4. **Metrik in der Grenze** (`metrik.wert ≤ grenze`).
5. **UQ:** Ohne Unsicherheitsangabe gibt es höchstens `vorbehalt`. Ab Risiko 4 sind Testdaten aus echten Messungen **und** UQ Pflicht.
