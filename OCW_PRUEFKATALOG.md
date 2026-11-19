# MIT OpenCourseWare → Prüfkatalog für maker-bridge 2

Stand 10.11.2026. Recherche in vier Fachgebieten auf https://ocw.mit.edu (Kursseiten und PDFs gelesen, wo „geprüft“ steht).
Ziel: Formeln, die mb2 **automatisch** rechnet (analytisch, ohne mehr Rechenzeit), als Vorab-Schätzung, Gegenprobe zur FEM oder harte Prüfung.
Lizenz OCW: CC BY-NC-SA – Formeln mit Quellenangabe übernehmen, keine Skripte in den Ordner kopieren.

## 1 Kernaussage

- OCW deckt die **Physik** vollständig ab (Balken, Beulen, Kerben, Viskoelastik/Kriechen, Wärme, Schwingung, Akustik, FEM-Konvergenz, Schaltungen, EMV, HF, Akkus).
- OCW hat **keine FDM-spezifischen Regeln** (Überhang, Brücke, Schichthaftung, Einschmelzmutter) und **keine Kennwerte für PLA/PETG/ASA** (Kriechen, α, ε_zul, μ, Wöhler). Die müssen aus Datenblättern oder eigenen Testkörpern am MK4 kommen.
- Größter Hebel für mb2 (Reihenfolge der Umsetzung):
  1. **FEM-Plausibilität:** Gleichgewicht (F23), Energiebilanz Wärme (W3), Netzkonvergenz + Richardson + Singularitäten (F20–F22).
  2. **Wärme-Lücken schließen:** h aus freier Konvektion (W1), Strahlung (W2), Innenluft (W5), Sonne (W6).
  3. **Druckrichtung in die Festigkeit:** anisotropes Kriterium (M7), Schnapphaken/Biegestege nur in XY (M1, M15).
  4. **Was lineare FEM nicht sieht:** Knicken (M4), Beulen von Rippen (M5), Kriechen unter Dauerlast und Schraubenvorspannung (D3, D4), Abstand zu Tg (D1).
  5. **Infill:** FEM rechnet Vollmaterial – Abminderung oder Regel „voll drucken“ (M9).
  6. **Elektronik:** Logikpegel (E1), Spannungsfall/Erwärmung (E2–E4), Akkubudget (E6), Brownout (E8), Entkopplung (E9), I2C (E11), Antennen-Keepout (E15), LiPo-Ladestrom (E21).

Legende Status: **OCW** = Formel im Kurs gelesen · **OCW-Thema** = Thema im Kurs, Formel Standardwissen · **abgeleitet** = selbst hergeleitet · **extern** = nicht auf OCW, andere Quelle nötig.
Umsetzung (Spalte „Umsetzung“, Stand 10.11.2026, Code in `mb2/pruefungen/`): **✅ umgesetzt** = Prüfung läuft wie beschrieben (fehlt eine Eingabe → `uebersprungen` mit Grund) · **◐ teilweise** = läuft mit Einschränkung (Notiz) · **○ offen** = nicht gebaut. Felder: `mb2/pruefungen/FELDER.md`, Befehl `pruefkatalog` / `audit`.
Eingaben: G = Geometrie (build123d), DR = Druckrichtung (cad_plate), S = soll.json, M = material.py, Sl = Slicer, FEM = FEM-Ergebnis, K = KiCad (Netzliste/Layout/Lagen/board_info), **neu** = Feld fehlt heute.

## 1a Stand 15.11.2026 – Scheinsicherheit beseitigt (Audit `audits/SCHEINSICHERHEIT_2026-11-15.md`)

Anlass: Bodenklima-Funkstrecke, auf dem Papier ok, im Feld 30 dB schlechter. Zwei Mechanismen statt Einzelflicken:
- **Muster A – Auslöser:** `mb2/pruefungen/merkmale.py` erkennt Merkmale (Funk, Akku, außen, Elektronik, Schrauben,
  Schnapper, Dauerlast, Handgerät, Anregung, Lautsprecher, FEM-Mechanik); `AUSLOESER` in `__init__.py` macht aus
  `uebersprungen` dieser Prüfungen einen `fehler` (oder ergänzt einen, wenn eine Prüfung gar nichts liefert).
  Verzicht nur über `_projekt.nicht_relevant`. Soll-gesteuerte Prüfungen (M1, M2, M12–M16, M19, M23, D2–D4, D7, D12)
  melden ohne Eintrag jetzt sichtbar `uebersprungen` statt nichts. Kaufmodule ohne KiCad (`elektronik.module`) werden
  in E6/E8/E15/E16/E21 gerechnet, Rest als `E-Rest`.
- **Muster B – Realterme:** `mb2/realterme.py` liefert alle Abschläge und die EINE Teiltemperatur (Luft + Sonne +
  Eigenerwärmung). Annahmen → höchstens `warnung`. FEM-Bewertung und Festigkeiten: σ_zul = σ_Z/(S·A_T·A_K·A_A);
  Bewertung wird bei Cache-Treffern neu bewertet.

Geändert je ID: **E4** T_Teil + RthJA×1,5 + Rth_gehaeuse · **E6** C_eff, Wandler I·V_out/(η·V_bat), ok ≥ 1,25×Ziel, ohne Ziel
`warnung` · **E8** R_eff = R_int×Kälte×1,5, Reserve 0,15 V · **E15** höchstens `warnung`, solange Metall im Gehäuse
ungeprüft · **E16** log-distance + Hindernisse/Kabel/Antenne, Funk ohne Angaben = `fehler` · **E21** ok ≤ 0,5 C, NTC Pflicht
bei T_min < 10 °C/außen · **M1** ε_zul ÷ f_eps ÷ 1,2 · **M6** globales Netz > ρ/3 an Kehle → `warnung` · **M7** Druckrichtung aus
`druck_drehung` · **M9** ungesliced Standardprofil (15 % grid, 2 Perimeter), S < 1 `fehler` · **M12** Restvorspannung
0,5·F0 ohne Kriechdaten · **M13/M14/M16/M23** Festigkeit mit Realtermen · **D1** Teiltemperatur mit Sonne, ohne Angabe
40/30 °C angenommen · **D4** 0,5·F0/A_T · **W6** Grenze wie D1 (Tg−20/−30 K), max(Box, realterme), eine Farbtabelle ·
**S4** S ≥ 2 bei Kälte/außen, Achsen-Warnung · **T1/T2/T6** σ 0,10 vorläufig (gedeckelt), `aussen_bett` +0,3 mm,
Wärmeglied α·L·ΔT (sonst ±20 K angenommen).

## 2 Kurse

