# V-Modell in maker-bridge 2 (seit 15.11.2026)

Grundsatz: **Grün heißt bewiesen, nicht „nichts gefunden“.** Jede Anforderung braucht einen bestandenen, belegten
Nachweis auf derselben Höhe des V. Anlass und Herleitung: `audits/KERNPROBLEM_2026-11-15.md`.

```
 Entwurf (links)                                              Nachweis (rechts)
 ───────────────                                              ─────────────────
 system      Lastenheft: was das Gerät im Einsatz können muss  ◄──►  abnahme am Gerät + feld im Einsatz
   subsystem   Pflichtenheft: Elektronik, Gehäuse, Firmware,   ◄──►  integration: Katalog-Systemprüfungen, FEM
               Montage
     komponente  Teil, Platine, Firmware-Konstante              ◄──►  komponente: cad_build, ERC/DRC, Katalog je Teil
                       └──── Umsetzung: build123d, KiCad, Firmware ────┘
```

## Dateien je Projekt

| Datei | Inhalt | wer schreibt |
|---|---|---|
| `projekt.md` | Idee, Anforderungen in Worten, Einsatzbedingungen, Entscheidungen | du / project_new |
| `anforderungen.json` | Lastenheft und Pflichtenheft als Daten: id, ebene, eltern, text, herkunft, eingaben, nachweise | project_new (Standard), du (eigene) |
| `cad/soll.json` → `_projekt` | Einsatz, Funk, Akku, Module, Firmware-Konstanten, `_herkunft`, `nicht_relevant` | project_new, Agenten |
| `abnahme.json` | Abnahmeprotokoll: Schritt, Anweisung (lageunabhängig), Soll, **Ist**, Datum | anforderungen_erzeugen, abnahme_eintragen |
| `feld.json` | Messungen im Einsatz (SNR, Empfangsquote, Laufzeit, Temperatur …) | feld_eintragen |
| `messung.json` | Referenzmessreihen (Kalibrierung, Prüfstand) mit Referenzmittel, Rückführung, Bedingungen | messreihe_eintragen |
| `pruef/katalog.json` | alle Katalog-Prüfungen | pruefkatalog/audit |
| `pruef/v_matrix.json` | Status je Anforderung + Belege + Freigabe + Kontext-Hash | anforderungen_pruefen/audit |
| `tests/feldfaelle/*.json` | Feldfälle als Regressionstests (Modell war zu optimistisch) | feld_abgleich |

## Status und Freigabe

- Je Anforderung: **bewiesen** · **vorbehalt** (bestanden, aber auf geschätzten Eingaben oder mit Reserve unter der
  Unsicherheit) · **unbewiesen** (Nachweis fehlt, übersprungen oder Warnung nicht bewertet) · **verletzt**.
- Eltern sind höchstens so gut wie ihr schlechtestes Kind.
- Freigabe: **nicht_druckfertig** → **druckfertig** (alle Komponenten- und Integrationsnachweise bestanden, keine
  Matrix-Mängel) → **fertig** (auch Abnahme am Gerät und Feldmessungen bestanden). Gedruckt wird ab druckfertig;
  „fertig“ meldest du erst mit ausgefülltem Abnahmeprotokoll und Feldwerten.

## Regeln der Matrix

- **Wunsch und Spezifikation getrennt** (seit 19.11.2026, nach Liu et al. 2025, Int J Adv Manuf Technol 139:2103):
  - Ebene `stakeholder`: Wunsch in Worten des Nutzers oder Kunden. Er braucht eine Herkunft und wird im Einsatz validiert (Abnahme oder Feld).
  - Ebene `system`: daraus **hergeleitete** messbare Spezifikation, mit `eltern` (welcher Wunsch) und `herleitung` (Rechnung oder Begründung, z. B. „P = ρgQH = 63 W, mit Reserve 70 W“).
  - Die Regel gilt, sobald ein Projekt Stakeholder-Wünsche führt. Ältere Projekte ohne sie bleiben gültig.
- **Simulationsfehler bei relativer Abweichung** (Glaubwürdigkeit, `validierung.einheit: "%"`):
  - über 10 %: nie validiert, auch nicht bei lockerer Projektgrenze
  - 5–10 %: höchstens Stufe 2
  - unter 5 %: volle Stufe

