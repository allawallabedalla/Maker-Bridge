"""Gegentests fuer mb2/pruefungen/dauer.py (D1-D12) und toleranz.py (T1-T6).
Jede Formel hat mindestens einen Fall, der von Hand nachgerechnet ist (Zahlen im Kommentar).
Aufruf: python tests/test_pruef_dauer_toleranz.py (Arbeitsverzeichnis maker-bridge-2)."""
import json
import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _nachweis import beispielprojekt, lang  # noqa: E402,F401

from mb2 import kennwerte as kw                             # noqa: E402
from mb2 import pruefungen                                  # noqa: E402
from mb2.pruefungen import dauer, toleranz                  # noqa: E402
from mb2.pruefungen import STUFEN                           # noqa: E402

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ECHT = ['testdose', 'schnapphaken', 'stifthalter-fem', 'frag-mich-alles-gehaeuse', 'bodenklima-sondenkopf',
        'kalibrierkoerper']


def nah(a, b, tol=1e-4):
    assert abs(a - b) <= tol * max(1.0, abs(b)), (a, b)


def projekt(soll, fem=None, board=None, pruefung=None, steps=None):
    """Synthetischer Projektordner im Temp-Verzeichnis."""
    d = tempfile.mkdtemp(prefix='mb2_dt_')
    for sub in ('cad', 'fem', 'out', 'electronics'):
        os.makedirs(os.path.join(d, sub))
    json.dump(soll, open(os.path.join(d, 'cad', 'soll.json'), 'w'))
    for fall, (ein, erg) in (fem or {}).items():
        json.dump(ein, open(os.path.join(d, 'fem', fall + '.json'), 'w'))
        json.dump(erg, open(os.path.join(d, 'fem', fall + '.erg.json'), 'w'))
    if board:
        json.dump(board, open(os.path.join(d, 'electronics', 'board_info.json'), 'w'))
    for t, p in (pruefung or {}).items():
        json.dump(p, open(os.path.join(d, 'out', t + '.pruefung.json'), 'w'))
    for t, shape in (steps or {}).items():
        from build123d import export_step
        export_step(shape, os.path.join(d, 'out', t + '.step'))
    return d


def finde(liste, id, teil=None, titel=None):
    r = [e for e in liste if e['id'] == id and (teil is None or e.get('teil') == teil)
         and (titel is None or titel in e['titel'])]
    assert r, (id, teil, titel, [(e['id'], e.get('teil'), e['titel']) for e in liste])
    return r[0]


KW_PETG = {'kriech_E_inf_zu_E0': [0.5, 'Test'], 'kriech_tau_h': [1000, 'Test'], 'alpha_1_K': [70e-6, 'Test'],
           'S_e_MPa': [15, 'Test'], 'mu': [0.3, 'Test'], 'eps_dauer': [0.01, 'Test']}
ECHT_KW = kw.KENNWERTE
LEER_KW = {m: ({} if m in ('PLA', 'PETG', 'ASA') else v) for m, v in ECHT_KW.items()}


def synthetisch(f):
    """Synthetische Faelle unabhaengig von mb2/kennwerte.py (wird parallel gefuellt): Druckstoff-Kennwerte leer,
    alles Noetige kommt ueber soll._projekt.kennwerte."""
    def w():
        kw.KENNWERTE = LEER_KW
        try:
            f()
        finally:
            kw.KENNWERTE = ECHT_KW
    w.__name__ = f.__name__
    return w


# ---------------------------------------------------------------- Formeln von Hand

def test_sls():
    # r 0,5, tau 100 h, t 100 h: 0,5 + 0,5 e^-1 = 0,683940
    nah(dauer.sls_verhaeltnis(100, 0.5, 100), 0.683940)
    # J: E_inf 1000, tau_c 200 h, t 200: 1/1000 - (1/1000 - 1/2000) e^-1 = 0,000816060
    J = dauer.sls_nachgiebigkeit(200, 2000, 0.5, 100)
    nah(J, 0.000816060)
    # Korrespondenz E0/E_r(t) ist konservativ gegen E0*J(t): E_r * J <= 1
    assert dauer.sls_verhaeltnis(200, 0.5, 100) * 2000 * J <= 1.0


def test_aT():
    # WLF ab Tg (T_ref = Tg): -17,44*10/61,6 = -2,83117
    nah(dauer.log10_aT(90, 80, 100, T_ref_C=80), -2.83117)
    # Arrhenius U 100 kJ/mol, 50 C gegen 23 C: 100000/(8,314 ln10) (1/323,15 - 1/296,15) = 5223,65 * -0,00028213
    nah(dauer.log10_aT(50, 80, 100), -1.47375, 1e-3)
    assert dauer.log10_aT(50, 80, None) is None


