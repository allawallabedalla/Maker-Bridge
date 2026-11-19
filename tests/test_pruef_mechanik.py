"""Gegentests fuer mb2/pruefungen/mechanik.py und mb2/geometrie.py (Katalog M1-M6, M12-M16, M19, M21-M24, M26).

Jede Formel hat mindestens einen Handrechen-Gegentest (Zahlen im Kommentar von Hand gerechnet), dazu kleine
synthetische Teile fuer die Geometrie-Erkennung und Laeufe an Kopien echter Projekte (projects/ bleibt unveraendert).
Aufruf (pytest nicht noetig): .venv/Scripts/python.exe tests/test_pruef_mechanik.py
"""
import json
import math
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from build123d import Align, Axis, Box, Pos, export_step, fillet  # noqa: E402

from mb2 import geometrie  # noqa: E402
from mb2.pruefungen import mechanik as M  # noqa: E402

HIER = os.path.dirname(os.path.abspath(__file__))
PROJEKTE = os.path.join(HIER, '..', 'projects')
MIN = (Align.CENTER, Align.CENTER, Align.MIN)


def nah(a, b, rel=1e-3, abs_=1e-9):
    assert abs(a - b) <= max(abs_, rel * abs(b)), f'{a} != {b}'


def finde(erg, id_, titel_teil, teil=None):
    r = [e for e in erg if e['id'] == id_ and titel_teil in e['titel'] and (teil is None or e.get('teil') == teil)]
    assert r, f'{id_} "{titel_teil}" fehlt: {[(e["id"], e["titel"]) for e in erg]}'
    return r[0]


# ================================================================ Handrechnungen je Formel

def test_m1_schnapphaken_hand():
    # L 12, b 6, t 1,6, y 0,8, E 2000: eps = 1,5*1,6*0,8/144 = 0,013333; F = 2000*6*4,096*0,8/(4*1728) = 5,6889 N
    r = M.m1_schnapper({'L_mm': 12, 'b_mm': 6, 't_mm': 1.6, 'hinterschnitt_mm': 0.8, 'E_MPa': 2000})
    nah(r['eps'], 0.0133333)
    nah(r['F_N'], 5.68889)
    nah(r['sigma_MPa'], 26.6667)
    nah(r['d_spitze_mm'], 0.8)            # Last an der Spitze: Weg dort = Hinterschnitt
    # Last bei a = 10: eps = 1,5*1,6*0,8/100 = 0,0192
    nah(M.m1_schnapper({'L_mm': 12, 'a_mm': 10, 'b_mm': 6, 't_mm': 1.6, 'hinterschnitt_mm': 0.8,
                        'E_MPa': 2000})['eps'], 0.0192)


def test_m2_fuegekraft_hand():
    # W = 5,6889 (0,3 + 0,57735)/(1 - 0,3*0,57735) = 4,99118/0,826795 = 6,0368 N
    nah(M.m2_fuegekraft(5.68889, 0.3, 30), 6.0368)
    assert M.m2_fuegekraft(5.0, 0.6, 60) is None           # 0,6*tan60 = 1,04 > 1: Selbsthemmung


def test_m3_balken_hand():
    # Kragarm F 5 bei a 14, b 6, h 1,8: I = 2,916; d = 5*14^3/(3*2000*2,916) = 0,78418; sigma = 5*14*0,9/2,916 = 21,605
    d, s = M.m3_balken('kragarm', 5, 15.6, 2000, 6 * 1.8 ** 3 / 12, 0.9, a=14)
    nah(d, 0.78418)
    nah(s, 21.605)
    # gelenkig mittig F 10, L 100, b 10, h 2: I = 6,6667; d = 1e7/(48*2000*6,6667) = 15,625; sigma = 250/6,6667 = 37,5
    d, s = M.m3_balken('gelenkig', 10, 100, 2000, 10 * 8 / 12, 1.0)
    nah(d, 15.625)
    nah(s, 37.5)
    d, s = M.m3_balken('eingespannt', 10, 100, 2000, 10 * 8 / 12, 1.0)
    nah(d, 15.625 / 4)
    nah(s, 18.75)


def test_m4_knicken_hand():
    # Rund d 4, L 50, K 2, E 2000: I = 12,566; P_cr = pi^2*2000*12,566/100^2 = 24,805 N; lambda = 100 > 29,6 -> Euler
    I, A = M.querschnitt({'d_mm': 4})
    nah(I, 12.5664)
    P, lam, art = M.m4_knicken(2000, I, A, 2.0, 50, 45)
    nah(P, 24.805)
    nah(lam, 100.0)
    assert art == 'Euler'
    # gedrungen d 10, L 10, K 1: lambda 4, Johnson P = 78,54*45*(1 - 45*16/(4 pi^2 2000)) = 3502,1 N
    I, A = M.querschnitt({'d_mm': 10})
    P, lam, art = M.m4_knicken(2000, I, A, 1.0, 10, 45)
    assert art == 'Johnson'
    nah(P, 3502.1, rel=2e-4)
    # Rechteck: I_min = 10*2^3/12 = 6,667 (schwache Achse)
    nah(M.querschnitt({'b_mm': 10, 'h_mm': 2})[0], 6.6667)


