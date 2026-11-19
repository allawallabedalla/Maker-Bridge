"""Gegentests Katalog S1-S8 (mb2/pruefungen/schwingung.py). Aufruf: python tests/test_pruef_schwingung.py
Jede Formel hat einen Handrechen-Gegentest (Zahlen im Kommentar von Hand gerechnet), dazu synthetische Projekte
(temporaerer Ordner) und die echten Projekte unter projects/ (nur lesen, nichts schreiben)."""
import copy
import json
import math
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _nachweis import beispielprojekt, lang  # noqa: E402,F401

from mb2.pruefungen import STUFEN, schwingung as S, soll  # noqa: E402

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJ = os.path.join(HIER, 'projects')


def nah(a, b, rel=1e-3):
    return abs(a - b) <= rel * abs(b)


def nach_id(liste, i, teil='*'):
    return [e for e in liste if e['id'] == i and (teil == '*' or e.get('teil') == teil)]


# ------------------------------------------------------------------ Handrechnungen
def test_s1_formel():
    # f = sqrt(9810 mm/s2 / 1 mm)/(2 pi) = 99,05/6,2832 = 15,764 Hz; delta 0,01 mm -> 157,64 Hz
    assert nah(S.f_aus_durchbiegung(1.0), 15.764)
    assert nah(S.f_aus_durchbiegung(0.01), 157.64)
    # Einmassen: k 100 N/mm = 1e5 N/m, m 0,1 kg -> sqrt(1e6)/2pi = 159,15 Hz
    assert nah(S.f_einmassen(100.0, 0.1), 159.15)


def test_s3_kragarm():
    # PETG E 2000, rho 1270, L 20, b 5, t 2: I = 5*8/12 = 3,333 mm4, A = 10 mm2
    # EI = 2e9*3,333e-12 = 6,667e-3 N m2; rho A L^4 = 1270*1e-5*1,6e-7 = 2,032e-9
    # sqrt(3,281e6) = 1811,3; * 1,8751^2/2pi = 0,55959 -> 1013,6 Hz
    f = S.kragarm_f(2000, 1270, 20, 5 * 8 / 12, 10)
    assert nah(f, 1013.6, 2e-3), f
    # Spitzenmasse 1 g: k = 3EI/L^3 = 3*6,667e-3/8e-6 = 2500 N/m; m = 1e-3 + 0,2357*0,254e-3 = 1,0599e-3 kg
    # f = sqrt(2500/1,0599e-3)/2pi = 1535,8/6,2832 = 244,4 Hz
    assert nah(S.kragarm_f(2000, 1270, 20, 5 * 8 / 12, 10, 1e-3), 244.4, 2e-3)
    # Durchbiegung Eigengewicht: q = 1270*10e-9 kg/mm*9,81 = 1,2459e-4 N/mm; qL^4/8EI = 1,2459e-4*160000/(8*6666,7)
    # = 3,738e-4 mm -> f(S1) = 15,764/sqrt(3,738e-4) = 815,4 Hz = 0,804 * S3 (erwartet ~ 2,828/3,516 = 0,804)
    d = S.kragarm_durchbiegung(2000, 1270, 20, 5 * 8 / 12, 10)
    assert nah(d, 3.738e-4, 2e-3), d
    assert nah(S.f_aus_durchbiegung(d) / f, 2 * math.sqrt(2) / S.BETA1 ** 2, 1e-3)


def test_s4_fallstoss():
    # m 0,1 kg, k 100 N/mm, h 1000 mm: mg = 0,981 N, delta = 0,00981 mm
    # F = 0,981*(1 + sqrt(1 + 2000/0,00981)) = 0,981*(1 + 451,53) = 443,9 N; Naeherung sqrt(2mghk) = 442,9 N
    F, d = S.fallstoss(0.1, 100.0, 1000.0)
    assert nah(d, 0.00981) and nah(F, 443.9, 1e-3), (F, d)
    assert nah(F, math.sqrt(2 * 0.1 * 9.81 * 1.0 * 1e5), 0.01)


def test_luft():
    c, rho, mu = S.luft(20.0)
    assert nah(c, 343.2e3, 1e-3) and nah(rho, 1.204, 2e-3) and nah(mu, 1.81e-5, 5e-3)