def test_effektive_zeit():
    # ohne Tagesgang: t/a_T
    lg = dauer.log10_aT(40, 80, 100)
    nah(dauer.effektive_zeit(1000, 40, 0, 80, 100), 1000 / 10 ** lg)
    # kleine Amplitude A = 2 K: Mittel(1/a_T) ~ I0(beta A)/a_T(Tm), beta = U/(R T^2) = 0,12266/K
    # -> I0(0,2453) = 1 + x^2/4 + x^4/64 = 1,01510
    f = dauer.effektive_zeit(1.0, 40, 4.0, 80, 100) * 10 ** lg
    nah(f, 1.01510, 5e-3)


def test_boltzmann():
    J = lambda t: dauer.sls_nachgiebigkeit(t, 2000, 0.5, 100)  # noqa: E731
    # 5 MPa ab 0 h, 8 MPa ab 100 h, t 300 h: 5 J(300) + 3 J(200) = 5*0,000888435 + 3*0,000816060 = 0,006890355
    nah(dauer.boltzmann_dehnung([(0, 5), (100, 8)], 300, J), 0.006890355)
    # eine Stufe = sigma J
    nah(dauer.boltzmann_dehnung([(0, 5)], 300, J), 5 * J(300))


def test_bimetall():
    # gleiche Schichten (m = n = 1): kappa = 1,5 da dT/h = 1,5*50e-6*40/2 = 0,0015 1/mm
    nah(dauer.bimetall_kruemmung(50e-6, 40, 1, 1, 2000, 2000), 0.0015)


def test_ermuedung():
    nah(dauer.wechselfestigkeit(1e3, 50, 15), 45.0)
    nah(dauer.wechselfestigkeit(1e6, 50, 15), 15.0)
    nah(dauer.wechselfestigkeit(10 ** 4.5, 50, 15), math.sqrt(45 * 15))     # log-Mitte = geom. Mittel 25,98
    # Goodman: 1/n = 10/20 + 10/50 = 0,7 -> n = 1,428571
    nah(dauer.goodman_n(10, 10, 20, 50), 1 / 0.7)


def test_cp_cpk_kette_ausgleich():
    cp, cpk = toleranz.cp_cpk(3.1, 2.9, 2.85, 0.05)        # 0,2/0,3 = 0,6667; min(0,25; -0,05)/0,15 = -0,3333
    nah(cp, 0.666667)
    nah(cpk, -0.333333)
    # Tasche +50,4 +/-0,15 Versatz -0,15, Platine -50 +/-0,1: Nenn 0,4, mit Versatz 0,25; WC 0,25-0,25 = 0;
    # RSS 0,25 - sqrt(0,0225 + 0,01) = 0,069722
    r = toleranz.kette([(50.4, 0.15, -0.15), (-50.0, 0.1, 0.0)])
    nah(r['wc_min'] + 1, 1.0)
    nah(r['rss_min'], 0.069722)
    # Ausgleich: k 0,995, b 0,05, Reste +/-0,01 -> sigma = sqrt(6e-4/4) = 0,012247
    a = toleranz.ausgleich([(20, 19.96), (20, 19.94), (40, 39.86), (40, 39.84), (110, 109.51), (110, 109.49)])
    nah(a['k'], 0.995)
    nah(a['b'], 0.05)
    nah(a['sigma'], 0.012247)


# ---------------------------------------------------------------- synthetische Projekte

@synthetisch
def test_d1_temperaturquelle():
    fem = {'waerme': ({'koerper': [{'step': 'out/schale.step', 'material': 'PETG', 'name': 's'}],
                       'konvektion': {'h_W_m2K': 6, 'T_umgebung_C': 25}},
                      {'T_max_je_koerper_C': {'s': 60.0}, 'T_min_C': 25})}
    # FEM 60 C bei 25 C Umgebung -> 35 K Eigenerwaermung; T_max_C 40 -> 75 C; PETG Tg 80 -> 5 K -> fehler
    d = projekt({'_projekt': {'material': 'PETG', 'T_max_C': 40}, 'schale': {}}, fem=fem)
    r = finde(dauer.pruefe(d), 'D1', 'schale')
    assert r['stufe'] == 'fehler' and abs(r['wert'] - 5.0) < 1e-6, r
    # ohne FEM: 55 C -> 25 K -> warnung; 45 C -> 35 K -> ok
    for T, st in ((55, 'warnung'), (45, 'ok')):
        d = projekt({'_projekt': {'material': 'PETG', 'T_max_C': T}, 'teil': {}})
        assert finde(dauer.pruefe(d), 'D1', 'teil')['stufe'] == st


@synthetisch
def test_d1_ohne_temperatur_angenommen():
    # Befund Scheinsicherheit: frueher 'uebersprungen'. Jetzt realterme.teil_temperatur:
    # ohne Elektronik 30 C angenommen: PETG 80 - 30 = 50 K -> 'ok', aber angenommen -> gedeckelt auf 'warnung'
    d = projekt({'_projekt': {'material': 'PETG'}, 'teil': {}})
    r = finde(dauer.pruefe(d), 'D1', 'teil')
    assert r['stufe'] == 'warnung' and abs(r['wert'] - 50.0) < 1e-6 and 'ANGENOMMEN' in r['hinweis'], r
    # mit Elektronik (Datei unter electronics/) 40 C: PLA 57 - 40 = 17 K < 20 -> 'fehler' bleibt 'fehler'
    d = projekt({'_projekt': {'material': 'PLA'}, 'teil': {}})
    open(os.path.join(d, 'electronics', 'modul.step'), 'w').write('ISO-10303-21;')
    r = finde(dauer.pruefe(d), 'D1', 'teil')
    assert r['stufe'] == 'fehler' and abs(r['wert'] - 17.0) < 1e-6, r


