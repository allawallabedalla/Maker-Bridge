"""Zusaetzliche Werkstoff-Kennwerte fuer die Katalog-Pruefungen (OCW_PRUEFKATALOG.md, Abschnitt 4).

Ergaenzt mb2/material.py, aendert es nicht. Werte fuer gedruckte Teile (FDM, 0,4-mm-Duese). Jeder Wert hat eine
Quelle; None = noch unbekannt -> die Pruefung meldet 'uebersprungen'. Richtung: 'xy' = in der Schichtebene,
'z' = quer zu den Schichten.

Zugriff nur ueber ``wert(material, feld)`` (Zahl oder None), ``quelle(material, feld)`` und
``vorlaeufig(material, feld)``.

Herkunft steht am Anfang jeder Quelle in eckigen Klammern:
  [gedruckt]      Messwert an gedruckten Probekoerpern (Datenblatt oder Studie)
  [voll, abgem.]  nur Spritzguss-/Vollmaterialwert gefunden, fuer gedruckte Teile konservativ abgemindert
  [abgeleitet]    aus anderen belegten Werten per Formel gerechnet (Formel in der Quelle)
  [vorlaeufig]    Richtwert, am MK4 zu kalibrieren (projects/kalibrierkoerper) - siehe VORLAEUFIG

Richtung der Konservativitaet (wenn eine Spanne belegt ist):
  alpha, mu, Streuung, Schwindung -> eher oberes Ende (Spannungen, Selbsthemmung, Sicherheit groesser)
  eps_zul, E_z, G, Festigkeiten, S_e, K_IC, Kriechmodul, c_p, Emission -> eher unteres Ende

Haupt-Quellen (Kurzform in den Eintraegen):
  PrusaPETG   Prusament PETG TDS (Prusa Polymers, Zugversuch ISO 527 gedruckt: horizontal / vertikal Z):
              Streckgrenze 47+-2 / 30+-5 MPa, E 1,5+-0,1 / 1,4+-0,1 GPa, Streckdehnung 5,1+-0,1 / 2,5+-0,5 %
  PrusaPLA    Prusament PLA TDS v1.1 (2022): Streckgrenze 51+-3 MPa, E 2,3+-0,1 GPa, Streckdehnung 2,9+-0,3 %
  PolyPLA     PolyLite PLA TDS V5.4 (Polymaker): Zug XY 52,3 / Z 40,5 MPa, Bruchdehnung XY 6,3 / Z 1,8 %
  PolyPETG    PolyLite PETG TDS V5.4: Bruchdehnung XY 8,4 / Z 3,3 %, Zug XY 50,8 / Z 42,8 MPa
  PolyASA     PolyLite ASA TDS V4.1 (2019): E XY 2379+-157 MPa, Zug XY 43,8 MPa, Bruchdehnung XY 6,7 %,
              Zug Z 27,4 MPa (100 % Fuellung, ASTM D638)
  FBG2024     Materials 17 (2024) 4668, CTE gedruckter Teile per Faser-Bragg-Gitter, 25-50 C:
              PLA 96+-5 (0 Grad) / 99+-5 (90 Grad), ABS 86 / 89 e-6/K
  OSTI1341825 Emissivity Measurements of Additively Manufactured Materials (OSTI 1341825):
              Gier-Dunkle-Reflektometer, PLA/ABS ca. 0,92 (rotes ABS 0,917, graues PLA 0,916)
  Bayer       Bayer MaterialScience, Snap-Fit Joints for Plastics, Tab. 4-1: zul. Dehnung einmaliges Fuegen
              23 C, Lustran ABS 1,8 %; haeufiges Loesen 0,6 x
"""