def test_s5_helmholtz():
    # 1 Loch d 10 (a 5, S 78,54), l 2, V 1e5 mm3: l_eff = 2 + 8 = 10; f = 343200/2pi*sqrt(78,54/1e6) = 54622*0,0088623
    # = 484,1 Hz
    c = 343.2e3
    f = S.helmholtz(1e5, [(math.pi * 25, 5.0)], 2.0, c)
    assert nah(f, 484.1, 1e-3), f
    # 4 gleiche Loecher parallel = 4-fache Flaeche -> f doppelt
    assert nah(S.helmholtz(1e5, [(math.pi * 25, 5.0)] * 4, 2.0, c), 2 * f)


def test_s6_box():
    # f_s 600, V_as 50000 mm3, V 1e5: f_c = 600*sqrt(1,5) = 734,8 Hz
    assert nah(S.box_fc(600, 5e4, 1e5), 734.85)
    # C = 1e-4 m3/(1,204*343,2^2) = 1e-4/141813 = 7,051e-10 m3/Pa
    assert nah(S.nachgiebigkeit(1e5, 1.204, 343.2e3), 7.051e-10, 2e-3)


def test_s7_s8():
    # L 100 mm: 343,2/(2*0,1) = 1716 Hz
    assert nah(S.stehwelle(100.0, 343.2e3), 1716.0)
    # delta_v(200 Hz) = sqrt(1,81e-5/(1,204*1256,6)) = sqrt(1,1963e-8) = 1,0938e-4 m = 0,1094 mm (Katalog 0,11)
    assert nah(S.grenzschicht_mm(200, 1.204, 1.81e-5), 0.1094, 2e-3)
    # Lochform: Kreis r 1 -> rund 1; Rechteck 2 x 20 (A 40, P 44) -> Breite 2
    f = S.lochform(math.pi, 2 * math.pi)
    assert f[0] == 'rund' and nah(f[1], 1.0)
    f = S.lochform(40.0, 44.0)
    assert f[0] == 'schlitz' and nah(f[1], 2.0) and nah(f[2], 20.0)
    assert nah(S.halbe_kleinste(f), 1.0)


# ------------------------------------------------------------------ synthetische Projekte
def _projekt(soll_daten, faelle=None, teile=None):
    d = tempfile.mkdtemp(prefix='mb2_schw_')
    for sub in ('cad', 'out', 'fem'):
        os.makedirs(os.path.join(d, sub))
    json.dump(soll_daten, open(os.path.join(d, 'cad', 'soll.json'), 'w'))
    for name, (spec, erg) in (faelle or {}).items():
        json.dump(spec, open(os.path.join(d, 'fem', name + '.json'), 'w'))
        json.dump(erg, open(os.path.join(d, 'fem', name + '.erg.json'), 'w'))
    for name, (teil, vol) in (teile or {}).items():
        if teil is not None:
            from build123d import export_step
            export_step(teil, os.path.join(d, 'out', name + '.step'))
        json.dump({'teil': name, 'volumen_mm3': vol}, open(os.path.join(d, 'out', name + '.pruefung.json'), 'w'))
    return d


def test_leer_alles_uebersprungen():
    d = _projekt({})
    try:
        r = S.pruefe(d)
        assert r and all(e['stufe'] == 'uebersprungen' and e['hinweis'] for e in r), r
        assert {e['id'] for e in r} >= {'S4', 'S5', 'S6', 'S7', 'S8'}
    finally:
        shutil.rmtree(d)