@synthetisch
def test_d1_sonne():
    # aussen, weiss: Sonne alpha 0,25 * 1000 / 25 = 10 K -> 30 + 10 = 40 C; PETG 80 - 40 = 40 K -> ok (nichts angenommen)
    d = projekt({'_projekt': {'material': 'PETG', 'T_max_C': 30, 'aussen': True, 'farbe': 'weiss'}, 'teil': {}})
    r = finde(dauer.pruefe(d), 'D1', 'teil')
    assert r['stufe'] == 'ok' and abs(r['wert'] - 40.0) < 1e-6, r
    # Farbe unbekannt: alpha 0,95 -> 38 K -> 68 C -> 12 K -> fehler (frueher ohne Sonne 50 K = ok)
    d = projekt({'_projekt': {'material': 'PETG', 'T_max_C': 30, 'aussen': True}, 'teil': {}})
    r = finde(dauer.pruefe(d), 'D1', 'teil')
    assert r['stufe'] == 'fehler' and abs(r['wert'] - 12.0) < 1e-6, r


@synthetisch
def test_d4_ohne_kriechwerte():
    # PETG ohne Kriechkennwerte (frueher immer uebersprungen). T_Teil 60 C, Tg (material.py) 80 -> 20 K unter Tg
    # A_T = 1 + (30 - 20) * 0,04 = 1,40 -> Rest 0,5/1,40 = 0,357143; F = 300 * 0,357143 = 107,14 N
    soll = {'_projekt': {'material': 'PETG', 'T_max_C': 60, 'lebensdauer_h': 1000},
            'teil': {'schrauben': [{'d_mm': 2, 'vorspannung_N': 300, 'klemmkraft_min_N': 100}]}}
    r = finde(dauer.pruefe(projekt(soll)), 'D4', 'teil')
    assert r['stufe'] == 'warnung' and abs(r['wert'] - 107.1) < 0.05, r       # >= 100 waere ok, angenommen -> warnung
    soll['teil']['schrauben'][0]['klemmkraft_min_N'] = 110
    assert finde(dauer.pruefe(projekt(soll)), 'D4', 'teil')['stufe'] == 'fehler'
    # 23 C: 55 K unter Tg -> A_T 1 -> 0,5 * 300 = 150 N
    soll['_projekt']['T_max_C'] = 23
    nah(finde(dauer.pruefe(projekt(soll)), 'D4', 'teil')['wert'], 150.0)
    # ohne vorspannung_N: Restanteil 0,5 als warnung, nicht uebersprungen
    soll['teil']['schrauben'] = [{'d_mm': 2}]
    r = finde(dauer.pruefe(projekt(soll)), 'D4', 'teil')
    assert r['stufe'] == 'warnung' and abs(r['wert'] - 0.5) < 1e-9 and r['einheit'] == 'F/F0', r
    # gar keine Schrauben: ein projektweites uebersprungen mit Grund
    r = finde(dauer.pruefe(projekt({'_projekt': {'material': 'PETG'}, 'teil': {}})), 'D4')
    assert r['stufe'] == 'uebersprungen' and 'schrauben' in r['hinweis'], r


@synthetisch
def test_d2_d3_d7_d12_ohne_dauerlast_sichtbar():
    erg = dauer.pruefe(projekt({'_projekt': {'material': 'PETG', 'T_max_C': 30}, 'teil': {}}))
    for i in ('D2', 'D3', 'D7', 'D12'):
        r = finde(erg, i)
        assert r['stufe'] == 'uebersprungen' and 'dauerlast' in r['hinweis'], r
    # dauerlast ohne geschichte: D7 je Teil uebersprungen statt nichts
    erg = dauer.pruefe(projekt({'_projekt': {'material': 'PETG', 'T_max_C': 30},
                                'teil': {'dauerlast': {'sigma_MPa': 2}}}))
    assert finde(erg, 'D7', 'teil')['stufe'] == 'uebersprungen'


