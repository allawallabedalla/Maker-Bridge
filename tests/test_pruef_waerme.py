"""Gegentests Waerme W1-W10 (mb2/pruefungen/waerme.py) und der neuen Elmer-Felder (mb2/fem.py waerme()).
Jede Formel hat mindestens einen von Hand nachgerechneten Fall. Aufruf aus maker-bridge-2/:
    .venv/Scripts/python.exe tests/test_pruef_waerme.py          (alles, ~1 min mit Elmer)
    .venv/Scripts/python.exe tests/test_pruef_waerme.py schnell  (nur Formeln + Pruefungen ohne Elmer)"""
import json
import math
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mb2 import fem                                   # noqa: E402
from mb2.pruefungen import waerme as W                # noqa: E402

SIG = 5.670374419e-8
TMP = []


def nah(a, b, rel=0.01, abs_=0.0):
    assert abs(a - b) <= max(rel * abs(b), abs_), f'{a} != {b} (rel {rel}, abs {abs_})'


def projekt(name, faelle=None, soll=None, pruef=None, slice_=None, ini=None):
    d = tempfile.mkdtemp(prefix=f'mb2w_{name}_')
    TMP.append(d)
    for u in ('fem', 'cad', 'out', 'print'):
        os.makedirs(os.path.join(d, u))
    for f, s in (faelle or {}).items():
        json.dump(s, open(os.path.join(d, 'fem', f + '.json'), 'w'))
    if soll:
        json.dump(soll, open(os.path.join(d, 'cad', 'soll.json'), 'w'))
    for t, p in (pruef or {}).items():
        json.dump(p, open(os.path.join(d, 'out', t + '.pruefung.json'), 'w'))
    if ini:
        open(os.path.join(d, 'print', 'cfg.ini'), 'w').write(ini)
        slice_ = dict(slice_ or {}, config=os.path.join(d, 'print', 'cfg.ini'))
    if slice_:
        json.dump(slice_, open(os.path.join(d, 'print', 'slice.json'), 'w'))
    return d


def nach_id(liste, i, teil=None):
    r = [e for e in liste if e['id'] == i and (teil is None or e.get('teil') == teil)]
    assert r, f'{i} fehlt'
    return r


# ---------------------------------------------------------------- Formeln von Hand

def test_w1_h_frei_hand():
    # 1,42 * (10 K / 0,1 m)^0,25 = 1,42 * 3,1623 = 4,490
    nah(W.h_frei(10, 0.1), 4.4904, 1e-3)
    # Gegenprobe ueber Nu = 0,56 Ra^1/4 mit Luft 300 K: Ra = 9,81/305*10*0,001/(1,589e-5*2,25e-5) = 9,0e5
    Ra = W.rayleigh(10, 0.1, 305)
    nah(Ra, 9.0e5, 0.01)
    h_nu = 0.56 * Ra ** 0.25 * 0.0263 / 0.1
    nah(W.h_frei(10, 0.1), h_nu, 0.03)        # SI-Umrechnung 1,42 aus dem Katalog bestaetigt


def test_w2_h_strahlung_hand():
    # 0,9 * sigma * (300 + 300) * (300^2 + 300^2) = 5,511 W/m2K ("~5,5 bei 300 K", Katalog)
    nah(W.h_strahlung(0.9, 26.85, 26.85), 0.9 * SIG * 600 * 180000, 1e-9)
    nah(W.h_strahlung(0.9, 26.85, 26.85), 5.511, 1e-3)


def test_w5_eps_eff_k_spalt_hand():
    nah(W.eps_eff(0.9, 0.9), 0.81818, 1e-4)                         # Katalog ~0,82
    # 0,026 + 4*0,8182*5,670e-8*310^3*0,002 = 0,026 + 0,01106 = 0,03706
    nah(W.k_spalt(0.002, 310, W.eps_eff(0.9, 0.9)), 0.03706, 1e-3)


