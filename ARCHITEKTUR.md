# maker-bridge 2 – Architektur

**Kern:** Idee → Elektronik (KiCad 10) → Gehäuse (build123d) → FEM (Gmsh + CalculiX/Elmer) → Druck (PrusaSlicer, MK4 IS).
Alles läuft ohne Oberfläche, alles in mm, jeder Schritt wird automatisch geprüft. Die alte `maker-bridge/` mit Fusion bleibt unverändert.

Stand: 10.11.2026 – Kette steht, beide Abnahmen bestanden; Katalog-Prüfungen (Abschnitt 7b) eingebaut (siehe „Status“ unten).

## 1 Aufbau

```
Skill idee-zu-druck-2 (Ablauf, Audit-Kreis)
   │  ruft Agenten auf (.claude/agents/mb2-*.md), jeder nur mit seinen Werkzeugen
   ▼
MCP-Server mb2 (mb2/server.py, dünn)  ──>  je Aufruf ein Unterprozess:  python -m mb2 <befehl> --json
                                                      │
          ┌──────────────┬───────────────┬────────────┴──────┬──────────────────┐
       kicad.py        cad.py          fem.py             slicer.py         projekt.py
   kicad-cli, pcbnew  build123d (OCCT) Gmsh → ccx / Elmer  prusa-slicer-     Ordner, Status
   Freerouting        Prüfungen, PNG                      console + Bundle
```

### Entscheidung: dünner MCP-Server über CLI (nicht nur CLI-Skripte)
- **Werkzeugrechte je Agent gehen nur mit MCP.** Mit reinen CLI-Skripten braucht jeder Agent `Bash` und kann damit alles. Mit MCP bekommt der CAD-Agent z. B. nur `cad_*` und Read/Write.
- **Trotzdem kein Ballast:** Der Server enthält keine Logik. Er reicht jeden Aufruf an `python -m mb2 …` in einem eigenen Prozess weiter.
  - Ein Absturz von OCCT, Gmsh oder einem Löser trifft nur diesen einen Aufruf.
  - `stdin` ist zu, das alte Hängeproblem beim DSN-Export kann nicht auftreten.
  - Jeder Befehl läuft auch von Hand in der Konsole (Tests, Fehlersuche).
- Kein Dauerzustand, kein geteiltes Dokument. Mehrere Sessions arbeiten parallel, jede auf ihren eigenen Dateien.

## 2 Projektordner

`maker-bridge-2/projects/<slug>/`

| Ordner | Inhalt |
|---|---|
| `projekt.md` | Idee, Anforderungen, Entscheidungen, Audit-Ergebnisse |
| `electronics/` | KiCad-Projekt, `board_info.json`, `board.step` |
| `cad/` | ein Skript je Teil (`<teil>.py`) + `soll.json` (Sollmaße) |
| `out/` | STEP, 3MF, PNG, Prüfberichte (`<teil>.pruefung.json`) |
| `fem/` | Netz, Löser-Eingaben, Ergebnis-JSON + PNG |
| `print/` | `platte.3mf`, `.bgcode`, PrusaSlicer-Projekt |

## 3 CAD (build123d)

**Ein Teil = ein Skript.** Das Skript baut mit build123d und gibt am Ende Folgendes aus:
- `teil`: der Körper (Part)
- optional `platzhalter = {"Platine": part, …}` für die Kollisionsprüfung
- optional `druckrichtung`: Drehung für den Druck

Mit `cad_build` geht es so weiter:
1. Skript im eigenen Prozess ausführen
2. Prüfen (siehe unten)
3. STEP und 3MF schreiben
4. PNG rendern: Iso, Draufsicht und Schnitt durch die Teilmitte (Blender, gleicher Maßstab)

**Prüfungen** – der Agent sieht nichts, also wird nach jedem Bauschritt gemessen:

| Prüfung | Methode | Grenze |
|---|---|---|
| Gültiger Körper | OCCT `BRepCheck` (`is_valid`), genau 1 Solid, geschlossen | Pflicht |
| Volumen, Bounding Box | gegen `soll.json` | Toleranz je Wert, Standard ±2 % bzw. ±0,1 mm |
| Kollision | Schnittvolumen Platzhalter ∩ Teil | > 0,001 mm³ = Fehler |
| Wandstärke | Strahl-Test: von Flächenpunkten nach innen entlang −Normale bis zur Gegenseite | ≥ 1,8 mm |
| Spalte | Strahl-Test nach außen: Abstand zur nächsten eigenen Fläche | keine Spalte < 0,4 mm (Düse) |
| Sichtkontrolle | PNG Iso + Draufsicht + Schnitt, mit Maßangaben und Legende | Agent schaut das Bild an |