def test_m5_beulen_hand():
    # PLA, k 0,425 (freie Rippe): h/t_grenz = sqrt(0,425*pi^2*3500/(12*0,8704)/50) = 5,30 - Katalogwert "PLA 5,3"
    nah(M.m5_grenze_ht(3500, 0.36, 50, 0.425), 5.302, rel=1e-3)
    # PETG gelenkig k 4, t 2, h 20: sigma_cr = 4*1922,55*0,01 = 76,90 MPa
    nah(4 * M.beul_faktor(2000, 0.38) * (2 / 20) ** 2, 76.90, rel=1e-3)
    nah(M.m5_k(20, 40, 'frei'), 0.456 + 0.25)
    assert M.m5_k(20, 40, 'frei_enden') == 0.425 and M.m5_k(20, 40, 'gelenkig') == 4.0


def test_m6_kt_hand():
    nah(M.m6_kt(0.5, 2.0), 2.0)          # 1 + 0,5*sqrt(4)
    nah(M.m6_kt(1.0, 2.0), 1.7071)       # rho = 0,5 t -> K_t 1,71


def test_m12_schraube_hand():
    # F_i 300, M3, d_w 5,5, d_h 3,2: p = 300/(pi/4*(30,25-10,24)) = 19,089 MPa
    # k_b = 210000*7,0686/6 = 247 401; k_m = 2000*pi/4*((5,5+3)^2 - 3,2^2)/6 = 16 234; C = 0,93842
    r = M.m12_schraube(300, 3, 5.5, 3.2, 6, 2000, P=100)
    nah(r['pressung_MPa'], 19.089)
    nah(r['C'], 0.93842, rel=2e-4)
    nah(r['F_klemm_N'], 293.84, rel=2e-4)
    nah(r['F_schraube_N'], 393.84, rel=2e-4)
    nah(r['P_klaffen_N'], 4871.6, rel=1e-3)
    # ohne Klemmlaenge: C = 0 fuers Klaffen, C = 1 fuer die Schraubenkraft (beides konservativ)
    r = M.m12_schraube(300, 3, 5.5, 3.2, None, 2000, P=100)
    nah(r['F_klemm_N'], 200.0)
    nah(r['F_schraube_N'], 400.0)


def test_m13_insert_hand():
    nah(M.m13_insert(50, 4.0, 5.7), 0.69806)      # 50/(pi*4*5,7)


def test_m14_pressitz_hand():
    # d 8, D 12, Uebermass 0,05, E 2000, nu 0,38: Q = 208/80 = 2,6; starr p = 100/(8*2,98) = 4,1946, sigma = 10,906
    p, s = M.m14_pressitz(2000, 0.38, 8, 12, 0.05)
    nah(p, 4.1946)
    nah(s, 10.906)
    p, s = M.m14_pressitz(2000, 0.38, 8, 12, 0.05, 'gleich')    # p = 100/(8*3,6) = 3,4722
    nah(p, 3.4722)
    nah(s, 9.0278)


def test_m15_scharnier_hand():
    th, k = M.m15_scharnier(1.5, 0.6, 0.04, 2000, 10)           # 2*1,5*0,04/0,6 = 0,2 rad; 2000*10*0,216/18 = 240
    nah(th, 0.2)
    nah(k, 240.0)


def test_m16_torsion_hand():
    nah(M.m16_tau({'art': 'offen', 'T_Nmm': 100, 'b_mm': 10, 't_mm': 1}), 30.0)
    nah(M.m16_tau({'art': 'rund', 'T_Nmm': 100, 'd_mm': 10}), 0.50930)
    nah(M.m16_tau({'art': 'rohr', 'T_Nmm': 100, 'd_mm': 10, 'd_innen_mm': 8}), 0.86264)
    nah(M.m16_tau({'art': 'bredt', 'T_Nmm': 100, 'A_m_mm2': 100, 't_mm': 1}), 0.5)


def test_m19_platte_hand():
    # Quadrat 50, t 2, PETG: D = 2000*8/(12*0,8556) = 1558,4 Nmm
    # gelenkig, q 0,01: w = 0,00406*0,01*50^4/D = 0,16283; Mittenlast 10 N: w = 0,0116*10*2500/D = 0,18609
    w, a, D = M.m19_platte(2000, 0.38, 50, 50, 2, q=0.01)
    nah(D, 1558.40, rel=1e-4)
    nah(w, 0.16283, rel=1e-3)
    w, _, _ = M.m19_platte(2000, 0.38, 50, 50, 2, F=10)
    nah(w, 0.18609, rel=1e-3)
    # 75 x 50 eingespannt (r = 1,5): alpha 0,00220 -> w = 0,0022*0,01*50^4/D = 0,08823
    w, a, _ = M.m19_platte(2000, 0.38, 75, 50, 2, q=0.01, rand='eingespannt')
    nah(a, 0.00220)
    nah(w, 0.08823, rel=1e-3)


def test_m22_bruch_hand():
    nah(M.m22_KI(10.0, 0.45), 0.42111, rel=1e-4)      # 1,12*10*sqrt(pi*0,00045)


def test_m23_lewis_hand():
    nah(M.lewis_Y(20), 0.322)
    nah(M.lewis_Y(23), 0.334)                         # zwischen 22 (0,331) und 24 (0,337)
    assert M.lewis_Y(10) is None
    # sigma = 50/(5*1*0,322) = 31,056 MPa (Rechnung in _pruefe_zahnraeder, hier die Formel selbst)
    nah(50 / (5 * 1 * M.lewis_Y(20)), 31.056)


def test_m24_constraints_hand():
    fg, doppelt, frei = M.m24_fg([{'sperrt': ['x', 'y', 'z']}, {'sperrt': ['x', 'rz']}])
    assert fg == 1 and doppelt == ['x'] and frei == ['rx', 'ry']
    assert M.m24_fg([{'anzahl': 7}])[0] == -1