def test_w4_platte_hand():
    # Kreisrippe fuer grosses m*a: K1/K0 -> 1 + 1/(2x)  ->  R*2*pi*k*t*m*a = 1/(1 + 1/(2x))
    k, t, h = 0.2, 0.002, 6.0
    m = math.sqrt(2 * h / (k * t))
    a = 50 / m
    nah(W.r_platte(k, t, h, a) * 2 * math.pi * k * t * m * a, 1 / (1 + 1 / 100), 2e-4)
    # Netz ohne Kontakt = 1/(hA): 0,5 W / (6 * 345e-6) = 241,5 K
    nah(W.netz_quelle(0.5, 6.0, 345e-6, 0.2, 0.002, 0.0, 6.0), 0.5 / (6 * 345e-6), 1e-9)


def test_w6_sonne_hand():
    # 0,5 * 1000 * 4e-4 / (10 * 2,4e-3) = 8,333 K
    nah(W.dT_sonne(0.5, 1000, 4e-4, 10, 2.4e-3), 8.3333, 1e-4)


def test_w7_biot_tau_hand():
    nah(W.biot(10, 0.001, 0.2), 0.05, 1e-9)
    # rho c V = 1270*1100*1e-6 = 1,397 J/K;  / (10 * 6e-3) = 23,28 s
    nah(W.zeitkonstante(1270 * 1100 * 1e-6, 10, 6e-3), 23.283, 1e-4)


def test_w8_quelle_hand():
    # 62500 W/m3 * 0,004^2 / (8*0,2) = 0,625 K; einseitig 4x = 2,5 K = qL^2/2k (waerme_check)
    nah(W.dT_quelle(62500, 0.004, 0.2), 0.625, 1e-9)


def test_w9_rippe_hand():
    # PETG-Rippe 20 x 2 x 10 mm, h 10: m = sqrt(10*0,044/(0,2*4e-5)) = 234,5; mL = 2,345; tanh/mL = 0,4187
    nah(W.rippe_eta(10, 0.2, 0.002, 0.02, 0.01), math.tanh(2.3452) / 2.3452, 1e-3)
    assert W.rippe_eta(10, 0.2, 0.002, 0.02, 0.01) < 0.5
    assert W.rippe_eta(10, 200, 0.002, 0.02, 0.01) > 0.99            # Alu lohnt


def test_w10_schicht_hand():
    # 1270*1100*2e-4/100 = 2,794 s * ln(225/55) = 1,4088 -> 3,936 s
    nah(W.abkuehlzeit_schicht(1270, 1100, 2e-4, 100, 250, 25, 80), 3.936, 1e-3)


# ---------------------------------------------------------------- Pruefungen ohne Elmer (synthetische Ergebnisse)

def _erg(h=6.0, T_inf=25.0, T_konv=40.0, mit_strahlung=False, abw=0.0):
    rb = {'h_W_m2K': h, 'T_umgebung_C': T_inf, 'kelvin': mit_strahlung}
    if mit_strahlung:
        rb['strahlung'] = {'emission': 0.9, 'himmel_anteil_mittel': 1.0}
    return {'T_max_C': 60.0, 'T_min_C': 25.0, 'T_mittel_konvektion_C': T_konv, 'randbedingungen': rb,
            'flaechen_mm2': {'konvektion': 10000.0, 'fest': 0.0, 'konvektion_ohne_sicht_nach_aussen': 0.0},
            'geometrie': {'bbox_mm': [50.0, 50.0, 20.0]},
            'energiebilanz': {'P_nenn_W': 1.0, 'P_netz_W': 1.0, 'Q_sonne_W': 0.0, 'Q_konvektion_W': 1.0 + abw,
                              'Q_strahlung_W': 0.0, 'Q_feste_temperatur_W': 0.0, 'Q_aus_W': 1.0 + abw,
                              'abweichung': abw},
            'koerper_info': {'schale': {'material': 'PETG', 'volumen_mm3': 10000.0, 'bbox_mm': [50, 50, 20],
                                        'waerme_W': 0.0, 'T_max_C': 60, 'T_min_C': 25, 'T_mittel_C': 40,
                                        'A_konvektion_mm2': 10000.0, 'A_fest_mm2': 0.0, 'kontakt_mm2': {}}}}


def _mit_erg(name, erg, spec=None):
    spec = spec or {'koerper': [{'box': [0, 0, 0, 1, 1, 1], 'material': 'PETG'}], 'konvektion': {'h_W_m2K': 6}}
    d = projekt(name, {'w': spec})
    json.dump(erg, open(os.path.join(d, 'fem', 'w.erg.json'), 'w'))
    return d