@synthetisch
def test_d2_d3_d4_kriechen():
    soll = {'_projekt': {'material': 'PETG', 'T_max_C': 23, 'lebensdauer_h': 1000, 'kennwerte': {'PETG': KW_PETG}},
            'teil': {'dauerlast': {'dauer_h': 1000, 'durchbiegung_mm': 0.2, 'durchbiegung_zul_mm': 0.3,
                                   'sigma_MPa': 12},
                     'schrauben': [{'d_mm': 3, 'vorspannung_N': 300, 'klemmkraft_min_N': 200}]}}
    erg = dauer.pruefe(projekt(soll))
    # 23 C = T_ref, keine Verschiebung: E_r/E0 = 0,5 + 0,5 e^-1 = 0,683940; delta = 0,2/0,68394 = 0,292424
    r = finde(erg, 'D3', 'teil')
    assert r['stufe'] == 'ok' and abs(r['wert'] - 0.2924) < 1e-4, r
    # D4: 300 * 0,68394 = 205,18 N >= 200
    r = finde(erg, 'D4', 'teil')
    assert r['stufe'] == 'ok' and abs(r['wert'] - 205.2) < 0.1, r
    # D2: 12/1500 = 0,008 (PETG E 1500 seit 19.11.2026) -> nach Kriechen 0,008/0,68394 = 0,011697 > 1 % -> fehler
    r = finde(erg, 'D2', 'teil')
    assert r['stufe'] == 'fehler' and abs(r['wert'] - 0.011697) < 1e-5, r
    soll['teil']['dauerlast']['durchbiegung_zul_mm'] = 0.25
    soll['teil']['schrauben'][0]['klemmkraft_min_N'] = 210
    erg = dauer.pruefe(projekt(soll))
    assert finde(erg, 'D3', 'teil')['stufe'] == 'fehler'
    assert finde(erg, 'D4', 'teil')['stufe'] == 'fehler'
    # warm (50 C) ohne U: nicht verschiebbar -> D3 hoechstens 'warnung', nie stilles ok
    soll['teil']['dauerlast']['durchbiegung_zul_mm'] = 1.0
    soll['_projekt']['T_max_C'] = 50
    assert finde(dauer.pruefe(projekt(soll)), 'D3', 'teil')['stufe'] == 'warnung'
    # mit U 100 kJ/mol: a_T(50 C) = 10^-1,47375 = 0,0336 -> t' = 29 760 h -> E_r/E0 ~ 0,5 -> delta 0,4
    soll['_projekt']['kennwerte']['PETG']['aktivierung_U_kJ_mol'] = 100
    erg = dauer.pruefe(projekt(soll))
    r = finde(erg, 'D3', 'teil')
    assert r['stufe'] == 'ok' and abs(r['wert'] - 0.4) < 1e-4, r
    assert abs(finde(erg, 'D5', 'teil')['wert'] - 10 ** -1.47375) < 1e-4


@synthetisch
def test_d6_d7():
    kwp = dict(KW_PETG, aktivierung_U_kJ_mol=100)
    soll = {'_projekt': {'material': 'PETG', 'T_max_C': 40, 'T_mittel_C': 30, 'T_tagesgang_K': 10,
                         'kennwerte': {'PETG': kwp}},
            'teil': {'dauerlast': {'dauer_h': 500, 'geschichte': [{'t_h': 0, 'sigma_MPa': 5}]}}}
    erg = dauer.pruefe(projekt(soll))
    r = finde(erg, 'D6', 'teil')
    f0 = dauer.effektive_zeit(1.0, 30, 0, 80, 100)
    assert r['stufe'] == 'info' and r['wert'] > f0          # Tagesgang beschleunigt (1/a_T konvex)
    r7 = finde(erg, 'D7', 'teil')
    tp = dauer.effektive_zeit(500, 30, 10, 80, 100)
    nah(r7['wert'], round(5 * dauer.sls_nachgiebigkeit(tp, 1500, 0.5, 1000), 5), 1e-3)   # PETG E 1500


@synthetisch
def test_d8_d9_platine():
    board = {'board_size_mm': [50.0, 30.0], 'mounting_holes': [{'pos': [3.5, 3.5], 'drill_mm': 3.2},
                                                                {'pos': [46.5, 26.5], 'drill_mm': 3.2}]}
    # aussen: false, sonst macht T_min < 5 C das Projekt zum Merkmal 'aussen' und die Sonne kaeme dazu (siehe unten)
    soll = {'_projekt': {'material': 'PETG', 'T_max_C': 60, 'T_min_C': -20, 'platine_spalt_mm': 0.2, 'aussen': False,
                         'platine_schraube_d_mm': 3.0, 'kennwerte': {'PETG': KW_PETG}},
            'schale': {'zwang': {'partner': 'FR4'}}}
    erg = dauer.pruefe(projekt(soll, board=board))
    # kalt: (70-15)e-6 * 50 * (-43) = -0,11825 -> Rest 0,2 - 0,11825 = 0,08175 < 0,1 -> fehler
    r = finde(erg, 'D8', titel='Rand, kalt')
    assert r['stufe'] == 'fehler' and abs(r['wert'] - 0.0818) < 1e-4, r
    assert finde(erg, 'D8', titel='Rand, warm')['stufe'] == 'ok'
    # Loecher: Abstand sqrt(43^2 + 23^2) = 48,765; warm 55e-6*48,765*37 = 0,09924 <= Spiel 0,2
    r = finde(erg, 'D8', titel='Befestigungsloecher, warm')
    assert r['stufe'] == 'ok' and abs(r['wert'] - 0.0992) < 1e-4, r
    # D9 voll: 1500 * 55e-6 * 37 = 3,0525 MPa (PETG E 1500 seit 19.11.2026)
    r = finde(erg, 'D9', 'schale')
    assert r['stufe'] == 'ok' and abs(r['wert'] - 3.05) < 1e-6, r     # auf 0,01 MPa gerundet
    # ohne alpha: uebersprungen, kein Absturz
    soll['_projekt'].pop('kennwerte')
    assert finde(dauer.pruefe(projekt(soll, board=board)), 'D8')['stufe'] == 'uebersprungen'
    # Merkmal aussen (T_min < 5 C, aussen nicht gesetzt): Sonne, Farbe unbekannt alpha 0,95 -> +38 K -> 98 C
    # Loecher warm: 55e-6 * 48,765 * 75 = 0,20116 > Spiel 0,2 -> warnung (vorher 0,0992 ok)
    soll['_projekt'].pop('aussen')
    soll['_projekt']['kennwerte'] = {'PETG': KW_PETG}
    r = finde(dauer.pruefe(projekt(soll, board=board)), 'D8', titel='Befestigungsloecher, warm')
    assert r['stufe'] == 'warnung' and abs(r['wert'] - 0.2012) < 1e-4, r