def test_m26_streuung_hand():
    ke, z = M.m26_ke(0.08, 0.99)                      # Katalog: 99 % -> 0,81
    nah(z, 2.3263, rel=1e-4)
    nah(ke, 0.81390, rel=1e-4)
    assert M.m26_sicherheit({'lastfaktor': 1.5, 'streuung_z': 0.08}, 'PETG', 'z') > 1.84


def test_baurichtung():
    nah(geometrie.baurichtung((90, 0, 0))[1], 1.0)       # auf der Seite: Schichten stapeln laengs Teil-Y
    nah(geometrie.baurichtung((0, 0, 0))[2], 1.0)
    nah(geometrie.baurichtung((0, 90, 0))[0], -1.0)


# ================================================================ Geometrie-Erkennung an kleinen Teilen

def test_geo_innenkante_und_kehle():
    platte = Box(20, 20, 2, align=MIN)
    wand = Pos(0, 0, 2) * Box(2, 20, 10, align=MIN)
    scharf = platte + wand
    ik = geometrie.innenkanten(scharf)
    assert len(ik) == 2, ik                                # beide Seiten der Wand am Boden
    assert all(abs(e['t_mm'] - 2.0) < 0.01 for e in ik), ik
    gerundet = fillet(scharf.edges().filter_by(Axis.Y).group_by(Axis.Z)[1], 1.0)
    assert geometrie.innenkanten(gerundet) == []
    kl = geometrie.kehlen(gerundet)
    assert len(kl) == 2 and all(abs(k['rho_mm'] - 1.0) < 1e-6 for k in kl), kl
    assert all(abs(k['t_mm'] - 2.0) < 0.01 for k in kl), kl     # rho/t = 0,5: genau an der Grenze


def test_geo_rippe_platte_schlitz_bohrung():
    # freie Rippe 1,5 x 15 auf Platte 3: h/t = 10
    teil = Box(40, 40, 3, align=MIN) + Pos(0, 0, 3) * Box(1.5, 40, 15, align=MIN)
    rp = [r for r in geometrie.rippen(teil) if abs(r['t_mm'] - 1.5) < 1e-6]
    assert len(rp) == 1, geometrie.rippen(teil)
    nah(rp[0]['h_mm'], 15.0)
    nah(rp[0]['a_mm'], 40.0)
    # Deckel (Platte ohne Wurzel): keine Rippe
    assert geometrie.rippen(Box(40, 30, 2)) == []
    # Wand mit Schlitz: Schlitzflanken sind keine freien Raender (nur die Oberkante der Wand zaehlt)
    wand = Box(40, 2, 20, align=MIN) + Pos(0, 10, 0) * Box(40, 20, 2, align=MIN) - Pos(0, 0, 8) * Box(2, 4, 6, align=MIN)
    hs = [r['h_mm'] for r in geometrie.rippen(wand) if abs(r['t_mm'] - 2) < 1e-6 and abs(r['ebene_normale'][1]) > 0.9]
    assert hs and max(hs) <= 20.0 + 1e-6, geometrie.rippen(wand)
    # Bohrung 3,2 durch 5-mm-Platte
    from build123d import Cylinder
    b = geometrie.bohrungen(Box(20, 20, 5) - Cylinder(1.6, 10))
    assert len(b) == 1 and abs(b[0]['d_mm'] - 3.2) < 1e-6 and abs(b[0]['tiefe_mm'] - 5) < 1e-6, b


# ================================================================ Gesamtlauf an einem synthetischen Projekt

def _projekt(tmp, soll, teile=None, druck=None, fem=None):
    os.makedirs(os.path.join(tmp, 'cad'), exist_ok=True)
    os.makedirs(os.path.join(tmp, 'out'), exist_ok=True)
    json.dump(soll, open(os.path.join(tmp, 'cad', 'soll.json'), 'w'))
    for name, teil in (teile or {}).items():
        export_step(teil, os.path.join(tmp, 'out', name + '.step'))
        json.dump({'druck_drehung': list((druck or {}).get(name, (0, 0, 0)))},
                  open(os.path.join(tmp, 'out', name + '.pruefung.json'), 'w'))
    for name, (spec, erg) in (fem or {}).items():
        os.makedirs(os.path.join(tmp, 'fem'), exist_ok=True)
        json.dump(spec, open(os.path.join(tmp, 'fem', name + '.json'), 'w'))
        json.dump(erg, open(os.path.join(tmp, 'fem', name + '.erg.json'), 'w'))
    return tmp