def test_w1_stufen():
    # dT = 15 K, L = 20 mm: h_c = 1,42*(15/0,02)^0,25 = 7,46; h_r(40/25 C) = 0,9 sigma (313,15+298,15)(..) = 5,79
    h_c = 1.42 * (15 / 0.02) ** 0.25
    nah(W.h_frei(15, 0.02), h_c, 1e-9)
    r = nach_id(W.pruefe(_mit_erg('w1a', _erg(h=10))), 'W1')[0]
    assert r['stufe'] == 'ok', r
    r = nach_id(W.pruefe(_mit_erg('w1b', _erg(h=30))), 'W1')[0]             # > 1,3*(h_c + h_r) = 17,2
    assert r['stufe'] == 'warnung' and 'optimistisch' in r['hinweis'], r
    r = nach_id(W.pruefe(_mit_erg('w1c', _erg(h=12, mit_strahlung=True))), 'W1')[0]   # Strahlung + 12 > 1,3*7,46
    assert r['stufe'] == 'warnung' and 'doppelt' in r['hinweis'], r
    r = nach_id(W.pruefe(_mit_erg('w1d', _erg(h=3))), 'W1')[0]                # < 7,46/1,3
    assert r['stufe'] == 'warnung' and 'konservativ' in r['hinweis'], r


def test_w3_stufen():
    assert nach_id(W.pruefe(_mit_erg('w3a', _erg(abw=0.01))), 'W3')[0]['stufe'] == 'ok'
    assert nach_id(W.pruefe(_mit_erg('w3b', _erg(abw=0.03))), 'W3')[0]['stufe'] == 'warnung'
    assert nach_id(W.pruefe(_mit_erg('w3c', _erg(abw=-0.08))), 'W3')[0]['stufe'] == 'fehler'


def test_w5_ohne_innenluft_warnt():
    e = _erg()
    e['flaechen_mm2']['konvektion_ohne_sicht_nach_aussen'] = 3000.0
    r = nach_id(W.pruefe(_mit_erg('w5', e)), 'W5')[0]
    assert r['stufe'] == 'warnung', r
    # Innenluft nur als kleine Tasche erfasst (Hohlraum durch Lueftung offen): darf den Alarm nicht unterdruecken
    e['randbedingungen']['innenluft'] = {'V_mm3': 143.5, 'eps_eff': 0.818, 'spalt_mm': 1.0, 'T_mittel_C': 40.0,
                                         'Nu': 1.0, 'k_W_mK': 0.03, 'Ra_spalt': 1.0, 'spalt_quelle': '2V/A'}
    r = nach_id(W.pruefe(_mit_erg('w5b', e)), 'W5')[0]
    assert r['stufe'] == 'warnung' and 'nur 144 mm3' in r['hinweis'], r


def _w6(farbe, T_max=40.0):
    s = {'_projekt': {'aussen': True, 'farbe': farbe, 'T_max_C': T_max, 'material': 'PETG'}}
    d = projekt('w6' + farbe, soll=s, pruef={'gehaeuse': {'bbox_mm': [100, 100, 20], 'volumen_mm3': 50000}})
    return [r for r in W.pruefe(d) if r['id'] == 'W6'][0]


def _w6_hand(alpha, T_umg=40.0):
    A_proj = math.sqrt(0.01 ** 2 + 0.002 ** 2 + 0.002 ** 2)
    A_ges = 0.028
    dT = 10.0
    for _ in range(50):
        Ts, Ti = T_umg + dT + 273.15, T_umg + 273.15
        h = 1.42 * (dT / 0.02) ** 0.25 + 0.9 * SIG * (Ts + Ti) * (Ts ** 2 + Ti ** 2)
        dT = alpha * 1000 * A_proj / (h * A_ges)
    return dT