Wandstärke und Spalte: Gemessen wird auf einem Punktraster über alle Flächen, Abstand ≈ 1 mm, dazu Kantennähe.
Gerundete Kanten und gewollte Fasen erzeugen falsche Treffer. Deshalb werden Punkte im Abstand < 0,3 mm von einer Kante ausgelassen.
Ausnahmen (z. B. Schnapphaken mit 1,2 mm) stehen in `soll.json` unter `ausnahmen` und werden im Bericht ausgewiesen, nicht verschwiegen.

**Druckplatte:** `cad_plate` legt mehrere Teile in build123d nebeneinander, Unterseite auf Z=0, Lage in der Bettmitte.
Daraus wird **ein** 3MF, denn die PrusaSlicer-CLI ordnet nicht an.

**Render (seit 10.11.2026):** Blender 5.2 headless (`render_blender.py` + `blender_szene.py`), Workbench-Engine, orthografisch, ca. 4 s je Teil. Drei Ansichten im gleichen Maßstab: Iso, Draufsicht und Schnitt. Der Schnitt liegt standardmäßig in der Teilmitte, seine Normale ist die mittlere Achse der Bounding Box; ein Teil-Skript kann ihn mit `schnitt = ('Y', 0.0)` festlegen. Gezeigt werden Platzhalter halbtransparent und farbig, Schnittflächen rotbraun, Prüf-Fehlerstellen als rote Kugeln, dazu eine Legende. Die Druckplatte zeigt Bett (iso), Teile (nah) und Draufsicht. Rückfall: matplotlib wie vorher, wenn Blender fehlt oder scheitert oder `MB2_RENDER=matplotlib` gesetzt ist. Das Rendern kostet keine Claude-Tokens, nur das Ansehen (≈ 1,5k je Bild, wie vorher). FEM-Feldbilder bleiben matplotlib.

**Druckfreigabe nur mit validen CAD-Daten (seit 11.11.2026, Regel des Nutzers):** Entwerfen darf mit vorläufigen
Maßen, gedruckt wird nur, wenn jedes Kaufteil belegt ist. Teil-Skripte setzen `quellen = {"Platzhalter": "<art>:<beleg>"}`
mit den Arten `step:` (Hersteller-STEP, Datei muss existieren), `zeichnung:` (offizielle Maßzeichnung/Datenblatt),
`gemessen:` (Nutzer), `eigen:` (eigene Platine/Druckteil), `norm:` (DIN/ISO), `freiraum:` (Konstruktions-Luft).
`Einsetzweg_<X>` erbt die Quelle von `<X>`. `cad.quellen_pruefen` schreibt `quellen` + `ungeprueft` in den Prüfbericht
(Warnung, kein Baufehler); `audit` meldet ungeprüfte Platzhalter als Mangel; `slice_plate` setzt dann `ok=false` mit
„NICHT drucken“ und `ungeprueft` in `print/slice.json`; `printer_upload` der alten Bridge liest diese Datei und lehnt ab.
Anlass: Frag-mich-Gehäuse – USB-A des Pi 4 traf eine Ecksäule (Platzhalter aus altem Skript geschätzt).

**Gemessene Toleranzen MK4 + PETG (11.11.2026):** Funktionsbohrungen kommen ≈ 0,1 mm zu eng → +0,15 zeichnen
(Ruthex M3 Ø 4,15); Steckpassungen mit 0,3 je Seite klemmten → 0,4 je Seite. Steht auch in `mb2-cad`.

**Beobachten: SolidCraft** (Rust, MCP eingebaut, Okt. 2026). Heute nicht genommen: eigener junger Geometriekern
(Rundungen/Fasen/STEP unbelegt), die Prüfungen brauchen OCCT-Strahlschnitte, Gmsh nutzt denselben Kern wie build123d.
Neu bewerten, sobald STEP-Austausch und Rundungen belegt sind – dann als Ansicht/zweites CAD andocken.

## 4 FEM

```
STEP ─ Gmsh (C3D10/Tet10, Verfeinerung per Box) ─┬─ CalculiX: .inp schreiben → ccx → .dat/.frd lesen
                                                   └─ Elmer:   .msh → ElmerGrid → .sif → ElmerSolver → .vtu lesen
```
- **Mechanik (CalculiX):** linear statisch oder `NLGEOM`, Kontakt per `*CONTACT PAIR` (Fläche-Fläche, Penalty).
  Lagerung und Last werden über Flächen-Auswahlen (Ebene/Box/Zylinder) in mm beschrieben, als JSON-Lastfall.