- Systemanforderung: hat eine `herkunft` (wer verlangt es) und einen Nachweis `abnahme` oder `feld`.
- Subsystem/Komponente: hat `eltern` (Rückverfolgbarkeit nach oben) und Nachweise auf ihrer Ebene.
- Eine Warnung zählt nur mit `warnung_akzeptiert: "Begründung"`.
- Herkunft jeder Eingabe in `_projekt._herkunft`: `gemessen | datenblatt | norm | berechnet | geschaetzt | angenommen: Beleg`.
  Die schwächste Herkunft bestimmt die Unsicherheit (relativ 5–50 %, Funk 3–15 dB). Die Reserve muss größer sein.
- Abnahme-Anweisungen nennen Pin 1, Dreieck, Aderfarbe oder Aufdruck – nie nur links/rechts/oben/unten.
  Neustart über Reset-Pin, nicht Batterie ziehen (Pufferkondensatoren).
- Firmware-Konstanten mit Prüfwirkung (Sendeleistung, SF, Intervall, Abschaltspannung) stehen in
  `_projekt.firmware.konstanten`. FW1 vergleicht sie mit der Datei.

## Glaubwürdigkeit der Rechenmodelle (seit 17.11.2026, `mb2/glaubwuerdigkeit.py`)

Begriffe und Quellenstand: **`VVUQ.md`**.
Neu seit 19.11.2026:
- Validierungsmetrik nach V&V 20. Stufe 3/4 gibt es nur mit gerechnetem E und u_val.
- Nachweisart `ml_modell` für KI/ML-Modelle, selbst abgeleitet.
- Feldmessungen, die eine Vorhersage widerlegen, heben deren Nachweis auf.
- Stichproben-Validierung (`stichproben.json`): einzelne Realmessungen gegen jede Modellvorhersage. Widerlegt heißt kein Nachweis, Extrapolation heißt höchstens `vorbehalt`.

Risikobasiert nach ASME V&V 40 und dem FDA-Leitfaden von 2023. Grundlage ist der öffentliche Leitfaden, die Norm selbst lag nicht vor.
Jeder FEM-Nachweis bekommt einen Block `modell`:
- `frage`: Was soll das Modell beantworten?
- `einsatz`: Was entscheidet es?
- `einfluss` und `folge`: je `gering`, `mittel` oder `hoch`.

**Risiko = 1 + Einfluss + Folge (1–5).** Jeder Faktor hat Stufen, wie in den Folien des V&V-40-Ausschusses.
Das Risiko legt fest, welche Stufe verlangt ist:

| Faktor | Stufen | verlangt bei Risiko 1–2 / 3 / 4 / 5 |
|---|---|---|
| Code-Verifikation | 0 keine · 1 Abgleich gegen bekannte Lösung (`tests/`) | 1 / 1 / 1 / 1 |
| Lösungsverifikation | 0 · 1 Netzkonvergenz, F20 ok · 2 zusätzlich Richardson-Fehlerband F21 | 0 / 1 / 1 / 2 |
| Sensitivität | 0 · 1 Studie mit Auswahl robust · 2 Standardsatz aller Eingaben robust (`fem_sensitivitaet`) | 0 / 1 / 1 / 2 |
| Validierung (Strenge) | 0 keine · 1 Sichtvergleich · 2 Differenz gepaarter Werte · 3 mit Unsicherheit einer Seite · 4 beider Seiten | 0 / 0 / 2 / 4 |
| Anwendbarkeit | 0 · 1 begründet | 0 / 0 / 1 / 1 |
| Herkunft der Eingaben | 0 · 1 alle stark | 0 / 0 / 0 / 1 |

Fehlt eine Stufe, gilt bei Risiko ≤ 3 `vorbehalt`. Bei Risiko ≥ 4 gilt `unbewiesen`, und das sperrt „druckfertig“.
Kippt in der Sensitivitätsstudie eine Variante auf „nicht ok“, ist das ein Befund: mindestens `vorbehalt`, bei jedem Risiko.
Ohne `modell`-Block gilt immer `vorbehalt`.
Leitsatz aus V&V 40: Lässt sich der Plan nicht erfüllen, wird der Einsatzzweck enger gefasst.