def test_s1_fem_schwerkraft_s2_s3_s4():
    # Kragarm-Teil 'arm': FEM mit Eigengewicht delta 0,01 mm -> 157,6 Hz; zweiter Lastfall 5 N, k 50 N/mm, sigma 10 MPa
    spec = {'koerper': [{'step': 'out/arm.step', 'material': 'PETG', 'name': 'arm'}], 'schwerkraft': True,
            'lasten': [{'name': 'schwerkraft', 'schwerkraft': True, 'kraft_N': [0, 0, 0]},
                       {'name': 'last', 'kraft_N': [0, 0, -5.0]}]}
    erg = {'koerper': ['arm'], 'lastfaelle': {
        'schwerkraft': {'kraft_N': [0, 0, 0], 'max_vonMises_MPa': 0.01, 'max_verschiebung_mm': 0.01},
        'last': {'kraft_N': [0, 0, -5.0], 'max_vonMises_MPa': 10.0, 'max_verschiebung_mm': 0.1, 'federrate_N_mm': 50.0}}}
    # S3-Gegenprobe: L 20, b 5, t 2 -> 877,8 Hz (PETG E 1500; vorher 1013,6 mit E 2000); S1-FEM 157,6 -> warnung
    so = {'_projekt': {'anregung_Hz': [20, 50], 'fallhoehe_m': 1.0, 'masse_g': 100},
          'arm': {'material': 'PETG', 'kragarm': [{'name': 'arm', 'L_mm': 20, 'b_mm': 5, 't_mm': 2}]}}
    d = _projekt(so, {'fall': (spec, erg)}, {'arm': (None, 1000.0)})
    try:
        r = S.pruefe(d)
        s1 = [e for e in nach_id(r, 'S1', 'arm') if 'FEM' in e['titel']]
        assert len(s1) == 1 and nah(s1[0]['wert'], 157.6, 1e-3), s1
        s3 = nach_id(r, 'S3', 'arm')[0]
        assert nah(s3['wert'], 877.8, 2e-3) and s3['stufe'] == 'warnung', s3   # 1013,6 * sqrt(1500/2000)
        # S2: f1 = min(157,6; 877,8) = 157,6; f_max 50 -> 3,15 >= 3 -> ok
        s2 = nach_id(r, 'S2', 'arm')[0]
        assert s2['stufe'] == 'ok' and nah(s2['wert'], 3.15, 2e-3), s2
        # S4: m 0,1 kg, k 50, h 1000: mg 0,981, delta 0,01962; F = 0,981*(1+sqrt(1+101937)) = 0,981*320,28 = 314,2 N
        # sigma = 10*314,2/5 = 628,4 MPa; S = 28/628,4 = 0,0446 -> fehler
        s4 = nach_id(r, 'S4')[0]
        assert s4['stufe'] == 'fehler' and nah(s4['daten']['F_max_N'], 314.2, 2e-3), s4
        assert nah(s4['wert'], 0.04, 0.15)
        # nur Achse z gerechnet -> eine warnung fuer x, y (Ecke/Kante ungeprueft)
        ax = [e for e in nach_id(r, 'S4') if 'Achsen' in e['titel']]
        assert len(ax) == 1 and ax[0]['stufe'] == 'warnung' and ax[0]['daten']['fehlt'] == ['x', 'y'], ax
    finally:
        shutil.rmtree(d)


def _s4_projekt(proj, achsen=('z',), vm=0.25):
    lf = {f'fall_{a}': {'kraft_N': [5.0 if a == 'x' else 0, 5.0 if a == 'y' else 0, -5.0 if a == 'z' else 0],
                        'max_vonMises_MPa': vm, 'max_verschiebung_mm': 0.1, 'federrate_N_mm': 50.0} for a in achsen}
    spec = {'koerper': [{'step': 'out/p.step', 'material': 'PETG', 'name': 'p'}], 'lasten': []}
    return _projekt({'_projekt': dict({'fallhoehe_m': 1.0, 'masse_g': 100}, **proj)},
                    {'f': (spec, {'koerper': ['p'], 'lastfaelle': lf})}, {'p': (None, 1000.0)})


def test_s4_kaelte_und_achsen():
    # F_max 314,2 N wie oben; sigma = 0,25 * 314,2/5 = 15,71 MPa; S = 28/15,71 = 1,782
    # warm: Ziel 1,5 -> ok; T_min 0 C (< 5 C, versproedet): Ziel 2 -> fehler; aussen ohne T_min: kalt angenommen -> fehler
    for proj, st, ziel in (({}, 'ok', 1.5), ({'T_min_C': 0}, 'fehler', 2.0), ({'aussen': True}, 'fehler', 2.0),
                           ({'T_min_C': 10}, 'ok', 1.5)):
        d = _s4_projekt(proj, achsen=('x', 'y', 'z'))
        try:
            r = nach_id(S.pruefe(d), 'S4')
            assert len(r) == 3, r                                   # 3 Achsen, keine Achsen-warnung
            for e in r:
                assert e['stufe'] == st and e['grenze'] == ziel and nah(e['wert'], 1.78, 3e-3), (proj, e)
            assert sorted(e['daten']['achse'] for e in r) == ['x', 'y', 'z']
        finally:
            shutil.rmtree(d)
    # ohne fallhoehe_m: weiter uebersprungen (Ausloeser 'handgeraet' stuft hoch)
    d = _s4_projekt({'fallhoehe_m': None})
    try:
        r = nach_id(S.pruefe(d), 'S4')
        assert len(r) == 1 and r[0]['stufe'] == 'uebersprungen' and 'fallhoehe_m' in r[0]['hinweis'], r
    finally:
        shutil.rmtree(d)