def test_w6_sonne_stufen():
    # Regel seit 15.11.2026 wie D1 (Tg - T >= 30 ok, >= 20 warnung, sonst fehler) und T = max(Box-Rechnung,
    # D1-Teiltemperatur realterme: Luft + alpha * 1000 / 25 W/m2K)
    r = _w6('weiss')
    nah(r['daten']['dT_sonne_K'], _w6_hand(0.25), 0.005)
    # Box ~8 K -> 48 C; realterme 0,25 * 40 = 10 K -> 50 C gilt; PETG 80 - 50 = 30 K -> ok
    nah(r['daten']['dT_sonne_realterme_K'], 10.0, 1e-9)
    assert r['stufe'] == 'ok' and abs(r['wert'] - 50.0) < 1e-6, r
    r = _w6('schwarz')
    nah(r['daten']['dT_sonne_K'], _w6_hand(0.95), 0.005)
    # Box ~25 K -> 65 C (frueher warnung, Grenze Tg - 10); realterme 0,95 * 40 = 38 K -> 78 C: 2 K unter Tg -> fehler
    assert r['stufe'] == 'fehler' and abs(r['wert'] - 78.0) < 1e-6, r
    assert _w6('pink')['stufe'] == 'fehler'                   # Farbe unbekannt -> 0,95 wie schwarz (frueher warnung)
    assert _w6('schwarz', 55)['stufe'] == 'fehler'            # 55 + 38 = 93 > Tg
    # hellgrau 0,5 – seit 15.11. EINE Farbtabelle (realterme): Box 14,4 K, realterme 0,5*1000/25 = 20 K -> 40 C;
    # PETG Tg 80 - 40 = 40 K >= 30 -> ok
    r = _w6('hellgrau', 20.0)
    assert r['daten']['alpha'] == 0.5 and abs(r['wert'] - 40.0) < 1e-6 and r['stufe'] == 'ok', r


def test_w6_gleich_d1():
    # dieselbe Teiltemperatur in W6 und D1 (Befund Scheinsicherheit: D1 ohne Sonne, W6 mit)
    from mb2.pruefungen import dauer
    s = {'_projekt': {'aussen': True, 'farbe': 'rot', 'T_max_C': 30.0, 'material': 'PETG'}, 'gehaeuse': {}}
    d = projekt('w6d1', soll=s, pruef={'gehaeuse': {'bbox_mm': [100, 100, 20], 'volumen_mm3': 50000}})
    w6 = [r for r in W.pruefe(d) if r['id'] == 'W6'][0]
    d1 = [r for r in dauer.pruefe(d) if r['id'] == 'D1' and r.get('teil') == 'gehaeuse'][0]
    # rot alpha 0,65 -> 26 K -> 56 C; PETG 80 - 56 = 24 K -> beide warnung
    nah(w6['daten']['T_realterme_C'], 56.0, 1e-9)
    nah(d1['daten']['T_teil_C'], 56.0, 1e-9)
    assert w6['stufe'] == d1['stufe'] == 'warnung', (w6, d1)


def test_w9_rippen():
    s = {'_projekt': {'material': 'PETG'},
         'kuehler': {'rippen': [{'name': 'r1', 'L_mm': 10, 't_mm': 2, 'b_mm': 20, 'h_W_m2K': 10},
                                {'name': 'alu', 'L_mm': 10, 't_mm': 2, 'b_mm': 20, 'h_W_m2K': 10, 'material': 'ALU'}]}}
    r = nach_id(W.pruefe(projekt('w9', soll=s)), 'W9')
    assert r[0]['stufe'] == 'warnung' and abs(r[0]['wert'] - 0.4187) < 1e-3, r[0]
    assert r[1]['stufe'] == 'ok', r[1]


def test_w10_schicht():
    ini = 'slowdown_below_layer_time = 9\nmin_print_speed = 15\ntemperature = 250\nlayer_height = 0.2\n'
    sl = {'stats': {'filament_type': 'PETG', 'layer_height': '0.2'}}
    pr = {'turm': {'bbox_mm': [5, 5, 40], 'volumen_mm3': 1000}, 'dose': {'bbox_mm': [60, 40, 25], 'volumen_mm3': 13800}}
    d = projekt('w10', soll={'_projekt': {'h_luefter_W_m2K': 100}}, pruef=pr, slice_=sl, ini=ini)
    r = {e['teil']: e for e in W.pruefe(d) if e['id'] == 'W10'}
    # Turm: Querschnitt 25 mm2 -> Weg 25/0,45 = 55,6 mm -> 3,7 s bei 15 mm/s < 3,94 s Abkuehlung (c_p PETG 1100)
    nah(r['turm']['wert'], 25 / 0.45 / 15, 1e-3)
    assert r['turm']['stufe'] == 'warnung', r['turm']
    assert r['dose']['stufe'] == 'ok', r['dose']                 # Mindestschichtzeit 9 s
    d2 = projekt('w10b', pruef=pr, slice_=sl, ini=ini)            # ohne h_Luefter -> uebersprungen
    assert all(e['stufe'] == 'uebersprungen' for e in W.pruefe(d2) if e['id'] == 'W10')