**`fem_sensitivitaet(projekt, fall, rel=0.2, nur=None)`** verstellt jede Eingabe um ±rel und rechnet gecacht neu. Die Varianten liegen in `fem/sens/`, Audit und Katalog sehen sie nicht.
- Mechanik: Lasten, Wegvorgaben, E-Modul je Material, Festigkeit (analytisch).
- Wärme: Quellen, h, Wärmeleitung.
- Ergebnis `fem/sens/<fall>.sens.json` mit Elastizität je Parameter, `robust` und `vollstaendig`. Die Studie gilt nur, solange der Grundfall unverändert ist.
- Erster Lauf, Schnapphaken `kraft` (67 s): Last −1,05, E-Modul 0,0 (bei Kraftvorgabe wie erwartet), Festigkeit +1,0.
- Neues Lastfeld `material_override` {"PETG": {"E_MPa": …}} gilt nur für diesen einen Lauf.

Der Bericht je Modell liegt in `pruef/glaubwuerdigkeit.md`, die Kurzfassung in `v_matrix.json` unter `glaubwuerdigkeit`.

## Messtechnik (seit 19.11.2026, `mb2/pruefungen/messkette.py`)

Ein Sensor ist nicht gut, weil seine Elektronik den DRC besteht. Er ist gut, wenn er seine Messgröße nachweislich richtig erfasst.
Darum gibt es zwei Ebenen:

1. **Entwurf, rechnerisch (Katalog MK1–MK5, Integration):** `_projekt.messkette` in `soll.json`.
   - MK1: Unsicherheitsbudget als Einzelbeiträge (Quantisierung q/√12, ADC-Rauschen, Referenz, TK, Verstärkung, Offset, Sensor, Kalibrierung). Daraus u_c und U = k·u_c.
   - MK2: rauschbegrenzte Auflösung. Die nominale Bitzahl ist nicht die Auflösung.
   - MK3: Aussteuerung des ADC über den Messbereich.
   - Vereinfachtes GUM-Modell: lineare Fortpflanzung, vorgegebene Sensitivitäten, Korrelationen nur wenn angegeben. Welch-Satterthwaite, sobald Freiheitsgrade angegeben sind.
2. **Nachweis am Gerät (Nachweisart `messung`, Abnahme):** Anforderung mit Block `messtechnik`, Referenzmessreihen in `messung.json` (`messreihe_eintragen`).

| Eigenschaft | Mindestverfahren (sonst `unbewiesen`, Grund `verfahren_unzureichend`) |
|---|---|
| messbereich | Messpunkte an beiden Bereichsgrenzen |
| genauigkeit | ≥ 3 Punkte gegen rückführbare Referenz |
| linearitaet | ≥ 5 Referenzwerte über ≥ 80 % der Spanne (Ausgleichsgerade) |
| hysterese | Auf- und Abwärtsmessung an ≥ 3 gemeinsamen Punkten |
| drift | ≥ 3 Zeitpunkte über ≥ `dauer_h` (Standard 168 h), Steigung auf Zieleinheit hochgerechnet |
| wiederholbarkeit | ≥ `wiederholungen` (Standard 10) am selben Punkt, Standardabweichung |

- **Kein neuer Status.** Fehlt der Nachweis, gilt weiter `unbewiesen`; der Grund steht in `nachweise[].grund`.
  Mögliche Gründe: `ohne_referenzmessung`, `referenz_ohne_unsicherheit`, `referenz_nicht_rueckfuehrbar`, `referenz_abgelaufen`, `bedingungen_abweichend`, `einheit_unpassend`.
- Jede Eigenschaft im `messtechnik`-Block braucht einen eigenen Nachweis. Fehlen dieser Nachweis oder die `bedingungen`, ist das ein Matrix-Mangel.
- Konformität mit Schutzband (ILAC-G8): Kennwert + U_prüf ≤ Grenze → bewiesen. Kennwert ≤ Grenze < Kennwert + U_prüf → vorbehalt. Kennwert > Grenze → verletzt.
- Merkmal `messung` (Messkette im soll oder `messtechnik` im Lastenheft) macht ein Überspringen von MK1/MK2 zum Fehler.
- **Datenstatus je Messreihe (Pflicht):** `rueckfuehrbar_gemessen` | `gemessen_nicht_rueckfuehrbar` | `demonstrationsdaten_nicht_rueckfuehrbar` | `simuliert`.
  - Nur `rueckfuehrbar_gemessen` kann beweisen. Dafür nötig: Sensor-ID, Seriennummer, Datum, Verfahren und an der Referenz Mittel, Seriennummer, Kalibrierschein, Rückführung, U, Gültigkeit. Fehlt etwas, gilt `nachweisdaten_unvollstaendig`.
  - Alle anderen Datenstatus werden ausgewertet und gezeigt (`auswertung_status`), bleiben aber `unbewiesen`.
