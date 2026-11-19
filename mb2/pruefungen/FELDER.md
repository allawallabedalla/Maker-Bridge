# Eingabefelder der Katalog-Prüfungen (Stand 19.11.2026)

Fehlt ein Feld, meldet die betroffene Prüfung `uebersprungen` mit Grund – nie ein stilles `ok`. **Seit 15.11.2026
ist das nur noch erlaubt, wenn der Entwurf das Merkmal nicht enthält:** erkennt `merkmale.py` z. B. Funk, Akku,
Außeneinsatz, Schrauben oder Schnapper (aus soll.json, KiCad, projekt.md-Stichworten, Dateinamen unter electronics/),
stuft `alle()` das Überspringen der zugehörigen Prüfungen zu `fehler` hoch (Tabelle `AUSLOESER` in `__init__.py`).
Verzicht nur ausdrücklich: `_projekt.nicht_relevant: {"S4": "fest an die Wand geschraubt"}` → `info` mit Begründung.
Wo ein konservativer Standard sinnvoll ist, rechnet die Prüfung damit (Abschläge aus `mb2/realterme.py`) und meldet
höchstens `warnung`. Die ausführliche Form jedes Felds steht im Kopf des zuständigen Moduls (`mb2/pruefungen/<modul>.py`);
hier ist die Übersicht mit Katalog-ID. Aufruf: `pruefkatalog(projekt)` bzw. automatisch in `audit` → `pruef/katalog.json`.

## 1 cad/soll.json – projektweit unter `_projekt`

| Feld | Bedeutung | Prüfungen |
|---|---|---|
| `material` | Standardmaterial aller Teile (PLA/PETG/ASA) | alle |
| `sicherheit` | Ziel-Sicherheit für **alle** Festigkeitsprüfungen (`mb2/sicherheit.py`): max(Minimum der Prüfung, Teil-/Projektziel, M26). Minima: FEM/M7/M9/D9/D11 2,0, M1 1,5, M4 3,0 | FEM, M*, D* |
| `zuverlaessigkeit`, `lastfaktor`, `streuung_xy`, `streuung_z` | Sicherheitsziel aus Streuung (Std. 0,99 / 1,0 / kennwerte) | M26, D11 |
| `T_max_C`, `T_min_C`, `T_mittel_C`, `T_tagesgang_K` (Spitze–Spitze) | Einsatztemperatur | D1, D5–D9, W6, S (Luftdaten) |
| `T_bauraum_C` | Druckraum (Standard 25) | D10, W10 |
| `lebensdauer_h`, `lastdauer_h` | Lebensdauer / Dauer der Wärmelast | D3, D12, W7 |
| `aussen`, `farbe` \| `absorption` | Sonne (Farbe → α_s; unbekannte Farbe → 0,95 + Warnung) | W6 |
| `h_luefter_W_m2K` | h des Bauteillüfters am MK4 (ohne: W10 übersprungen) | W10 |
| `platine_spalt_mm`, `platine_schraube_d_mm` | Spalt Platine↔Wand je Seite bei 23 °C, Schraube der Platine | D8 |
| `kennwerte` | Projekt-Überschreibung `{"PETG": {"kriech_tau_h": [1000, "Quelle"]}}` – geht vor `mb2/kennwerte.py` | D*, M* |
| `kriechbruch` | `{"PETG": {"eps0_1_h", "s_MPa", "n", "Q_kJ_mol", "C_MG"}}` (Norton/Monkman-Grant) | D12 |
| `anregung_Hz` | Zahl oder `[f_min, f_max]` | S2 |
| `fallhoehe_m`, `masse_g` | Fallstoß, Gerätemasse gesamt | S4 |
| `akku_mAh`, `laufzeit_ziel_h`, `akku_chemie` (lipo, li_fes2, alkali, lifepo4, nimh) | Akku; Chemie für Kälte/Selbstentladung (realterme) | E6, E8, E21 |
| `nicht_relevant` | `{"<Prüf-ID>": "Begründung"}` – ausdrücklicher Verzicht auf eine vom Merkmal ausgelöste Prüfung | alle |
| `elektronik.module` | Kaufmodule ohne KiCad (z. B. LILYGO T3): `[{name, funk, f_MHz, akku, akku_mAh, chemie, R_int_Ohm, V_abschalt_V, I_ruhe_uA, wandler, eta, V_out_V, dropout_V, I_peak_mA, VDD_min_V, V_in_min_V, I_chg_mA, ntc}]` | E6, E8, E15, E16, E21 |
| `elektronik.funk` | `{r_m, umgebung (frei/sicht/land/dorf/stadt/innen), hindernisse [ziegel_dach, holz, mauer, … oder dB], kabel [{typ, m}], magnetfuss_ohne_blech, polarisation_gekreuzt, G_t_dBi, G_r_dBi, P_t_dBm, P_rx_min_dBm}` | E16 |
| `elektronik.Rth_gehaeuse_K_W`, `elektronik.kuehlflaeche` | Eigenerwärmung im Gehäuse (Std. 15 K/W), Kühlfläche (sonst RthJA ×1,5) | E4 |
| `elektronik` | `netze`, `i2c_kHz`, `modi`, `V_abschalt_V`, `R_int_Ohm`, `qi_spule_uH`, `lautsprecher_Ohm`, `funk`, `frequenzen`, `abtastrate_Hz`, `T_a_C`, `lagenaufbau` (Form: Kopf von `elektronik.py`) | E1–E25 |
| `toleranzketten` | wie unten je Teil | T2 |

