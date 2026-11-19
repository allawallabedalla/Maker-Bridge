# maker-bridge 2 (mb2)

Von der Idee zum druckfertigen Gerät, ohne Oberfläche: **KiCad 10 → build123d → FEM (Gmsh/CalculiX/Elmer) → PrusaSlicer**.
Claude Code steuert alles über einen MCP-Server (`mb2`), fünf spezialisierte Agenten (`mb2-*`) und einen Skill (`idee-zu-druck-2`).
Jede Aussage über das Gerät ist entweder **bewiesen** (Rechnung, Messung, Datenblatt mit Beleg) oder ausdrücklich nur
**vorbehalt / unbewiesen**. Grün heißt bewiesen.

Weiterführend: [ARCHITEKTUR.md](ARCHITEKTUR.md) (Aufbau, Datenfluss, Dateien), [VMODELL.md](VMODELL.md) (Anforderungen,
Freigabe, Glaubwürdigkeit nach ASME V&V 40), [OCW_PRUEFKATALOG.md](OCW_PRUEFKATALOG.md) (analytische Prüfungen),
[mb2/pruefungen/FELDER.md](mb2/pruefungen/FELDER.md) (Eingabefelder), [IN_SILICO.md](IN_SILICO.md) (Einordnung In-silico/V&V 40).

---

## 1. Voraussetzungen (Windows 11)

| Programm | Version (getestet) | Installation | wofür |
|---|---|---|---|
| Claude Code | aktuell | Desktop-App oder `npm i -g @anthropic-ai/claude-code` | Steuerung |
| uv | 0.12 | `powershell -c "irm https://astral.sh/uv/install.ps1 \| iex"` | Python 3.12 + Pakete |
| KiCad | 10.0 | kicad.org, Standardinstallation (Benutzer oder Program Files) | Schaltplan, Platine, `kicad-cli`, `pcbnew` |
| PrusaSlicer | 2.9.6 | prusa3d.com, nach `C:\Program Files\Prusa3D\PrusaSlicer` | Slicen (CLI) |
| CalculiX | 2.23 | `winget install MSYS2.MSYS2`, dann in „MSYS2 UCRT64“: `pacman -S mingw-w64-ucrt-x86_64-calculix-ccx` | Mechanik-FEM |
| Elmer | 26.1 (meldet sich als 9.0) | `ElmerFEM-nogui-mpi-Windows-AMD64-rel26.1.exe` von nic.funet.fi/pub/sci/physics/elmer/bin/windows/rel26.1/ | Wärme-FEM |
| Microsoft MPI | 10 | `winget install Microsoft.msmpi` | für Elmer |
| Java (JRE) | 25 | portabel nach `%USERPROFILE%\tools\jdk-*` (z. B. Adoptium-ZIP entpacken) | Freerouting |
| Freerouting | 2.5.0 | `freerouting-2.5.0.jar` nach `%USERPROFILE%\tools\freerouting\` (github.com/freerouting/freerouting/releases) | Autorouter |
| Blender | 5.2, optional | blender.org | schönere Renderbilder (sonst matplotlib) |

Python-Pakete (build123d 0.13, gmsh 4.15, mcp, numpy, matplotlib) installiert `uv` automatisch aus `pyproject.toml`/`uv.lock`.
Die Programme werden über feste Orte gefunden (`mb2/werkzeuge.py`); andere Orte dort eintragen.

## 2. Einrichten in einem neuen Konto

```powershell
git clone https://github.com/allawallabedalla/Maker-Bridge.git maker-bridge-2
cd maker-bridge-2
powershell -ExecutionPolicy Bypass -File claude\install.ps1
```

Das Skript
1. legt mit `uv sync --all-groups` die Python-Umgebung `.venv` an,
2. zeigt, welche externen Programme gefunden wurden (`FEHLT: …` nennt den Installationsweg),
3. kopiert die Agenten nach `%USERPROFILE%\.claude\agents\` und den Skill nach `%USERPROFILE%\.claude\skills\idee-zu-druck-2\`
   und setzt dabei den tatsächlichen Ordner für `{MB2}` ein,
4. trägt den MCP-Server `mb2` für alle Projekte ein (`claude mcp add mb2 --scope user …`).

Optionen: `-Bestellliste "C:\…\Bestellliste.html"` (eigene Einkaufsliste, siehe 6.), `-NurPruefen` (nur Schritt 1–2).
Danach Claude Code neu starten und prüfen: „ruf `mcp__mb2__tools_status` auf“. Nach Code-Änderungen an `mb2/` den MCP-Server
neu starten, sonst fehlen neue Werkzeuge.

Ohne `claude`-CLI im PATH gibt das Skript den JSON-Block für `%USERPROFILE%\.claude.json` aus:
```json
"mcpServers": { "mb2": { "type": "stdio", "command": "C:\\Users\\<du>\\.local\\bin\\uv.exe",
  "args": ["run", "--directory", "C:\\…\\maker-bridge-2", "python", "-m", "mb2.server"] } }