def test_fehlende_eingaben_kein_absturz():
    d = projekt('leer')
    r = W.pruefe(d)
    assert r and all(e['stufe'] == 'uebersprungen' for e in r), r
    # altes Ergebnis ohne Zusatzfelder -> uebersprungen mit Hinweis
    d = _mit_erg('alt', {'T_max_C': 50, 'bewertung': {}})
    assert all(e['stufe'] == 'uebersprungen' for e in W.pruefe(d))
    from mb2 import pruefungen
    erg = pruefungen.alle(d, module=('waerme',))
    assert erg['ok'] and 'waerme' in erg['module']


# ---------------------------------------------------------------- Elmer (synthetisch, von Hand nachgerechnet)

def _rechne(name, spec):
    d = projekt(name, {name: spec})
    return d, fem.waerme(d, name)


def test_elmer_strahlung_alu():
    # isothermer Alublock 20x20x4, 0,5 W, nur Strahlung eps 0,9: T^4 = T_inf^4 + P/(eps sigma A), A = 1120 mm2
    d, e = _rechne('str', {'koerper': [{'box': [0, 0, 0, 20, 20, 4], 'material': 'ALU', 'waerme_W': 0.5}],
                           'netz': {'groesse': 2.0}, 'konvektion': {'h_W_m2K': 0.0, 'T_umgebung_C': 25},
                           'strahlung': {'emission': 0.9}})
    T = (298.15 ** 4 + 0.5 / (0.9 * SIG * 1.12e-3)) ** 0.25 - 273.15         # 86,06 C
    nah(e['T_max_C'], T, abs_=0.1)
    assert abs(e['energiebilanz']['abweichung']) < 0.005
    nah(e['randbedingungen']['strahlung']['himmel_anteil_mittel'], 1.0, 0.01)
    assert nach_id(W.pruefe(d), 'W2')[0]['stufe'] == 'ok'


def test_elmer_konvektion_auto():
    # Alu-Wuerfel 20 mm, 0,5 W: P = 1,42 A dT^1,25 L^-0,25 -> dT = (P L^0,25/(1,42 A))^0,8 = 24,74 K
    d, e = _rechne('auto', {'koerper': [{'box': [0, 0, 0, 20, 20, 20], 'material': 'ALU', 'waerme_W': 0.5}],
                            'netz': {'groesse': 3.0}, 'konvektion': {'auto': True, 'T_umgebung_C': 25}})
    nah(e['T_max_C'] - 25, (0.5 * 0.02 ** 0.25 / (1.42 * 2.4e-3)) ** 0.8, 0.01)
    assert len(e['randbedingungen']['konvektion_auto']['verlauf']) <= 3          # Fixpunkt h^0,2*h_k^0,8
    assert nach_id(W.pruefe(d), 'W1')[0]['stufe'] == 'ok'


def test_elmer_sonne_schatten():
    # Dach 30x30x2 ueber Wuerfel: Dach nimmt 0,5*1000*900e-6 = 0,45 W auf, dT = 0,45/(10*(1800+240)e-6) = 22,06 K;
    # der Wuerfel liegt im Schatten und bleibt auf 25 C
    d, e = _rechne('sonne', {'koerper': [{'box': [0, 0, 0, 20, 20, 20], 'material': 'ALU', 'name': 'wuerfel'},
                                         {'box': [-5, -5, 30, 25, 25, 32], 'material': 'ALU', 'name': 'dach'}],
                             'netz': {'groesse': 3.0}, 'konvektion': {'h_W_m2K': 10.0, 'T_umgebung_C': 25},
                             'sonne': {'G_W_m2': 1000, 'absorption': 0.5}})
    nah(e['T_max_je_koerper_C']['dach'] - 25, 0.45 / (10 * 2040e-6), 0.02)
    assert e['T_max_je_koerper_C']['wuerfel'] < 25.1
    nah(e['randbedingungen']['sonne']['P_W'], 0.45, 0.01)
    assert abs(e['energiebilanz']['abweichung']) < 0.005