## 2 cad/soll.json – je Teil (Schlüssel = Teilname)

| Feld | Form (Kurz) | Prüfungen |
|---|---|---|
| `material`, `sicherheit` | wie `_projekt`, überschreibt | alle |
| `bricklayers` | `true` = versetzte Innenwände beim Slicen (mehr Z-Haftung, dichter); kein Festigkeitsbonus im Katalog | BL, slice_plate |
| `druckrichtung` | `"z"`, `"-y"` oder `[x, y, z]` (Schichtnormale im Teil-KS); sonst aus `druck_drehung` (cad_build) | M1, M4, M7, M14–M16, M23, D11 |
| `schnapper` | `[{name, L_mm, b_mm, t_mm, hinterschnitt_mm, winkel_grad, rueck_winkel_grad, a_mm, achse, eps_zul, mu, anzahl, handkraft_N, zyklen}]` | M1, M2, S3 |
| `balken` | `[{fall, last, art: kragarm\|gelenkig\|eingespannt, L_mm, b_mm, h_mm, a_mm, kraft_N}]` – Gegenprobe zu fem/<fall> | M3 |
| `knicken` | `[{L_mm, lagerung \| K, b_mm+h_mm \| d_mm(+d_innen_mm) \| I_mm4+A_mm2, kraft_N, achse}]` | M4 |
| `rippen` | `[{h_mm, t_mm, a_mm, rand: frei\|gelenkig, druck_MPa, schub_MPa}]` (M5 von Hand); W9: `[{name, L_mm, t_mm, b_mm}]` | M5, W9 |
| `rippen_drucklast` | `false` = erkannte Rippen tragen keine Drucklast (M5 → info, ausgewiesen) | M5 |
| `schrauben` | `[{d_mm, anzahl, vorspannung_N, rest_vorspannung (Anteil nach Kriechen, sonst 0,5 bzw. kennwerte), klemmkraft_min_N, einschraub_mm, kopf_d_mm, loch_d_mm, last_N, klemmlaenge_mm, art: direkt\|insert\|mutter}]` | M12, M13, D4 |
| `inserts` | `[{d_aussen_mm, laenge_mm, kraft_N}]` (ohne kraft_N: Schraubenkraft aus M12) | M13 |
| `pressitze` | `[{d_mm, D_aussen_mm, uebermass_mm, laenge_mm, welle: starr\|gleich, achse, mu}]` | M14 |
| `scharniere` | `[{L_mm, t_mm, b_mm, winkel_grad, achse, eps_zul}]` | M15 |
| `torsion` | `[{art: offen\|rund\|rohr\|bredt, T_Nmm, b_mm, t_mm, d_mm, d_innen_mm, A_m_mm2}]` | M16 |
| `deckelbiegung` | `[{a_mm, b_mm, t_mm, druck_MPa \| last_N, last_art: flaeche\|punkt, rand, abstand_mm}]` | M19 |
| `zahnraeder` | `[{m_mm, z, b_mm, F_t_N \| M_Nmm, achse}]` | M23 |
| `constraints`, `fg_soll` | `[{name, sperrt: ["x","rz",..]} \| {name, anzahl}]`, Soll-Freiheitsgrade | M24 |
| `dauerlast` | `{dauer_h, durchbiegung_mm \| fem: "fall[/lastfall]", sigma_MPa, dehnung, durchbiegung_zul_mm, richtung: xy\|z, geschichte: [{t_h, sigma_MPa}]}` | D2, D3, D6, D7 |
| `zwang` | `{partner: FR4\|ALU\|STARR, alpha_partner_1_K, dT_K, art: voll\|bimetall, t_mm, t_partner_mm, L_mm, E_partner_MPa, durchbiegung_zul_mm, richtung}` | D9 |
| `zyklen`, `wechsellast` | `{sigma_max_MPa \| fem, sigma_min_MPa \| R (fehlt beides: R = -1), k_faktor, zuverlaessigkeit, richtung}` | D11 |
| `kriechbruch` | wie `_projekt`, je Teil | D12 |
| `toleranzen` | `[{name, nenn_mm, tol_mm \| plus_mm/minus_mm, art: aussen\|bohrung\|bohrung_liegend\|z\|fremd, cad_mm}]` | T1, T4 |
| `toleranzketten` | `[{name, glieder: [{name, nenn_mm (mit Vorzeichen), tol_mm, art, cad_mm}], spalt_min_mm, spalt_max_mm}]` | T2 |
| `steckungen` | `[{name, D_mm, d_mm, fase_mm, tiefe_mm, mu, versatz_mm}]` | T3 |
| `wand_gleichmaessig` | `true \| {raster_mm}` (Strahltest, kostet Sekunden) | T5 |
| `fehlerbudget` | `{ziel_mm, posten: [{name, fehler_mm} \| {winkel_mrad, abstand_mm} \| {L_mm, dT_K, material} \| {druck: <art>, nenn_mm, kompensiert}]}` | T6 |
| `kragarm` | `[{name, L_mm, b_mm, t_mm} \| {L_mm, I_mm4, A_mm2}, masse_spitze_g]` | S1b, S3 |
| `zusatzmasse_g`, `masse_g` | Zusatzmasse am Teil / Gerätemasse | S1, S4 |
| `lautsprecher` | `{vorkammer_mm3 \| vorkammer: {d_mm, h_mm}, loecher: {anzahl, d_mm} \| {anzahl, breite_mm, laenge_mm} \| {liste} \| "auto", mitte_mm, r_mm, achse, teil, wand_mm, f_s_Hz, V_as_l, geschlossen, innenvolumen_mm3, einbauten_mm3, innen_mm, gehaeuse_teile, band_Hz, f_H_min_Hz}` | S5–S8 |