### Mechanik, Strukturen, Maschinenelemente
| Kurs | Titel, Semester | URL | Relevant |
|---|---|---|---|
| 2.001 | Mechanics & Materials I, F06 | https://ocw.mit.edu/courses/2-001-mechanics-materials-i-fall-2006/ | L4 Reibung, L14 Wärmedehnung/dünnwandig, L17 Versagen (Tresca/Mises), L18–21 Biegung, L22–23 Torsion |
| 2.002 | Mechanics and Materials II, S04 | https://ocw.mit.edu/courses/2-002-mechanics-and-materials-ii-spring-2004/ | L2 Biegung/Knicken/Schwingung, L7 Anisotropie, L14–15 Kriechen, L17–19 Bruchmechanik, L20–22 Ermüdung, **Labor 2 Polymer-Viskoelastik** |
| 2.72 | Elements of Mechanical Design, S09 | https://ocw.mit.edu/courses/2-72-elements-of-mechanical-design-spring-2009/ | L04 Ermüdung, L06 Constraints, **L08 Biegegelenke**, **L10 Schraubverbindungen**, L13 Zahnräder, L16 Schwingung |
| 2.080J | Structural Mechanics, F13 | https://ocw.mit.edu/courses/2-080j-structural-mechanics-fall-2013/ | L5–7 Balken/Platten, L9–10 Knicken, **L11 Plattenbeulen**, L12 Plastizität |
| 2.081J | Plates and Shells, S07 | https://ocw.mit.edu/courses/2-081j-plates-and-shells-spring-2007/ | Plattenbiegung, Beulen (nicht geöffnet) |
| 16.20 | Structural Mechanics, F02 | https://ocw.mit.edu/courses/16-20-structural-mechanics-fall-2002/ | Unit 4/5 anisotrope Elastizität, 8 Kerben, 9 Wärmespannung, 10–12 Torsion, 16–18 Knicken/Beulen, **19 Dynamik-Regime**, 23 Balkenschwingung |
| 16.001 | Unified Eng.: Materials & Structures, F21 | https://ocw.mit.edu/courses/16-001-unified-engineering-materials-and-structures-fall-2021/ | Balken, Trägheitsmoment, Torsion, Knicken |
| 2.007 | Design and Manufacturing I, S09 | https://ocw.mit.edu/courses/2-007-design-and-manufacturing-i-spring-2009/ | L13 Lewis-Zahnfestigkeit |
| 2.75 | Precision Machine Design, F01 | https://ocw.mit.edu/courses/2-75-precision-machine-design-fall-2001/ | Constraints, **Topic 4 Fehler: Wärmedehnung, Bimetall, Gradient, Fehlerbudget** |
| 2.76 | Multi-Scale System Design, F04 | https://ocw.mit.edu/courses/2-76-multi-scale-system-design-fall-2004/ | L10 Fehlerbudgets |
| 2.875 | Mechanical Assembly, F04 | https://ocw.mit.edu/courses/2-875-mechanical-assembly-and-its-role-in-product-development-fall-2004/ | cls3 Verkeilen/Fasen, **cls8/9 Toleranzketten WC/RSS**, class16 DFA |
| 1.050 | Solid Mechanics F04 / Eng. Mechanics I F07 | https://ocw.mit.edu/courses/1-050-solid-mechanics-fall-2004/ | Grundlagen (nicht einzeln geprüft) |
| 2.009 | Product Engineering Process, F21 | https://ocw.mit.edu/courses/2-009-product-engineering-process-fall-2021 | Prozess, keine Formeln |

### Werkstoffe, Fertigung
| Kurs | Titel, Semester | URL | Relevant |
|---|---|---|---|
| **3.064** | Polymer Engineering, F03 | https://ocw.mit.edu/courses/3-064-polymer-engineering-fall-2003/ | **wichtigste Polymer-Quelle:** lec_8 Kriechen/Relaxation, lec_10–13 Maxwell/Zener, **lec_14 WLF/effektive Zeit**, lec_16 Boltzmann, lec_33 Abkühlen, **latch_design (Schnapphaken)** |
| 3.032 | Mechanical Behavior of Materials, F07 | https://ocw.mit.edu/courses/3-032-mechanical-behavior-of-materials-fall-2007/ | Ses 16/28/29 Viskoelastik/Kriechen (ohne PDF), 35–37 Ermüdung |
| 3.063 | Polymer Physics, S07 | https://ocw.mit.edu/courses/3-063-polymer-physics-spring-2007/ | lec7 Glasübergang (nicht gelesen) |
| 3.054 | Cellular Solids, S15 | https://ocw.mit.edu/courses/3-054-cellular-solids-structure-properties-and-applications-spring-2015/ | Waben, Schäume, Gitter, Sandwich (Infill-Modell; Handschrift-Scans) |
| 2.008 | Design and Manufacturing II, S25 | https://ocw.mit.edu/courses/2-008-design-and-manufacturing-ii-spring-2025/ | L02/03 Spritzguss (Wand ±10 %, Schwindung), L08 Montage, L11 Qualität, **L23 Additive Fertigung (nur qualitativ)** |
| 2.830J | Control of Manufacturing Processes, S08 | https://ocw.mit.edu/courses/2-830j-control-of-manufacturing-processes-sma-6303-spring-2008/ | **L8 Prozessfähigkeit Cp/Cpk** |
| 3.044 | Materials Processing, S13 | https://ocw.mit.edu/courses/3-044-materials-processing-spring-2013/ | L4 Biot, Newton-Abkühlung |
| 16.881 | Robust System Design, Su98 | https://ocw.mit.edu/courses/16-881-robust-system-design-summer-1998/ | Toleranzauslegung (nur Gliederung) |

### Wärme, Schwingung, Akustik, FEM-Methodik
| Kurs | Titel, Semester | URL | Relevant |
|---|---|---|---|
| 2.51 | Intermediate Heat and Mass Transfer, F08 | https://ocw.mit.edu/courses/2-51-intermediate-heat-and-mass-transfer-fall-2008/ | Widerstände, Biot, Rippen, freie Konvektion, Strahlung/Sichtfaktoren, Sonne (Lehrbuch Lienhard, frei, nicht OCW) |
| 16.050 | Thermal Energy, F02 | https://ocw.mit.edu/courses/16-050-thermal-energy-fall-2002/ | **Teil 3 Heat Transfer:** Widerstände, Biot, Quelle im Körper, Rippe, Zeitkonstante, graue Strahler, ε-Tabelle |
| **4.42J** | Fundamentals of Energy in Buildings, F10 | https://ocw.mit.edu/courses/4-42j-fundamentals-of-energy-in-buildings-fall-2010/ | **Heat-Transfer-Skript:** Biot < 1/6, h-Faustformeln freie Konvektion, Luftspalt, **h_r = 4σT³** |
| 3.185 | Transport Phenomena in Materials Eng., F03 | https://ocw.mit.edu/courses/3-185-transport-phenomena-in-materials-engineering-fall-2003/ | Nu-Korrelationen senkrechte Platte, Sichtfaktoren |
| 2.997 | Direct Solar/Thermal to Electrical Energy, F09 | https://ocw.mit.edu/courses/2-997-direct-solar-thermal-to-electrical-energy-conversion-technologies-fall-2009/ | L8 Strahlung, Solarkonstante, AM1.5 |
| 10.302 | Transport Processes, F04 | https://ocw.mit.edu/courses/10-302-transport-processes-fall-2004/ | nur Übungen (nicht geöffnet) |
| 2.092 | FEA of Solids and Fluids I, F09 | https://ocw.mit.edu/courses/2-092-finite-element-analysis-of-solids-and-fluids-i-fall-2009/ | L11 Wärme-RB, L18 Dynamik/Δt, L19 Grenzfrequenz/Moden |
| **2.094** | FEA of Solids and Fluids II, S11 | https://ocw.mit.edu/courses/2-094-finite-element-analysis-of-solids-and-fluids-ii-spring-2011/ | **L8 Konvergenzordnung**, L9 Locking, L10 Newton-Abbruch (kein Kontakt) |
| RES.2-002 | FE Procedures (Bathe, Videos), S10 | https://ocw.mit.edu/courses/res-2-002-finite-element-procedures-for-solids-and-structures-spring-2010/ | nichtlinear evtl. Kontakt (nicht geöffnet) |
| 2.29 | Numerical Fluid Mechanics, S15 | https://ocw.mit.edu/courses/2-29-numerical-fluid-mechanics-spring-2015/ | L1/2 Fehler, **L10 Ordnung, Richardson** |
| 16.920J, 18.085, 18.086 | Numerik PDE / CSE | https://ocw.mit.edu/courses/16-920j-numerical-methods-for-partial-differential-equations-sma-5212-spring-2003/ | Grundlagen (nicht geöffnet) |
| 2.003SC | Engineering Dynamics, F11 | https://ocw.mit.edu/courses/2-003sc-engineering-dynamics-fall-2011/ | L19–21 Schwinger, **f = √(g/δ)**, L27 Kontinua |
| 2.003J | Dynamics and Control I, S07/F07 | https://ocw.mit.edu/courses/2-003j-dynamics-and-control-i-fall-2007/ | Schwinger, Bode (nicht geöffnet) |
| **6.551J** | Acoustics of Speech and Hearing, F04 | https://ocw.mit.edu/courses/6-551j-acoustics-of-speech-and-hearing-fall-2004/ | **L7 akustische Elemente, L10 Helmholtz**, L15–17 Röhren |
| 2.067 | Adv. Structural Dynamics and Acoustics, S04 | https://ocw.mit.edu/courses/2-067-advanced-structural-dynamics-and-acoustics-13-811-spring-2004/ | nur Akustik-Teil online |
| 21M.380 | Music and Technology: Sound Design, S16 | https://ocw.mit.edu/courses/21m-380-music-and-technology-sound-design-spring-2016/ | Helmholtz (nicht geöffnet) |
| 2.25 | Advanced Fluid Mechanics, F13 | https://ocw.mit.edu/courses/2-25-advanced-fluid-mechanics-fall-2013/ | Hintergrund Belüftung |