def test_gesamt_synthetisch():
    with tempfile.TemporaryDirectory() as tmp:
        soll = {
            # T_max 23 C, T_min 20 C, innen: keine Realterme ausser Dauerlast (PETG Tg 78 C - 23 C = 55 K -> A_T 1)
            '_projekt': {'material': 'PETG', 'streuung_xy': 0.08, 'streuung_z': 0.08, 'T_max_C': 23, 'T_min_C': 20,
                         'aussen': False},
            'teil': {
                'schnapper': [{'name': 'gut', 'L_mm': 12, 'b_mm': 6, 't_mm': 1.6, 'hinterschnitt_mm': 0.8,
                               'winkel_grad': 30, 'mu': 0.3, 'achse': 'x', 'eps_zul': 0.02, 'zyklen': 1},
                              {'name': 'quer', 'L_mm': 12, 'b_mm': 6, 't_mm': 1.6, 'hinterschnitt_mm': 0.8,
                               'achse': 'z', 'eps_zul': 0.02},
                              {'name': 'zu_kurz', 'L_mm': 5, 'b_mm': 6, 't_mm': 2, 'hinterschnitt_mm': 1.2,
                               'achse': 'x', 'winkel_grad': 60, 'mu': 0.6, 'eps_zul': 0.02}],
                'knicken': [{'name': 'stift', 'L_mm': 50, 'd_mm': 4, 'lagerung': 'frei', 'kraft_N': 20, 'achse': 'x'}],
                'rippen': [{'name': 'steg', 'h_mm': 20, 't_mm': 2, 'rand': 'gelenkig', 'druck_MPa': 10}],
                'schrauben': [{'d_mm': 3, 'vorspannung_N': 300, 'kopf_d_mm': 5.5, 'loch_d_mm': 3.2,
                               'klemmlaenge_mm': 6, 'last_N': 100, 'klemmkraft_min_N': 100, 'einschraub_mm': 4,
                               'achse': 'x'}],
                'inserts': [{'d_aussen_mm': 4.0, 'laenge_mm': 5.7}],
                'pressitze': [{'d_mm': 8, 'D_aussen_mm': 12, 'uebermass_mm': 0.05, 'achse': 'z'}],
                'scharniere': [{'L_mm': 1.5, 't_mm': 0.6, 'b_mm': 10, 'winkel_grad': 90, 'achse': 'x',
                                'eps_zul': 0.04}],
                'torsion': [{'art': 'rund', 'T_Nmm': 100, 'd_mm': 10}],
                'deckelbiegung': [{'a_mm': 50, 'b_mm': 50, 't_mm': 2, 'last_N': 10, 'last_art': 'punkt',
                                   'abstand_mm': 0.15}],
                'zahnraeder': [{'m_mm': 1, 'z': 20, 'b_mm': 5, 'F_t_N': 50, 'achse': 'z', 'dauerlast': False}],
                'constraints': [{'name': 'Boden', 'sperrt': ['z', 'rx', 'ry']}, {'name': 'Stift', 'sperrt': ['x', 'y']},
                                {'name': 'Nut', 'sperrt': ['x', 'rz']}],
            },
        }
        teil = Box(40, 40, 3, align=MIN) + Pos(0, 0, 3) * Box(1.5, 40, 15, align=MIN)
        _projekt(tmp, soll, {'teil': teil})
        e = M.pruefe(tmp)
        st = lambda i, t: finde(e, i, t)['stufe']  # noqa: E731
        # M1: zyklen 1, T_min 20 C -> eps_zul 0,02 / 1 / S_eps 1,2 = 0,016667 >= eps 0,01333 ok;
        #     Fuegen = Kurzzeit, A_T 1 -> sigma 26,7 MPa <= 45/1/1,5 = 30 ok; Druckrichtung x in XY ok
        assert st('M1', 'gut: Dehnung') == 'ok' and st('M1', 'gut: Spannung') == 'ok'
        assert st('M1', 'gut: Druckrichtung') == 'ok'
        assert st('M1', 'quer: Druckrichtung') == 'fehler'        # Hakenachse || Z
        # zu_kurz: eps = 1,5*2*1,2/25 = 0,144 > 0,02
        assert st('M1', 'zu_kurz: Dehnung') == 'fehler'
        nah(finde(e, 'M2', 'Fuegekraft gut')['wert'], 6.04, rel=1e-2)
        assert st('M2', 'Fuegekraft gut') == 'ok'
        assert st('M2', 'Fuegekraft zu_kurz') == 'fehler'        # Selbsthemmung
        # M4: P_cr 24,8 N / 20 N = 1,24 < 3 -> warnung
        assert st('M4', 'stift') == 'warnung'
        # M5 von Hand: sigma_cr 76,9 / 10 = 7,7 >= 2 ok; automatisch: Rippe h/t 10 > 4,26 -> warnung
        assert st('M5', 'steg') == 'ok'
        assert st('M5', 'Rippen-Schlankheit') == 'warnung'
        # M6: zwei scharfe Innenkanten an der Rippenwurzel
        assert finde(e, 'M6', 'Scharfe Innenecken')['wert'] == 2
        # M12: Pressung 19,09 MPa gegen Druckfestigkeit / A_K 1,7 (Vorspannung = Dauerlast) / S 2
        # (kennwerte druck_MPa PETG 30 -> 30/1,7 = 17,65 MPa; 19,09 > 17,65 -> fehler, vor dem Audit warnung);
        # Klaffen 293,8 >= 100 ok; Einschraubtiefe 4/3 = 1,33 D -> warnung
        from mb2 import kennwerte
        druck = (kennwerte.wert('PETG', 'druck_MPa') or 45.0) / 1.7
        kp = finde(e, 'M12', 'Kopfpressung')
        nah(kp['wert'], 19.09, rel=1e-3)
        nah(kp['grenze'], round(druck / 2, 2), rel=1e-3)
        assert kp['stufe'] == ('ok' if 19.09 <= druck / 2 else 'warnung' if 19.09 <= druck else 'fehler'), kp
        assert st('M12', 'Klaffen') == 'ok'
        # Restvorspannung: PETG ohne Kriechdaten -> 0,5 x 300 = 150 N; (1-C) P = 300 - 293,8 = 6,2 N
        # -> F_klemm 143,8 N >= 100 -> ok, aber nur angenommen -> warnung
        rv = finde(e, 'M12', 'Restvorspannung')
        nah(rv['wert'], 143.8, rel=2e-3)
        assert rv['stufe'] == 'warnung' and rv['daten']['rest_faktor'] == 0.5, rv
        assert st('M12', 'Einschraubtiefe') == 'warnung'
        # M13: Kraft aus M12 (393,8 N): tau = 393,8/(pi*4*5,7) = 5,50 MPa; Grenze schub_z oder 28/sqrt3 = 16,2
        ins = finde(e, 'M13', 'Insert')
        nah(ins['daten']['tau_MPa'], 5.498, rel=1e-3)
        # Dauerlast A_K 1,7: S = 14 (schub_z PETG) / 1,7 / 5,498 = 1,498 -> zwischen 1 und 2 -> warnung
        tz = kennwerte.wert('PETG', 'schub_z_MPa') or 28 / math.sqrt(3)
        nah(ins['wert'], round(tz / 1.7 / 5.498, 2), rel=5e-3)
        assert ins['stufe'] == ('ok' if tz / 1.7 / 5.498 >= 2 else 'warnung' if tz / 1.7 / 5.498 >= 1 else 'fehler')
        # M14: stehende Bohrung (z): sigma_theta 10,9 gegen 45 / A_K 1,7 (Uebermass dauernd) -> S 4,1/1,7 = 2,43 ok
        assert st('M14', 'Pressitz') == 'ok'
        nah(finde(e, 'M14', 'Pressitz')['wert'], round(finde(e, 'M14', 'Pressitz')['daten']['S_roh'] / 1.7, 2), 1e-2)
        # M15: 90 Grad bei theta_max 11,5 Grad -> fehler
        assert [x for x in e if x['titel'] == 'Filmscharnier 1'][0]['stufe'] == 'fehler' and st('M15', 'Druckrichtung') == 'ok'
        # M16: 0,51 MPa -> S gross, aber Dauer unbekannt -> A_K 1,7 angenommen -> hoechstens warnung
        assert st('M16', 'Torsion') == 'warnung'
        assert 'angenommen' in finde(e, 'M16', 'Torsion')['hinweis']
        # M19: w 0,186 > Abstand 0,15 -> fehler
        assert st('M19', 'Deckeldurchbiegung') == 'fehler'
        # M23: liegend (z), sigma 31,1 MPa > 45/2 -> warnung (S 1,45); Eintrag dauerlast false -> f = 1
        assert st('M23', 'Druckrichtung') == 'ok'
        assert [x for x in e if x['titel'] == 'Zahnrad 1 (Lewis)'][0]['stufe'] == 'warnung'
        # M24: C = 7 -> FG -1, x doppelt -> warnung
        m24 = finde(e, 'M24', 'Constraint')
        assert m24['stufe'] == 'warnung' and m24['wert'] == -1
        # M21: PETG zaeh -> info
        assert st('M21', 'Plastische Reserve') == 'info'
        # M26 aus _projekt-Streuung: S_ziel = 1/0,814 = 1,229 < 2 -> info
        nah(finde(e, 'M26', 'PETG Z')['wert'], 1.229, rel=1e-3)
        # Jede Pruefung traegt ID und Quelle
        assert all(x['quelle'] for x in e if x['stufe'] != 'uebersprungen'), [x for x in e if not x['quelle']]