## 3 fem/<fall>.json – Mechanik (neu, optional; ohne sie rechnet fem_mech wie vorher)

| Feld | Bedeutung | Ausgabe in `<fall>.erg.json` | Prüfungen |
|---|---|---|---|
| `"schwerkraft": true \| {g, richtung, in_allen_lastfaellen}` | Eigengewicht; Standard eigener Lastfall `eigengewicht` (Wegvorgaben dort 0) | `masse_kg`, `schwerpunkt_mm`, je Lastfall `durchbiegung_g_richtung_max_mm`, `durchbiegung_mittel_mm`, `rayleigh_f1_Hz` | S1, S2 |
| `"konvergenz": {"faktoren": [1.0, 0.7, 0.5]}` | Netzstudie, Hauptergebnis bleibt Faktor 1 | `konvergenz` (Energie, σ_max, u, Reaktion, Ort je Faktor) | F20–F22 |
| `"druckrichtung"` (Lastfall oder je Körper) | Aufbaurichtung → Tsai-Hill in der Bewertung (kann nur verschärfen) | `min_sicherheit_tsai_hill`, je Lastfall `tsai_hill` | M7 |
| `"orthotrop": true \| {E_z_MPa, G_MPa, nu_z}` | transversal-isotrope Steifigkeit (braucht druckrichtung) | `hinweise` | M8 |
| (immer) | – | je Lastfall `gleichgewicht`, `energie_Nmm`, `spannung_max`, bei NLGEOM `newton`, `kontakt`; Feld `fem/<fall>/<lastfall>.spannung.npz` | F23, F24, M7, M9, M22 |