- **Bezug der Genauigkeit** (`messtechnik.genauigkeit.bezug`): `einzelwert` (Voreinstellung, jeder Messwert muss die Grenze einhalten) oder `mittelwert` (nur ausdrücklich, wenn das Gerät immer mittelt; dann Abweichung der Punktmittel, Streuung als s/√n in U_prüf).
- **Prüfunsicherheit** U_prüf = 2·√(u_ref² + Σ `pruefunsicherheit` + (s/√n)²). Dazu gehören thermische Kopplung, Eintauchtiefe und Homogenität des Mediums.
- **Protokoll** `pruef/messprotokoll.md`. Je Nachweis: gemessene Abweichung, zulässige Abweichung, U_prüf, Akzeptanzgrenze (Grenze − U_prüf), Entscheidungsregel, Fehlentscheidungsrisiko, Status, Gründe. Dazu je Messpunkt n, Mittelwert, s und Abweichung.
- **Messtechnische Freigabe** (`v_matrix.messtechnische_freigabe`):
  - `nicht_freigegeben`: eine messtechnische Anforderung (Block `messtechnik` oder Nachweis MK*) ist nicht bewiesen.
  - `bereit_zur_menschlichen_freigabe`: alles bewiesen, aber noch keine menschliche Freigabe.
  - `freigegeben`: nur mit `freigabe.json`, die ein Mensch über `anforderungen.messtechnik_freigeben(pdir, name)` von Hand schreibt. Kein MCP-Befehl. Die Freigabe ist an den Kontext-Hash gebunden, jede Änderung macht sie ungültig.
  - „fertig“ verlangt bei messtechnischen Projekten `freigegeben`.
- Fehlt eine Pflichteingabe und schlägt deshalb ein Auslöser an, steht in der V-Matrix `unbewiesen`, nicht `verletzt`. Im Katalog bleibt es ein `fehler`.
- **Sensorprofile** (`mb2/sensorprofile/`):
  - Die Modellgleichung liefert numerische Sensitivitäten (`budget_aus_modell`).
  - Das erste Profil ist `rtd_ratiometrisch_3leiter`: IEC 60751, IDAC-Tausch, MK4-Bauteilgrenzen. Bauteilgrenzen sind Daten, keine eingebauten Datenblattwerte.
  - Der Demonstrator dazu liegt unter `demonstratoren/MB2-TEMP-001/`.
- **Kalibrierung** (`kalibrierung_auswerten`): Eine Reihe liefert die Korrektur. Sie darf nicht zugleich Nachweis sein (Grund `kalibrierdaten_als_nachweis`). Der Nachweis braucht eine unabhängige Reihe nach dem Laden der Korrektur.
- **Risiken** (`risiko` je Anforderung oder Liste `risiken` in `anforderungen.json`): bewusst eingegangen, z. B. Nutzerentscheidung gegen eine Empfehlung. Blockieren nichts, stehen aber in `v_matrix.risiken`, im audit (`v_matrix.risiken`) und im Messprotokoll. `messtechnik_freigeben` verlangt `risiken_akzeptiert=True` und speichert die akzeptierten Risiken in `freigabe.json`.
- Grenze: Der KI-Prüfer organisiert und rechnet den Nachweis. Beweiskraft hat nur die Messung mit rückführbarer Referenz. Eine kritische Freigabe macht ein Mensch.

## Befehle (MCP mb2)

`project_new(…, einsatz)` → `anforderungen_erzeugen` → `eingaben_offen` → Entwurf (Agenten) → `audit`
(enthält `anforderungen_pruefen`, Feld `freigabe`) → Druck ab druckfertig → `abnahme_eintragen` am Gerät →
`messreihe_eintragen` am Prüfstand → `feld_eintragen` im Einsatz → `feld_abgleich` (zu optimistisch → Feldfall → Modell nachkalibrieren).

## Erstes echtes Beispiel

`projects/bodenklima-system/`:

- Lastenheft mit Herkunft.
- AB-ANSCHLUSS ist bewiesen, nach dem Umklemmen.
- AB-FUNK ist verletzt: SNR −17 dB am Beet.
- Die Feldmessungen vom 15.11.2026 sind eingetragen.
- E16 sagt jetzt −132,7 dBm voraus, gemessen wurden −134 dBm. Das passt.
- Das alte Freiraum-Modell hätte −84 dBm versprochen. Das ist der erste Feldfall in `tests/feldfaelle/`.
