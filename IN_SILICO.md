# In-silico-Simulation – Bewertung für mb2 (17.11.2026)

**Ergebnis:** Ja, das passt. mb2 macht vieles davon schon. Es fehlt die formale Schicht, mit der Regulierer
Simulationen als Nachweis akzeptieren: die **Glaubwürdigkeit je Modell nach ASME V&V 40**.
Punkt 1 und 3 des Vorschlags sind am 17.11.2026 eingebaut (`mb2/glaubwuerdigkeit.py`, siehe VMODELL.md). Punkt 2 und 4 sind offen.

## Was „in silico“ in der Medizintechnik heute heißt
- **In-silico-Trials:** klinische bzw. technische Prüfungen an virtuellen Populationen (viele Patienten oder Geräte im Rechner).
  Referenz: *Toward Good Simulation Practice*, herausgegeben von Viceconti und Emili, Springer, Open Access.
  Getragen von der VPH Institute / Avicenna Alliance.
- **ASME V&V 40-2018:** risikobasierte Glaubwürdigkeit eines Rechenmodells für einen bestimmten Einsatzzweck (Context of Use, COU)
  und eine bestimmte Frage (Question of Interest, QOI).
  - Modellrisiko = Einfluss des Modells auf die Entscheidung × Folge einer falschen Entscheidung.
  - Je höher das Risiko, desto mehr Verifikation, Validierung und Anwendbarkeitsnachweis.
  - 13 Glaubwürdigkeitsfaktoren (Code-Verifikation, Rechenverifikation, Validierung, Anwendbarkeit).
- **FDA-Leitfaden (final, Nov. 2023):** „Assessing the Credibility of Computational Modeling and Simulation in Medical Device Submissions“.
  - Gilt nur für physikalische bzw. mechanistische Modelle, nicht für reine KI-Modelle.
  - Stützt sich auf V&V 40, mit 9 Schritten von der Frage bis zum Credibility Assessment Report.

## Abgleich mit mb2

| V&V-40-Baustein | in mb2 heute | Lücke |
|---|---|---|
| Frage und Einsatzzweck je Modell | implizit im Lastfall bzw. in der Anforderung | Feld `qoi`/`cou` je FEM-Fall und je Twin-Lauf fehlt |
| Modellrisiko (Einfluss × Folge) | nicht vorhanden | gleiche Strenge für ein Schnapphaken- und ein Alarm-Modell |
| Code-Verifikation | Abgleiche gegen bekannte Lösungen (Stifthalter, Schnapphaken, Elmer-Platte) | als Testsuite vorhanden, aber nicht je Modell verlinkt |
| Rechenverifikation (Netzkonvergenz) | `konvergenz` optional | nicht an das Risiko gekoppelt |
| Validierung gegen Messung | Feldfälle (Funk: −84 → −134 → −132,7 dBm), Abnahme | für Thermik und Mechanik noch keine Messung |
| Unsicherheit der Eingaben | Herkunft → relative Unsicherheit, Reserve > Unsicherheit | nicht durch die FEM fortgepflanzt (keine Sensitivität und keine Monte-Carlo-Rechnung über Eingaben) |
| Virtuelle Population | Thermo-Flow-Twin: 100 Köpfe × 45 Szenarien | nur in Thermo-Flow, nicht allgemein in mb2 |
| Bericht | `v_matrix.json`, `audit` | kein Credibility Assessment Report je Modell |

## Vorschlag (wenn gewünscht)
1. **`modell_risiko` je Nachweis** in `anforderungen.json`, mit Einfluss (gering/mittel/hoch) × Folge (gering/mittel/hoch).
   Daraus folgen Pflichten:
   - Ab „mittel“: Netzkonvergenz Pflicht.
   - Ab „hoch“: Validierung gegen Messung Pflicht, sonst nur „vorbehalt“.
   Das passt zu „grün heißt bewiesen“.
2. **Sensitivität über die Eingaben:** Die Eingaben mit der schwächsten Herkunft ±Unsicherheit variieren und Min und Max der Kenngröße melden.
   Das läuft gecacht, der Aufwand ist also gering.
