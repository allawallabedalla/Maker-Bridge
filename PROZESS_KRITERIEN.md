# Wann ist der Prozess fertig? (Definition, 19.11.2026)

| # | Kriterium | Stand |
|---|---|---|
| 1 | **Keine Scheinsicherheit:** keine Prüfung meldet ohne Eingaben „ok“; das Entfernen einer Eingabe macht kein Ergebnis besser | **umgesetzt** (`tests/test_keine_scheinsicherheit.py`): leeres Projekt, Teil ohne Angaben, jede Nachweisart ohne Daten, Weglass-Probe für Mechanik (12 Prüf-IDs aktiv), Elektronik (5), Messkette/Ziele/Widerspruch, Dauer/Toleranz/Schwingung (4). **Lücke:** D5–D12, T*, S*, W*, F*, M7–M9 brauchen FEM- bzw. Geometriedaten und sind in der Weglass-Probe noch nicht aktiv |
| 2 | **Doku = Code:** jede Behauptung „✅ umgesetzt“ im Prüfkatalog wird automatisch gegen den Code geprüft | **umgesetzt** (`tests/test_doku_code.py`): ✅/◐ nur mit ID im Code; jede ausgegebene ID steht im Katalog; „offen“ wird nie ausgegeben; ✅ nur mit Test, der die ID nennt. Fehlerinjektion geprüft. **Grenze:** prüft, dass ein Test die ID nennt – nicht, dass er die Regel inhaltlich abdeckt (das ist Kriterium 3) |
| 3 | **Jede Regel getestet:** jede Regel aus `VMODELL.md` und dem Skill hat mindestens einen Test | offen |
| 4 | **Nichts bleibt ungeprüft:** auf der Referenzplattform läuft jeder Test | offen (16 Beispielprojekt fehlt, 6 Elmer fehlt, 1 langer Lauf) |
| 5 | **Ein Durchlauf von vorn bis hinten:** ein Projekt läuft komplett von der Idee bis zur Freigabe, ohne Handeingriff außer den Nutzerantworten | offen |

Gefunden beim Bau von Kriterium 1: Ein fehlendes `messbereich.min` ließ die Messkette abstürzen. Behoben in `rtd.py`.

Gefunden beim Bau von Kriterium 2: 6 Prüfungen standen auf ✅ ohne Test (E3, E9, E17, E18, M22, W8) → auf „◐ ungetestet“ gesetzt. 20 ausgegebene IDs fehlten im Katalog (FW1, K1–K4, MK1–MK5, X1–X9) → Abschnitt 3.8 ergänzt.