@synthetisch
def test_d10_verzug_kalibriert():
    m = tempfile.mktemp(suffix='.json')
    json.dump({'ASA': {'verzug_asa': {'laenge_mm': 120, 'dicke_mm': 2, 'abheben_mm': 0.5, 'T_bauraum_C': 25}}},
              open(m, 'w'))
    alt = toleranz.MESSUNG
    toleranz.MESSUNG = m
    try:
        d = projekt({'_projekt': {'T_bauraum_C': 25}, 'kasten': {'material': 'ASA'}},
                    pruefung={'kasten': {'bbox_mm': [100, 50, 10], 'druck_drehung': [0, 0, 0]}})
        r = finde(dauer.pruefe(d), 'D10', 'kasten')
        # alpha kuerzt sich: 0,5 * (111,803^2/10) / (120^2/2) = 0,5 * 1250/7200 = 0,086806 -> ok (<= 0,1)
        assert r['stufe'] == 'ok' and abs(r['wert'] - 0.087) < 1e-3, r
        # gedreht (90 um X): Grundflaeche 100 x 10, Hoehe 50 -> kleiner
        d = projekt({'kasten': {'material': 'ASA'}},
                    pruefung={'kasten': {'bbox_mm': [100, 50, 10], 'druck_drehung': [90, 0, 0]}})
        r2 = finde(dauer.pruefe(d), 'D10', 'kasten')
        nah(r2['wert'], round(0.5 * (100 ** 2 + 10 ** 2) / 50 / 7200, 3), 1e-3)
    finally:
        toleranz.MESSUNG = alt


@synthetisch
def test_d11_d12():
    soll = {'_projekt': {'material': 'PETG', 'T_max_C': 23, 'lebensdauer_h': 1000, 'kennwerte': {'PETG': KW_PETG}},
            'teil': {'zyklen': 1e6, 'wechsellast': {'sigma_max_MPa': 10, 'R': 0}}}
    # k = 1 - 0,08*2,3263 = 0,81390; S_f = 12,2085; n_xy = 1/(5/12,2085 + 5/45) = 1,9206 -> warnung
    r = finde(dauer.pruefe(projekt(soll)), 'D11', 'teil')
    assert r['stufe'] == 'warnung' and abs(r['wert'] - 1.92) < 0.01, r
    # Zuverlaessigkeit 0,5 (k = 1): n_xy = 2,25, aber n_z = 1/(5/9,333 + 5/28) = 1,40 -> ohne Richtung warnung
    soll['teil']['wechsellast']['zuverlaessigkeit'] = 0.5
    r = finde(dauer.pruefe(projekt(soll)), 'D11', 'teil')
    assert r['stufe'] == 'warnung' and abs(r['wert'] - 2.25) < 1e-6, r
    soll['teil']['wechsellast']['richtung'] = 'xy'
    assert finde(dauer.pruefe(projekt(soll)), 'D11', 'teil')['stufe'] == 'ok'
    # Befund D11-R0-still: weder R noch sigma_min -> R = -1: sigma_a 10, sigma_m 0, n_xy = 12,2085/10 = 1,22
    s2 = json.loads(json.dumps(soll))
    s2['teil']['wechsellast'] = {'sigma_max_MPa': 10}
    r = finde(dauer.pruefe(projekt(s2)), 'D11', 'teil')
    assert abs(r['wert'] - 1.22) < 0.01 and 'R = -1' in r['hinweis'] and r['stufe'] in ('warnung', 'fehler'), r
    # Befund D-material-gross: 'petg' klein geschrieben wie PETG behandeln
    s3 = json.loads(json.dumps(soll))
    s3['_projekt']['material'] = 'petg'
    s3['_projekt']['kennwerte'] = {'PETG': KW_PETG}
    r = finde(dauer.pruefe(projekt(s3)), 'D11', 'teil')      # wie oben (Zuverlaessigkeit 0,5, Richtung xy)
    assert r['stufe'] == 'ok' and abs(r['wert'] - 2.25) < 1e-6, r
    # D12: eps0 1/h, s 10, n 2, Q 0 -> eps_punkt (5/10)^2 = 0,25/h; C_MG 0,1 -> t_f 0,4 h < 1000 h -> fehler
    soll['teil'] = {'dauerlast': {'sigma_MPa': 5},
                    'kriechbruch': {'eps0_1_h': 1, 's_MPa': 10, 'n': 2, 'Q_kJ_mol': 0, 'C_MG': 0.1}}
    r = finde(dauer.pruefe(projekt(soll)), 'D12', 'teil')
    assert r['stufe'] == 'fehler' and abs(r['wert'] - 0.4) < 1e-9, r
    soll['teil'].pop('kriechbruch')
    assert finde(dauer.pruefe(projekt(soll)), 'D12', 'teil')['stufe'] == 'uebersprungen'