def test_s2_stufen():
    # f1 aus FEM 157,6 Hz: Band [100, 150] -> f1/f_max 1,05 -> fehler; [10, 60] -> 2,63 -> warnung; [300, 500] -> Isolation
    spec = {'koerper': [{'step': 'out/p.step', 'material': 'PETG', 'name': 'p'}], 'schwerkraft': True, 'lasten': []}
    erg = {'koerper': ['p'], 'lastfaelle': {'eigengewicht': {'kraft_N': [0, 0, 0], 'max_verschiebung_mm': 0.01}}}
    for band, stufe in (([100, 150], 'fehler'), ([10, 60], 'warnung'), ([300, 500], 'info'), (40, 'ok')):
        d = _projekt({'_projekt': {'anregung_Hz': band}}, {'f': (spec, erg)}, {'p': (None, 100.0)})
        try:
            s2 = nach_id(S.pruefe(d), 'S2', 'p')
            assert s2 and s2[0]['stufe'] == stufe, (band, s2)
        finally:
            shutil.rmtree(d)


def test_s1_zusatzmasse_ohne_federrate_warnt():
    spec = {'koerper': [{'step': 'out/p.step', 'material': 'PETG', 'name': 'p'}], 'schwerkraft': True, 'lasten': []}
    erg = {'koerper': ['p'], 'lastfaelle': {'g': {'kraft_N': [0, 0, 0], 'max_verschiebung_mm': 0.01}}}
    d = _projekt({'p': {'zusatzmasse_g': 30}}, {'f': (spec, erg)}, {'p': (None, 100.0)})
    try:
        s1 = nach_id(S.pruefe(d), 'S1', 'p')
        assert s1 and s1[0]['stufe'] == 'warnung' and 'NICHT' in s1[0]['hinweis'], s1
    finally:
        shutil.rmtree(d)


def test_akustik_synthetisch():
    """Geschlossene Box aussen 54 x 44 x 34, Wand 2 -> innen 50 x 40 x 30 (60 cm3); Deckel z oben mit 4 Loechern d 3
    um (0, 0). Hand: S7 f1(x) = 343,2/0,1 = 3432 Hz -> < 3400? nein -> 3432 > 3400 -> x ok, y 40 -> 4290, z 30 -> 5720:
    alle ueber dem Band -> ok. S5: 4 x S 7,069, a_eq 1,5, l 2 -> l_eff 4,4; V 1000: f = 54622*sqrt(4*7,069/4,4/1000)
    = 54622*0,080164 = 4378,7 Hz. S8: a 1,5 / delta_v(300) 0,0894 = 16,8 -> ok. S6: f_s 600, V_as 0,05 l, V 60000
    -> 600*sqrt(1+50000/60000) = 812,4 Hz -> 1,354 < 1,5, aber einbauten fehlen -> warnung."""
    from build123d import Box, Cylinder, Pos
    aussen = Box(54, 44, 34)
    box = aussen - Box(50, 40, 30)
    for x, y in ((-4, -4), (4, -4), (-4, 4), (4, 4)):
        box -= Pos(x, y, 16) * Cylinder(1.5, 4)
    ls = {'loecher': 'auto', 'mitte_mm': [0, 0], 'r_mm': 8, 'vorkammer_mm3': 1000, 'f_s_Hz': 600, 'V_as_l': 0.05}
    d = _projekt({'box': {'lautsprecher': ls}}, teile={'box': (box, box.volume)})
    try:
        r = S.pruefe(d)
        s5 = nach_id(r, 'S5', 'box')[0]
        assert s5['daten']['n_loecher'] == 4 and nah(s5['daten']['l_mm'], 2.0, 1e-3), s5
        assert nah(s5['daten']['S_mm2'], 4 * math.pi * 2.25, 2e-3), s5
        assert nah(s5['wert'], 4378.7, 3e-3), s5
        s7 = nach_id(r, 'S7', 'box')[0]
        assert [round(x, 2) for x in s7['daten']['innen_mm']] == [50.0, 40.0, 30.0], s7
        assert s7['stufe'] == 'ok' and nah(s7['wert'], 3432, 2e-3), s7
        s6 = nach_id(r, 'S6', 'box')[0]
        assert nah(s6['daten']['V_mm3'], 60000, 1e-3), s6
        assert nah(s6['daten']['f_c_Hz'], 812.4, 2e-3) and s6['stufe'] == 'warnung', s6
        s8 = nach_id(r, 'S8', 'box')[0]
        assert s8['stufe'] == 'ok' and nah(s8['daten']['a_mm'], 1.5, 1e-3), s8
        # gleiche Box als Lautsprecher mit engen Loechern d 0,8 von Hand: a 0,4 < 0,894 -> S8 warnung
        ls2 = dict(ls, loecher={'anzahl': 50, 'd_mm': 0.8}, wand_mm=2.0, innen_mm=[90, 40, 30], einbauten_mm3=0)
        r2 = S.pruefe(d, {'box': {'lautsprecher': ls2}})
        assert nach_id(r2, 'S8', 'box')[0]['stufe'] == 'warnung'
        # S7: 90 mm -> 1907 Hz im Band -> warnung
        assert nach_id(r2, 'S7', 'box')[0]['stufe'] == 'warnung'
    finally:
        shutil.rmtree(d)