3. **Glaubwürdigkeitsbericht** je Modell aus `v_matrix` erzeugen: Frage, Einsatzzweck, Risiko, Verifikation, Validierung, Anwendbarkeit.
4. **Virtuelle Population als allgemeines Werkzeug:** Fertigungsstreuung (Kalibrierkörper) und Einsatzstreuung je Projekt würfeln, statt nur einen Nennfall zu rechnen.

**Nutzen:** Für Thermo-Flow wäre das genau die Sprache, in der ein Hersteller Simulationen als Nachweis einreicht.
Für die Forscherpräsentation liefert es den Fachbegriff: mb2 ist risikobasierte In-silico-Verifikation im Sinne von V&V 40.

## Abgleich mit den Folien des V&V-40-Ausschusses (17.11.2026)
Die Datei `asme_vv_40_model_simulation_standard.pdf` (IMAG-Wiki, NIH) enthält Vortragsfolien des Ausschusses aus der Zeit
um 2014, nicht den Normtext. Sie bestätigen den Aufbau: Risiko = Einfluss × Folge, je 3 Stufen.
Die Faktoren stehen dort einzeln:
- **Rechenmodell:** Code-Verifikation, Lösungsverifikation, Systemkonfiguration, Systemeigenschaften, Randbedingungen, Grundgleichungen.
- **Vergleichsgröße:** Probencharakterisierung, Kontrolle der Versuchsbedingungen, Messunsicherheit.
- **Abgleich:** Diskrepanz der Ein- und Ausgaben, Strenge des Vergleichs.
- **Anwendbarkeit** auf den Einsatzzweck.
- **Sensitivität der Ergebnisse** gegenüber den Eingaben.

Beide Lücken sind am 17.11.2026 geschlossen (Stufen je Faktor, `fem_sensitivitaet`, siehe VMODELL.md). Es waren:
1. Jeder Faktor hat dort **Abstufungen** statt ja/nein. Beispiel Strenge des Vergleichs:
   Sichtvergleich → Differenz gepaarter Werte → mit Unsicherheit einer Seite → mit Unsicherheit beider Seiten.
2. Die **Sensitivitätsanalyse** ist ein eigener Faktor (keine → Schlüsselgrößen über den Einsatzbereich → alle Eingaben). Bei uns fehlt sie noch.

Dazu der Leitsatz: Lässt sich der Plan nicht erfüllen, wird der Einsatzzweck enger gefasst. Dadurch sinkt das Risiko und mit ihm die Schwelle.

## Quellen
- `asme_vv_40_model_simulation_standard.pdf`, Folien des V&V-40-Ausschusses (Popelar, Morrison, Rau), IMAG-Wiki
- [PubMed 30973403 – V&V 40-Rahmen](https://www.pubmed.gov/30973403/)
- [ASME Blog – Regulatory Framework for Medical Device Simulation](https://www.asme.org/topics-resources/content/bioengineering-blog-an-emerging-regulatory-framework-for-medical-device-simulation)
- [PMC6445134 – Beispiel Modellrisiko](https://pmc.ncbi.nlm.nih.gov/articles/PMC6445134/table/T2)
- [FDA-Webinar zum finalen Leitfaden](https://www.fda.gov/medical-devices/medical-devices-news-and-events/webinar-assessing-credibility-computational-modeling-and-simulation-medical-device-submissions-final), Zusammenfassung: [Exponent](https://www.exponent.com/article/fda-issues-final-guidance-silico-device-model-credibility), [RAPS](https://www.raps.org/resource/fda-publishes-final-guidances-on-device-shortage-r.html)
- [Toward Good Simulation Practice (Open Access)](https://library.oapen.org/handle/20.500.12657/88346)
- [VPH Institute – FDA/MDIC Symposium](https://vph-institute.org/news/unveiling-the-future-highlights-from-the-fda-mdic-symposium-on-computational-modeling-and-simulation.html)