FELDER = {
    # feld: (einheit, beschreibung)
    'eps_zul_xy': ('-', 'zulaessige Dehnung kurzzeitig, in der Schichtebene (Schnapper, Biegestege)'),
    'eps_zul_z': ('-', 'zulaessige Dehnung quer zu den Schichten'),
    'eps_dauer': ('-', 'zulaessige Dehnung unter Dauerlast (Kriechgrenze)'),
    'alpha_1_K': ('1/K', 'linearer Waermeausdehnungskoeffizient'),
    'cp_J_kgK': ('J/(kg K)', 'spezifische Waermekapazitaet'),
    'E_z_MPa': ('MPa', 'E-Modul quer zu den Schichten'),
    'G_MPa': ('MPa', 'Schubmodul'),
    'schub_xy_MPa': ('MPa', 'Schubfestigkeit in der Schichtebene'),
    'schub_z_MPa': ('MPa', 'Schubfestigkeit zwischen den Schichten'),
    'druck_MPa': ('MPa', 'Druckfestigkeit (Flaechenpressung)'),
    'kriech_E_inf_zu_E0': ('-', 'Standard Linear Solid: E_inf/E_0 bei 23 C'),
    'kriech_tau_h': ('h', 'Standard Linear Solid: Relaxationszeit bei 23 C'),
    'kriechmodul_1000h_MPa': ('MPa', 'Kriechmodul nach 1000 h bei 23 C, niedrige Last'),
    'aktivierung_U_kJ_mol': ('kJ/mol', 'Arrhenius-Aktivierungsenergie unterhalb Tg'),
    'S_e_MPa': ('MPa', 'Wechselfestigkeit bei 1e6 Zyklen'),
    'mu': ('-', 'Reibwert Kunststoff/Kunststoff bzw. /Stahl'),
    'K_IC_MPa_sqrtm': ('MPa*sqrt(m)', 'Bruchzaehigkeit'),
    'emission': ('-', 'Emissionsgrad (Waermestrahlung)'),
    'schwindung': ('-', 'Schwindung im FDM-Druck (Mass-Vorhalt), am MK4 zu kalibrieren'),
    'streuung_xy': ('-', 'relative Streuung der Festigkeit in XY (1 sigma)'),
    'streuung_z': ('-', 'relative Streuung der Festigkeit in Z (1 sigma)'),
}

# Gemeinsame Quellen-Texte (gleiche Herleitung fuer alle drei Druckstoffe)
_Q_SCHUB = ('[abgeleitet] Tresca tau = sigma/2 aus material.py festigkeit_{r}_MPa (konservativer als '
            'von Mises sigma/sqrt(3)); keine zugaengliche Messung fuer {m} gefunden')
_Q_EMISSION = ('[gedruckt] OSTI 1341825: gedruckte Kunststoffe ca. 0,92 (Reflektometer); unteres Ende der '
               'Kunststoff-Spanne 0,90-0,97 gewaehlt (weniger Abstrahlung = waermer = konservativ)')
_Q_STREU_XY = ('[gedruckt] Datenblatt-Streuung XY 2-6 % (PrusaPLA 51+-3, PrusaPETG 47+-2, PolyASA 43,8+-0,8 MPa) '
               'plus Druck-zu-Druck-Streuung: 8 % gewaehlt (ergibt im Katalog M26 k_e = 0,81 bei 99 %)')
_Q_STREU_Z = ('[gedruckt] PrusaPETG Z 30+-5 MPa = 17 %; Z-Haftung streut am staerksten (Temperatur, Luefter, '
              'Schichtzeit); 17 % fuer alle Druckstoffe angesetzt')
_Q_EPS_DAUER = ('[voll, abgem.] Faustregel amorphe Thermoplaste: Dauerdehnung (Wochen) <= 1 % (Eng-Tips, '
                'Konstrukteurspraxis); ISO 899-1 Kriechmodul bei <= 0,5 % Dehnung (Luran S 797 S). Fuer '
                'gedruckte Teile (Poren, Schichtfugen) 0,5 % angesetzt')