Ältere `*.erg.json` ohne diese Felder: F23/F24/M7/M9 melden `uebersprungen` („fem_mech neu=true“).

## 4 fem/<fall>.json – Wärme (neu, optional; ohne sie rechnet fem_waerme bit-gleich wie vorher)

| Feld | Bedeutung | Prüfungen |
|---|---|---|
| `"strahlung": {"emission": 0.9}` | Strahlung gegen Umgebung, je Fläche mit Himmelsanteil | W2 |
| `"konvektion": {"auto": true, "L_mm": Höhe}` | h aus freier Konvektion (Fixpunkt) statt Festwert | W1 |
| `"innenluft": true \| {box, spalt_mm, emission, strahlung}` | Hohlraum als Ersatzleiter | W5 |
| `"sonne": {G_W_m2, absorption, richtung}` | Sonnenlast mit Abschattung | W6 |
| `lastdauer_h`, `rippen`, `wand_mm` | Zeitkonstante, Rippen, Wanddicke für das Widerstandsnetz | W7, W9, W4 |

Ausgabe zusätzlich: `randbedingungen`, `energiebilanz`, `koerper_info`, `flaechen_mm2`, `geometrie`, `hinweise` (W3 läuft immer).

## 5 Weitere Eingaben

- `mb2/kennwerte.py`: Zusatz-Kennwerte PLA/PETG/ASA (+ FR4/ALU), Zugriff `wert(material, feld)`, `None` = unbekannt, Grund in `OFFEN`.
- `mb2/bauteile.json` (zentral) + `<projekt>/electronics/bauteile.json` (Ergänzung je Projekt): Kennwerte je Teilenummer mit Quelle.
- Strom je Netz: Netzklassenname mit Strom (`Leistung_2A`) oder Symbolfeld `Strom` (`"VBAT=0.5A; +3V3=120mA"`), sonst Schätzung aus der DB.
- `print/slice.json` + aufgelöste `.ini`: Füllgrad, Perimeter, Linienbreite, Decklagen, Schichtzeit (M9, M22, W10).
- Kalibrierkörper `projects/kalibrierkoerper/`: einmal am MK4 drucken und messen, Werte in `messung.json`
  (T1, T4, T-UB, D10). Bis dahin rechnen T1/T4 mit vorläufigen MK4-Werten und melden höchstens `warnung`.


## Realterme und Lastdauer (seit 15.11.2026)

| Wo | Feld | Bedeutung |
|---|---|---|
| fem/<fall>.json (ganzer Fall oder je Eintrag in `lasten`) | `kurzzeit: true` bzw. `dauerlast: false` | Last ist kurz (Fügen, Stoß) → kein Kriechabschlag A_K; ohne Angabe gilt Dauerlast (ungünstig) |
| Teil `schnapper[]` | `zyklen`, `vorgespannt` | häufiges Fügen ×0,6 auf ε_zul, vorgespannt = Dauerlast |
| Teil Toleranz-Glieder | Merkmalart `aussen_bett`, `alpha_1_K`, `material` | Elefantenfuß +0,3 mm; Wärmeglied je Glied (Fremdteile z. B. FR4) |
| `_projekt` | `farbe`/`absorption`, `T_min_C`, `T_max_C`, `aussen` | gehen in die EINE Teiltemperatur (realterme.teil_temperatur) für D*, M*, E4, W6 |

Abschläge (realterme.py): Festigkeit σ_zul = σ_Z/(S·A_T·A_K·A_A); Kapazität ×0,85 nutzbar × Kälte × Alterung − Selbstentladung;
R_int × Kälte × 1,5; ε_zul ÷ (0,6 häufig, 0,7 kalt); Maß-σ ×2 bis Kalibrierkörper; RthJA ×1,5. Unbekannte Bedingung →
ungünstiger Standard, Ergebnis höchstens `warnung`.

## V-Modell-Felder (seit 15.11.2026, Einzelheiten `VMODELL.md`, `mb2/anforderungen.py`)