- **Wärme (Elmer):** stationäre Wärmeleitung, Wärmequelle je Volumen oder Fläche, Konvektion außen (h, T∞). Optional (seit 10.11.2026): Strahlung mit Himmelsanteil je Fläche, h aus freier Konvektion, Innenluft als Ersatzleiter, Sonne mit Abschattung; Energiebilanz bei jedem Lauf.
- **Mechanik optional (seit 10.11.2026):** Eigengewicht (`schwerkraft`), Netzstudie (`konvergenz`), Druckrichtung → Tsai-Hill in der Bewertung, transversal-isotrope Steifigkeit (`orthotrop`); immer: Gleichgewicht, Energie, Spannungsfeld `.npz`, Newton/Kontakt. Ohne die neuen Felder gleiche Ergebnisse wie vorher (Stifthalter-Abnahme unverändert).
- **Material:** `mb2/material.py` mit PLA, PETG und ASA (E, ν, Streckgrenze, Wärmeleitfähigkeit, Glasübergang).
- **Ergebnis-JSON:** max. von Mises, Sicherheit = Festigkeit / σmax je Material, max. Verschiebung bzw. T_max, dazu ein PNG.
- **Referenz:** Stifthalter v5 gegen `fem_halter.py` (scikit-fem, Tet10, linear). Abnahme: Verschiebung und σ an denselben Punkten innerhalb ±3 %. Bestanden, siehe Status.
- **σ-Bewertung linear:** an den Elementecken aus dem Verschiebungsfeld (`von_mises_feld`), weil dort bei Tet10 das Maximum liegt.

## 5 Elektronik (KiCad 10)
Übernommen aus `maker-bridge/maker_bridge/kicad.py` und entschlackt. Projekt, Board-Info, ERC/DRC, STEP, Render, Fertigungsdaten, Bibliothekssuche, Freerouting und Katze bleiben.
Die Fusion-Übergabe entfällt. Stattdessen schreibt `kicad_step` `board.step` + `board_info.json` in den Rahmen, den die CAD-Skripte direkt laden.
**Jede Platine bekommt eine Katze** (`kicad_cat`), nach dem Routing.
**F8 ohne Oberfläche (13.11.2026):** `kicad_sync` = „Platine aus Schaltplan aktualisieren“: kicad-cli exportiert die Netzliste (XML), KiCads Python legt fehlende Footprints rechts neben der Platine an, tauscht geänderte (Lage bleibt), setzt Wert, Schaltplan-Pfad (Symbol-UUID) und Pad-Netze; Abgleich per UUID (`m_Uuid`, nicht `id()` der SWIG-Hülle). Wiederholbar (2. Lauf ändert nichts), DRC-Parität danach 0. `kicad_layout` führt `electronics/layout.py` mit KiCads Python aus. Damit hält kein Agent mehr für F8 beim Nutzer an.

## 6 Slicen
Übernommen aus `maker-bridge/maker_bridge/slicer.py`. Die Profile werden selbst aus dem Bundle aufgelöst und per `--load` übergeben.
Seit 10.11.2026 hat `slice_plate` zwei Parameter: `brim_mm` (Brim nur außen, für hohe und schmale Teile) und `perimeter` (Zahl der Wandlinien statt Profilwert). Das MCP-Schema zeigt sie erst nach einem Neustart des mb2-Servers, bis dahin geht es über `python -m mb2 slice_plate '{…}'`.

**Bricklayers (seit 10.11.2026, je Teil zuschaltbar):** `"bricklayers": true` beim Teil in `cad/soll.json` → `slice_plate` slicet ASCII statt binär und hebt in `mb2/bricklayers.py` jede zweite Innenwand um h/2 an (verzahnt wie Mauersteine; Außenwand bleibt). Ausgabe `print/<projekt>.gcode` statt `.bgcode` (MK4 druckt beides).
- Zuordnung Teil → G-Code-Objekt über Lage und Höhe (`print/platte.json` bbox ↔ Extrusionsbereich je `M486`), weil PrusaSlicer die Objekte **nicht** in Plattenreihenfolge nummeriert (im Test vertauscht!). Unsicher (> 3 mm) → Abbruch statt falsches Teil.
- Erste Schicht angehobene Linie 1,5 × E, letzte Objektschicht 0,5 × E ohne Anhebung. Gegenprüfung im G-Code: Extrusion ±2 %, Z-Maximum unverändert, Anhebung = Rückstellung. Ergebnis in `slice.json` → `bricklayers`.
- Grenzen: nur relative E, Überhang-Wandlinien unberührt, an Zwischen-Deckflächen steht die angehobene Linie h/2 über.
- Nutzen laut Literatur +14 % (PLA) / +10 % (PETG) Festigkeit quer zu den Schichten und deutlich dichtere Wände (CNC Kitchen; Drucktest 4 bar). Der Katalog rechnet **ohne** Bonus (nicht am MK4 gemessen); Modul `pruefungen/druck.py` meldet Status (BL: info/warnung/fehler). Audit meldet, wenn das Flag gesetzt, der G-Code aber ohne ist.
- Test: `tests/test_bricklayers.py`; Ende-zu-Ende an einer Kopie von frag-mich-alles: 5122 Linien angehoben, Extrusion ±0,0 %, Profilprüfung MK4IS ok.
Nach dem Slicen wird geprüft:
- `printer_model` = MK4IS
- Filament wie verlangt
- Druckprofil `@MK4IS 0.4`