### Elektronik, Leistung, EMV, HF, Akkus
| Kurs | Titel, Semester | URL | Relevant |
|---|---|---|---|
| 6.002 | Circuits and Electronics, S07 | https://ocw.mit.edu/courses/6-002-circuits-and-electronics-spring-2007/ | **L4 Störabstand**, L12 RC, **L13 RC-Verzögerung/Übersprechen**, L18 Filter, **L22 Leistung/Akkulaufzeit** |
| 6.012 | Microelectronic Devices and Circuits, F09 | https://ocw.mit.edu/courses/6-012-microelectronic-devices-and-circuits-fall-2009/ | Dioden, LEDs, CMOS-Störabstand, Verlustleistung |
| 6.01SC | Intro to EECS I, S11 | https://ocw.mit.edu/courses/6-01sc-introduction-to-electrical-engineering-and-computer-science-i-spring-2011/ | Grundlagen Schaltungen |
| 6.071J | Electronics, Signals, Measurement, S06 | https://ocw.mit.edu/courses/6-071j-introduction-to-electronics-signals-and-measurement-spring-2006/ | Filter, Güte, Dioden, OpAmps |
| 6.101 | Analog Electronics Lab, S07 | https://ocw.mit.edu/courses/6-101-introductory-analog-electronics-laboratory-spring-2007/ | **Ripple ΔV = IΔt/C**, Regler, Filter, max. Leistung |
| 6.111 | Digital Systems Lab, S06 | https://ocw.mit.edu/courses/6-111-introductory-digital-systems-laboratory-spring-2006/ | **L16 P = αCV²f, Tj = Ta + RθJA·P** |
| 6.302 / RES.6-010 | Feedback Systems S07 / Roberge S13 | https://ocw.mit.edu/courses/6-302-feedback-systems-spring-2007/ | Phasenreserve, OpAmp-Stabilität |
| 6.334 | Power Electronics, S07 | https://ocw.mit.edu/courses/6-334-power-electronics-spring-2007/ | DC/DC, Magnetik, EMI-Filter (Thermik nur Scan) |
| **6.622** | Power Electronics, S23 | https://ocw.mit.edu/courses/6-622-power-electronics-spring-2023/ | **beste Quelle:** L9 Magnetkreis, L12 Kupferverlust/Skin, L16 Thermik, L28–30 EMI, **L38 Layout/Schleifeninduktivität** |
| 6.013 | Electromagnetics and Applications, S09 | https://ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/ | **L11 λ/8-Regel, Z0**, L14 Resonatoren, **L17 Friis**, **L19 Antennen/Masse** |
| 6.776 | High Speed Communication Circuits, S05 | https://ocw.mit.edu/courses/6-776-high-speed-communication-circuits-spring-2005/ | Leitungen, S-Parameter, Smith |
| 6.630, 6.641, 6.007, 6.061, 6.661, 6.331 | EM/Power/Receiver | https://ocw.mit.edu/courses/6-061-introduction-to-electric-power-systems-spring-2011/ | Hintergrund (nicht vertieft) |
| 10.626 | Electrochemical Energy Systems, S14 | https://ocw.mit.edu/courses/10-626-electrochemical-energy-systems-spring-2014/ | **L3 Akkumodell V = V0 − I·Rint**, L13 Li-Ionen |
| 2.627 | Fundamentals of Photovoltaics, F13 | https://ocw.mit.edu/courses/2-627-fundamentals-of-photovoltaics-fall-2013/ | nur bei Solar-Laden |

**Nicht auf OCW:** 2.744, 2.810, 2.S998 (Additive), 6.131, 6.115, 6.014, 2.005/2.006, 2.032, 2.060J.

## 3 Prüfkatalog