| Wo | Feld | Bedeutung |
|---|---|---|
| `_projekt._herkunft` (bzw. Teil `_herkunft`) | `{"<feld.pfad>": "gemessen\|datenblatt\|norm\|berechnet\|geschaetzt\|angenommen: Beleg"}` | Herkunft je Eingabe; Elternfeld deckt Kinder ab; schwächste Herkunft → Unsicherheit → Reserve-Pflicht |
| `_projekt.firmware` | `{pfad, konstanten: {NAME: {datei, soll \| soll_aus, herkunft}}}` | Firmware-Konstanten mit Prüfwirkung, FW1 vergleicht mit der Datei |
| `anforderungen.json` | `{id, ebene, eltern, text, herkunft, eingaben, nachweise: [{art, ref, teil, stufe, kriterium, warnung_akzeptiert, beleg, geprueft_von}]}` | Lastenheft/Pflichtenheft |
| `abnahme.json` | `schritte: [{id, anforderung, anweisung, soll {groesse, op, wert, einheit}, ist, datum, notiz}]` | Abnahme am Gerät |
| `feld.json` | `messungen: [{groesse, wert, einheit, ort, quelle, datum}]` | Messungen im Einsatz (snr_dB, rssi_dBm, empfangsquote_proz, laufzeit_h …) |

## Messkette (seit 19.11.2026, MK1–MK5, Einzelheiten `mb2/pruefungen/messkette.py`, `VMODELL.md`)

`_projekt.messkette` – alle Unsicherheiten als Standardunsicherheit (k = 1), Bezugspunkt in Klammern:

| Feld | Bedeutung | Prüfungen |
|---|---|---|
| `adc_bits`, `v_ref_V` | ADC-Auflösung und Referenzspannung | MK1, MK2, MK3 |
| `adc_rauschen_V` | ADC-Rauschen RMS (ADC-Eingang), getrennt von der Quantisierung q/√12 | MK1, MK2 |
| `u_ref_V`, `tk_ref_ppm_K`, `delta_T_K` | Unsicherheit und Temperaturkoeffizient der Referenz, Temperaturspanne | MK1 |
| `verstaerkung`, `u_verstaerkung_rel`, `tk_verstaerkung_ppm_K` | Verstärkung und ihre relative Toleranz/Drift | MK1, MK3 |
| `u_offset_V` | Eingangsoffset (Verstärkereingang) | MK1 |
| `empfindlichkeit_V_je_einheit`, `einheit` | Sensorempfindlichkeit S und Einheit der Messgröße | alle |
| `sensor_u`, `kalibrier_u` | Sensorelement, Kalibrierfunktion (Messgröße) | MK1 |
| `signal_V` | Signal am ADC für relative Fehler (Standard V_ref = ungünstigster Fall) | MK1 |
| `mittelung`, `k` | Mittelung über n Werte, Erweiterungsfaktor (Standard 2) | MK1, MK2 |
| `beitraege` | weitere Beiträge `[{name, wert, verteilung, k, c, einheit, freiheitsgrade}]` | MK1 |
| `ziel_U`, `ziel_aufloesung` | Ziel der erweiterten Unsicherheit und der kleinsten unterscheidbaren Änderung | MK1, MK2 |
| `messbereich {min, max}`, `offset_V_am_adc` | Aussteuerung über den Messbereich | MK3 |

Herkunft je Feld unter `_projekt._herkunft["messkette.<feld>"]`. Ist eine Herkunft schwach oder offen, ergibt MK1/MK2 höchstens eine `warnung`.
Anforderung mit `messtechnik`-Block (Format im Kopf von `mb2/anforderungen.py`) und Nachweis `art: messung`.
Die Messreihen stehen in `messung.json`.

### Profil `rtd_ratiometrisch_3leiter` (`mb2/sensorprofile/rtd.py`, MK1–MK4)

`messkette.profil = "rtd_ratiometrisch_3leiter"`, `modus = ab_werk | kalibriert`, `messbereich {min, max}`, `einheit`, `ziel_U`, `ziel_aufloesung`.

