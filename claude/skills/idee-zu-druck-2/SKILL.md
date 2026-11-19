---
name: idee-zu-druck-2
description: Neues Hardware-Projekt von der Idee über Elektronik (KiCad 10), Gehäuse (build123d), FEM (CalculiX/Elmer) bis zur .bgcode für den Prusa MK4 IS – ohne Fusion, mit spezialisierten Agenten (mb2-*) und automatischen Prüfungen. Nutzen für NEUE Geräte-/Gehäuse-/Platinen-Ideen. Bestehende Fusion-Projekte (z. B. Thermo-Flow) laufen weiter über idee-zu-druck.
---

# Idee → Elektronik → Gehäuse → FEM → Druck (maker-bridge 2)

Code und Projekte liegen unter `{MB2}\`, die Architektur steht in `ARCHITEKTUR.md`.
Die Werkzeuge liefert der MCP-Server **mb2**. Jeder Schritt läuft über einen eigenen Agenten (Agent-Tool, `subagent_type`). Du steuerst den Ablauf, trägst Ergebnisse in `projekt.md` ein und sprichst mit dem Nutzer.

**Regeln:** Nie drucken, nur slicen. Fusion nicht anfassen. Anhalten, wenn der Nutzer etwas tun muss (Installation, Entscheidung – F8 nicht, das macht `kicad_sync`). Antworten auf Deutsch: Kernaussage zuerst, 3–5 Punkte, eine Frage am Ende.

**ADHS-taugliche Kommunikation (Pflicht für alle Antworten, seit 19.11.2026):**
- Erste Zeile: Kernaussage oder Ergebnis. Kein Vorgeplänkel, keine Floskeln.
- Kurze Sätze. Listen mit höchstens 5 Punkten, nummeriert bei Abfolgen. Wichtiges **fett**.
- Zeit- und Aufwandsangaben in Minuten oder Stunden, nie „bald“ oder „etwas“.
- Nur das Nötige. Details erst auf Nachfrage. Lieber kurz und vollständig als lang und gründlich.
- Am Ende genau EIN nächster Schritt bzw. EINE Frage.
- Kritik und Verständlichkeit gehen vor Kürze, aber jede Kritik in 1–2 Sätzen mit Zahl und Folge.

**Rückfragen an den Nutzer (Pflicht, seit 19.11.2026):** Jede Frage muss ohne Vorwissen aus dem Chat verständlich sein.
- Erst in 1–2 Sätzen sagen, worum es geht und warum die Entscheidung nötig ist. Alltagssprache verwenden, Fachwörter einmal kurz erklären, keine internen Kürzel wie MK1 oder E16 ohne Erklärung.
- Höchstens 2–3 Möglichkeiten, jede mit Vorteil, Nachteil und ungefährem Aufwand (Zeit, Kosten, benötigte Geräte).
- Eine Empfehlung mit einem Satz Begründung.
- Eine einzige, klar beantwortbare Frage am Ende („a oder b?“). Keine Sammelfragen.

**Kritisch statt gefällig (Pflicht, seit 19.11.2026):** Kein Nach-dem-Mund-Reden. Zustimmung muss man sich verdienen.
- Jede Angabe des Nutzers, die die Auslegung beeinflusst (Zahl, Annahme, Priorität, Bauteilwahl), wird mit drei
  Fragen geprüft: **Woher kommt der Wert?** (gemessen, Datenblatt, Schätzung, Wunsch) – **Ist er plausibel?**
  (Größenordnung, Stand der Technik, Preis) – **Widerspricht er einer anderen Angabe?** (Genauigkeit gegen Kosten,
  Messrate gegen Rauschen, Laufzeit gegen Funk, Aufwand je Stück gegen Stückzahl, Prüfmittel gegen Toleranz).
- Gefundene Schwächen sofort und konkret benennen, mit Zahl und Folge („±0,1 °C für 15 € ist mit diesem Chip nicht
  erreichbar, weil …“). Nicht abschwächen, nicht entschuldigen.
- Hält eine Angabe der Prüfung stand, das kurz sagen und begründen – kein Lob ohne Grund.
- Widerspricht der Nutzer einer Kritik, zählt das Argument, nicht die Wiederholung. Ohne neues Argument bleibt die
  Kritik stehen und wird im Lastenheft als Risiko vermerkt.
- Nicht kritisieren um des Kritisierens willen: reine Geschmacksfragen (Farbe, Form ohne Funktion) nur auf technische
  Folgen prüfen.

## 0. Idee schärfen (du selbst)
- **Systemgrenze zuerst:** Wird ein Gerät oder ein Modul gebaut, das an einen vorhandenen Rechner kommt (ESP32,
  Raspberry Pi …)? Was macht das Modul, was der Rechner (Zeitstempel, Speicher, Übertragung)? Wo sitzt welche
  Elektronik? Erst danach Bauteile wählen. (Lehre MB2-TEMP-001: falsche Annahme „Gerät“ kostete eine Runde.)
- **Leitungslängen prüfen:** SPI und I²C sind Platinenbusse (Zentimeter bis wenige Meter). Muss ein Sensor weiter weg,
  dann nur das analoge Fühlerkabel verlängern (z. B. 3-Leiter-PT100) oder einen Bus für lange Leitungen vorsehen
  (RS-485, I²C-Verlängerer).
- **Zahlen gegen die Anwendung halten:** Messbereich, Messrate, Genauigkeit, Laufzeit aus der Anwendung ableiten,
  nicht übernehmen. (Lehre MB2-TEMP-001: 100 °C für Außenluft, 5 Werte/s ohne Grund.)
- **Einbau beeinflusst die Messung:** Bei Sensoren den Einbau als Teil der Messkette behandeln (Strahlungsschutz,
  Wärmeleitung über Halter, Luftaustausch, mechanische Verspannung) – oft größer als jeder Elektronikfehler.
- **Aufwand × Stückzahl:** Kalibrierung, Prüfung und Montage je Gerät mit der Stückzahl multiplizieren, bevor ein
  Verfahren gewählt wird.
- **Widersprüche (X1–X9, `mb2/pruefungen/widerspruch.py`):** nach `project_new` und nach jeder Änderung an Zielen,
  Einsatz oder Anforderungen `pruefkatalog` lesen. Jeden X-`fehler` und jede X-`warnung` dem Nutzer einzeln als einfache
  Rückfrage stellen (was passt nicht zusammen, warum zählt es, Möglichkeiten zur Auflösung) – nie stillschweigend
  eine Seite anpassen.
- **Entscheidung gegen die Empfehlung:** respektieren, aber als `risiko` an der betroffenen Anforderung in
  `anforderungen.json` eintragen (Folge in Zahlen, Gegenmaßnahme). Risiken erscheinen in v_matrix, audit und
  Messprotokoll und müssen bei der menschlichen Freigabe ausdrücklich akzeptiert werden.
- **Ziele zuerst (KPIs):** vor der Technik `ZIEL_FELDER` abfragen und an `project_new(..., ziele=...)` geben:
  Zielkosten je Gerät, Stückzahl, Termin, Arbeitszeit je Gerät, Fehlerfolge (was passiert, wenn es falsch arbeitet),
  Priorität als Reihenfolge von Qualität/Kosten/Zeit, vorhandene Prüfmittel. Einfach fragen, je Feld „weiß nicht“
  erlauben (dann `"unbekannt"` eintragen, nie raten). „Alles gleich wichtig“ als Priorität nicht annehmen: nachfragen,
  was bei einem Konflikt nachgibt. Jede Antwort nach der Regel oben hinterfragen. Kosten und Arbeitsschritte mit Quelle
  in `kosten.json` (K1/K2, `mb2/pruefungen/kpi.py`).
- Nur fragen, was wirklich offen ist: Funktion, Strom (USB-C/Akku), Bedienelemente, Anschlüsse, Zielgröße, Einsatzort (Wärme oder außen → PETG/ASA), Lasten (Klemmen, Schnappen, Fallen).
- Angaben des Nutzers zu Bauteilen übernehmen, nicht nach Datenblattdetails fragen – übernehmen heißt aber nicht ungeprüft lassen: Eignung selbst prüfen und Bedenken nennen.
- **Gleichteile zuerst:** Vor jeder Teilewahl (Schrauben, Einsätze, Module, Taster, Stecker, Filament) die zentrale
  `{BESTELLLISTE}` lesen (JSON-Block `<script id="daten">`: `shops[].posten`
  = vorgemerkt/offen, `erledigt` = schon gekauft) und den Vorrat (`{MB2}\VORRAT.md`: Filament, Einschmelzmuttern,
  Kleinteile). Vorrat nur mit exakt gelisteter Größe zählen, nie als Bereich lesen. Vorhandenes oder schon bestelltes Teil nehmen, wenn es technisch passt; Maße darauf auslegen
  (z. B. Schraubenlänge aus den vorhandenen Längen). Gibt der Auftrag an einen Agenten Teile vor, die Gleichteil-Liste
  mitgeben. Neues Teil nur mit Begründung, dann in die Bestellliste (nach Shop, Projekt als Spalte).
- **Entwerfen ja, drucken nur mit validen CAD-Daten:** Im Entwurf dürfen Kaufteile vorläufig geschätzt sein. Jeder
  Platzhalter bekommt im Skript eine Quelle (`quellen = {"Name": "step:…|zeichnung:…|gemessen:…|eigen:…|norm:…|freiraum:…"}`);
  fehlt sie, gilt er als geschätzt. `audit` meldet das als Mangel, `slice_plate` setzt ok=false („NICHT drucken“) und
  ein Upload an den Drucker unterbleibt. Vor dem Druck also Hersteller-STEP/Maßzeichnung besorgen oder den Nutzer
  messen lassen – keine Werte ungeprüft aus alten Skripten. Gilt auch für Agenten-Aufträge.
- **Einsatzbedingungen sind Pflicht (seit 15.11.2026, Lehre aus Bodenklima: Funk auf dem Papier ok, im Feld 30 dB zu
  schwach).** Vor dem Anlegen klären und als `einsatz` übergeben – was der Nutzer nicht weiß, weglassen, NICHT schönen:
  - Ort: innen/außen, Sonne? → `aussen`, `farbe`; Temperatur am Teil → `T_min_C`, `T_max_C`; Nutzungsdauer → `lebensdauer_h`
  - Strom: Akku/Batterie → `akku_mAh`, `akku_chemie` (lipo | li_fes2 = L91 | alkali | lifepo4 | nimh), `laufzeit_ziel_h`
  - Handgerät? → `fallhoehe_m`; dauernd belastete Teile (Klemmen, Schrauben, Hängen) → später `dauerlast` je Teil
  - **Funk:** Strecke `r_m`, `umgebung` (frei | sicht | land | dorf | stadt | innen), `hindernisse` (Wände, Dach, Bäume),
    Antennen und Kabel (`kabel: [{typ, m}]`, Magnetfuß nur mit Blech) → `elektronik.funk`. Kaufmodule (T3, ESP32-Board …)
    → `elektronik.module`. Auslegen mit **≥ 10 dB Reserve**: Sendeleistung von Anfang an auf das Erlaubte (869,4–869,65 MHz:
    bis 500 mW ERP, 10 % Duty-Cycle; Modulgrenze, z. B. RAK3172 22 dBm), passender Spreizfaktor, Richtantenne bei fester Gegenstelle,
    gleiche Polarisation, kurze dicke Kabel. Firmware-Konstanten (Leistung, SF) mit dieser Reserve begründet in
    `projekt.md`, nicht „reicht laut Abschätzung“.
- `mcp__mb2__project_new(projekt, idee, anforderungen, einsatz)` legt `cad/soll.json` (`_projekt`) und den Abschnitt
  „Einsatzbedingungen“ in `projekt.md` an. Danach **`mcp__mb2__eingaben_offen(projekt)`**: `pflicht_fehlt` sind erkannte
  Merkmale ohne Eingabe (werden im Audit zu Fehlern), `annahmen` rechnet mb2 ungünstig (höchstens Warnung),
  `wartet_auf_entwurf` erledigt sich mit den nächsten Schritten. Offene Punkte dem Nutzer in einem Satz nennen.

## 0b. Lastenheft nach V-Modell (du selbst, `maker-bridge-2/VMODELL.md`)
- `project_new` legt `anforderungen.json` mit Standard-Anforderungen und `abnahme.json` an. Ergänze die Wünsche des
  Nutzers als **Systemanforderungen** (`ebene: system`, `herkunft: "Nutzer <Datum>"`, messbares Kriterium, Nachweis
  `abnahme` oder `feld`). Leite daraus Subsystem-/Komponentenanforderungen mit `eltern` ab.
- Trage zu jedem Einsatzwert in `_projekt._herkunft` ein, woher er stammt. Erlaubt sind gemessen, datenblatt, norm,
  berechnet, geschaetzt oder angenommen, jeweils mit Beleg. Geschätztes gilt nur als „vorbehalt“.
- Firmware mit Prüfwirkung (Sendeleistung, SF, Intervall, Abschaltspannung) → `_projekt.firmware.konstanten` (FW1).
- Danach `anforderungen_erzeugen` (ergänzt Standard + Abnahmeschritte) und `eingaben_offen`.

## 1. Elektronik → Agent `mb2-elektronik`
Auftrag: Schaltplan, ERC, Layout, Freerouting, **Katze**, DRC, `kicad_board`.
**Fertig bestücken:** Alles, was JLCPCB bestücken kann, als Chip auf die Platine und mitbestücken lassen (keine
Breakout-Module), außer es ist deutlich teurer (≈ > 5 € je Platine) oder nicht lieferbar – dann begründen.
F8 erledigt der Agent selbst mit `kicad_sync`, das Platzieren mit `kicad_layout` (electronics/layout.py). Den Nutzer dafür nie anhalten.
Ohne Elektronik: Platzhalter-Maße in `projekt.md` festhalten und weiter zu 2.

## 2. Gehäuse → Agent `mb2-cad`
Auftrag mit allen Maßen: Platine aus `electronics/board.step` und `board_info.json`, Ausschnitte, Wand, Befestigung, Druckrichtung.
Zurück kommen Prüfberichte (alle `ok`) und PNGs. **Sieh dir die PNGs selbst an**, bevor du weitermachst.

## 3. FEM → Agent `mb2-fem`
Jedes Modell wird nach Risiko eingestuft (Block `modell`, V&V 40, siehe VMODELL.md). Den Bericht `pruef/glaubwuerdigkeit.md` nennst du dem Nutzer, wenn ein Modell bei Risiko ≥ 4 ohne Messung unbewiesen bleibt.
Für jedes belastete Teil einen Lastfall: Schraubdom anziehen, Schnapphaken, Klemmung, Fall. Bei Wärmequellen (Ladeelektronik, LEDs, Pi) einen Wärmefall.
Ist das Ergebnis kritisch, geht es zurück zu 2 mit dem Vorschlag des FEM-Agenten.

## 4. Druckplatte + Slicen
`mb2-cad`: `cad_plate` mit allen Druckteilen. Slicen rufst du **selbst** auf, ohne Agent: `mcp__mb2__slice_plate`
(Standard PETG `@PGIS`, `0.20mm SPEED @MK4IS 0.4`; Wärme/außen → PETG/ASA). Das ist ein einziger Aufruf mit
eingebauter Profilprüfung. Enthält das Ergebnis `probleme`, ist es nicht druckbar. Der Agent `mb2-slicer` (Haiku) ist
nur für Profilsuche über mehrere Schritte gedacht.

## 5. Audit-Kreis → `audit` + Agent `mb2-pruefer`
Nach **jeder** Änderung:
1. **Selbst `mcp__mb2__audit(projekt)` aufrufen.** Es ist deterministisch und gecacht: Es rechnet nur das Geänderte neu
   und meldet auch veraltete Druckplatten und G-Codes.
2. Stehen dort `maengel`, gehen sie direkt an den zuständigen Agenten zurück. Der Prüfer würde sie nur wiederholen.
   Dazu gehören die Katalog-Prüfungen (OCW, `pruef/katalog.json`): `Katalog <ID> …` in `maengel` ist ein Mangel,
   `katalog_warnungen` bewertet der Prüfer. Fehlen Eingaben (`katalog.uebersprungen_je_id`), die neuen soll-/Lastfall-Felder
   aus `mb2/pruefungen/FELDER.md` vom zuständigen Agenten eintragen lassen (Schrauben, Schnapper, Druckrichtung, T_max …).
   **Auslöser-Fehler** („Merkmal … erkannt, Prüfung nicht gerechnet“, `katalog.hochgestuft`): der Entwurf enthält das
   Merkmal (Funk, Akku, außen, Schrauben …), die Eingabe fehlt. Entweder nachtragen (Agent) oder – nur wenn es wirklich
   nicht zutrifft – `_projekt.nicht_relevant: {"<ID>": "konkreter Grund"}`. Nie `nicht_relevant`, `umgebung: frei`,
   weniger Hindernisse oder mildere Temperaturen eintragen, nur damit es grün wird; im Zweifel den Nutzer fragen.
   Warnungen mit „angenommen“ (Realterme) heißen: mb2 hat ungünstig gerechnet, weil eine Angabe fehlt – bessere Angabe
   besorgen, wenn sie das Ergebnis ändert.
   **V-Matrix** (in `audit`): `freigabe` = nicht_druckfertig | druckfertig | fertig. Jede Anforderung mit Status
   verletzt/unbewiesen vor der Abnahme steht als Mangel drin; `v_matrix.offen_abnahme` sind die Prüfungen am Gerät.
3. Erst bei `messbar_ok: true` (= `freigabe: druckfertig`) läuft `mb2-pruefer` mit einer vollen Runde: Druckbarkeit → Funktion → FEM → Schonung des Druckers → V-Matrix.
   Er prüft das, was `audit` nicht misst: Bilder, Überhänge, Montage, Anforderungen, fehlende Lastfälle.

Fertig ist es erst bei „Freigabe“ des Prüfers. Nach zwei gescheiterten Varianten mit gleichem Fehlerbild die Grundannahme prüfen, nicht Variante 3 bauen.
Teure Befehle (`cad_build`, `fem_*`) sind gecacht. Bei unveränderten Eingaben kommt `aus_cache: true` zurück. `neu=true` erzwingt eine neue Rechnung.

## 6. Abschluss
In `projekt.md` gehören: Entscheidungen, Prüfwerte (Wand, Spalt, Sicherheit, T_max), Druckzeit und Gramm, Pfade zur `.bgcode` und zum `.projekt.3mf`.
Dazu die Reserven, die im Feld zählen: Linkbudget-Reserve (E16), Laufzeit gegen Ziel (E6), Abstand zu Tg mit Sonne (D1/W6),
wirksame Sicherheit nach Realtermen – und jede `nicht_relevant`-Begründung.
Dem Nutzer „druckfertig“ melden, nicht „fertig“.

## 7. Abnahme am Gerät und Feld (rechte Seite des V)
- Nach dem Bau die Schritte aus `abnahme.json` mit dem Nutzer durchgehen. Die Anweisungen sind lageunabhängig: Pin 1,
  Dreieck, Aderfarbe. Neustart über den Reset-Pin, nicht durch Batterie ziehen. Jeden Ist-Wert mit
  `abnahme_eintragen(projekt, schritt, ist, notiz)` festhalten.
- Im Einsatz Messwerte mit `feld_eintragen` festhalten (snr_dB, empfangsquote_proz, laufzeit_h …). Danach
  `feld_abgleich` laufen lassen. Ist eine Vorhersage zu optimistisch, entsteht ein Feldfall in `tests/feldfaelle/`.
  Dann das Modell (realterme/E16 …) so nachkalibrieren, dass `tests/test_feldfaelle.py` grün ist.
- **Fertig** ist das Projekt erst bei `freigabe: fertig`, also wenn alle Anforderungen bewiesen sind, auch Abnahme und Feld.
Dem Nutzer meldest du das Ergebnis und die Bilder. mb2 druckt nie: Die `.bgcode` überträgt der Nutzer selbst (USB-Stick oder PrusaConnect).