def test_fehlende_eingaben_nie_absturz():
    with tempfile.TemporaryDirectory() as tmp:
        soll = {'teil': {'schnapper': [{'L_mm': 10}], 'schrauben': [{}], 'inserts': [{'d_aussen_mm': 4}],
                         'pressitze': [{'d_mm': 8}], 'scharniere': [{}], 'torsion': [{'art': 'quatsch'}],
                         'deckelbiegung': [{}], 'zahnraeder': [{}], 'knicken': [{}], 'balken': [{'fall': 'x'}],
                         'rippen': [{}]}}
        _projekt(tmp, soll)
        e = M.pruefe(tmp)
        assert e and all(x['stufe'] == 'uebersprungen' for x in e if x.get('teil') == 'teil'), \
            [x for x in e if x['stufe'] != 'uebersprungen']
        assert not any('Absturz' in x['titel'] for x in e)
    with tempfile.TemporaryDirectory() as tmp:                 # leeres Projekt
        e = M.pruefe(tmp)
        assert e and not any(x.get('teil') or x['stufe'] == 'fehler' for x in e), e


def test_druckrichtung_aus_cad():
    """Haken auf der Seite gedruckt (90, 0, 0): Schichtnormale = Teil-Y, Zunge laengs X -> in XY ok.
    Dasselbe Teil flach (0, 0, 0) mit Zunge laengs Z -> fehler."""
    with tempfile.TemporaryDirectory() as tmp:
        s = {'L_mm': 12, 'b_mm': 6, 't_mm': 1.6, 'hinterschnitt_mm': 0.8}
        soll = {'a': {'schnapper': [{**s, 'achse': 'x'}]}, 'b': {'schnapper': [{**s, 'achse': 'y'}]},
                'c': {'schnapper': [{**s, 'achse': 'z'}]}}
        klotz = Box(5, 5, 5)
        _projekt(tmp, soll, {'a': klotz, 'b': klotz, 'c': klotz}, druck={'a': (90, 0, 0), 'b': (90, 0, 0)})
        e = M.pruefe(tmp)
        assert finde(e, 'M1', 'Druckrichtung', 'a')['stufe'] == 'ok'
        assert finde(e, 'M1', 'Druckrichtung', 'b')['stufe'] == 'fehler'      # Y || Druck-Z nach Drehung
        assert finde(e, 'M1', 'Druckrichtung', 'c')['stufe'] == 'fehler'      # flach, Zunge stehend


# ================================================================ Realterme und Ausloeser (Audit Scheinsicherheit 15.11.2026)

