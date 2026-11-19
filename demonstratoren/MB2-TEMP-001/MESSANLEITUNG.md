# Messanleitung MB2-TEMP-001: Sensor abgleichen und Genauigkeit nachweisen

**Ziel:** Der Temperatursensor soll von −20 bis +100 °C auf ±0,5 °C genau messen.
Dafür vergleichst du ihn im Temperaturbad mit einem geprüften Referenzthermometer, an **zwei verschiedenen Tagen**:

| Termin | Wozu | Dauer (geschätzt) |
|---|---|---|
| **1 – Abgleich** | Der Sensor lernt seine eigenen Fehler. Daraus entsteht eine Korrekturformel. | 4–6 h (9 Temperaturen, aufwärts) |
| **2 – Nachweis** | Mit eingespielter Korrektur wird geprüft, ob er wirklich ±0,5 °C schafft. | 6–9 h (9 Temperaturen aufwärts, 8 wieder abwärts) |

Warum zwei Termine? Würde man mit denselben Messwerten abgleichen und prüfen, bestätigt sich der Sensor nur selbst.

Die meiste Zeit wartest du, bis das Bad die Temperatur hält. Gemessen wird je Temperatur nur etwa 1 Minute.

---

## 1 Was du brauchst

- ☐ **Temperaturbad oder Blockkalibrator, der −20 bis +100 °C schafft.** Reines Wasser reicht nicht: Es friert unter 0 °C und kocht bei 100 °C. Geeignet sind ein Kältebad mit passender Badflüssigkeit oder ein Trockenblock-Kalibrator. Was das Gerät verträgt, steht in seiner Anleitung.
- ☐ **Referenzthermometer** mit **Kalibrierschein** (siehe Abschnitt 2)
- ☐ Sensor MB2-TEMP-001 mit aufgespielter Firmware, PT100-Fühler angeschlossen
- ☐ Laptop, USB-Kabel, Terminalprogramm, das mitschreiben kann (zum Beispiel Arduino IDE „Serieller Monitor“ oder PuTTY mit Log-Datei)
- ☐ Halter oder Klebeband, um beide Fühler nebeneinander zu fixieren, dazu ein Lineal
- ☐ Raumthermometer
- ☐ Diese Anleitung und das Protokollblatt (letzte Seite), ausgedruckt
- ☐ Tabellenvorlage `vorlage_messwerte.csv` (öffnet sich in Excel oder LibreOffice)

## 2 Kalibrierschein prüfen (5 min)

Diese Punkte musst du mit Ja beantworten können. Sonst zählt die Messung nicht als Nachweis.

- ☐ Die Seriennummer auf dem Schein ist die deines Referenzthermometers.
- ☐ Der Schein ist am Messtag noch gültig („gültig bis“ bzw. Rekalibrierdatum).
- ☐ Der kalibrierte Bereich deckt −20 bis +100 °C ab.
- ☐ Die Messunsicherheit U ist ≤ 0,1 °C (meist mit „k = 2“ angegeben).
- ☐ Der Schein stammt von einem akkreditierten Kalibrierlabor (in Deutschland mit DAkkS-Zeichen).

Notiere auf dem Protokollblatt: Gerät, Seriennummer, Schein-Nummer, Labor, U, k, gültig bis.

## 3 Aufbau (15 min)

1. **Beide Fühler nebeneinander** ins Bad: Spitzen auf gleicher Höhe, höchstens 10 mm Abstand. Gut fixieren, damit nichts rutscht.
2. **Tief genug eintauchen:** als Faustregel mindestens 15-mal so tief wie der Fühler dick ist. Ob es reicht, prüft Abschnitt 5.
3. **Elektronik außerhalb** bei Raumtemperatur. Sie darf nicht über dem Bad hängen (Wärme, Dampf).
4. **Raumtemperatur** notieren. Sie soll zwischen 18 und 28 °C liegen.

## 4 Gerät starten (35 min, davon 30 min warten)

1. Sensor per USB an den Laptop, Terminal mit **115200 Baud** öffnen, **Mitschreiben in eine Datei einschalten**.
2. Die erste Zeile prüfen:
   - Termin 1: `kal=0/0/0` (noch keine Korrektur) und `start_fehler=0`
   - Termin 2: `kal=` mit den neuen Zahlen und `start_fehler=0`
3. Jede Zeile danach ist ein Messwert: `zeit_ms;code_a;code_b;offset_code;fehlerbits;r_ohm;t_roh_c;t_c`
   - **Termin 1** liest die Spalte **`t_roh_c`** ab (ohne Korrektur).
   - **Termin 2** liest die Spalte **`t_c`** ab (mit Korrektur).
   - Steht bei `fehlerbits` etwas anderes als `0`: anhalten und Fühler und Kabel prüfen.