### 3.1 Mechanik am Teil (Vorab-Schätzung vor der FEM, Gegenprobe danach)
| ID | Prüfung | Formel | Quelle (Status) | Eingaben | Kriterium | Prio | Umsetzung |
|---|---|---|---|---|---|---|---|
| M1 | Schnapphaken | δ = P·a²(3L−a)/(6EI); Endlast ε = 1,5·t·y/L², F = E·b·t³·y/(4L³) | 3.064 latch_design (OCW), 2.001 L18–20, 2.72 L08 | G, DR, M, **ε_zul neu** | ε ≤ ε_zul, σ ≤ σ_XY/1,5; Hakenachse ∥ Z → **Fehler** | hoch | ✅ umgesetzt – Achse aus soll |
| M2 | Fügekraft Keil/Rastnase | W = F(μ + tanα)/(1 − μ·tanα) | 2.001 L4 (OCW-Thema) | G, M1, **μ neu** | W ≤ Handkraft ~30 N; Selbsthemmung melden | mittel | ✅ umgesetzt |
| M3 | Balken-Gegenprobe | σ = Mc/I, δ = FL³/(3EI), Superposition | 2.001 L18–21, 2.080J L5 (OCW) | G, Lastfall, M | FEM ↔ Analytik ≤ 20–30 %, sonst Netz/RB verdächtig | hoch | ◐ teilweise – nur mit soll `balken` |
| M4 | Euler-Knicken | P_cr = π²EI/(KL)², K = 2/1/0,7/0,5 | 2.002 L2, 2.080J L9/10 (OCW) | G, Lagerung, M (E_Z bei stehend) | P_cr/P ≥ 3 – lineare FEM sieht Knicken nicht | hoch | ◐ teilweise – Stabdaten nur aus soll |
| M5 | Plattenbeulen Wand/Rippe | σ_cr = k·π²E/(12(1−ν²))·(t/b)²; k = 4 (gelenkig), ≈ 0,456 + (b/a)² (freier Rand), Schub 5,35–9,35 | 2.080J L11 (OCW) | G (t aus Strahltest), M | σ_cr ≥ σ_Fest/S → Regel freie Rippe **h/t ≤ ~4,4** (Code 19.11.2026: PLA 4,45, PETG 4,41 mit E_Z; die alten Werte 5,3/4,8 stammten aus E = 3500) | hoch | ✅ umgesetzt – auto aus STEP, nur ebene Platten |
| M6 | Kerbwirkung Innenecke | K_f = 1 + q(K_t − 1), q ≈ 1 (spröde) | 2.72 L04 (OCW), 16.20 Unit 8 | Innenradien aus Kantenanalyse G | ρ ≥ 0,5·t bzw. K_t ≤ 2; Netz an Kerbe ≤ ρ/3 | hoch | ✅ umgesetzt – auto aus STEP, nur zyl. Kehlen |
| M7 | Anisotropes Versagen | Tsai-Hill transversal-isotrop: (σx² + σy² − σxσy)/X² + σz²/Z² + (τxz² + τyz²)/S_Z² + τxy²/S_XY² ≤ 1/S² | 16.20 Unit 4/5, 2.002 L7 (OCW-Thema); Tsai-Hill **extern** | FEM-Tensor, DR, M (Schub **neu**, ≈ σ/√3) | Index ≤ 1/S_ziel – ersetzt „σ_vM gegen σ_XY/σ_Z“ | hoch | ✅ umgesetzt – braucht druckrichtung |
| M8 | Orthotrope Steifigkeit | CalculiX `*ELASTIC, TYPE=ENGINEERING CONSTANTS` | 16.20 Unit 4/5 (OCW-Thema) | **E_Z, G neu** | – | mittel | ✅ umgesetzt – `orthotrop` |
| M9 | Infill als zellulärer Körper | E*/E ≈ (ρ*/ρ)², σ* ≈ 0,3σ(ρ*/ρ)^1,5; Sandwich: Perimeter = Deckschichten | 3.054 L4/5/7/17 (OCW-Thema, Gibson-Ashby) | Sl (Infill %, Perimeter), G | Querschnitt ≤ 2·Perimeterbreite·n (voll) oder FEM-Kern abmindern | hoch | ◐ teilweise – analytisch am Spannungsfeld, Kern im Löser nicht abgemindert |
| M12 | Schraubverbindung | C = k_b/(k_b + k_m); F_b = C·P + F_i; Klaffen bei P = F_i/(1−C); Pressung F_i/(π/4(d_w² − d_h²)) | 2.72 L10 (OCW) | G (Bohrungen), S (**Schraubenliste neu**), M | kein Klaffen; Pressung ≤ σ_Druck/S; Einschraubtiefe ≥ 2–2,5·D in Kunststoff | hoch | ✅ umgesetzt |
| M13 | Dom/Einschmelzmutter ausreißen | τ = F/(π·d_a·L) ≤ σ_Z/√3 | 2.001 L17 (OCW-Thema) | S (Insert-Maße), G, M (σ_Z) | S ≥ 2; Domfuß-Radius (M6) | hoch | ✅ umgesetzt |
| M14 | Pressitz | Lamé: p aus Übermaß; σ_θ = p(D² + d²)/(D² − d²) | 2.001 L14 dünnwandig (OCW), Lamé extern | G, S (Übermaß), M | σ_θ ≤ σ/S (liegende Bohrung: σ_Z); Relaxation → D3 | mittel | ✅ umgesetzt |
| M15 | Filmscharnier/Federsteg | θ_max = 2·L·ε_zul/t; k_θ = E·b·t³/(12L) | 2.72 L08 (OCW) | G, S (Sollwinkel) | θ_soll ≤ θ_max/S; Biegung nur in XY; Ausnahme von 1,8 mm per S-Flag | mittel | ✅ umgesetzt |
| M16 | Torsion | τ ≈ 3T/(b·t²) offen; Bredt τ = T/(2A_m·t) | 2.001 L22/23, 16.20 Unit 10–12 (OCW) | G, M | τ ≤ σ/(√3·S); stehende Welle: σ_Z | mittel | ✅ umgesetzt – nur soll |
| M19 | Deckeldurchbiegung | D = Eh³/(12(1−ν²)); w = α·q·b⁴/D | 2.080J L7 (OCW-Thema) | G, S (Last), M | w ≤ Abstand zur Platine darunter | mittel | ✅ umgesetzt – nur soll |
| M21 | Plastische Reserve | Rechteck M_p = 1,5·M_y | 2.002, 2.080J L12 | G | nur Info (PETG), nicht in Z | niedrig | ✅ umgesetzt – info |
| M22 | Bruchmechanik Fehlstellen | K_I = Yσ√(πa), a ≈ Linienbreite | 2.002 SES 23–26 | **K_IC neu** | K_I ≤ K_IC/S | niedrig | ✅ umgesetzt – nimmt FEM-Spitze, konservativ |
| M23 | Zahnrad (Lewis) | σ = F_t/(b·m·Y) | 2.007 L13 (OCW) | G/S | σ ≤ σ_XY/S, liegend drucken | niedrig | ✅ umgesetzt – nur soll |
| M24 | Constraint-Zählung | FG = 6 − C | 2.72 L08, 2.75 | S (Baugruppe) | Überbestimmung melden | niedrig | ✅ umgesetzt – nur soll |
| M26 | Sicherheitsziel aus Streuung | k_e = 1 − 0,08·z (99 % → 0,81) | 2.72 L04 (OCW) | Streuung je Richtung **neu** | S_ziel ≥ Lastfaktor/k_e; in Z höher | mittel | ✅ umgesetzt |

### 3.2 FEM-Methodik und Plausibilität
| ID | Prüfung | Formel/Verfahren | Quelle | Kriterium | Prio | Umsetzung |
|---|---|---|---|---|---|---|
| F20 | Netzkonvergenz | Fehler u ~ h^(k+1), σ ~ h^k, Energie ~ h^(2k) (Tet10: k = 2); Energie steigt monoton | 2.094 L8 (OCW) | 2–3 Netze per Gmsh-Box, r ≈ 1,5–2; Ordnung ≈ erwartet | hoch | ✅ umgesetzt – `konvergenz` |
| F21 | Richardson | p = ln((f₃−f₂)/(f₂−f₁))/ln r; f_∞ = f₁ + (f₁−f₂)/(r^p − 1) | 2.29 L10 (OCW-Thema) | Ergebnis mit Fehlerband; < 5 % (T, δ), < 10 % (σ) | hoch | ✅ umgesetzt – GCI/Celik |
| F22 | Singularität erkennen | σ_max wächst bei jeder Verfeinerung, Energie konvergiert → Kerbsingularität | abgeleitet aus 2.094 L8 | σ dort „singulär“, nicht für Sicherheit; Radius ≥ 1 mm vorschlagen | hoch | ✅ umgesetzt |
| F23 | Gleichgewicht | ΣF_Reaktion + ΣF_Last = 0, ΣM = 0 | 2.092 (OCW-Thema) | Abweichung < 0,5 % | hoch | ✅ umgesetzt |
| F24 | Newton/Kontakt konvergiert | ‖ΔU‖/‖U‖ < ε_D, ‖R − F‖ < ε_F; Durchdringung ≪ Element | 2.094 L10 (OCW); Penalty **extern** | Durchdringung < 1 % Element und < 0,05 mm | mittel | ◐ teilweise – Residuen nur berichtet, Durchdringung geprüft |
| F25 | Locking | ν → 0,5 | 2.094 L8/9 (OCW) | ν > 0,45 (TPU) → Warnung | niedrig | ✅ umgesetzt |
| F13/F14 | Dynamik-Netz/Δt | ω_co = 4·ω_max; Δt ≤ 2/ω_max | 2.092 L18/19 (OCW) | nur falls Modal/Transient kommt | niedrig | ○ offen – keine Modal-/Transientrechnung |