Feste Standardwerte: `Original Prusa MK4 Input Shaper 0.4 nozzle`, `0.20mm SPEED @MK4IS 0.4`, `Prusament PETG @PGIS`.
Kein Upload, kein Drucker. Das macht weiter die alte Bridge, nur auf ausdrücklichen Wunsch.

## 7 Agenten (`Claude Code Projekte/.claude/agents/`)

| Agent | Werkzeuge |
|---|---|
| `mb2-elektronik` | `kicad_*`, Read, Write, Edit |
| `mb2-cad` | `cad_*`, Read, Write, Edit |
| `mb2-fem` | `fem_*`, `cad_render`, Read, Write |
| `mb2-slicer` | `slice_*`, Read |
| `mb2-pruefer` | alle Prüf- und Lese-Werkzeuge, **kein** Write. Audit-Kreis: Druckbarkeit → Funktion → FEM → Schonung des Druckers |

Der Skill `idee-zu-druck-2` steuert den Ablauf und ruft die Agenten der Reihe nach auf. Die Ergebnisse trägt er in `projekt.md` ein.

## 7a Effizienz (05.11.2026)
Ziel: weniger Modellaufrufe und weniger Rechenzeit, ohne Qualitätsverlust.
- **Cache** (`mb2/cache.py`) für `cad_build`, `fem_mech` und `fem_waerme`.
  - Schlüssel: SHA-256 über alle Eingaben (`cad/` komplett, `board.step`, `board_info.json` bzw. Lastfall-JSON und jede darin genannte STEP-Datei), den Quelltext von `mb2/*.py` und den Pfad des Lösers.
  - Ändert sich etwas davon, wird neu gerechnet, auch nach einer Änderung an den Prüfungen. Treffer zählen nur, wenn alle Ausgabedateien noch da sind. `neu=true` erzwingt eine neue Rechnung.
  - Ergebnis `aus_cache: true`. Testdose-Audit: 24 s → 2 s.
- **`audit(projekt)`:** alle messbaren Prüfungen in einem deterministischen Aufruf.
  - Teile, FEM-Bewertungen, DRC und Katze
  - Druckplatte bzw. G-Code älter als ihre Eingaben
  - Slicer-Profilprüfung (`print/slice.json`)
  - Der Skill ruft es nach jeder Änderung selbst auf. `mb2-pruefer` läuft erst bei `messbar_ok`, beginnt mit `audit` und kümmert sich dann nur um das Nichtmessbare (Bilder, Überhänge, Montage, Anforderungen).
- **Modelle:**
  - `mb2-slicer` läuft auf Haiku. Slicen ruft der Skill direkt auf, ohne einen Agenten zu starten.
  - CAD, Elektronik, FEM und Prüfer bleiben auf dem großen Modell, weil dort die Qualität entsteht.
- **Bewusst nicht geändert:** Die Auflösung der Renderbilder (1540 × 660 px) liegt unter der Grenze, ab der Bilder verkleinert werden. Kleiner hieße weniger Detail bei der Sichtkontrolle.
- Geprüft und verworfen: DSPy, RouteLLM, EasyDistill und lokale 3–14B-Modelle.
  - Zu wenige gleichartige Aufrufe, um zu optimieren oder zu trainieren.
  - Kleine Modelle schreiben unzuverlässigen build123d-Code.

## 7c Nicht-planare Bahnen (seit 10.11.2026, erster Stand)
- `mb2/nonplanar.py`: Bahn direkt als Punktliste/G-Code ohne Slicer. Erster Fall Becher mit Flechtwand: eine Spirale, Hoehe schwingt mit halbzahligem k Wellen je Runde, Steigung h = Strang + 2·Amplitude → Straenge beruehren sich nur an Kreuzungen.
- Pruefungen auf der Punktliste: Abstand zur Vorrunde (kein Durchdringen, Haftung an Kreuzungen), Steigung ≤ 45°, freie Spannweite, Hotend-Kollision gegen eine Huellkontur der Nextruder-Duese (angenommen, nicht vermessen; eigener Strang der letzten 3 mm ausgenommen), Bauraum.
- Vorschau: `mb2/blender_bahn.py` rendert die Bahn als Roehren (Workbench, Iso + Nah), ~7 s. Pfade an Blender absolut uebergeben.
- `print/bahn_koerper.gcode` enthaelt nur Bewegungen; Start-/End-Code MK4 fehlt noch – nicht drucken. Projekt: `projects/teelicht-nonplanar`.

## 7d V-Modell (seit 15.11.2026) – `VMODELL.md`, `mb2/anforderungen.py`
Anforderungen als Daten (`anforderungen.json`, Ebenen system/subsystem/komponente mit Eltern und Herkunft), Nachweise
je V-Ebene (komponente: cad/DRC/Katalog je Teil, integration: Katalog-Systemprüfungen/FEM, abnahme: `abnahme.json` am
Gerät, feld: `feld.json`). `anforderungen_pruefen` (in `audit` enthalten) schreibt `pruef/v_matrix.json` mit Status
bewiesen/vorbehalt/unbewiesen/verletzt, Reserve gegen Unsicherheit aus der Herkunft (`_projekt._herkunft`) und Freigabe
nicht_druckfertig/druckfertig/fertig. `feld_abgleich` macht aus zu optimistischen Vorhersagen Feldfälle
(`tests/feldfaelle/`, geprüft von `tests/test_feldfaelle.py`). Firmware-Konstanten prüft `pruefungen/firmware.py` (FW1).