def test_realterme_m1_haeufig_kalt_aussen():
    """Schnapper L 12, b 6, t 1,6, PETG, eps_zul 0,02.
    Haeufig (zyklen 10) + kalt (T_min 0 C): f_eps = 1/(0,6*0,7) = 2,381 -> eps_zul_real = 0,0084, / S_eps 1,2 = 0,007.
      y 0,80: eps = 1,5*1,6*0,8/144 = 0,013333 > 0,0084 -> fehler (vorher ok)
      y 0,48: eps = 0,008 zwischen 0,007 und 0,0084 -> warnung
    Spannung aussen, Farbe weiss: Sonne 0,25*1000/25 = 10 K -> T = 30 + 10 = 40 C, PETG Tg 78 - 40 = 38 K >= 30 -> A_T 1;
      A_A 1,3; Fuegen = Kurzzeit -> f = 1,3: sigma = 2000*0,013333 = 26,67 MPa gegen 45/1,3/1,5 = 23,08 -> warnung
      (<= 45/1,3 = 34,6)."""
    with tempfile.TemporaryDirectory() as tmp:
        s = {'L_mm': 12, 'b_mm': 6, 't_mm': 1.6, 'achse': 'x', 'eps_zul': 0.02, 'zyklen': 10}
        soll = {'_projekt': {'material': 'PETG', 'T_max_C': 30, 'T_min_C': 0, 'aussen': True, 'farbe': 'weiss'},
                'teil': {'druckrichtung': 'z', 'schnapper': [{**s, 'name': 'a', 'hinterschnitt_mm': 0.8},
                                                              {**s, 'name': 'b', 'hinterschnitt_mm': 0.48}]}}
        _projekt(tmp, soll)
        e = M.pruefe(tmp)
        da, db = finde(e, 'M1', 'a: Dehnung'), finde(e, 'M1', 'b: Dehnung')
        nah(da['grenze'], 0.007, rel=1e-3)
        nah(da['daten']['eps_zul_real'], 0.0084, rel=1e-3)
        assert da['stufe'] == 'fehler' and db['stufe'] == 'warnung', (da, db)
        assert 'haeufiges Fuegen' in da['hinweis'] and 'Kaelte' in da['hinweis']
        sa = finde(e, 'M1', 'a: Spannung')
        nah(sa['daten']['abminderung'], 1.3, rel=1e-6)
        nah(sa['grenze'], round(45 / 1.3 / 1.5, 2), rel=1e-3)
        assert sa['stufe'] == 'warnung', sa
        # vorgespannt in Ruhelage -> Dauerlast A_K 1,7: f = 1,3*1,7 = 2,21, Grenze 45/2,21/1,5 = 13,57;
        # 26,67 > 45/2,21 = 20,36 -> fehler
        soll['teil']['schnapper'][0]['vorgespannt'] = True
        _projekt(tmp, soll)
        sa = finde(M.pruefe(tmp), 'M1', 'a: Spannung')
        nah(sa['grenze'], round(45 / 2.21 / 1.5, 2), rel=1e-3)
        assert sa['stufe'] == 'fehler', sa


def test_realterme_ohne_angaben_hoechstens_warnung():
    """Ohne T_max_C, zyklen, Dauer: unguenstige Standards angenommen -> nie 'ok'.
    PLA (Tg 57), Luft 30 C angenommen (keine Elektronik): dT 27 -> A_T = 1 + 3*0,04 = 1,12. Fuegen kurzzeit -> f 1,12.
    Schnapper y 0,2: eps = 1,5*1,6*0,2/144 = 0,003333; eps_zul_xy PLA 0,014 / 0,6 (Zyklen unbekannt -> haeufig)
    / 1,2 = 0,01944 -> rechnerisch ok, wegen Annahme warnung. sigma = 2300*0,003333 = 7,67 MPa << 45/1,12/1,5."""
    with tempfile.TemporaryDirectory() as tmp:
        soll = {'_projekt': {'material': 'PLA'},
                'teil': {'druckrichtung': 'z', 'schnapper': [{'L_mm': 12, 'b_mm': 6, 't_mm': 1.6,
                                                              'hinterschnitt_mm': 0.2, 'achse': 'x'}]}}
        _projekt(tmp, soll)
        e = M.pruefe(tmp)
        d, s = finde(e, 'M1', ': Dehnung'), finde(e, 'M1', ': Spannung')
        from mb2.material import MATERIAL
        nah(d['grenze'], round(0.014 / (1 / 0.6) / 1.2, 5), rel=1e-3)
        assert d['stufe'] == 'warnung' and s['stufe'] == 'warnung', (d, s)
        nah(s['daten']['abminderung'], 1.12, rel=1e-3)
        nah(s['grenze'], round(MATERIAL['PLA']['festigkeit_xy_MPa'] / 1.12 / 1.5, 2), rel=1e-3)


def test_m12_restvorspannung_asa_und_klaffen():
    """ASA: Kriechmodul 1000 h 900 / E 2000 = 0,45 (kennwerte). M3, F_i 200 N, P 300 N, ohne klemmlaenge -> C = 0:
    F_klemm = 200 - 300 = -100 -> Klaffen schon kurzzeitig fehler; Restvorspannung 0,45*200 - 300 = -210 -> fehler.
    Mit P 50: Klaffen 150 ok, Rest 90 - 50 = 40 N > 0 -> ok, aber angenommen -> warnung."""
    with tempfile.TemporaryDirectory() as tmp:
        soll = {'_projekt': {'material': 'ASA', 'T_max_C': 23, 'aussen': False},
                'teil': {'schrauben': [{'name': 'a', 'd_mm': 3, 'vorspannung_N': 200, 'last_N': 300},
                                       {'name': 'b', 'd_mm': 3, 'vorspannung_N': 200, 'last_N': 50}]}}
        _projekt(tmp, soll)
        e = M.pruefe(tmp)
        ra, rb = finde(e, 'M12', 'a: Restvorspannung'), finde(e, 'M12', 'b: Restvorspannung')
        nah(ra['daten']['rest_faktor'], 0.45, rel=1e-6)
        nah(ra['wert'], -210.0)
        assert ra['stufe'] == 'fehler'
        nah(rb['wert'], 40.0)
        assert rb['stufe'] == 'warnung' and 'Kriechmodul' in rb['hinweis'], rb
        nah(M.rest_vorspannung(None, 'PETG')[0], 0.5)            # ohne Kriechdaten
        nah(M.rest_vorspannung(None, 'PLA', {'rest_vorspannung': 0.3})[0], 0.3)