### 3.3 Wärme (schließt die offenen Punkte Strahlung und Innenluft)
| ID | Prüfung | Formel | Quelle | Eingaben | Kriterium | Prio | Umsetzung |
|---|---|---|---|---|---|---|---|
| W1 | h freie Konvektion | Ra = gβΔT·L³/(να); laminar Nu = 0,56·Ra^¼; Luft ≈ 1,42·(ΔT/L)^¼ W/m²K | 3.185 §5.4, 4.42J Gl. 3.13 (OCW; SI-Umrechnung abgeleitet) | G, Lösung ΔT (iterativ) | Festwert ↔ Korrelation > 30 % → neu rechnen | hoch | ✅ umgesetzt – `konvektion.auto` |
| W2 | Strahlung | h_r = εσ(T_s + T∞)(T_s² + T∞²) ≈ 4εσT³ ≈ 5,5 W/m²K bei 300 K, ε = 0,9 | 4.42J Gl. 4.5–4.7, 16.050 §9 (OCW) | ε = 0,9 | h_ges = h_c + h_r als Robin-RB; ab ΔT > 30 K T⁴ | hoch | ✅ umgesetzt – `strahlung` |
| W3 | Energiebilanz | ΣQ_Quelle = ∫h(T−T∞)dA + ∫εσ(T⁴−T∞⁴)dA | 2.092 L11 (OCW) | Lösung, Leistung | Abweichung < 2 % | hoch | ✅ umgesetzt – immer |
| W4 | Wärmewiderstands-Netz | R = t/(kA), 1/(hA); ΔT = Q·R_ges | 4.42J §2, 16.050 §2 (OCW) | G, M | Elmer-ΔT_mittel ±25 % | hoch | ◐ teilweise – nur Quelle auf Druckwand |
| W5 | Innenluft | Spalt < ~10 mm: Nu = 1, h = k_Luft/δ (0,026 W/mK); Strahlung ε_eff = 1/(1/ε₁ + 1/ε₂ − 1) ≈ 0,82 | 4.42J Gl. 3.15, 16.050 §9.3 (OCW) | G + board.step | Luft als Ersatzleiter + h_r Platine↔Wand | hoch | ✅ umgesetzt – `innenluft` |
| W6 | Sonne | Q = α_s·G·A_proj, G ≈ 1000 W/m²; ΔT ≈ Q/((h_c + h_r)·A_ges) | 2.997 L8 (OCW, 1000 W/m² Standardwert) | **S: außen, Farbe→α_s neu** | T∞ + ΔT_Sonne + ΔT_intern < Tg − 10 K (→ D1) | hoch | ✅ umgesetzt – `sonne` + Prüfung |
| W7 | Biot, Zeitkonstante | Bi = hL/k < 1/6; τ = ρcV/(hA) | 4.42J, 16.050 §3.3/§6, 3.044 L4 (OCW) | G, M (**c_p neu**), S (Lastdauer) | Lastdauer > 3τ → stationär ok | mittel | ◐ teilweise – c_p FR4/ALU fehlt → τ eher zu klein |
| W8 | Quelle im Körper | ΔT = q'''L²/(8k) | 16.050 §4 (OCW) | G, Leistung | T_max-Größenordnung | niedrig | ✅ umgesetzt – nur info |
| W9 | Rippen-Wirkungsgrad | m = √(hP/(kA)), η = tanh(mL)/(mL) | 16.050 §5 (OCW) | G, M | η < 0,5 → Rippe lohnt nicht (PLA k ≈ 0,13) | niedrig | ✅ umgesetzt |
| W10 | Abkühlung beim Druck | Fo = αt/L², α ≈ 10⁻⁷ m²/s | 3.064 lec_33, 3.044 L4 | Sl (Schichtzeit) | Schichtzeit ≥ Abkühlzeit bis Tg (kleine Türme) | niedrig | ◐ teilweise – braucht `h_luefter_W_m2K` |

### 3.4 Werkstoff, Dauerlast, Temperatur
| ID | Prüfung | Formel | Quelle | Eingaben | Kriterium | Prio | Umsetzung |
|---|---|---|---|---|---|---|---|
| D1 | Abstand zu Tg | Steifigkeit fällt um ~Faktor 1000 innerhalb 10–20 K um Tg | 2.002 Labor 2 (OCW) | M (Tg), **S: T_max neu**, Elmer | T_max ≤ Tg − 20 K (abgeleitet); Warnung ab Tg − 30 K | hoch | ✅ umgesetzt |
| D2 | Grenze lineare Viskoelastik | linear nur bis ε ≈ 1 % | 2.002 Labor 2 (OCW) | FEM ε, **S: Dauerlast neu** | ε_Dauer < 1 % (PLA eher 0,5 %) | hoch | ✅ umgesetzt |
| D3 | Kriechdurchbiegung | Korrespondenzprinzip δ(t) = δ_FEM·E₀/E_r(t); SLS E_r = E_∞ + (E₀ − E_∞)e^(−t/τ) | 2.002 Labor 2, 3.064 lec_8/10–12 (OCW) | **M: E_∞/E₀, τ neu; S: t_Ende neu** | δ(t_Ende) ≤ zulässig | hoch | ◐ teilweise – Kriechkennwerte nur ASA (1000 h) |
| D4 | Vorspannungsverlust Schrauben | F(t) = F₀·E_r(t)/E₀ + M12 | 3.064 lec_8, 2.72 L10 (OCW) | M12 + D3 | F(t_Ende) ≥ nötige Klemmkraft | hoch | ◐ teilweise – wie D3 |
| D5 | Zeit-Temperatur-Verschiebung | WLF log a_T = −17,44(T−Tg)/(51,6 + T−Tg); unter Tg Arrhenius | 3.064 lec_14 (OCW) | **S: T_einsatz; M: U neu** | t/a_T in D3/D4 | hoch | ◐ teilweise – Aktivierungsenergie U fehlt → höchstens warnung |
| D6 | Effektive Zeit Tagesgang | t′ = ∫dξ/a_T(T(ξ)) | 3.064 lec_14 (OCW) | **S: T_avg, ΔT neu** | wie D3 | mittel | ◐ teilweise – wie D5 |
| D7 | Boltzmann-Superposition | ε(t) = ΣΔσ_i·J(t − t_i) | 3.064 lec_16 (OCW) | Lastgeschichte | Baustein | niedrig | ◐ teilweise – SLS-Kennwerte fehlen, nur per Projekt-Überschreibung |
| D8 | Wärmedehnung gegen Platine/Metall | Δδ = (α_K − α_FR4)·L·ΔT | 2.75 Topic 4, 2.001 L14 (OCW) | K (board_info), G (Spalt), **M: α neu** | Spalt − Δδ ≥ 0,1 mm (das Kriterium „warm ≥ 0,4 mm“ ist **nicht** umgesetzt) | hoch | ◐ teilweise – braucht `platine_spalt_mm` |
| D9 | Bimetall/Zwang | voll eingespannt σ ≈ E·Δα·ΔT; Timoshenko-Bimetall | 2.75 Topic 4 (OCW, Folie verstümmelt) | G, M | σ ≤ σ_XY/S | mittel | ✅ umgesetzt |
| D10 | Verzug-Indikator ASA | Schwindungsdehnung α·(Tg − T_Bauraum)·L_Grundfläche; κ = αΔT/h | 2.75 Topic 4, 2.008 L23 (OCW qualitativ) | G, Sl, M | Rangfolge; Schwelle **am MK4 kalibrieren** | mittel | ◐ teilweise – Schwelle erst nach Kalibrierkörper |
| D11 | Ermüdung | Goodman σ_a/S_e + σ_m/S_ut = 1/n; S_e mit k-Faktoren | 2.72 L04, 2.002 L20–22 (OCW) | FEM, **S: Zyklen; M: S_e neu** | n ≥ 2 | mittel | ◐ teilweise – S_e PETG fehlt |
| D12 | Kriechbruch | ε̇ = ε̇₀(σ/s)ⁿe^(−Q/RT); Monkman-Grant | 2.002 L14a/b/15 (OCW, Metalle) | **M neu** | t_f ≥ Lebensdauer | niedrig | ◐ teilweise – nur mit soll `kriechbruch` |

### 3.5 Toleranz, Montage, Druckgenauigkeit
| ID | Prüfung | Formel | Quelle | Eingaben | Kriterium | Prio | Umsetzung |
|---|---|---|---|---|---|---|---|
| T1 | Prozessfähigkeit | C_p = (USL − LSL)/(6σ); C_pk = min(USL − μ, μ − LSL)/(3σ) | 2.830J L8 (OCW) | S (Toleranzen), **MK4-σ/μ je Merkmalart neu** | C_pk ≥ 1,33, sonst Toleranz aufweiten | hoch | ✅ umgesetzt – vorläufige MK4-Werte bis messung.json |
| T2 | Toleranzkette | WC: ΣT; RSS √ΣT² **plus systematischer Versatz linear** | 2.875 cls8/9 (OCW) | **S: Kettendefinition neu**, T1 | Spalt_min ≥ 0,4 mm | hoch | ✅ umgesetzt |
| T3 | Verkeilen/Fasen | c = (D − d)/D; Verkeilen wenn Kontaktlänge < μ·D | 2.875 cls3 (OCW; Grenze abgeleitet) | G, **μ neu** | Fase ≥ c·D, ≥ 0,4 mm | mittel | ✅ umgesetzt |
| T4 | Schwindungsvorhalt | ΔL = a·L | 2.008 L03 (OCW, Spritzguss-Werte) | **a je FDM-Material am MK4 messen** | Bohrung_CAD = Soll + Kompensation | mittel | ✅ umgesetzt – Schwindung vorläufig |
| T5 | Gleichmäßige Wand | Wand ±10 % | 2.008 L03 (OCW) | Strahltest-Verteilung | Hinweis bei Streuung > ±10–20 % | niedrig | ✅ umgesetzt – opt-in `wand_gleichmaessig` |
| T6 | Fehlerbudget | Konzept 4× besser als Ziel; Abbe θ·Abstand | 2.75 Topic 4, 2.76 L10 | S | Präzisionsteile (Stiftplotter) | niedrig | ✅ umgesetzt |
| – | Überhang, Brücke | **nicht auf OCW.** Vorschlag: Brücke als Balken unter Eigengewicht mit E nahe Tg; Grenzwerte mit Testkörper am MK4 kalibrieren | extern | G, DR | heute Sichtkontrolle | – | ◐ teilweise – T-UB: Messwerte aus messung.json als info |

### 3.6 Schwingung, Stoß, Akustik
| ID | Prüfung | Formel | Quelle | Eingaben | Kriterium | Prio | Umsetzung |
|---|---|---|---|---|---|---|---|
| S1 | Eigenfrequenz aus statischer Durchbiegung | f₁ ≈ 15,8/√(δ_st in mm) Hz – FEM-Lastfall 1 g, **keine Modalanalyse** | 2.003SC L21, Rez. 10 (OCW) | FEM, Masse, S (Zusatzmassen) | → S2 | hoch | ✅ umgesetzt – FEM `schwerkraft`, kragarm, Einmassen-Untergrenze |
| S2 | Resonanzabstand | quasistatisch wenn f_Last ≪ f₁; Isolation ab f/f₁ > √2 | 16.20 Unit 19, 2.003SC L21 (OCW) | **S: Anregung neu** | f₁ > 2–3·f_Anregung | hoch | ✅ umgesetzt |
| S3 | Kragarm-Frequenz | f = (1,875²/2π)·√(EI/(ρAL⁴)) | 2.002 L2, 2.003SC L27 | G, M | Gegenprobe zu S1 (±30 %) | mittel | ✅ umgesetzt |
| S4 | Fallstoß | F_max ≈ mg(1 + √(1 + 2h/δ_st)) ≈ √(2mghk) | **extern** (16.20 Unit 19 qualitativ) | k aus FEM, m, S (Fallhöhe) | statischer Ersatzlastfall, S ≥ 1,5 (σ_Z!) | mittel | ✅ umgesetzt |
| S5 | Helmholtz Vorkammer/Gitter | f_H = (c/2π)·√(S/(V·l_eff)), l_eff = l + 1,6a, S = Nπa²; gültig bei Maßen < 0,1λ | 6.551J L7/L10 (OCW) | G (V, Löcher, Wanddicke) | Sprache: f_H > 4 kHz | hoch (Lautsprecher) | ✅ umgesetzt – Löcher auto aus STEP |
| S6 | Luftpolster geschlossene Box | C = V/(ρc²); f_c ≈ f_s√(1 + V_as/V) | 6.551J L7 (OCW); Thiele-Small **extern** | G, Datenblatt | f_c/f_s < 1,5 | mittel | ✅ umgesetzt – braucht f_s/V_as |
| S7 | Stehwellen | f₁ = c/(2L_innen) | 2.003SC L27, 6.551J L15 | G | im Sprachband → Dämmung | mittel | ✅ umgesetzt |
| S8 | Gitterloch vs. Grenzschicht | δ_v = √(μ/(ρω)) ≈ 0,11 mm bei 200 Hz | 6.551J L7 (OCW) | G | a < 10δ_v → Gitter dämpft | niedrig | ✅ umgesetzt |

### 3.7 Elektronik (Python-Schritt nach dem DRC, aus Netzliste + pcbnew + Lagenaufbau)
| ID | Prüfung | Formel/Regel | Quelle | Eingaben | Kriterium | Prio | Umsetzung |
|---|---|---|---|---|---|---|---|
| E1 | Logikpegel | NM_H = V_OH − V_IH, NM_L = V_IL − V_OL | 6.002 L4, 6.012 L14 (OCW) | K, **Bauteil-DB** | NM ≥ 0,4 V; Eingang ≤ V_DD + 0,3 V | hoch | ✅ umgesetzt |
| E2 | Spannungsfall | R = ρl/(wt), ~0,5 mΩ/□ bei 35 µm | 6.622 L12 (OCW) | K, **Strom je Netz neu** | ΔV ≤ 2–3 % | hoch | ✅ umgesetzt |
| E3 | Leiterbahnerwärmung | P = I²R; Grenze IPC-2152 (**extern**) | 6.622 L12/16 | K | oder an fem_waerme übergeben | hoch | ✅ umgesetzt |
| E4 | Sperrschicht LDO/Lader | P = (V_in − V_out)·I + V_in·I_q; T_j = T_a + P·RθJA | 6.622 L16, 6.111 L16 (OCW) | K, DB (RθJA), T_a aus Elmer | T_j ≤ T_j,max − 20 K | hoch | ✅ umgesetzt |
| E5 | Widerstand/LED | P = I²R; R_LED = (V_s − V_f)/I | 6.002 L22, 6.012 L8 (OCW) | K (Footprint → P_nenn), DB (V_f) | P ≤ 0,5·P_nenn; V_s − V_f ≥ 0,3 V | hoch | ✅ umgesetzt |
| E6 | Akkulaufzeit | t = C/I_mittel, I_mittel = ΣI_i·D_i; P = αCV²f | 6.002 L22 (OCW) | K (Dauerverbraucher), DB/S (Modi) | ≥ Projektziel | hoch | ◐ teilweise – Ruhestrom-Untergrenze, Modi aus soll |
| E7 | Spannungsteiler | I = V/(R1 + R2); R_th = R1‖R2 | 6.002 L3/L12 (OCW) | K | I ≤ 1–5 µA bei Akku; R_th ≤ ADC-Vorgabe | hoch | ✅ umgesetzt |
| E8 | Brownout bei Funkspitze | V = V0 − I·R_int; ΔV = IΔt/C | 10.626 L3, 6.101 (OCW) | K, DB (I_peak, R_int) | V_min ≥ Brownout + Reserve | hoch | ✅ umgesetzt |
| E9 | Entkopplung | C ≥ ΔIΔt/ΔV; L_loop ≈ μ0·Δ·l/w; f = 1/(2π√(LC)) | 6.622 L38, 6.101 (OCW) | K | ≥ 1 C je Power-Pin, ≤ 2–3 mm, L_loop ≤ 2–5 nH | hoch | ✅ umgesetzt |
| E10 | Hot Loop Schaltregler | Masche klein, SW-Fläche klein | 6.622 L38 (OCW) | K, DB (Pin-Rollen) | Eingangs-C ≤ 3 mm | hoch* | ◐ teilweise – SW-Fläche nur info |
| E11 | I2C-Pull-up | t_r ≈ 0,85·RC; R_min = (V_DD − V_OL)/I_OL; C_Leiterbahn ≈ εwl/h | 6.002 L13 (OCW); Grenzen NXP UM10204 (**extern**) | K | t_r ≤ 1000/300 ns | hoch | ✅ umgesetzt |
| E12 | RC/LC-Grenzfrequenz | f_c = 1/(2πRC); Q = ω0L/R | 6.002 L18, 6.101 (OCW) | K | Anti-Alias, Audio-Hochpass ≤ 20 Hz, Q ≤ 1 | mittel | ◐ teilweise – nur RC, kein LC-Q/Audio-Hochpass |
| E13 | Lange Leitung | l > λ/8 → Z0 nötig | 6.013 L11 (OCW) | K, Frequenz | sonst Serien-R | mittel | ◐ teilweise – ohne Flankensteilheit |
| E14 | Z0 Antenne/USB | Γ = (Z − Z0)/(Z + Z0); Microstrip Hammerstad (**extern**) | 6.013 L11–14, 6.776 L3–5 | K (Lagenaufbau) | ±10 % | mittel* | ◐ teilweise – nur Microstrip, kein CPWG |
| E15 | Antennen-Keepout | Masse unter Antenne löscht Abstrahlung; λ/4 868 MHz ≈ 8,6 cm | 6.013 L18/19 (OCW) | K, Gehäuse-3D, DB | 0 Kupfer im Keepout, Metall ≥ λ/10 | hoch* | ◐ teilweise – Platine ja, Metall im Gehäuse nein |
| E16 | Link-Budget | log-distance PL = PL(1 m) + 10·n·log10(r), n je Umgebung (frei 2 … dorf 3,5 … stadt 4); + Hindernisse, Kabel, Antennenfehler | 6.013 L17 (OCW), n: Rappaport Tab. 4.2 (**extern**), kalibriert Bodenklima 15.11.2026 | S, K (Funk erkannt) | Reserve ≥ 10 dB; Funk im Entwurf ohne soll `funk` = **fehler** | hoch* | ✅ umgesetzt (15.11.2026: vorher nur Freiraum + still übersprungen, im Feld 30 dB zu optimistisch) |
| E17 | Rückstrompfad | L ≈ μ0·Δ·l/w | 6.622 L38 (OCW) | K | 100 % über durchgehender Fläche | mittel | ✅ umgesetzt |
| E18 | Übersprechen | C = εwl/d; Serien-R bremst Flanke | 6.002 L13, 6.622 L38 (OCW) | K | Serien-R 22–33 Ω an schnellen Ausgängen | mittel | ✅ umgesetzt |
| E19 | EMI-Filter | f0 ≤ f_sw/10 | 6.622 L28–30 (OCW) | K, DB | Dämpfung ausreichend | mittel | ◐ teilweise – Ferrite ohne L übersprungen |
| E20 | Verstärker vs. Lautsprecher | BTL P ≈ V_DD²/(2R_L), I_peak ≈ V_DD/R_L (passend zu P; korrigiert nach Gegenprüfung) | 6.002 L22, 6.101 (OCW) | K, DB | R_L ≥ R_L,min; I_peak → E2/E8 | mittel | ✅ umgesetzt |
| E21 | LiPo-Ladestrom | I_chg ≤ 0,5–1 C; P_Lader → E4 | C-Rate **extern**, Wärme 6.622 L16 | K (R_PROG), S (mAh) | I ≤ 1 C | hoch | ✅ umgesetzt |
| E22 | Qi-Resonanz | f0 = 1/(2π√(LC)), Skintiefe ≈ 0,19 mm bei 150 kHz | 6.622 L9/L12, 6.013 L14 (OCW) | K, DB | f0 im Qi-Band ±5 % | niedrig | ✅ umgesetzt |
| E23–E25 | Gate-Treiber, Zener-Regler, OpAmp-Stabilität | P = Q_g·V·f; R_L,min; Phasenreserve ≥ 45° | 6.622 L38, 6.101, 6.302 | DB | – | niedrig | ◐ teilweise – Q_g/Zener/OpAmp ohne DB-Daten |

\* hoch, wenn Wandler bzw. eigene Funk-Zuleitung vorhanden.

### 3.8 Ergänzungen außerhalb von OCW (seit 15.–19.11.2026)

| ID | Prüfung | Formel/Regel | Quelle (Status) | Eingaben | Kriterium | Prio | Umsetzung |
|---|---|---|---|---|---|---|---|
| FW1 | Firmware-Konstanten gegen Prüfannahmen | Wert in Datei = soll (mit `faktor`/`kehrwert`) | eigen | `_projekt.firmware` | Gleichheit | hoch | ✅ umgesetzt – `mb2/pruefungen/firmware.py` |
| K1 | Stückkosten | Σ Menge × Preis ≤ Ziel | eigen | `ziele`, `kosten.json` | Lücken nie als 0 € | mittel | ✅ umgesetzt – `kpi.py` |
| K2 | Arbeitszeit je Stück | Σ Schritte ≤ Ziel | eigen | `ziele`, `kosten.json` | Lücken nie als 0 h | mittel | ✅ umgesetzt – `kpi.py` |
| K3 | Termin | liegt in der Zukunft | eigen | `ziele.termin` | – | niedrig | ✅ umgesetzt – `kpi.py` |
| K4 | Priorität | eindeutige Reihenfolge Qualität/Kosten/Zeit | eigen | `ziele.prioritaet` | – | niedrig | ✅ umgesetzt – `kpi.py` |
| MK1 | Unsicherheitsbudget Messkette | GUM: u_c, U = k·u_c (Modellgleichung, numerische Sensitivitäten) | JCGM 100 (GUM) | `messkette` | U ≤ ziel_U | hoch | ✅ umgesetzt – `messkette.py`, `sensorprofile/rtd.py` |
| MK2 | Rauschbegrenzte Auflösung | max(q, 6,6 σ) / Steigung | eigen | `messkette` | ≤ ziel_aufloesung | mittel | ✅ umgesetzt |
| MK3 | ADC-Aussteuerung | G·V_in/V_ref ≤ 1 − Reserve | Datenblatt ADC | `messkette` | – | hoch | ✅ umgesetzt |
| MK4 | Bauteilgrenzen der Messschaltung (REF, IDAC, PGA, SELBST) | Datenblattgrenzen als Daten | Datenblatt (z. B. TI SBAS501D) | `bauteile.adc` | – | hoch | ✅ umgesetzt |
| MK5 | Zeitbudget Messrate | Mittelung × (Wandlung + Einschwingen) ≤ 1/Rate | Datenblatt ADC | `messkette` | – | mittel | ✅ umgesetzt |
| X1 | Prüfmittel gegen Toleranz | Toleranz / U_ref ≥ 4 (Faustregel) | Faustregel (TUR 4:1) | Anforderungen, `messung.json` | – | hoch | ✅ umgesetzt – `widerspruch.py` |
| X2 | Messbereich gegen Einsatz | Einsatz ⊂ Messbereich, nicht > 2× breiter | eigen | Anforderungen, Einsatz | – | hoch | ✅ umgesetzt |
| X3 | Budget gegen Toleranz | ziel_U < Toleranz | ILAC-G8-Logik | `messkette`, Anforderungen | – | hoch | ✅ umgesetzt |
| X4 | Ziele ohne Quelle | jede Zahl mit `_herkunft` | eigen | `ziele` | – | mittel | ✅ umgesetzt |
| X5 | Aufwand gegen Termin | h × Stück ≤ h/Woche × Wochen | eigen | `ziele` | – | mittel | ✅ umgesetzt |
| X6 | Priorität gegen Fehlerfolge | Fehlerfolge hoch → Qualität zuerst | eigen | `ziele` | – | mittel | ✅ umgesetzt |
| X7 | Bus gegen Leitungslänge | SPI ≤ 0,3 m, I²C ≤ 1 m (Faustregel) | Faustregel | `schnittstelle` | – | mittel | ✅ umgesetzt |
| X8 | Kalibrierung im Aufwand | Kalibrierschritt in `kosten.json` | eigen | `messkette`, `kosten.json` | – | niedrig | ✅ umgesetzt |
| X9 | Stückzahl gegen Seriennachweis | Stückzahl 1 → kein Seriennachweis | eigen | `ziele`, Anforderungen | – | mittel | ✅ umgesetzt |
| X10 | Erkennung gegen Messgrößen (Beobachtbarkeit) | eine Variante aus `braucht_eine_von` ⊆ `_projekt.messgroessen` | eigen | Anforderung `erkennung`, `messgroessen` | sonst fehler (Fehler unsichtbar) | hoch | ✅ umgesetzt – `widerspruch.py` |
| FL1 | Strömungsform | Re = ρ v d_h / μ; < 2000 laminar | Lehrbuch Rohrströmung | `stroemung` (Medium mit Herkunft, Kanäle) | turbulent → FL2 gilt nicht | hoch | ✅ umgesetzt – `stroemung.py` |
| FL2 | Druckverlust | laminar Hagen-Poiseuille (rund/Rechteck); turbulent Darcy-Weisbach mit Blasius (glatt) bzw. Colebrook (Rauigkeit); + Σζ ρv²/2 | Lehrbuch | `stroemung` | ≤ `dp_max_Pa`; Übergang 2000–4000 ohne Formel | hoch | ✅ umgesetzt |
| FL3 | Einlauflänge vor dem Sensor | L_e ≈ 0,06 Re d_h | Lehrbuch (White) | `einlauf_vor_sensor_mm` | gerade Strecke ≥ L_e | mittel | ✅ umgesetzt |
| FL4 | Messbarkeit Differenzdruck | Δp(Q_min) ≥ 10 × Sensorauflösung | eigen | `dp_sensor_aufloesung_Pa` | sonst warnung (Prinzip ungeeignet) | mittel | ✅ umgesetzt |
| FL5 | CFD Code-Verifikation | generierter Kanal gegen Hagen-Poiseuille | eigen (V&V 40: Code) | `cfd/<fall>.json` mit `geometrie.kanal` | ≤ 5 % ok, ≤ 15 % warnung | hoch | ✅ umgesetzt – `stroemung.py`, `mb2/cfd.py` |
| FL6 | CFD Massenbilanz | \|Q_aus − Q_ein\| / Q_ein | eigen | CFD-Ergebnis (OpenFOAM) | ≤ 1 % | mittel | ✅ umgesetzt |
| FL7 | CFD Netzstudie | Δp der zwei feinsten Netze | eigen (V&V 40: Lösung) | `netzstudie` | ≤ 2 % | hoch | ✅ umgesetzt |
| FL8 | Kanal fertigbar | kleinstes Kanalmaß ≥ Mindestmaß des Verfahrens | eigen | Kanal `teil`, `fertigung.min_kanal_mm` / `fdm_min_kanal_mm` | < 1,5-fach warnung | hoch | ✅ umgesetzt |
| CH1 | Werkstoffverträglichkeit | jede Paarung Werkstoff × Medium belegt (A–D) | Herstellertabellen | `_projekt.stoff` | A ok, B warnung, C/D/fehlt fehler | hoch | ✅ umgesetzt – `stoff.py` |
| CH2 | Mischung quer zum Kanal | Pe = v w/D, L_mix ≈ v w²/D | Lehrbuch | `stoff.mischung` | L ≥ L_mix, wenn gemischt werden muss | mittel | ✅ umgesetzt |
| CH3 | Ansprechzeit Diffusion | t = δ²/(2D) | Einstein-Smoluchowski | `stoff.ansprechen` | ≤ `ansprechzeit_max_s` | mittel | ✅ umgesetzt |
| CH4 | Drift durch Belag/Adsorption | Drift × Kalibrierintervall ≤ Toleranz | eigen | `stoff.drift` (gemessen) | sonst höchstens warnung | mittel | ✅ umgesetzt |
| FW2 | Hosttest der Firmware-Rechenlogik | Testprogramm am PC, je Fall `MB2 {json}`; Ergebnis an den Quell-Hash gebunden | eigen | `firmware.hosttest`, Befehl `firmware_test` | alle Fälle bestanden, nicht veraltet | hoch | ✅ umgesetzt – `firmware.py`, `firmware_test.py` |
| FW3 | Fehlerinjektion in Software | je Fehler aus `erkennung` ein bestandener Fall `fehlerinjektion` + ein Fehlalarm-Fall | eigen | Hosttest, Anforderungen | vollständig | hoch | ✅ umgesetzt |
| DS1 | Datenspeicher | Satz × 3600/Intervall × Aufbewahrung ≤ Speicher × (1 − Reserve) | eigen | `_projekt.daten` | – | mittel | ✅ umgesetzt – `daten.py` |
| DS2 | Datenübertragung | Nutzdaten/h ≤ Pakete × Nutzlast; Luftzeit ≤ Duty-Cycle bzw. Bits/Rate ≤ Nutzanteil | eigen | `daten.uebertragung` | – | mittel | ✅ umgesetzt |
| DS3 | Flash-Verschleiß | Schreibvorgänge × max(Block, Puffer) × Lebensdauer / Speicher ≤ 0,5 × Zyklen | eigen | `daten`, `lebensdauer_h` | – | mittel | ✅ umgesetzt |


## 4 Was mb2 dafür neu braucht

> **Stand 10.11.2026 eingebaut:** Kennwerte in `mb2/kennwerte.py` (statt material.py; Lücken mit Grund in `OFFEN`: Kriech-SLS, U, Kriechmodul PLA/PETG, S_e PETG, K_IC ASA), Bauteil-DB `mb2/bauteile.json`, soll-/Lastfall-Felder in `mb2/pruefungen/FELDER.md`, Kalibrierkörper `projects/kalibrierkoerper/` (noch nicht gedruckt/gemessen), Druckrichtung aus `druck_drehung` (cad_build) oder soll `druckrichtung`.

**material.py** (je PLA/PETG/ASA, Quelle Datenblatt/Literatur, nicht OCW):
ε_zul (XY/Z), α (Wärmeausdehnung), c_p, E_Z und G, Schubfestigkeit, Kriechen (E_∞/E₀, τ oder Kriechmodul 1000 h, Aktivierungsenergie U), Dauerfestigkeit S_e, Reibwert μ, K_IC, Emissionsgrad ε, Streuung je Richtung.

**soll.json** (je Teil/Projekt):
Einsatztemperatur (max, Mittel, Tagesgang), außen ja/nein + Farbe, Dauerlast mit Dauer, Schraubenliste (Größe, Vorspannung), Insert-Maße, Toleranzketten, Zyklenzahl, Anregungsfrequenz, Zusatzmassen, Fallhöhe, Ausnahmen (Filmscharnier).

**Bauteil-Kennwerttabelle** (je LCSC-/Teilenummer, für E-Prüfungen):
V_IH/V_IL/V_OH/V_OL, 5-V-Toleranz, RθJA, V_f, I_q, Spitzen-/Modusströme, Pin-Rollen (VIN/SW/GND), Antennen-Keepout, R_L,min. Dazu Strom je Netz als Netzklassen- oder Symbolfeld.

**MK4-Kalibrierkörper** (einmal drucken und messen):
Maßversatz μ und Streuung σ je Merkmalart (Bohrung, Außenmaß, Z), Schwindung je Material, Überhang-/Brückengrenzen, Verzug ASA.

**Druckrichtung je Teil** an alle Festigkeitsprüfungen durchreichen (aus `cad_plate`).

## 5 Nicht auf OCW (andere Quelle nötig)
FDM-Überhang/Brücke · Einschmelzmutter-Bohrmaße · Tsai-Hill wörtlich · Lamé (vermutet 2.002 L5) · Kennwerte PLA/PETG/ASA (Kriechen, α, ε_zul, μ, Wöhler) · Penalty-Kontakt · GCI nach Roache · Williams-Kerbsingularität · Fallstoß-Formel · Thiele-Small · Enclosure-Konvektion (Lienhard-Lehrbuch, frei) · IPC-2152 · Microstrip Hammerstad/IPC-2141 · I2C-Grenzen NXP UM10204 · LiPo-C-Rate/CC-CV · ESD/TVS · Qi-Kopplungsfaktor.

Unsicher bzw. nicht geöffnet: 2.75/2.081J/2.875-Skripte teilweise, 16.20-Units teilweise, 3.054 (Handschrift), 2.008 S04 (Weiterleitungsschleife), 6.013-Lehrbuch, 6.334 Ch13 (Scan), 2.003SC-Balkenkonstanten (nur Video).