## 7e Glaubwürdigkeit nach V&V 40 (seit 17.11.2026) – `mb2/glaubwuerdigkeit.py`
Jeder FEM-Nachweis wird je Modell nach Risiko (Einfluss × Folge) eingestuft. Die Pflichten wachsen mit dem Risiko: Die Faktoren haben Stufen (Code, Lösung, Sensitivität, Strenge der Validierung, Anwendbarkeit, Herkunft). Die Sensitivität rechnet `fem_sensitivitaet`, die Varianten liegen in `fem/sens/`, der Materialwechsel je Lauf geht über `material_override`.
Einzelheiten in `VMODELL.md`, Bewertung und Quellen in `IN_SILICO.md`. Test: `tests/test_glaubwuerdigkeit.py`.

## 7b Katalog-Prüfungen (mb2/pruefungen)
Analytische Prüfungen aus `OCW_PRUEFKATALOG.md` als Vorab-Schätzung, Gegenprobe zur FEM und harte Grenze. Sie **lesen nur**, was vorliegt (STEP, `*.pruefung.json`, FEM-Ergebnisse, `print/slice.json`, KiCad), und rechnen keine FEM.

- **Aufbau:** je Fachgebiet ein Modul mit `pruefe(pdir) -> list[dict]`, Rahmen in `mb2/pruefungen/__init__.py` (`ergebnis()`, `uebersprungen()`, `alle()`).
  - Jedes Ergebnis hat Katalog-ID, Stufe (`ok`/`info`/`warnung`/`fehler`/`uebersprungen`), Wert, Grenze, Einheit, Quelle und Hinweis, optional Teil und Daten.
  - Ein Modulabsturz wird als `fehler` mit der Modul-ID gemeldet und nicht verschluckt; die übrigen Module laufen weiter.
  - **Keine Scheinsicherheit (seit 15.11.2026):** `merkmale.py` erkennt, was der Entwurf enthält (Funk, Akku, außen, …);
    `AUSLOESER` in `__init__.py` macht ein `uebersprungen` dieser Prüfungen zum `fehler` (Verzicht nur über
    `_projekt.nicht_relevant`). `mb2/realterme.py` hält alle Realabschläge (Temperatur, Kriechen, UV, Kälte, Alterung,
    Funkpfad, Maßstreuung) und die eine Teiltemperatur; Annahmen → höchstens `warnung`. `pruefkatalog`/`audit` melden
    `hochgestuft` und `merkmale`. Anlass und Funde: `audits/SCHEINSICHERHEIT_2026-11-15.md`.
  - **Ablauf:** `project_new(projekt, idee, anforderungen, einsatz)` legt die Einsatzbedingungen in `cad/soll.json`
    (`_projekt`) und `projekt.md` an (`EINSATZ_FELDER` in befehle.py); `eingaben_offen(projekt)` listet `pflicht_fehlt`
    (Auslöser ohne Eingabe), `wartet_auf_entwurf`, `annahmen` und offene Einsatzfelder – nach project_new und nach jedem
    Agentenschritt (Skill idee-zu-druck-2, Agenten mb2-*). FEM-Bewertungen aus dem Cache werden mit den aktuellen
    Realtermen neu bewertet. Feldmessungen gehören nach `projects/<p>/feld.json` und kalibrieren realterme nach.

  | Modul | IDs | liest |
  |---|---|---|
  | `fem_plausi` | F20–F25, M7–M9 | Mechanik-`*.erg.json` + `.spannung.npz`, Slicer |
  | `waerme` | W1–W10 | Wärme-`*.erg.json`, soll, Slicer |
  | `mechanik` | M1–M6, M12–M16, M19, M21–M24, M26 | soll, STEP (`geometrie.py`), FEM |
  | `dauer` | D1–D12 | soll, Wärme-FEM, `board_info.json`, `kennwerte` |
  | `toleranz` | T1–T6, T-UB | soll, `projects/kalibrierkoerper/messung.json` |
  | `schwingung` | S1–S8 | FEM (Eigengewicht, Federrate), soll, STEP |
  | `elektronik` | E1–E25 | `.kicad_pcb` (pcbnew) + Netzliste (kicad-cli), Kopien im Temp-Ordner, `bauteile.json` |