def test_soll_gesteuert_ohne_eintrag_uebersprungen():
    """Ohne soll-Eintrag liefern M1, M2, M12-M16, M19, M23 je ein 'uebersprungen' (nicht []), damit AUSLOESER
    es bei erkanntem Merkmal hochstufen kann; Bohrung 2,5 im STEP wird als Kernloch M3 genannt."""
    from build123d import Cylinder
    with tempfile.TemporaryDirectory() as tmp:
        _projekt(tmp, {'teil': {'material': 'PETG'}}, {'teil': Box(20, 20, 6) - Cylinder(1.25, 10)})
        e = M.pruefe(tmp)
        for id_ in ('M1', 'M2', 'M12', 'M13', 'M14', 'M15', 'M16', 'M19', 'M23'):
            r = [x for x in e if x['id'] == id_]
            assert len(r) == 1 and r[0]['stufe'] == 'uebersprungen' and 'soll.json' in r[0]['hinweis'], (id_, r)
        assert 'Kernloch M3' in finde(e, 'M12', 'Schrauben')['hinweis']
    with tempfile.TemporaryDirectory() as tmp:                # mit Eintrag: kein zusaetzliches Ueberspringen
        _projekt(tmp, {'teil': {'material': 'PETG', 'torsion': [{'art': 'rund', 'T_Nmm': 100, 'd_mm': 10}]}})
        e = M.pruefe(tmp)
        assert [x['stufe'] for x in e if x['id'] == 'M16'] == ['warnung'], [x for x in e if x['id'] == 'M16']


def test_m6_netz_an_echter_kehle():
    """Kehle rho 1,0 mm: Netz muss <= rho/3 = 0,333 mm sein. Globales Netz 2,0 ohne Box -> warnung (vorher keine
    Pruefung); Box mit innen 0,3 um das Teil -> ok; Box mit innen 0,5 -> warnung."""
    platte = Box(20, 20, 2, align=MIN)
    wand = Pos(0, 0, 2) * Box(2, 20, 10, align=MIN)
    teil = fillet((platte + wand).edges().filter_by(Axis.Y).group_by(Axis.Z)[1], 1.0)
    spec = {'koerper': [{'step': 'out/teil.step', 'material': 'PETG'}], 'lagerung': [{'wo': {}, 'fest': 'xyz'}],
            'netz': {'groesse': 2.0}}
    with tempfile.TemporaryDirectory() as tmp:
        _projekt(tmp, {'teil': {'material': 'PETG'}}, {'teil': teil}, fem={'f': (spec, {'lastfaelle': {}})})
        r = finde(M.pruefe(tmp), 'M6', 'Netz an Kerben (f)')
        assert r['stufe'] == 'warnung' and r['daten']['netz_zu_grob'][0]['netz'] == 'global', r
        assert r['daten']['netz_zu_grob'][0]['netz_mm'] == 2.0
        box = [-12, -12, -1, 12, 12, 14]                      # MIN = mittig in x/y, ab z 0
        for innen, soll_st in ((0.3, 'ok'), (0.5, 'warnung')):
            spec['netz'] = {'groesse': 2.0, 'felder': [{'box': box, 'innen': innen}]}
            _projekt(tmp, {'teil': {'material': 'PETG'}}, {'teil': teil}, fem={'f': (spec, {'lastfaelle': {}})})
            r = finde(M.pruefe(tmp), 'M6', 'Netz an Kerben (f)')
            assert r['stufe'] == soll_st, (innen, r)


# ================================================================ Kopien echter Projekte

def _kopie(name, tmp):
    src = os.path.join(PROJEKTE, name)
    dst = os.path.join(tmp, name)
    for sub in ('cad', 'out', 'print', 'fem', 'electronics'):
        s = os.path.join(src, sub)
        if not os.path.isdir(s):
            continue
        os.makedirs(os.path.join(dst, sub), exist_ok=True)
        for f in os.listdir(s):
            p = os.path.join(s, f)
            if os.path.isfile(p) and (f.endswith(('.json', '.step'))):
                shutil.copy2(p, os.path.join(dst, sub, f))
    return dst


def _soll_ergaenzen(pdir, teil, felder, projekt=None):
    p = os.path.join(pdir, 'cad', 'soll.json')
    s = json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}
    s.setdefault(teil, {}).update(felder)
    if projekt:
        s.setdefault('_projekt', {}).update(projekt)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(s, open(p, 'w', encoding='utf-8'))