@synthetisch
def test_t1_t4_messung():
    leer = tempfile.mktemp(suffix='.json')
    alt = toleranz.MESSUNG
    try:
        # ohne Messung: Bohrung 3 +/-0,1 -> erwartet 2,85 (Standard -0,15), sigma 0,05 * 2 (realterme 'streuung') =
        # 0,10: C_pk = (2,85-2,9)/0,30 = -0,17: Mittelwert ausserhalb der Toleranz -> fehler auch mit VORLAEUFIGem
        # Modell (Befund T1-vorlaeufig-deckel)
        toleranz.MESSUNG = leer
        d = projekt({'_projekt': {'material': 'PETG'},
                     'teil': {'toleranzen': [{'name': 'B3', 'nenn_mm': 3.0, 'tol_mm': 0.1, 'art': 'bohrung'}]}})
        erg = toleranz.pruefe(d)
        r = finde(erg, 'T1', 'teil')
        assert r['stufe'] == 'fehler' and abs(r['wert'] + 0.17) < 1e-6 and 'VORLAEUFIG' in r['hinweis'], r
        # +/-0,2: C_pk = min(3,2-2,85; 2,85-2,8)/0,30 = 0,17 (0 <= C_pk < 1) -> vorlaeufig bleibt warnung
        d2 = projekt({'_projekt': {'material': 'PETG'},
                      'teil': {'toleranzen': [{'name': 'B3', 'nenn_mm': 3.0, 'tol_mm': 0.2, 'art': 'bohrung'}]}})
        r = finde(toleranz.pruefe(d2), 'T1', 'teil')
        assert r['stufe'] == 'warnung' and abs(r['wert'] - 0.17) < 1e-6, r
        # +/-1: C_pk = min(4-2,85; 2,85-2)/0,30 = 2,83 >= 1,33, aber sigma nur angenommen -> gedeckelt auf warnung
        d3 = projekt({'_projekt': {'material': 'PETG'},
                      'teil': {'toleranzen': [{'name': 'B3', 'nenn_mm': 3.0, 'tol_mm': 1.0, 'art': 'bohrung'}]}})
        r = finde(toleranz.pruefe(d3), 'T1', 'teil')
        assert r['stufe'] == 'warnung' and abs(r['wert'] - 2.83) < 1e-6, r
        # aussen_bett (Elefantenfuss): 20 +/-0,2 -> erwartet 20 + 0,05 + 0,25 = 20,30 > 20,2: C_pk (20,2-20,3)/0,3
        # = -0,33 -> fehler; dasselbe Mass als 'aussen' 20,05: min(0,15; 0,25)/0,3 = 0,5 -> warnung
        for art, cpk, st in (('aussen_bett', -0.33, 'fehler'), ('aussen', 0.5, 'warnung')):
            d4 = projekt({'_projekt': {'material': 'PETG'},
                          'teil': {'toleranzen': [{'name': 'L', 'nenn_mm': 20.0, 'tol_mm': 0.2, 'art': art}]}})
            r = finde(toleranz.pruefe(d4), 'T1', 'teil')
            assert r['stufe'] == st and abs(r['wert'] - cpk) < 1e-6, (art, r)
        # gemessen: 3/5/8 je 2,90/2,92/2,88 usw. -> k 1, b -0,1, sigma sqrt(0,0024/7) = 0,018516
        m = tempfile.mktemp(suffix='.json')
        json.dump({'PETG': {'bohrung': [{'nenn_mm': n, 'ist_mm': [n - 0.1, n - 0.08, n - 0.12]} for n in (3, 5, 8)]}},
                  open(m, 'w'))
        toleranz.MESSUNG = m
        md = toleranz.modell('PETG', 'bohrung')
        nah(md['k'], 1.0)
        nah(md['b'], -0.1)
        nah(md['sigma'], 0.018516)
        erg = toleranz.pruefe(d)
        r = finde(erg, 'T1', 'teil')        # mu 2,9 = LSL -> C_pk 0, gemessen -> fehler
        assert r['stufe'] == 'fehler' and abs(r['wert']) < 1e-9, r
        r4 = finde(erg, 'T4', 'teil')       # Abweichung -0,1 > 0,05 -> Vorhalt CAD 3,1
        assert r4['stufe'] == 'warnung' and '3.100' in r4['hinweis'], r4
        # mit Vorhalt cad_mm 3,1: mu 3,0 -> C_pk 0,1/(3*0,018516) = 1,80 -> ok
        d = projekt({'_projekt': {'material': 'PETG'}, 'teil': {'toleranzen': [
            {'name': 'B3', 'nenn_mm': 3.0, 'tol_mm': 0.1, 'art': 'bohrung', 'cad_mm': 3.1}]}})
        r = finde(toleranz.pruefe(d), 'T1', 'teil')
        assert r['stufe'] == 'ok' and abs(r['wert'] - 1.80) < 0.01, r
    finally:
        toleranz.MESSUNG = alt