- **Befehl `pruefkatalog(projekt, module=None)`** (Gruppe audit): ruft `alle()`, schreibt `pruef/katalog.json` und gibt Zählung je Stufe, Fehler und Warnungen als Zeilen sowie `uebersprungen_je_id` zurück. Laufzeit an den 6 Projekten 0,1–6 s, die Elektronik ist dabei der größte Posten.
  - Mit `module=[…]` wird nur eine Teilmenge geprüft; `katalog.json` enthält dann nur diese Module.
  - Im MCP-Schema erscheint der Befehl erst nach einem Neustart des mb2-Servers, bis dahin `python -m mb2 pruefkatalog projekt=<slug>`.
- **In `audit`:** Der Katalog läuft zuletzt, nach CAD und FEM. Katalog-`fehler` werden zu `maengel` („Katalog M22 [haken] …“), damit ist `messbar_ok` falsch. `warnung` steht in der eigenen Liste `katalog_warnungen`, die Zählung unter `katalog`. Alle bisherigen Audit-Schlüssel bleiben.
  - `mb2-pruefer` bewertet die Warnungen: begründet hinnehmen oder als Mangel melden.
  - `uebersprungen` heißt, dass eine Eingabe fehlt. Der Prüfer schlägt das passende soll-Feld vor (`FELDER.md`).
- **Neue Felder:** alle optional in `cad/soll.json` (`_projekt` bzw. je Teil) und in den FEM-Lastfällen (`schwerkraft`, `konvergenz`, `druckrichtung`, `orthotrop`; Wärme `strahlung`, `konvektion.auto`, `innenluft`, `sonne`). Die vollständige Liste steht in `mb2/pruefungen/FELDER.md`. Ohne die Felder bleibt jedes bisherige Ergebnis gleich.
- **Kennwerte:** `mb2/kennwerte.py` liefert je Wert eine Quelle mit Herkunfts-Tag (`[gedruckt]`, `[voll, abgem.]`, `[abgeleitet]`, `[vorlaeufig]`), `None` heißt unbekannt (Grund in `OFFEN`). Ein Projekt kann Werte über `_projekt.kennwerte` überschreiben. Die Bauteil-DB `mb2/bauteile.json` gibt je Wert Quelle und Stand an (geprüft/datenblatt/typklasse).
- **Grenzen:**
  - FEM-Spitzen an Kerben und Lagern gehen bewusst ungefiltert in M7/M22 ein und werden nicht unterdrückt. M6/F22 benennen die Singularität. Heute melden deshalb haken und front M22 `fehler`.
  - Kriechen (D3–D7) läuft mangels SLS-Kennwerten nur für ASA (Kriechmodul 1000 h) oder mit Projekt-Werten.
  - T1/T4/D10 rechnen bis zur Messung am Kalibrierkörper vorläufig und melden dann höchstens `warnung` – außer T1 bei C_pk < 0 (Mittelwert schon außerhalb der Toleranz): `fehler`.
  - Achsen von Haken, Scharnieren, Bohrungen und Zahnrädern sowie Stab- und Deckeldaten kommen aus soll, nicht aus der Geometrie.
  - M9 prüft den Infill-Kern analytisch, der Löser rechnet weiter Vollmaterial.
  - S1 aus FEM nimmt die größte Verschiebung (Einmassen-Näherung, etwa 20 % unter dem Kragarm-Wert). `rayleigh_f1_Hz` steht zusätzlich im Ergebnis. S2 bewertet mit der schärfsten belastbaren f₁-Schätzung, nicht blind mit der kleinsten.
  - PLA-E-Modul seit 10.11.2026 2300 MPa (Prusament TDS, gedruckt) statt 3500 (Vollmaterial); alte PLA-FEM-Ergebnisse rechnen beim nächsten Lauf neu (Cache).
  - Alte `*.erg.json` ohne die neuen Felder: F23, F24, M7 und M9 melden `uebersprungen` („neu=true“).
- **Tests:** `tests/test_pruef_*.py`, `tests/test_kennwerte.py`, Integration `tests/test_pruef_katalog.py` (fem.py-Ausgabe → Leser, Befehl, Audit, alle Projekte in Kopien). Jedes Skript läuft einzeln mit `.venv/Scripts/python.exe tests/<datei>.py` (kein pytest).

## 8 Installation
- Python 3.12 per `uv sync` (OCCT-Räder gibt es für 3.12 sicher)
- CalculiX 2.23: MSYS2 (`C:\msys64`, winget `MSYS2.MSYS2`), in „MSYS2 UCRT64“ `pacman -S mingw-w64-ucrt-x86_64-calculix-ccx`; Update `pacman -Syu`
- Elmer 26.1 (nogui, MPI): offizieller Installer `ElmerFEM-nogui-mpi-Windows-AMD64-rel26.1.exe` nach `C:\Program Files\Elmer 9.0-Release` (Name veraltet, Build 20.01.2026) + Microsoft MPI (winget `Microsoft.msmpi`)
- `python -m mb2.werkzeuge` zeigt nur noch an, was gefunden wurde (Pfade, Versionen) – lädt nichts mehr
- KiCad 10, PrusaSlicer sind installiert; Java und Freerouting liegen weiter portabel in `~/tools` (alte Bridge)