# Werte. Format: feld: (wert, 'quelle')
KENNWERTE = {
    'PLA': {
        'eps_zul_xy': (0.014, '[gedruckt] 0,5 x Streckdehnung XY 2,9 % (PrusaPLA); Bayer: einmaliges Fuegen bis '
                              '~0,7 x, gedruckt wegen Kerben/Poren halbiert'),
        'eps_zul_z': (0.009, '[gedruckt] 0,5 x Bruchdehnung Z 1,8 % (PolyPLA); Z bricht sproede ohne Fliessen'),
        'eps_dauer': (0.005, _Q_EPS_DAUER + '; PLA kriecht ab ~40 C stark (Tg 57 C) - D5 verschiebt'),
        'alpha_1_K': (97e-6, '[gedruckt] FBG2024: PLA gedruckt 96-99e-6/K (25-50 C); Literatur-Vollmaterial '
                             'oft 40-80e-6/K, gedruckter Messwert ist hoeher -> oberes Ende genommen'),
        'cp_J_kgK': (1200.0, '[voll, abgem.] Pyda/Bopp/Wunderlich, J. Chem. Thermodyn. 36 (2004) 731: festes PLA '
                             'bei 25 C ~1,2 J/(g K) (Zahl aus Kurve/Tarasov-Fit, Tabelle nicht eingesehen); '
                             'MakeItFrom nennt 1800 - niedriger Wert ist fuer Aufheizen konservativ'),
        'E_z_MPa': (2100.0, '[abgeleitet] PrusaPLA E 2,3 GPa x Z/XY-Verhaeltnis 0,93 aus PrusaPETG (1,4/1,5); '
                            'konservativ, passend zu material.py E 2300'),
        'G_MPa': (845.0, '[abgeleitet] G = E/(2(1+nu)) = 845,6 mit E 2300 MPa (PrusaPLA) und nu 0,36 (material.py)'),
        'schub_xy_MPa': (25.0, _Q_SCHUB.format(r='xy', m='PLA')),
        'schub_z_MPa': (15.0, _Q_SCHUB.format(r='z', m='PLA')),
        'druck_MPa': (45.0, '[gedruckt, abgem.] PLA 100 % Fuellung 81 MPa (J. Test. Eval., ASTM, 2026); gleiche '
                            'Studie PETG 52 MPa gegen ISO-604-Messung 30 MPa -> Faktor 0,58 auch auf PLA'),
        'kriech_E_inf_zu_E0': None,
        'kriech_tau_h': None,
        'kriechmodul_1000h_MPa': None,
        'aktivierung_U_kJ_mol': None,
        'S_e_MPa': (5.0, '[gedruckt] Azadi/Dadashi, Data in Brief 2022 (Umlaufbiegung R=-1, gedruckt liegend): '
                         '5 MPa -> 0,7-1,5e6 Zyklen bei guten Parametern, mit 0,4-mm-Duese schon darunter Bruch; '
                         'Gomez-Gras 2018 (Mater. Des. 140) nennt 35,8 MPa fuer optimierte Proben - unteres '
                         'Ende gewaehlt'),
        'mu': (0.5, '[gedruckt] PLA/Stahl gleitend 0,49 (Stift-Scheibe, C45); PLA/PLA Haftreibung 0,12-0,38 '
                    '(Schraeg-Ebene, doi 10.1177/1464420720978997); Uebersicht SERBIATRIB 2025: PLA 0,3-0,6; '
                    'oberer Wert (Selbsthemmung/Verkeilen konservativ)'),
        'K_IC_MPa_sqrtm': (2.5, '[gedruckt, abgem.] Ahmed/Susmel 2018 (3D-printed PLA, TCD): K_IC 3,7 (C(T) '
                                '30 mm, ASTM D5045), K_c 3,5 (4 mm); x 0,7 fuer Riss in der Schichtfuge'),
        'emission': (0.90, _Q_EMISSION),
        'schwindung': (0.003, '[vorlaeufig] Skalierung PLA/PETG ueblich 99,6-99,8 % (Praxis-Kalibrierung); '
                              'am MK4 mit projects/kalibrierkoerper messen'),
        'streuung_xy': (0.08, _Q_STREU_XY),
        'streuung_z': (0.17, _Q_STREU_Z),
    },
    'PETG': {
        'eps_zul_xy': (0.020, '[gedruckt] Streckdehnung horizontal 5,1 % (PrusaPETG); 0,5 x waeren 2,55 %, auf '
                              '2,0 % begrenzt (mit E 1500 seit 19.11.2026: E x eps = 30 MPa < sigma_xy 45 MPa)'),
        'eps_zul_z': (0.012, '[gedruckt] 0,5 x Streckdehnung Z 2,5 % (PrusaPETG; PolyPETG Bruchdehnung Z 3,3 %)'),
        'eps_dauer': (0.005, _Q_EPS_DAUER),
        'alpha_1_K': (68e-6, '[voll] PETG 23-100 C ISO 11359-2 0,068 mm/(m K) (PETG-Datenblatt Oadby Plastics); '
                             'Eastar 6763 5,1e-5/K (ASTM D696) - oberer Wert; gedruckt nicht gefunden'),
        'cp_J_kgK': (1100.0, '[voll] Xometry PETG-Datenblatt 1100 J/(kg K); Eastar 6763 DSC 1,30 kJ/(kg K) erst bei '
                             '60 C, darunter kleiner -> unteres Ende'),
        'E_z_MPa': (1400.0, '[gedruckt] PrusaPETG E vertikal Z 1,4+-0,1 GPa'),
        'G_MPa': (540.0, '[abgeleitet] G = E/(2(1+nu)) mit E 1500 MPa (PrusaPETG) und nu 0,38 (material.py)'),
        'schub_xy_MPa': (22.5, _Q_SCHUB.format(r='xy', m='PETG')),
        'schub_z_MPa': (14.0, _Q_SCHUB.format(r='z', m='PETG')),
        'druck_MPa': (30.0, '[gedruckt] PETG 100 % Fuellung, ISO 604: 29,8-30,8 MPa (E3S Web Conf. 2024); '
                            'andere Studie 52 MPa - unteres Ende'),
        'kriech_E_inf_zu_E0': None,
        'kriech_tau_h': None,
        'kriechmodul_1000h_MPa': None,
        'aktivierung_U_kJ_mol': None,
        'S_e_MPa': None,
        'mu': (0.35, '[gedruckt] Co-Polyester Stift-Scheibe trocken 0,29 (Tribologie PCL/ABS/PLA/Co-Polyester); '
                     'PETG/PETG Haftreibung 0,13-0,21 (doi 10.1177/1464420720978997); +20 % fuer Haftreibung'),
        'K_IC_MPa_sqrtm': (1.8, '[gedruckt] Polymers 11 (2019) 1220, Tab. 2: PETG gedruckt 240 C 1,81, 250 C 2,09, '
                                'Granulat 2,1-2,5 MPa m^0,5 - unteres Ende'),
        'emission': (0.90, _Q_EMISSION),
        'schwindung': (0.003, '[vorlaeufig] wie PLA 99,6-99,8 % Skalierung; am MK4 kalibrieren'),
        'streuung_xy': (0.08, _Q_STREU_XY),
        'streuung_z': (0.17, _Q_STREU_Z),
    },
    'ASA': {
        'eps_zul_xy': (0.015, '[voll, abgem.] Bayer Tab. 4-1: Lustran ABS (ASA-aehnlich) 1,8 % einmaliges Fuegen; '
                              'gedruckt auf 1,5 % abgemindert; PolyASA Bruchdehnung XY 6,7 %'),
        'eps_zul_z': (0.006, '[abgeleitet] sproeder Z-Bruch: eps_B,z ~ sigma_z/E = 27,4/2379 = 1,15 % (PolyASA), '
                             'davon 0,5 x'),
        'eps_dauer': (0.005, _Q_EPS_DAUER),
        'alpha_1_K': (100e-6, '[voll] Luran S 797 S (BASF 2008) 23-80 C ISO 11359: 0,8-1,1e-4/K; Luran S 778T '
                              '80-110e-6; ABS gedruckt 86-89e-6 (FBG2024) - oberer Bereich'),
        'cp_J_kgK': (1300.0, '[voll] NETZSCH Polymer-Datenbank ASA 1,3-1,4 J/(g K); MakeItFrom 1300 - unteres Ende'),
        'E_z_MPa': (1850.0, '[abgeleitet] material.py E 2000 x Z/XY 0,93 (PrusaPETG); Z-Modul fuer ASA nirgends '
                            'veroeffentlicht gefunden'),
        'G_MPa': (740.0, '[abgeleitet] G = E/(2(1+nu)) mit E 2000 MPa und nu 0,35 (material.py; PolyASA 2379 '
                         'waere hoeher)'),
        'schub_xy_MPa': (20.0, _Q_SCHUB.format(r='xy', m='ASA')),
        'schub_z_MPa': (12.5, _Q_SCHUB.format(r='z', m='ASA')),
        'druck_MPa': (36.0, '[gedruckt] ASA 100 % Fuellung, ISO 604: 36,5-38,7 MPa (gleiche Gruppe wie PETG, '
                            'E3S/ETASR 2024) - unteres Ende'),
        'kriech_E_inf_zu_E0': None,
        'kriech_tau_h': None,
        'kriechmodul_1000h_MPa': (900.0, '[voll, abgem.] Luran S 797 S: Zug-Kriechmodul 1000 h, 23 C, <= 0,5 % '
                                         '(ISO 899-1) 1100 MPa bei E ~2300 -> Verhaeltnis 0,48 x material.py E '
                                         '2000 = 960, abgerundet 900'),
        'aktivierung_U_kJ_mol': None,
        'S_e_MPa': (4.3, '[gedruckt] Polymers 18 (2026) 302 (ASA FFF, R=0,05): Dauerfestigkeit 8 MPa = 25 % '
                         'sigma_R (Oberspannung angenommen); Goodman auf R=-1: sigma_a 3,8 / (1 - 4,2/32) = 4,4, '
                         'abgerundet 4,3'),
        'mu': (0.45, '[gedruckt] ABS (ASA-aehnlich) gedruckt gegen Stahl 0,21-0,45 (SERBIATRIB 2025), '
                     'Stift-Scheibe 0,4 - oberes Ende'),
        'K_IC_MPa_sqrtm': None,
        'emission': (0.90, _Q_EMISSION + '; ABS rot 0,917 gemessen, ASA chemisch verwandt'),
        'schwindung': (0.006, '[vorlaeufig] ASA/ABS Skalierung 98,5-99,5 % (Praxis), Nutzerbericht 100,6 % XY; '
                              'am MK4 kalibrieren'),
        'streuung_xy': (0.08, _Q_STREU_XY),
        'streuung_z': (0.17, _Q_STREU_Z),
    },
    'FR4': {'alpha_1_K': (15e-6, 'FR4 in-plane typ. 14-17e-6/K (Datenblaetter Isola/Shengyi)'),
            'emission': (0.9, 'Loetstopplack, typ. 0,9')},
}