def test_elmer_innenluft_spalt():
    # Spalt 2 mm Luft zwischen Alu-Platten 20x20, oben 0,1 W, unten 25 C fest, Rest adiabat:
    # dT = P delta/(k A), k = 0,026 + 4 eps_eff sigma T_m^3 delta (Fixpunkt von Hand)
    d, e = _rechne('spalt', {'koerper': [{'box': [0, 0, 0, 20, 20, 2], 'material': 'ALU', 'name': 'unten'},
                                         {'box': [0, 0, 4, 20, 20, 6], 'material': 'ALU', 'name': 'oben',
                                          'waerme_W': 0.1}],
                             'netz': {'groesse': 1.5}, 'konvektion': {'h_W_m2K': 0.0, 'T_umgebung_C': 25},
                             'flaechen': [{'wo': {'ebene': ['z', 0.0]}, 'temperatur_C': 25}],
                             'innenluft': {'box': [0, 0, 2, 20, 20, 4]}})
    Tm = 298.15
    for _ in range(30):
        k = 0.026 + 4 * W.eps_eff(0.9, 0.9) * SIG * Tm ** 3 * 0.002
        dT = 0.1 * 0.002 / (k * 4e-4)
        Tm = 298.15 + dT / 2
    il = e['randbedingungen']['innenluft']
    nah(il['spalt_mm'], 2.0, 1e-3)                            # 2V/A mit benetzter Flaeche
    nah(il['dT_K'], dT, 0.02)                                 # 13,69 K
    assert abs(e['energiebilanz']['abweichung']) < 0.005
    assert nach_id(W.pruefe(d), 'W5')[0]['stufe'] == 'ok'


def _hohlkasten(innenluft):
    w = 2.0
    wand = [[0, 0, 0, 30, 30, w], [0, 0, 20 - w, 30, 30, 20], [0, 0, w, w, 30, 20 - w], [30 - w, 0, w, 30, 30, 20 - w],
            [w, 0, w, 30 - w, w, 20 - w], [w, 30 - w, w, 30 - w, 30, 20 - w]]
    k = [{'box': b, 'material': 'PETG', 'name': f'w{i}'} for i, b in enumerate(wand)]
    k.append({'box': [10, 10, w, 20, 20, w + 2], 'material': 'FR4', 'name': 'quelle', 'waerme_W': 0.3})
    s = {'koerper': k, 'netz': {'groesse': 2.0}, 'konvektion': {'h_W_m2K': 6.0, 'T_umgebung_C': 25}, 'strahlung': {}}
    if innenluft:
        s['innenluft'] = True
    return s


def test_elmer_hohlraum():
    # geschlossener Kasten 30x30x20, Wand 2: Hohlraum 26*26*16 - Quelle 10*10*2 = 10616 mm3, Flaeche 3096 mm2
    d, e = _rechne('hohl', _hohlkasten(True))
    nah(e['randbedingungen']['innenluft']['V_mm3'], 26 * 26 * 16 - 200, 0.005)
    assert abs(e['energiebilanz']['abweichung']) < 0.01
    d2, e2 = _rechne('hohl_ohne', _hohlkasten(False))
    # Innenflaechen ohne Sicht: Hohlraum 2*26*26 + 4*26*16 = 3016 - Quellenfuss 100 + Quelle oben 100 + Seiten 80
    nah(e2['flaechen_mm2']['konvektion_ohne_sicht_nach_aussen'], 3016 - 100 + 100 + 80, 0.02)
    assert nach_id(W.pruefe(d2), 'W5')[0]['stufe'] == 'warnung'
    assert nach_id(W.pruefe(d), 'W5')[0]['stufe'] == 'ok'