4. **30 Minuten warmlaufen** lassen.

## 5 Kopplungstest (einmal, an Termin 1, etwa 30 min)

So prüfst du, ob die Fühler tief genug stecken und die Wärme nicht über Schaft und Kabel abfließt.

1. Bad auf **100 °C** stellen und warten, bis es stabil ist (siehe Abschnitt 6, Schritt 2).
2. 10 Wertepaare aufschreiben (Referenz, Sensor), wie in Abschnitt 6.
3. Beide Fühler **20 mm herausziehen**, 5 Minuten warten, wieder 10 Wertepaare aufschreiben.
4. Auf dem Protokollblatt rechnen: Abweichung = Mittel(Sensor − Referenz). **Kopplung = halbe Differenz** der Abweichung zwischen „tief“ und „20 mm höher“.
5. Bei **−20 °C** wiederholen. Den **größeren** der beiden Werte notieren.
6. Ist die Kopplung über 0,05 °C: tiefer eintauchen und wiederholen.

## 6 Messen an einer Temperatur (immer gleich)

1. Bad auf den Sollpunkt stellen.
2. **Warten, bis es stabil ist:** mindestens **10 Minuten**, und die Referenz ändert sich über 1 Minute um weniger als 0,01 °C. Die Wartezeit aufschreiben.
3. **10 Wertepaare** aufschreiben, **etwa alle 6 Sekunden** eines. Referenz und Sensor jeweils möglichst gleichzeitig ablesen, Uhrzeit dazu.
4. Weiter zum nächsten Punkt.

## 7 Termin 1: Abgleich

1. Abschnitte 2 bis 5 erledigen.
2. Abschnitt 6 für diese Punkte, **aufsteigend**: **−20, 0, 10, 20, 30, 40, 50, 70, 100 °C**.
3. Werte in `vorlage_messwerte.csv` eintragen: nur die Zeilen mit `richtung = auf`, Spalte `sensor_C` = abgelesenes `t_roh_c`. Die „ab“-Zeilen bleiben leer.
4. Schick mir: die CSV-Datei, die Terminal-Log-Datei, die Angaben vom Kalibrierschein, Kopplung und Raumtemperatur.
5. Ich lese alles ein, berechne die Korrekturformel und trage sie in die Firmware ein. Dann spielst du die Firmware neu auf.

## 8 Termin 2: Nachweis (anderer Tag)

1. Abschnitte 2 bis 4 wiederholen. Die erste Zeile muss jetzt die neuen `kal=`-Zahlen zeigen.
2. Abschnitt 6 **aufsteigend**: −20, 0, 10, 20, 30, 40, 50, 70, 100 °C.
3. Danach **absteigend**: 70, 50, 40, 30, 20, 10, 0, −20 °C. Daraus ergibt sich die Hysterese, also wie stark der Sensor beim Abkühlen anders anzeigt als beim Aufheizen.
4. Neue, leere `vorlage_messwerte.csv`: alle Zeilen füllen, Spalte `sensor_C` = abgelesenes **`t_c`**.
5. Schick mir CSV, Log-Datei und Raumtemperatur. Die Maker-Bridge prüft daraus Genauigkeit, Linearität, Wiederholbarkeit, Messbereich und Hysterese und erstellt das Messprotokoll.

**Freigegeben** ist der Sensor erst, wenn alle Prüfungen bestanden sind **und** ein Mensch unterschreibt. Das bist du oder ein Prüfer deiner Wahl.

---

## Protokollblatt (je Termin ausdrucken)

**Termin:** ☐ 1 Abgleich ☐ 2 Nachweis  **Datum:** ________  **Prüfer:** ________________

**Sensor:** Seriennummer ________  **Raumtemperatur:** Beginn ____ °C, Ende ____ °C  **Versorgung:** USB ____ V

**Referenzthermometer:** Gerät ____________ SN ________ Schein-Nr. ____________ Labor ____________
U = ______ °C, k = ___, gültig bis ________

**Kopplungstest (nur Termin 1):** bei 100 °C: ____ °C  bei −20 °C: ____ °C  → Kopplung (größerer Wert): ____ °C

| Soll °C | Richtung | Wartezeit min | Nr. | Uhrzeit | Referenz °C | Sensor °C |
|---|---|---|---|---|---|---|
| ____ | auf / ab | ____ | 1 | | | |
| | | | 2 | | | |
| | | | 3 | | | |
| | | | 4 | | | |
| | | | 5 | | | |
| | | | 6 | | | |
| | | | 7 | | | |
| | | | 8 | | | |
| | | | 9 | | | |
| | | | 10 | | | |

(Ein Block je Temperatur. Für Termin 1 sind es 9 Blöcke, für Termin 2 sind es 17.)
