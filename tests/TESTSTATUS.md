# Teststatus (19.11.2026, Linux-Container, `uv run python tests/alle.py`)

Klassifiziert wird je Testfunktion. **Nicht ausgeführt heißt nicht bestanden.** `tests/alle.py` beendet sich nur dann mit 0, wenn alle Funktionen bestanden sind.

| Klasse | Funktionen | Bedeutung |
|---|---|---|
| bestanden | 226 | lief durch (mit CalculiX im PATH; ohne CalculiX 218) |
| beispielprojekt_fehlt | 16 | braucht `projects/<name>` (gitignored) oder `../maker-bridge/projects/` |
| werkzeug_fehlt | 6 | Elmer nicht installiert (unter Linux nicht im Standard-Paketbestand); ohne CalculiX zusätzlich 8 |
| lauf_nicht_angefordert | 1 | `test_taster_echt_lang` nur mit `MB2_LANG=1` |
| fehlgeschlagen | **0** | kein erkannter Softwarefehler |

## Die früher sieben roten Dateien

| Datei | Klasse(n) | Ursache |
|---|---|---|
| `test_fem_vorbereitung.py` | bestanden | Fall baut sich jetzt selbst (vorher: fehlendes Beispielprojekt + Importpfad) |
| `test_pruefung.py` | bestanden | Importpfad fehlte (Testaufruf-Fehler, kein Softwarefehler) |
| `test_pruef_dauer_toleranz.py` | 21 bestanden, 1 beispielprojekt_fehlt | `test_echte_projekte` |
| `test_pruef_mechanik.py` | 27 bestanden, 4 beispielprojekt_fehlt | `test_echt_*` |
| `test_pruef_schwingung.py` | 13 bestanden, 2 beispielprojekt_fehlt | `test_echte_projekte_laufen`, `test_frag_mich_alles` |
| `test_pruef_fem_plausi.py` | 9 bestanden, 7 werkzeug_fehlt, 1 beispielprojekt_fehlt, 1 lauf_nicht_angefordert | CalculiX |
| `test_pruef_katalog.py` | 4 bestanden, 1 werkzeug_fehlt, 1 beispielprojekt_fehlt | CalculiX |
| `test_pruef_waerme.py` | 17 bestanden, 6 werkzeug_fehlt, 2 beispielprojekt_fehlt | Elmer |

## Scheinsicherheit beseitigt

Acht Funktionen meldeten bisher „bestanden“, obwohl sie nichts prüften, weil das Projekt fehlte:
- `test_pruef_elektronik.py`: `test_echt_*`, 5 Funktionen (`return` bzw. `continue`)
- `test_pruef_fem_plausi.py`: `test_echte_projekte_kein_absturz` (Leerlauf über fehlende Projekte) und `test_taster_echt_lang` (`return` ohne MB2_LANG)
- `test_pruef_mechanik.py`: `test_echt_alle_projekte_laufen`
- `test_pruef_schwingung.py`: `test_echte_projekte_laufen`

Sie werfen jetzt `NichtAusgefuehrt` (`tests/_nachweis.py`). Folge: `test_pruef_elektronik.py` läuft direkt aufgerufen nicht mehr „31 bestanden“ durch, sondern bricht an der ersten fehlenden Platine ab.
Das ist gewollt. `tests/alle.py` zeigt je Funktion den richtigen Stand.

## Was fehlt, um alles auszuführen

1. Beispielprojekte `projects/{testdose, schnapphaken, stifthalter-fem, frag-mich-alles-gehaeuse, bodenklima-sondenkopf}` und `../maker-bridge/projects/{klimalogger, evolve-kiesel, rad-warnknopf, bodenklima}`. Sie sind nicht öffentlich.
2. CalculiX: unter Linux im PATH reicht (`apt install calculix-ccx`, 2.21 geprüft, alle 8 CalculiX-Tests bestanden). Elmer: unter Linux selbst installieren, `ElmerSolver` in den PATH.