def test_elmer_bilanz_fest_und_konvektion():
    # gemischte Raender (feste Temperatur + Konvektion): Bilanz muss schliessen (Knotenlasten nur an freien Knoten)
    d, e = _rechne('mix', {'koerper': [{'box': [0, 0, 0, 20, 20, 4], 'material': 'PETG', 'waerme_W': 0.2}],
                           'netz': {'groesse': 1.0}, 'konvektion': {'h_W_m2K': 10.0, 'T_umgebung_C': 25},
                           'flaechen': [{'wo': {'ebene': ['z', 0.0]}, 'temperatur_C': 30}]})
    eb = e['energiebilanz']
    assert abs(eb['abweichung']) < 1e-3, eb
    assert eb['Q_feste_temperatur_W'] > 0 and eb['Q_konvektion_W'] > 0


# ---------------------------------------------------------------- echte Projekte

def test_testdose_unveraendert():
    """Standardfaelle ohne neue Felder: T wie vor der Erweiterung (111,57 / 27,55 C), Bilanz geschlossen."""
    from mb2 import befehle
    e = befehle.fem_waerme('testdose', 'waerme_check')
    nah(e['T_max_C'], 27.55, abs_=0.005)
    nah(e['T_max_C'], 27.5, 0.005)                             # analytisch 25 + qL^2/2k
    e = befehle.fem_waerme('testdose', 'waerme')
    nah(e['T_max_C'], 111.57, abs_=0.005)
    assert abs(e['energiebilanz']['abweichung']) < 1e-3
    sif = open(os.path.join(befehle.pdir('testdose'), 'fem', 'waerme', 'fall.sif')).read()
    assert 'Radiation' not in sif and 'Kelvin' not in sif and 'Heat Flux' not in sif
    r = W.pruefe(befehle.pdir('testdose'))
    assert nach_id(r, 'W3', 'waerme')[0]['stufe'] == 'ok'
    assert nach_id(r, 'W4', 'waerme')[0]['stufe'] == 'ok'      # Netz Quelle auf Platte +-25 %
    assert not [x for x in r if x['stufe'] == 'fehler'], [x for x in r if x['stufe'] == 'fehler']


def test_andere_projekte_laufen():
    from mb2 import befehle
    for p in ('frag-mich-alles-gehaeuse', 'schnapphaken', 'stifthalter-fem', 'bodenklima-sondenkopf'):
        r = W.pruefe(befehle.pdir(p))
        assert r and all(x['stufe'] in ('ok', 'info', 'warnung', 'fehler', 'uebersprungen') for x in r)
        for x in r:
            assert x['id'].startswith('W') and x['quelle'], x


SCHNELL = ('test_w', 'test_fehlende')

def test_w8_quelle_im_koerper_hand():
    """1 W in 10 x 10 x 2 mm Metall (k aus MATERIAL): q3 = 1 W / 200e-9 m^3 = 5e6 W/m^3, L = 2 mm,
    dT = q3 L^2 / (8 k). Ohne Waermeleitung: uebersprungen."""
    from mb2.material import MATERIAL
    mat = next(m for m, v in MATERIAL.items() if (v.get('waermeleitung_W_mK') or 0) > 50)
    k = MATERIAL[mat]['waermeleitung_W_mK']
    erg = {'koerper_info': {'block': {'waerme_W': 1.0, 'material': mat, 'volumen_mm3': 200.0, 'bbox_mm': [10, 10, 2],
                                      'T_max_C': 30.0, 'T_min_C': 29.0}}}
    e = W._w8('fall', {}, erg)[0]
    assert e['id'] == 'W8' and e['stufe'] == 'info', e
    assert abs(e['wert'] - 5e6 * 0.002 ** 2 / (8 * k)) <= 0.0005, (e['wert'], k)      # auf 3 Stellen gerundet
    erg['koerper_info']['block']['material'] = 'GIBT_ES_NICHT'
    assert W._w8('fall', {}, erg)[0]['stufe'] == 'uebersprungen'


if __name__ == '__main__':
    schnell = 'schnell' in sys.argv
    try:
        for n, f in list(globals().items()):
            if n.startswith('test_') and callable(f) and (not schnell or n.startswith(SCHNELL)):
                f()
                print('ok', n)
    finally:
        for d in TMP:
            shutil.rmtree(d, ignore_errors=True)