@synthetisch
def test_t2_t3_t6():
    alt = toleranz.MESSUNG
    toleranz.MESSUNG = tempfile.mktemp(suffix='.json')      # Standardmodell
    try:
        kette = {'name': 'Platine', 'spalt_min_mm': 0.2, 'glieder': [
            {'name': 'Tasche', 'nenn_mm': 50.4, 'tol_mm': 0.15, 'art': 'bohrung'},
            {'name': 'Platine', 'nenn_mm': -50.0, 'tol_mm': 0.1, 'art': 'fremd'}]}
        d = projekt({'_projekt': {'material': 'PETG', 'toleranzketten': [kette]}})
        r = finde(toleranz.pruefe(d), 'T2')
        # Tasche T = max(0,15; 3*0,10) = 0,30, Versatz -0,15; Platine 0,1 (fremd, ohne alpha -> 0);
        # Waerme ohne T_min/T_max: +/-20 K, alpha PETG unbekannt -> 1e-4: 50,4 * 1e-4 * 20 = 0,1008
        # RSS sqrt(0,09 + 0,01 + 0,01016) = 0,331905 -> 0,25 - 0,331905 = -0,0819 < 0,2 -> fehler
        assert r['stufe'] == 'fehler' and abs(r['wert'] + 0.0819) < 1e-4, r
        assert 'Waerme' in r['hinweis'] and 'angenommen' in r['hinweis'], r
        # mit Temperatur und alpha: T_min -7, T_max 53 -> dT +/-30 K; Tasche 51,0 (PETG 70e-6), Platine FR4 1,5e-5:
        # je K 51*70e-6 - 50*1,5e-5 = 0,002820 -> Waerme 0,0846; Mitte 1,0 - 0,15 = 0,85
        # RSS sqrt(0,09 + 0,01 + 0,0846^2) = 0,327349 -> 0,522651; WC 0,85 - 0,4846 = 0,3654
        k2 = {'name': 'P2', 'glieder': [{'name': 'Tasche', 'nenn_mm': 51.0, 'tol_mm': 0.15, 'art': 'bohrung'},
                                        {'name': 'Platine', 'nenn_mm': -50.0, 'tol_mm': 0.1, 'art': 'fremd',
                                         'material': 'FR4'}]}
        pj = {'material': 'PETG', 'T_min_C': -7, 'T_max_C': 53, 'kennwerte': {'PETG': KW_PETG}, 'toleranzketten': [k2]}
        for smin, st in ((0.4, 'warnung'), (0.6, 'fehler'), (0.3, 'warnung')):   # 0,3: ok, aber sigma vorlaeufig
            k2['spalt_min_mm'] = smin
            r = finde(toleranz.pruefe(projekt({'_projekt': pj})), 'T2')
            assert r['stufe'] == st and abs(r['wert'] - 0.5227) < 1e-4, (smin, r)
            nah(r['daten']['wc_min'], 0.3654)
        # T3: D 5,2 / d 5,0: Spiel nach Druck (5,2-0,15) - (5,0+0,05) = 0 -> klemmt; Fase 0,3 < 0,4; mu D = 1,56 <= 2
        d = projekt({'_projekt': {'material': 'PETG'}, 'teil': {'steckungen': [
            {'name': 'Stift', 'D_mm': 5.2, 'd_mm': 5.0, 'fase_mm': 0.3, 'tiefe_mm': 2.0, 'mu': 0.3}]}})
        erg = toleranz.pruefe(d)
        assert finde(erg, 'T3', titel='Stift Spiel')['stufe'] == 'fehler'
        assert finde(erg, 'T3', titel='Stift Fase')['stufe'] == 'warnung'
        r = finde(erg, 'T3', titel='Stift Verkeilen')
        assert r['stufe'] == 'ok' and abs(r['grenze'] - 1.56) < 1e-9
        # T6: 0,01 + Abbe 0,5 mrad*20 = 0,01 + Waerme 70e-6*10*10 = 0,007 -> RSS 0,015780 <= 0,025 -> ok
        fb = {'ziel_mm': 0.1, 'posten': [{'name': 'Fuehrung', 'fehler_mm': 0.01},
                                         {'name': 'Kippen', 'winkel_mrad': 0.5, 'abstand_mm': 20},
                                         {'name': 'Dehnung', 'L_mm': 10, 'dT_K': 10, 'alpha_1_K': 70e-6}]}
        d = projekt({'_projekt': {'material': 'PETG'}, 'teil': {'fehlerbudget': fb}})
        r = finde(toleranz.pruefe(d), 'T6', 'teil')
        assert r['stufe'] == 'ok' and abs(r['wert'] - 0.01578) < 1e-5, r
        # + Druckmass 20 aussen unkompensiert: systematisch 0,05 + RSS mit 3 sigma = 3*0,10 = 0,30:
        # 0,05 + sqrt(0,01^2 + 0,01^2 + 0,007^2 + 0,3^2) = 0,05 + 0,300415 = 0,350415 > 0,1 -> fehler
        fb['posten'].append({'name': 'Lage', 'druck': 'aussen', 'nenn_mm': 20})
        r = finde(toleranz.pruefe(projekt({'_projekt': {'material': 'PETG'}, 'teil': {'fehlerbudget': fb}})),
                  'T6', 'teil')
        assert r['stufe'] == 'fehler' and abs(r['wert'] - 0.3504) < 1e-4, r
    finally:
        toleranz.MESSUNG = alt