# Kennwerte, die am MK4 kalibriert werden muessen (Ergebnis dann nur 'vorlaeufig' bzw. Hinweis ausgeben)
VORLAEUFIG = {(m, 'schwindung') for m in ('PLA', 'PETG', 'ASA')}

# Warum None (fuer Berichte): Feld -> Grund
OFFEN = {
    'kriech_E_inf_zu_E0': 'kein belastbarer SLS-Fit bei 23 C fuer gedruckte Teile gefunden (Studien nur 3 h bzw. '
                          'erhoehte Temperatur); ein Fit aus einem 1000-h-Wert waere fuer laengere Zeiten nicht '
                          'konservativ',
    'kriech_tau_h': 'wie kriech_E_inf_zu_E0',
    'kriechmodul_1000h_MPa': 'PLA/PETG: kein zugaenglicher 1000-h-Kriechmodul (Eastman/NatureWorks nicht '
                             'oeffentlich); nur ASA aus Luran-S-Datenblatt',
    'aktivierung_U_kJ_mol': 'keine belastbare Aktivierungsenergie unterhalb Tg fuer PLA/PETG/ASA gefunden',
    'S_e_MPa': 'PETG: S-N-Daten (Martins 2024, R=0,2) nicht zugaenglich',
    'K_IC_MPa_sqrtm': 'ASA: keine K_IC-Messung (gedruckt oder Vollmaterial) gefunden',
}


def wert(material, feld):
    """Kennwert oder None."""
    assert feld in FELDER, feld
    v = KENNWERTE.get(material, {}).get(feld)
    return None if v is None else v[0]


def quelle(material, feld):
    v = KENNWERTE.get(material, {}).get(feld)
    return None if v is None else v[1]


def vorlaeufig(material, feld):
    """True, wenn der Wert ein Richtwert ist, der am MK4 zu kalibrieren ist."""
    return (material, feld) in VORLAEUFIG