## Dateien
| Datei | Inhalt |
|---|---|
| `mb2/befehle.py` | alle Befehle **einmal** (Name, Doku, Parameter) – CLI und MCP lesen dieselbe Tabelle |
| `mb2/__main__.py` | CLI: `python -m mb2 <befehl> key=wert …` oder JSON |
| `mb2/server.py` | MCP `mb2`, je Aufruf ein Unterprozess (eingetragen in `~/.claude.json`) |
| `mb2/cad.py`, `render.py`, `render_blender.py`, `blender_szene.py` | Teil-Skript ausführen, Prüfungen, STEP/3MF/PNG (Blender), Druckplatte (`cad_plate`, Abstand Standard 10 mm) |
| `mb2/fem.py`, `material.py` | Gmsh-Netz, CalculiX-.inp/.dat, Elmer-Netz/.sif/.vtu, Bewertung |
| `mb2/kicad.py`, `sexpr.py` | aus der alten Bridge, entschlackt |
| `mb2/slicer.py` | aus der alten Bridge, nur MK4 IS 0.4, ohne GUI/PrusaLink |
| `mb2/cache.py` | Ergebnis-Cache (Hash über Eingaben + mb2-Code) |
| `mb2/pruefungen/` | Katalog-Prüfungen je Fachgebiet (`fem_plausi`, `waerme`, `mechanik`, `dauer`, `toleranz`, `schwingung`, `elektronik`), Felder in `FELDER.md` |
| `mb2/kennwerte.py`, `mb2/bauteile.json` | Zusatz-Kennwerte Druckstoffe (mit Quelle, Lücken in `OFFEN`), Bauteil-Kennwerte Elektronik |
| `mb2/geometrie.py` | Geometrie-Merkmale aus STEP (Baurichtung, Innenkanten, Kehlen, Bohrungen, Rippen) |
| `mb2/werkzeuge.py` | Programme finden (Pfade, Versionen, Thread-Zahl für ccx) |
| `tests/` | Gegentests der Prüfungen, FEM-Vorbereitung |
| `.claude/agents/mb2-*.md` (Projekte-Ordner) | 5 Agenten · Skill `~/.claude/skills/idee-zu-druck-2/` |

## Status (05.11.2026)
- [x] Python-Umgebung (build123d 0.13, Gmsh 4.15, scikit-fem 12)
- [x] CAD + Prüfungen – 5 Gegentests grün (dünne Wand 1,2, Spalt 0,3, Kollision, Soll, runde Dome ohne Fehlalarm)
- [x] KiCad (neu, Katze, DRC, board.step, Render) und Slicer (MK4IS-Profile im G-Code bestätigt)
- [x] Agenten, Skill, MCP-Server (22 Werkzeuge, Aufruf getestet)
- [x] Abnahme Testgehäuse bis .bgcode: `projects/testdose` – Unterschale + Deckel ok, 40 min, 23 g PETG
- [x] CalculiX 2.23 (MSYS2/pacman) + Elmer 26.1 (Installer, MS-MPI) normal installiert (05.11.2026; vorher portabel in `~/tools`). Abnahmen damit wiederholt: Stifthalter bestanden (60 s statt hängend), Schnapphaken bestanden (Kontakt 855 s), Testdose 111,6 °C, Wärmecheck 27,55 °C
- [x] `~/tools/calculix` + `~/tools/elmer` gelöscht (05.11.2026, 633 MB)
- [x] **Abnahme FEM Stifthalter bestanden** (`tests/fem_abgleich.py`), gleiches Netz (57 235 Tet10):

  | Lastfall | Spitze u (Abw.) | σ an skfem-Punkten vs. Referenz | σ CalculiX-IP | σ Ecken (Bewertung) | Federrate |
  |---|---|---|---|---|---|
  | Andruck 0,25 N | 0,00005 mm | 3,171 = 3,171 | 2,814 | 3,567 | 0,6438 vs. 0,644 |
  | quer X 0,1 N | 0,00004 mm | 2,120 = 2,120 | 1,835 | 2,498 | – |
  | quer Y 0,1 N | 0,00004 mm | 0,470 = 0,470 | 0,406 | 0,552 | – |

  **Erkenntnis:** Die alte Rechnung und CalculiX haben dasselbe FE-Feld. Sie werten es nur an verschiedenen Punkten im Element aus (CalculiX an 4 Integrationspunkten, scikit-fem an 11 Quadraturpunkten).
  Bei Tet10 ist die Dehnung im Element linear, das Maximum liegt also an den Ecken. Deshalb rechnet `fem_mech` bei linearen Fällen σ aus den Verschiebungen an den Elementecken (`von_mises_feld`).
  Das ist bis +27 % höher als der alte Wert, also konservativ. Für NLGEOM gilt weiter der Wert an den CalculiX-Integrationspunkten.