@synthetisch
def test_t5_wand():
    from build123d import Align, Box, Pos
    MIN = (Align.CENTER, Align.CENTER, Align.MIN)
    dose = Box(40, 30, 20, align=MIN) - Pos(0, 0, 2) * Box(36, 26, 20, align=MIN)    # ueberall 2 mm
    d = projekt({'dose': {'wand_gleichmaessig': True}}, steps={'dose': dose})
    r = finde(toleranz.pruefe(d), 'T5', 'dose')
    assert r['stufe'] == 'ok' and r['wert'] < 0.01, r
    keil = Box(40, 30, 20, align=MIN) - Pos(0, 0, 2) * Box(36, 20, 20, align=MIN)     # Wand 2 und 5 mm
    d = projekt({'keil': {'wand_gleichmaessig': True}}, steps={'keil': keil})
    assert finde(toleranz.pruefe(d), 'T5', 'keil')['stufe'] == 'info'


@synthetisch
def test_leer_kein_absturz():
    d = projekt({})
    for m in (dauer, toleranz):
        for e in m.pruefe(d):
            assert e['stufe'] in STUFEN
    r = pruefungen.alle(d, module=('dauer', 'toleranz'))
    assert r['ok'] and os.path.exists(os.path.join(d, 'pruef', 'katalog.json'))


# ---------------------------------------------------------------- echte Projekte

def test_echte_projekte():
    gesamt = {}
    for p in ECHT:
        pd = beispielprojekt(os.path.join(BASIS, 'projects', p))
        for m in (dauer, toleranz):
            for e in m.pruefe(pd):
                assert e['stufe'] in STUFEN and e['id'] and (e['quelle'] or e['stufe'] == 'uebersprungen'), e
                if e['stufe'] == 'uebersprungen':
                    assert e['hinweis'], e
                gesamt.setdefault(p, []).append(e)
    # Kein Alarm unterdrueckt: die Waerme-FEM von testdose und frag-mich-alles ist ueber Tg - 20 -> D1 fehler
    assert finde(gesamt['testdose'], 'D1', 'unterschale')['stufe'] == 'fehler'
    assert finde(gesamt['frag-mich-alles-gehaeuse'], 'D1', 'rueckschale')['stufe'] == 'fehler'
    # Kalibrierkoerper: Toleranzen laufen mit Standardmodell (vorlaeufig, nie stilles ok bei C_pk < 1,33)
    t1 = [e for e in gesamt['kalibrierkoerper'] if e['id'] == 'T1']
    # C_pk < 0 (Mittelwert ausserhalb der Toleranz, Bohrungen ohne Vorhalt) -> fehler trotz vorlaeufigem Modell
    assert len(t1) == 7 and all(e['stufe'] == ('fehler' if e['wert'] < 0 else e['stufe']) for e in t1)
    assert all(e['stufe'] in ('ok', 'warnung') for e in t1 if e['wert'] >= 0)
    assert all('VORLAEUFIG' in e['hinweis'] for e in t1 if e['stufe'] != 'uebersprungen')
    # ASA-Streifen: ohne Kalibrierung nur Rangfolge (info) oder uebersprungen (alpha fehlt), nie ok/fehler
    assert finde(gesamt['kalibrierkoerper'], 'D10', 'verzugsstreifen')['stufe'] in ('info', 'uebersprungen')
    return gesamt


if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_'):
            f()
            print('ok', n)