# ------------------------------------------------------------------ echte Projekte
def test_echte_projekte_laufen():
    for p in ('testdose', 'schnapphaken', 'stifthalter-fem', 'frag-mich-alles-gehaeuse', 'bodenklima-sondenkopf'):
        r = S.pruefe(beispielprojekt(os.path.join(PROJ, p)))
        assert r, p
        for e in r:
            assert e['stufe'] in STUFEN and e['id'].startswith('S') and e['quelle'], (p, e)
            if e['stufe'] == 'uebersprungen':
                assert e['hinweis'], (p, e)


def vorschlag_frag_mich_alles():
    """Vorschlag fuer cad/soll.json der Front (Lautsprecher LOUDITY 52 mm hinter dem Schlitzgitter). Vorkammer
    angenommen: Membran im Mittel 1,5 mm hinter der Frontinnenseite ueber Oe 44."""
    return {'loecher': 'auto', 'mitte_mm': [24, 73], 'r_mm': 22, 'vorkammer': {'d_mm': 44, 'h_mm': 1.5},
            'geschlossen': False, 'gehaeuse_teile': ['rueckschale', 'front']}


def test_frag_mich_alles():
    pd = beispielprojekt(os.path.join(PROJ, 'frag-mich-alles-gehaeuse'))
    so = copy.deepcopy(soll(pd))
    so['front']['lautsprecher'] = vorschlag_frag_mich_alles()
    r = S.pruefe(pd, so)
    s5 = nach_id(r, 'S5', 'front')[0]
    # Gitter aus front.py: 9 Schlitze 2 breit, Raster 4, Huellkreis r 21 -> Laengen 41,95 / 2x40,79 / 2x37,95 /
    # 2x32,98 / 2x24,66 = 314,8 mm -> S ~ 2*314,8 = 629,6 minus Eckrundung r 0,95 (9*2*(4-pi)*0,9025*... ~ 7) = 622,5
    assert s5['daten']['n_loecher'] == 9 and nah(s5['daten']['S_mm2'], 622.5, 0.01), s5
    assert nah(s5['daten']['l_mm'], 2.4, 1e-3)
    s7 = nach_id(r, 'S7', 'front')[0]
    # front.py: innen X -9..96 = 105, Y -2,8..102,2 = 105, Z -16,9..18 = 34,9
    assert [round(x, 1) for x in s7['daten']['innen_mm']] == [105.0, 105.0, 34.9], s7
    assert s7['stufe'] == 'warnung'
    return r


if __name__ == '__main__':
    fehler = 0
    for name, fn in sorted((k, v) for k, v in dict(globals()).items() if k.startswith('test_') and callable(v)):
        try:
            fn()
            print('ok     ', name)
        except Exception as ex:  # noqa: BLE001
            fehler += 1
            print('FEHLER ', name, type(ex).__name__, ex)
    print('\nfrag-mich-alles-gehaeuse mit Vorschlag lautsprecher:')
    for e in test_frag_mich_alles():
        print(f"  {e['id']} {e.get('teil')} {e['stufe']}: {e['wert']} {e['einheit']} | {e['hinweis']}")
    print('\n', 'alle ok' if not fehler else f'{fehler} Fehler')
    sys.exit(1 if fehler else 0)
