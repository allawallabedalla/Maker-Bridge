# Wann ist der Prozess fertig? (Definition, 19.11.2026)

| # | Kriterium | Stand |
|---|---|---|
| 1 | **Keine Scheinsicherheit:** keine Prüfung meldet ohne Eingaben „ok“; das Entfernen einer Eingabe macht kein Ergebnis besser | **umgesetzt** (`tests/test_keine_scheinsicherheit.py`): leeres Projekt, Teil ohne Angaben, jede Nachweisart ohne Daten, Weglass-Probe für Mechanik (12 Prüf-IDs aktiv), Elektronik (5), Messkette/Ziele/Widerspruch, Dauer/Toleranz/Schwingung (4). **Lücke:** D5–D12, T*, S*, W*, F*, M7–M9 brauchen FEM- bzw. Geometriedaten und sind in der Weglass-Probe noch nicht aktiv |
| 2 | **Doku = Code:** jede Behauptung „✅ umgesetzt“ im Prüfkatalog wird automatisch gegen den Code geprüft | offen |
| 3 | **Jede Regel getestet:** jede Regel aus `VMODELL.md` und dem Skill hat mindestens einen Test | offen |
| 4 | **Nichts bleibt ungeprüft:** auf der Referenzplattform läuft jeder Test | offen (16 Beispielprojekt fehlt, 6 Elmer fehlt, 1 langer Lauf) |
| 5 | **Ein Durchlauf von vorn bis hinten:** ein Projekt läuft komplett von der Idee bis zur Freigabe, ohne Handeingriff außer den Nutzerantworten | offen |

Gefunden beim Bau von Kriterium 1: Ein fehlendes `messbereich.min` ließ die Messkette abstürzen. Behoben in `rtd.py`.