- [x] Elmer: analytischer Check (Platte mit Quelle, qL²/2k) 27,55 vs. 27,5 °C; Testdose mit 0,5 W Lader → 111 °C, Energiebilanz 0,500 W geschlossen
- [x] **Abnahme Kontakt + NLGEOM bestanden**: Biegesteifigkeit Kontakt-Lauf vs. Kraft-Lauf −0,1 %, σ Balkenmitte vs. Gleichgewicht +0,7 %. Die Steifigkeit wird an der Zungenunterseite gemessen; am Gratscheitel steckt die örtliche Eindrückung des PETG mit drin (+6 % Weg).
  Die Balkentheorie mit starrer Einspannung ist 15 % steifer, weil der PETG-Sockel nachgibt. Das heißt für echte Haken: Die Rechnung mit Sockel liefert die realistischere, kleinere Montagekraft.
- Kontakt + NLGEOM am Schnapphaken (`projects/schnapphaken`, `tests/schnapphaken_abgleich.py`). Neu dazu: Lagerung mit `weg` (vorgegebene Verschiebung) und Reaktionskraft im Ergebnis.
  - **Lehre:** Beim Kontakt ist der Lastpunkt ein Ergebnis. Mit flacher Nase wanderte er durch das Kippen der Zunge auf x = 13,15, beim Zylinder-Drücker auf 13,62. Ein Vergleich gegen eine Theorie mit festem Lastpunkt misst also die Annahme, nicht die FEM.
  - Deshalb: schmaler Grat (r = 0,6) als Kontaktstelle. Geprüft wird Kontakt gegen den Kraft-Lauf ohne Kontakt (gleiche Steifigkeit) und Biegespannung gegen Gleichgewicht.
  - Die CAD-Prüfung hat dabei einen echten Mangel gefunden: Der Grat saß 0,4 mm vor dem Zungenende, dazwischen nur 1,68 mm Material. Die Zunge ist deshalb auf 15,6 mm verlängert.
  - Rechenzeit Kontakt mit feinem Netz am Grat: > 10 min. Deshalb laufen `fem`-Werkzeuge mit 2 h Zeitgrenze.
- [x] Strahlung (ε ≈ 0,9) und Innenluft im Wärmemodell (10.11.2026): optional per Lastfall `strahlung` / `innenluft` (dazu `konvektion.auto`, `sonne`). Gegentests Hand ↔ Elmer < 0,1 %. Testdose 0,5 W: nur Konvektion 111,6 °C (unverändert), + Strahlung 89,3 °C, + Innenluft 80,4 °C. Bestehende Lastfälle rechnen weiter nur mit Konvektion (konservativ), bis die Felder eingetragen sind; W2/W5 weisen darauf hin.
- [x] **Prüfkatalog aus MIT OpenCourseWare** (10.11.2026) – `OCW_PRUEFKATALOG.md`, 87 Katalog-IDs, je ID Spalte „Umsetzung“ (umgesetzt/teilweise/offen). Eingebaut in `mb2/pruefungen/` (Abschnitt 7b), Kennwerte `mb2/kennwerte.py`, Bauteil-DB `mb2/bauteile.json`, Kalibrierkörper `projects/kalibrierkoerper/` (gebaut, noch nicht gedruckt/gemessen).
- [ ] Offen: Kalibrierkörper drucken + `messung.json` füllen (T1/T4/D10 bis dahin vorläufig); Kriech-SLS/U für PLA/PETG/ASA; vorhandene `*.erg.json` neu rechnen (nächster `audit` tut das, Cache ist durch den Code ungültig; Schnapphaken-Montage ≈ 15 min); in den echten Projekten die neuen soll-Felder eintragen.

## Installation – Erfahrungen und Grenzen
- **Löser fest auf SPOOLES** (`*STATIC, SOLVER=SPOOLES`). Ohne Angabe nimmt der MSYS2-ccx PaStiX (mit StarPU). PaStiX hing am Stifthalter (295 k Unbekannte) über 85 min ohne Ergebnis. Bei 32 Threads kam außerdem „unable to get the core“, weil die CPU 24 physische Kerne bei 32 logischen hat. SPOOLES rechnet denselben Fall durch. Die portable Version hatte ebenfalls SPOOLES benutzt.
- Thread-Zahl = **physische** Kerne (`werkzeuge.physische_kerne()`), nicht `os.cpu_count()`.
- Kein Intel-Pardiso: Für große nichtlineare Modelle ist das langsamer als der ccx aus PrePoMax. Für Gehäusegrößen reicht es.
- Elmer hat MPI (MS-MPI). Die Bridge ruft trotzdem `ElmerSolver.exe` seriell auf, denn die Wärmefälle dauern nur Sekunden.
- Updates: MSYS2 `pacman -Syu`. Elmer: neuen Installer von funet holen; `werkzeuge.elmer_bin()` nimmt den neuesten `Program Files\Elmer*`-Ordner.