| Feld | Bedeutung |
|---|---|
| `sensor {R0_ohm, klasse (AA/A/B/C), eigenerwaermung_mW_K}` | Element nach IEC 60751 |
| `schaltung {I_idac_A, R_ref_ohm, R_ref_tol_rel, R_ref_tk_ppm_K, gain, bits, R_leitung_ohm, dR_leitung_ohm, idac_tausch, mittelung, T_elektronik_C [min, max], T_kal_C, R_filter_ohm, messrate_Hz, einschwing_s}` | ratiometrische 3-Leiter-Schaltung |
| `bauteile.adc {avdd_V, rauschen_Vrms, verstaerkungsfehler_rel, verstaerkungsdrift_ppm_K, offset_V, offsetdrift_V_K, inl_ppm_fsr, idac_fehlanpassung_rel, ref_eingangsstrom_A, idac_compliance_rand_V, pga_ausgang_rand_V, vcm_min_avdd_anteil, vref_min_V, vref_max_V, verstaerkungen, wandlungszeit_s, aussteuerung_reserve}` | ADC-Grenzen aus dem Datenblatt. Fehlt ein Wert, wird nicht gerechnet |
| `kalibrierung {u_referenz, u_fit, u_kopplung, koeffizienten {k0, k1, k2}, grad, reihe}` | Modus kalibriert. Füllt `kalibrierung_auswerten` aus einer rückführbaren Reihe. `reihe` darf kein Nachweis sein. Fehlen die Werte, zeigt MK1 die Planung: welche Unsicherheit die Kalibrierung höchstens haben darf |
| `vernachlaessigt {beitrag: Begründung}` | Beitrag bewusst weggelassen, MK1 ergibt dann höchstens `warnung` |

MK4-REF (Referenzspannung), MK4-IDAC (Compliance), MK4-PGA (Gleichtaktbereich: max(AVSS + Rand + G·V_in,max/2, Anteil·AVDD) ≤ V_CM ≤ AVDD − Rand − G·V_in,max/2), MK4-SELBST (Eigenerwärmung), MK5 (Zeitbudget: mittelung × (wandlungszeit + einschwing) ≤ 1/messrate).
Messreihe in `messung.json`: `datenstatus`, `sensor_id`, `seriennummer`, `datum`, `verfahren`, `referenz {mittel, seriennummer, kalibrierschein, rueckfuehrung, U, k, einheit, gueltig_bis}`, `bedingungen` (Schlüssel `_min`/`_max` als Mindest- bzw. Höchstwert), `pruefunsicherheit [Beiträge]`, `punkte [{ref, ist, richtung, t_h, zeit, roh_code}]`.

## Projektziele (seit 19.11.2026, K1–K4, `mb2/pruefungen/kpi.py`)

`project_new(..., ziele={...})` → `_projekt.ziele`. Jedes Feld darf `"unbekannt"` sein und wird dann als Risiko gemeldet.

| Feld | Bedeutung | Prüfung |
|---|---|---|
| `zielkosten_eur_stueck` | Bauteil- und Materialkosten je Gerät | K1 gegen `kosten.json → posten [{name, menge, preis_eur, quelle}]` |
| `aufwand_h_stueck` | Arbeitszeit je Gerät (Bau, Abgleich, Prüfung) | K2 gegen `kosten.json → arbeitsschritte [{name, h, quelle}]` |
| `termin` | erstes Gerät fertig und geprüft (JJJJ-MM-TT) | K3: liegt in der Zukunft |
| `prioritaet` | Reihenfolge von `qualitaet`, `kosten`, `zeit` | K4: eindeutig, jedes genau einmal |
| `stueckzahl`, `fehlerfolge` (gering/mittel/hoch), `pruefmittel` | Grundlage der Widerspruchsprüfung (folgt) | – |

Posten ohne Preis oder Quelle zählen als Lücke, nie als 0 €.

## Widerspruchsprüfung (seit 19.11.2026, X1–X9, `mb2/pruefungen/widerspruch.py`)

Hält Ziele, Einsatz, Messanforderungen und Schnittstelle gegeneinander. Ein harter Widerspruch ergibt `fehler`, ein Verstoß gegen eine Faustregel `warnung`.
Zusätzliche Eingaben:
- `_projekt.schnittstelle {bus: spi|i2c, leitung_m}` (X7)
- `ziele.zeit_h_pro_woche` (X5)

Alle übrigen Werte kommen aus `ziele`, `messkette`, `anforderungen.json`, `messung.json` und `kosten.json`.