```

## 3. Benutzung

Im Chat eine Geräteidee beschreiben („Ich brauche ein Gehäuse für …“). Der Skill **idee-zu-druck-2** übernimmt:

0. **Idee schärfen**: nur echte Lücken erfragen (Strom, Bedienung, Anschlüsse, Größe, Einsatzort, Lasten, Funkstrecke).
   `project_new` mit `einsatz` (innen/außen, T_min/T_max, Akku, Fallhöhe, Funk …), dann `eingaben_offen`.
0b. **Lastenheft (V-Modell)**: Systemanforderungen mit messbarem Kriterium in `anforderungen.json`, Herkunft jeder Eingabe
   in `_projekt._herkunft` (gemessen | datenblatt | norm | berechnet | geschaetzt | angenommen).
1. **Elektronik** → Agent `mb2-elektronik`: Schaltplan als S-Expression, ERC, `kicad_sync` (= F8 ohne Oberfläche),
   Platzieren per `layout.py`, Freerouting, **Katze im Bestückungsdruck**, DRC, `board.step` + `board_info.json`.
2. **Gehäuse** → Agent `mb2-cad`: ein build123d-Skript je Teil unter `cad/`, jeder Bau geprüft
   (gültig, Soll-Maße, Kollision, Wand ≥ 1,8 mm, Spalt ≥ 0,4 mm, Renderbild).
3. **FEM** → Agent `mb2-fem`: Lastfälle (Schraubdom, Schnapphaken, Klemmung, Fall) mit CalculiX, Wärme mit Elmer;
   Modell nach V&V 40 einstufen, ab Risiko 3 Konvergenz + `fem_sensitivitaet`.
4. **Druckplatte + Slicen**: `cad_plate`, dann `slice_plate` (Prusa MK4 IS 0.4, PETG `@PGIS`). **mb2 druckt nie.**
5. **Audit-Kreis** nach jeder Änderung: `audit` (deterministisch, gecacht), Mängel zurück an den zuständigen Agenten;
   bei `freigabe: druckfertig` prüft `mb2-pruefer` (Druckbarkeit → Funktion → FEM → Schonung des Druckers → V-Matrix).
6. **Abnahme am Gerät und im Feld**: `abnahme_eintragen`, `feld_eintragen`, `feld_abgleich`. Erst dann `freigabe: fertig`.

Projekte liegen in `projects/<name>/` mit `projekt.md`, `anforderungen.json`, `abnahme.json`, `cad/`, `electronics/`,
`fem/`, `out/` (Prüfberichte), `print/` (.3mf, .bgcode), `pruef/` (Katalog, V-Matrix, Glaubwürdigkeit).

## 4. Werkzeuge des MCP-Servers `mb2`

Jeder Aufruf läuft als eigener Prozess (`python -m mb2 <befehl> <json>`); ein Absturz von OCCT, Gmsh oder einem Löser trifft
nur diesen Aufruf. `cad_build` und `fem_*` sind gecacht (SHA-256 über Eingaben, Code und Löserversion); `neu=true` erzwingt
eine neue Rechnung.

| Gruppe | Werkzeuge |
|---|---|
| Projekt | `project_new`, `project_status`, `eingaben_offen` |
| Anforderungen | `anforderungen_erzeugen`, `anforderungen_pruefen`, `abnahme_eintragen`, `feld_eintragen`, `feld_abgleich`, `messreihe_eintragen`, `messreihen_aus_csv` |
| Messtechnik | `messkette_rechnen`, `kalibrierung_auswerten` |
| CAD | `cad_build`, `cad_plate`, `cad_check_step`, `cad_check_3mf` |
| FEM | `fem_mech`, `fem_waerme`, `fem_sensitivitaet`, `fem_materialien` |
| KiCad | `kicad_new`, `kicad_find`, `kicad_symbol`, `kicad_erc`, `kicad_schematic_pdf`, `kicad_sync`, `kicad_layout`, `kicad_route`, `kicad_cat`, `kicad_drc`, `kicad_render`, `kicad_board`, `kicad_fab` |
| Slicen | `slice_plate`, `slice_profiles` |
| Prüfen | `audit`, `pruefkatalog` |
| System | `tools_status` |

Zeitgrenzen: FEM und Audit 2 h, KiCad 1 h, Slicen 30 min, sonst 15 min (`mb2/server.py`).

## 5. Agenten (`claude/agents/`)

| Agent | Modell | Aufgabe |
|---|---|---|
| `mb2-elektronik` | Standard | Schaltplan, Layout, Routing, Katze, DRC, Fertigungsdaten (JLCPCB: alles Bestückbare mitbestücken) |
| `mb2-cad` | Standard | build123d-Teile, Druckplatte |
| `mb2-fem` | Standard | Lastfälle, Wärmefälle, Konvergenz, Sensitivität, V&V-40-Einstufung |
| `mb2-pruefer` | Standard | unabhängige Prüfung, ändert nichts |
| `mb2-slicer` | Haiku | Profilsuche über mehrere Schritte |

Jeder Agent hat nur die Werkzeuge, die er braucht (Kopfzeile `tools:`).

## 6. Eigene Angaben

- **`VORRAT.md`**: Filament und Kleinteile, die vorrätig sind. Agenten legen Maße darauf aus (z. B. Einschmelzmuttern).
- **Bestellliste** (optional): HTML-Datei mit JSON-Block `<script id="daten">` (`shops[].posten` = offen, `erledigt` = gekauft).
  Ohne sie sammeln die Agenten neue Kaufteile in `projekt.md`.
- **Drucker**: fest auf Prusa MK4 mit Input Shaper, Düse 0,4 (`Original Prusa MK4 Input Shaper 0.4 nozzle`,
  `… @MK4IS 0.4`, Filamente `… @PGIS`). Bett 250 × 210 mm. Anderer Drucker: `mb2/slicer.py` anpassen.

Empfohlene Regeln für die `CLAUDE.md` des neuen Kontos:
```markdown
- Nie drucken, nur slicen; die .bgcode überträgt der Nutzer selbst.
- Wände ≥ 1,8 mm, keine Spalte unter Düsenbreite (0,4 mm).
- Jede Platine bekommt eine Katze im Bestückungsdruck (kicad_cat).
- Kaufteile: drucken erst mit Hersteller-STEP, Maßzeichnung oder Messung (sonst "geschätzt" → slice_plate ok=false).
- Vor dem Anschließen eines Moduls die Chip-Aufschrift am echten Bauteil prüfen und mit dem Datenblatt belegen.
- Funkstrecken mit ≥ 10 dB Reserve auslegen.
- Nach zwei gescheiterten Varianten mit gleichem Fehlerbild die Grundannahme prüfen, keine dritte Variante.
```

## 7. Tests

```powershell
.venv\Scripts\python.exe tests\test_glaubwuerdigkeit.py
```
Jede Datei unter `tests/` läuft für sich. `fem_abgleich.py`, `schnapphaken_abgleich.py` und `test_pruef_waerme.py` sind die
Code-Verifikation der Löser (V&V 40). Einige Tests (`test_pruef_katalog`, `_mechanik`, `_schwingung`, `_fem_plausi`,
`_elektronik`, `_dauer_toleranz`) lesen Beispielprojekte unter `projects/`; die sind nicht im Repository – diese Funktionen
melden dann `NichtAusgefuehrt` (nie „bestanden“). `test_fem_vorbereitung.py` baut seinen Fall seit 19.11.2026 selbst (nur Gmsh nötig). `test_messkette.py` prüft
Messkette, Unsicherheitsbudget und Messnachweise (ohne Löser). `test_temp_demonstrator.py` prüft den PT100-Demonstrator
(braucht g++ für die Firmware-Rechnung). **`tests/alle.py`** führt alle Dateien aus und ordnet jede einer Klasse zu:
bestanden, werkzeug_fehlt, beispielprojekt_fehlt oder fehlgeschlagen. Ein nicht ausgeführter Test zählt nie als bestanden.
Stand der roten Dateien: `tests/TESTSTATUS.md`.

## 8. Grenzen

- Werkzeugpfade: CalculiX und Elmer werden unter Windows an festen Orten, sonst im PATH gesucht (`ccx`, `ElmerSolver`). KiCad, PrusaSlicer und Blender sind weiter nur für Windows hinterlegt (`mb2/werkzeuge.py`). Die Python-Teile und Tests ohne diese Werkzeuge laufen auch unter Linux (Stand 19.11.2026, `tests/TESTSTATUS.md`).
- Kein Druckerupload, keine Fusion-Anbindung (das war maker-bridge 1).
- KiCad nur Standardbibliothek.
