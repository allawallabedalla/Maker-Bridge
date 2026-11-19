# Wann ist der Prozess fertig? (Definition, 19.11.2026)

| # | Kriterium | Stand |
|---|---|---|
| 1 | **Keine Scheinsicherheit:** keine Prüfung meldet ohne Eingaben „ok“; das Entfernen einer Eingabe macht kein Ergebnis besser | **umgesetzt** (`tests/test_keine_scheinsicherheit.py`): leeres Projekt, Teil ohne Angaben, jede Nachweisart ohne Daten, Weglass-Probe für Mechanik (12 Prüf-IDs aktiv), Elektronik (5), Messkette/Ziele/Widerspruch, Dauer/Toleranz/Schwingung (4). Seit 19.11.2026 auch FEM-gestützt (`test_weglassprobe_fem`, öffentlicher Wandhaken mit CalculiX: M3, M7, M9, F23–F25, D*, T*, S*; je Angabe in soll.json und Lastfall). **Lücke:** W* (Wärme braucht Elmer, nur auf dem Nutzer-Rechner) |
| 2 | **Doku = Code:** jede Behauptung „✅ umgesetzt“ im Prüfkatalog wird automatisch gegen den Code geprüft | **umgesetzt** (`tests/test_doku_code.py`): ✅/◐ nur mit ID im Code; jede ausgegebene ID steht im Katalog; „offen“ wird nie ausgegeben; ✅ nur mit Test, der die ID nennt. Fehlerinjektion geprüft. **Grenze:** prüft, dass ein Test die ID nennt – nicht, dass er die Regel inhaltlich abdeckt (das ist Kriterium 3) |
| 3 | **Jede Regel getestet:** jede Regel aus `VMODELL.md` und dem Skill hat mindestens einen Test | **umgesetzt** (`tests/test_regeln.py`): 37 Regeln in VMODELL.md, 26 im Skill, je mit Marke `<!-- R:… -->`. 55 haben Tests, 8 sind Verhaltensregeln fürs Gespräch (Ton, Fragen, Kritik) und ausdrücklich als „nicht per Code prüfbar“ geführt. Der Test schlägt an, wenn eine Marke ohne Zuordnung oder eine Zuordnung ohne Testfunktion ist |
| 4 | **Nichts bleibt ungeprüft:** auf der Referenzplattform läuft jeder Test | **hier erledigt, Rest nur auf dem Nutzer-Rechner:** Referenzplattform ist der Rechner des Nutzers (KiCad, PrusaSlicer, Elmer, `projects/`) – im Container wird nichts installiert. `tests/test_zwillinge.py` erzwingt: jede Prüf-ID aus einem Test an privaten Projekten hat auch einen öffentlichen Test (E14, M3, W4 nachgezogen). Offen: einmal `MB2_LANG=1 uv run python tests/alle.py` auf dem Nutzer-Rechner |
| 5 | **Ein Durchlauf von vorn bis hinten:** ein Projekt läuft komplett von der Idee bis zur Freigabe, ohne Handeingriff außer den Nutzerantworten | **bis vor das Slicen belegt** (`tests/test_durchlauf.py`, Wandhaken): Idee → Ziele/Einsatz → Lastenheft (Wunsch → Zahl) → CAD v1 → FEM findet zu schwach → Karte an mb2-fem → v2 → FEM ok, M3-Gegenprobe. Slicen, druckfertig und Abnahme → fertig laufen nur mit PrusaSlicer (Nutzer-Rechner); ohne meldet der Test `werkzeug_fehlt`, nie bestanden |
| 6 | **Läuft weiter, bis fertig oder gestoppt:** Arbeit geht als Auftragskarte mit maschinenprüfbarer Abnahme an das kleinste passende Modell; Fehlversuch → eine Stufe höher, nie dreimal gleich; Übergabe über einen kurzen Stand (≤ 5 KB); Laufsperre und Budgetbremse; Kosten je Karte gemessen (Vorbild: grenzland-forschung, Dirigent + Karten) | **umgesetzt** (`mb2/karten.py`, Befehle `lauf_start`, `karte_naechste`, `karte_ergebnis`, `lauf_ende`, Tests `tests/test_karten.py`, Skill 5a). Abnahme durch das audit, nicht durch den Agenten. **Nicht belegt:** Ob es in mb2 Tokens spart, zeigt erst ein echter Lauf mit Token-Angaben (`lauf_ende` → Kosten je Agent/Stufe) |

Gefunden beim Bau von Kriterium 1: Ein fehlendes `messbereich.min` ließ die Messkette abstürzen. Behoben in `rtd.py`.

Gefunden beim Bau von Kriterium 2: 6 Prüfungen standen auf ✅ ohne Test (E3, E9, E17, E18, M22, W8) → auf „◐ ungetestet“ gesetzt. 20 ausgegebene IDs fehlten im Katalog (FW1, K1–K4, MK1–MK5, X1–X9) → Abschnitt 3.8 ergänzt.

Gefunden beim Bau von Kriterium 3:
- Der Cache-Schlüssel enthielt nur `mb2/*.py`, nicht `mb2/pruefungen/` – eine geänderte Prüfung hätte alte Ergebnisse gelten lassen. Behoben (`cache.quelldateien`).
- Die Regel „alle Fragen, aber nur eine je Nachricht“ hatte keinen Code. Neu: `mb2/fragen.py` und Befehl `fragen`.
- Skill und CLAUDE.md verlangten Minutenschätzungen. Ersetzt durch „Umfang statt geratener Zeit“.
- E3, E9, E17, E18, W8 haben jetzt Handrechen-Tests, M22 nennt seine ID im Test. Alle sechs wieder ✅.

Gefunden beim Bau von Kriterium 4–6:
- `A-MONTAGE` (Adern, Pin 1) wurde auch für Teile ohne Elektronik angelegt – jetzt nur mit Elektronik/Funk/Akku/Messung.
- PrusaSlicer wurde nur unter Windows gefunden – jetzt auch im PATH (Linux/macOS), Profil-Bundle über `werkzeuge.prusa_bundle`.
- M3 warnt bei gedrungenen Balken (Länge/Höhe ≈ 2) zu Recht: Euler-Bernoulli ohne Schub. Möglicher Ausbau: Schubanteil (Timoshenko) – nicht umgesetzt: es verschiebt Sollwerte privater Tests (Schnapphaken), die hier nicht laufen können.

Gefunden mit der FEM-Weglass-Probe:
- `anregung_Hz: 0` ließ das Modul `schwingung` abstürzen (Division durch null). Jetzt `uebersprungen` mit Hinweis.
- M3 ohne `a_mm`: Last an der Spitze angenommen, die Spannungs-Gegenprobe sprang von warnung auf ok. Jetzt höchstens warnung mit Hinweis.
- Druckplatte galt nach jedem cad_build als veraltet (Zeitstempel im STEP-Kopf), auch bei gleicher Geometrie. Jetzt Geometrie-Hash in `platte.json`: kein unnötiges cad_plate/Slicen in langen Läufen.