def test_echt_schnapphaken():
    """Zunge L 15,6 x b 6 x t 1,8, Grat bei x = 14, PETG, auf der Seite gedruckt.
    M3 von Hand: d = 5*14^3/(3*2000*2,916) = 0,784 mm, FEM 0,930 -> +18,6 % (nachgiebiger Sockel, ARCHITEKTUR.md);
    sigma = 21,6 MPa, FEM-Spitze 267 MPa am Grat -> warnung (singulaer)."""
    with tempfile.TemporaryDirectory() as tmp:
        p = _kopie('schnapphaken', tmp)
        _soll_ergaenzen(p, 'haken', {
            'schnapper': [{'name': 'zunge', 'L_mm': 15.6, 'a_mm': 14, 'b_mm': 6, 't_mm': 1.8,
                           'hinterschnitt_mm': 1.0, 'achse': 'x', 'winkel_grad': 30, 'mu': 0.25}],
            'balken': [{'fall': 'kraft', 'last': 'grat', 'art': 'kragarm', 'L_mm': 15.6, 'a_mm': 14,
                        'b_mm': 6, 'h_mm': 1.8}]})
        e = M.pruefe(p)
        w = finde(e, 'M3', 'Weg')
        nah(w['grenze'], 0.7842, rel=1e-3)
        assert w['stufe'] == 'ok' and 0.15 < w['daten']['abweichung'] < 0.2, w
        s = finde(e, 'M3', 'Spannung')
        assert s['stufe'] == 'warnung' and s['daten']['verhaeltnis'] > 5, s
        assert finde(e, 'M1', 'zunge: Druckrichtung')['stufe'] == 'ok'        # druck (90,0,0) aus haken.py
        # FEM-Kontaktlauf: 5,31 N fuer 1,0 mm; Balken mit starrer Einspannung F = 2000*6*1,8^3*1/(4*14^3) = 6,38 N
        # (15 % steifer, wie ARCHITEKTUR.md) - M1 rechnet mit der Balkentheorie, also konservativ hoeher
        r = M.m1_schnapper({'L_mm': 15.6, 'a_mm': 14, 'b_mm': 6, 't_mm': 1.8, 'hinterschnitt_mm': 1.0, 'E_MPa': 2000})
        nah(r['F_N'], 6.3776, rel=1e-3)
        # Druckrichtung absichtlich falsch: Zunge stehend
        _soll_ergaenzen(p, 'haken', {'druckrichtung': 'x'})
        e = M.pruefe(p)
        assert finde(e, 'M1', 'zunge: Druckrichtung')['stufe'] == 'fehler'
        assert finde(e, 'M6', 'Scharfe Innenecken')['stufe'] == 'warnung'    # Wurzel ohne Rundung (haken.py)


def test_echt_frag_mich_alles():
    """Rueckschale PETG: Ruthex-Insert M2,5 (d_a 3,6, L 3,7 laut soll-Rechnung), 150 N wie fem/dom_ruthex.
    tau = 150/(pi*3,6*3,7) = 3,585 MPa."""
    with tempfile.TemporaryDirectory() as tmp:
        p = _kopie('frag-mich-alles-gehaeuse', tmp)
        _soll_ergaenzen(p, 'rueckschale', {'inserts': [{'name': 'pi_dom', 'd_aussen_mm': 3.6, 'laenge_mm': 3.7,
                                                        'kraft_N': 150}]})
        e = M.pruefe(p)
        ins = finde(e, 'M13', 'pi_dom')
        nah(ins['daten']['tau_MPa'], 3.585, rel=1e-3)
        assert ins['stufe'] in ('ok', 'warnung', 'fehler')
        assert finde(e, 'M6', 'Kehlradien', 'rueckschale')['stufe'] in ('ok', 'warnung')
        assert finde(e, 'M5', 'Rippen-Schlankheit', 'rueckschale')['stufe'] == 'warnung'   # Wand 36,6/2,1
        assert not any('Absturz' in x['titel'] for x in e)


def test_echt_testdose_deckel():
    """Deckel 60 x 40, Platte 2 mm, Finger 10 N mittig, Platine 3,0 mm darunter, PETG, gelenkig:
    D = 1558,4; r = 1,5 -> beta = 0,01484 + (0,01570-0,01484)/2 = 0,01527; w = 0,01527*10*40^2/1558,4 = 0,1568 mm."""
    with tempfile.TemporaryDirectory() as tmp:
        p = _kopie('testdose', tmp)
        _soll_ergaenzen(p, 'deckel', {'material': 'PETG', 'deckelbiegung': [
            {'a_mm': 60, 'b_mm': 40, 't_mm': 2, 'last_N': 10, 'last_art': 'punkt', 'abstand_mm': 3.0}]})
        e = M.pruefe(p)
        d = finde(e, 'M19', 'Deckeldurchbiegung')
        nah(d['wert'], 0.1568, rel=2e-3)
        assert d['stufe'] == 'ok'
        assert finde(e, 'M6', 'Kehlradien', 'unterschale')['stufe'] == 'ok'     # r 1 an Wand 2: rho/t = 0,5


def test_echt_alle_projekte_laufen():
    for name in ('testdose', 'schnapphaken', 'stifthalter-fem', 'frag-mich-alles-gehaeuse', 'bodenklima-sondenkopf'):
        e = M.pruefe(os.path.join(PROJEKTE, name))
        assert e, name
        assert not any('Absturz' in x['titel'] for x in e), (name, [x for x in e if 'Absturz' in x['titel']])
        assert all(x['stufe'] in M.RANG for x in e)
        assert all(x['id'].startswith('M') for x in e)


if __name__ == '__main__':
    fehler = 0
    for n, f in list(globals().items()):
        if n.startswith('test_'):
            try:
                f()
                print('ok  ', n)
            except Exception as ex:  # noqa: BLE001
                fehler += 1
                import traceback
                traceback.print_exc()
                print('FEHL', n, type(ex).__name__, ex)
    print('alle ok' if not fehler else f'{fehler} Tests fehlgeschlagen')
    sys.exit(1 if fehler else 0)
