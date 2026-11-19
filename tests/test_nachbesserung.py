"""Gegentests zu den Befunden der Gegenpruefer (Nachbesserung): je Befund ein Handrechen-Fall.
Lauf: .venv/Scripts/python.exe tests/test_nachbesserung.py"""
import json
import math
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from mb2 import fem  # noqa: E402
from mb2.material import MATERIAL  # noqa: E402
from mb2.pruefungen import elektronik as el, mechanik as M, schwingung as S  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_pruef_elektronik import C0603, R0603, _platine  # noqa: E402


def nah(a, b, rel=1e-3):
    assert abs(a - b) <= rel * max(1e-12, abs(b)), (a, b)


def _projekt(soll_daten, faelle=None):
    d = tempfile.mkdtemp(prefix='mb2_nb_')
    for sub in ('cad', 'out', 'fem', 'electronics'):
        os.makedirs(os.path.join(d, sub))
    json.dump(soll_daten, open(os.path.join(d, 'cad', 'soll.json'), 'w'))
    for name, (spec, erg) in (faelle or {}).items():
        json.dump(spec, open(os.path.join(d, 'fem', name + '.json'), 'w'))
        json.dump(erg, open(os.path.join(d, 'fem', name + '.erg.json'), 'w'))
    return d


def test_s2_schaerfste_schaetzung():
    """Befund S2-min-untergrenze: PLA-Kragarm b 10, t 2, L 42,82 (E 2300; vorher L 47,56 bei E 3500, gleiche Frequenz), Band 300-3400 Hz.
    Hand: I = 10*8/12 = 6,667 mm4, A = 20 mm2; f3 = 1,875^2/(2 pi) sqrt(EI/(rho A L^4))
    = 0,5595 * sqrt(2,3e9*6,667e-12 / (1240*20e-6*0,04282^4)) = 0,5595 * 428,8 = 239,9 Hz > 300/sqrt2 = 212,1 Hz
    und 239,9/3400 = 0,07 < 2 -> fehler. S1b (analytisch, ~20 % tiefer, 193 Hz) liegt unter 212 -> waere 'info'."""
    E, rho = MATERIAL['PLA']['E_MPa'], MATERIAL['PLA']['dichte_kg_m3']
    hand = 1.875 ** 2 / (2 * math.pi) * math.sqrt(E * 1e6 * (10 * 8 / 12) * 1e-12 / (rho * 20e-6 * 0.04282 ** 4))
    so = {'_projekt': {'anregung_Hz': [300, 3400]},
          'arm': {'material': 'PLA', 'kragarm': [{'name': 'arm', 'L_mm': 42.82, 'b_mm': 10, 't_mm': 2}]}}
    d = _projekt(so)
    try:
        r = S.pruefe(d)
        s3 = [e for e in r if e['id'] == 'S3' and e.get('teil') == 'arm'][0]
        nah(s3['wert'], round(hand, 1), 2e-3)
        s1 = [e for e in r if e['id'] == 'S1' and e.get('teil') == 'arm'][0]
        assert s1['wert'] < 300 / math.sqrt(2) < s3['wert'], (s1['wert'], s3['wert'])
        s2 = [e for e in r if e['id'] == 'S2' and e.get('teil') == 'arm'][0]
        assert s2['stufe'] == 'fehler', s2
        nah(s2['daten']['f1_Hz'], hand, 2e-3)
        assert len(s2['daten']['schaetzungen']) == 2
    finally:
        shutil.rmtree(d)
    # Gegenfall: beide Schaetzungen unter 212 Hz (L 60 -> f3 = 239,9*(47,56/60)^2 = 150,7 Hz) -> info (Isolation)
    so['arm']['kragarm'][0]['L_mm'] = 60
    d = _projekt(so)
    try:
        s2 = [e for e in S.pruefe(d) if e['id'] == 'S2' and e.get('teil') == 'arm'][0]
        assert s2['stufe'] == 'info', s2
    finally:
        shutil.rmtree(d)


def test_m22_eckwert():
    """Befund M22-IP-statt-Ecke: linear Eckwert 3,567 > IP 2,814 -> Eckwert gilt.
    Hand: K_I = 1,12 * sigma * sqrt(pi a) linear in sigma -> mit Eckwert um 3,567/2,814 = 1,268 groesser."""
    class K:
        def faelle_zu(self, teil, mech=True):
            return [('f', {}, {'lastfaelle': {'a': {'max_vonMises_MPa': 3.567,
                                                    'max_vonMises_integrationspunkte_MPa': 2.814}}}, None)]

        def ts(self, teil):
            return {}

        def kw(self, mat, feld):
            return 2.0, 'Test'

        def S(self, teil, r):
            return 2.0

        def get(self, k, std=None):
            return std
        pdir = tempfile.gettempdir() + '/mb2_gibt_es_nicht'
    r = M._pruefe_bruch(K(), 'teil', 'PETG')[0]
    assert r['id'] == 'M22', r
    assert 'sigma 3.6 MPa' in r['hinweis'], r
    a = float(r['hinweis'].split('a = ')[1].split(' mm')[0])
    nah(r['wert'], round(M.m22_KI(3.567, a), 3), 1e-3)
    nah(M.m22_KI(3.567, a) / M.m22_KI(2.814, a), 3.567 / 2.814, 1e-9)


def test_i1_bewertung_null():
    """Befund I1: Sicherheit 0,0 (gerundet) darf nicht als 'fehlt' (1e9) zaehlen."""
    lf = {'andruck': {'sicherheit': {'PETG': {'xy': 0.01, 'z': 0.0}}},
          'quer': {'sicherheit': {'PETG': {'xy': 20.0, 'z': 11.21}}}}
    bw = fem.bewertung_mech(lf, ['PETG'])
    assert bw['min_sicherheit_z'] == 0.0 and bw['ok'] is False, bw
    lf['andruck']['sicherheit']['PETG']['z'] = None          # keine Spannung -> unendlich sicher
    bw = fem.bewertung_mech(lf, ['PETG'])
    assert bw['min_sicherheit_z'] == 11.21 and bw['ok'] is True, bw
    lf['quer']['energiebilanz'] = {'abweichung': 0.3}           # Befund I2: verletzte Bilanz -> nie ok
    bw = fem.bewertung_mech(lf, ['PETG'])
    assert bw['ok'] is False and bw['energiebilanz_verletzt'] == ['quer'], bw


def _tet10_wuerfel():
    """Ein Tet10-Element (Ecken 0, e1, e2, e3; Kantenmitten in gmsh-Reihenfolge)."""
    ecken = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], float)
    kn = [ecken[i] for i in range(4)]
    for (a, b), k in sorted(fem.TET10_KANTE.items(), key=lambda t: t[1]):
        kn.append(0.5 * (ecken[a] + ecken[b]))
    return np.array(kn), np.arange(10)[None]


def test_i2_innere_energie_hand():
    """Clapeyron-Gegenprobe: u = eps0 * x in x (reine Dehnung eps_xx, sonst 0).
    Hand: U = 1/2 C11 eps0^2 V, C11 = lam + 2 mu; E 1000, nu 0,3: lam = 576,92, mu = 384,62 -> C11 = 1346,15;
    V = 1/6, eps0 = 1e-3 -> U = 0,5 * 1346,15 * 1e-6 / 6 = 1,1218e-4 Nmm.
    Zusaetzlich quadratisches Feld u_x = x^2 (eps_xx = 2x): U = 1/2 C11 Int(4x^2 dV) = 2 C11 * 1/60."""
    knoten, tets = _tet10_wuerfel()
    C = fem.elastizitaet(1000.0, 0.3)
    lam, mu = 1000 * 0.3 / (1.3 * 0.4), 1000 / 2.6
    u = np.zeros_like(knoten)
    u[:, 0] = 1e-3 * knoten[:, 0]
    nah(fem._innere_energie(knoten, tets, u, np.zeros(1, int), {0: C}), 0.5 * (lam + 2 * mu) * 1e-6 / 6, 1e-9)
    u[:, 0] = knoten[:, 0] ** 2
    nah(fem._innere_energie(knoten, tets, u, np.zeros(1, int), {0: C}), 2 * (lam + 2 * mu) / 60, 1e-9)


def _lader_platine(mit_out=True):
    teile = {'U3': ('BQ24073RGTR', 'x', {'LCSC': 'C15220'}), 'J1': ('AKKU', 'Connector_JST:x', {}),
             'R3': ('2k4', R0603, {}), 'C2': ('1u', C0603, {}), 'Q1': ('AO3401A', 'x', {}),
             'R9': ('100k', R0603, {})}
    netze = {'/VBAT': [('U3', '2', 'BAT', 'power_out'), ('J1', '1', 'Pin_1', 'passive'), ('C2', '1', '', 'passive'),
                       ('Q1', '2', 'S', 'passive'), ('R9', '1', '', 'passive')],
             '/OUT': [('U3', '10', 'OUT', 'power_out')],
             '/GATE': [('Q1', '1', 'G', 'input'), ('R9', '2', '', 'passive')],
             '/LAST': [('Q1', '3', 'D', 'passive')],
             'GND': [('U3', '8', 'VSS', 'power_in'), ('J1', '2', 'Pin_2', 'passive'), ('C2', '2', '', 'passive'),
                     ('R3', '2', '', 'passive')],
             '/ISET': [('U3', '16', 'ISET', 'passive'), ('R3', '1', '', 'passive')]}
    return _platine(teile, netze)


def test_e2_out_folgt_akku():
    """Befund E2: BQ24073 OUT = 4,4 V +-3 % mit Eingang, ohne Eingang am Akku (LiPo ohne Schutz-IC: 3,0 V).
    Hand: OUT = (min(4,268; 3,0), 4,532) = (3,0; 4,532)."""
    pl = _lader_platine()
    assert pl.V['/VBAT'] == (3.0, 4.2), pl.V['/VBAT']
    nah(pl.V['/OUT'][0], 3.0, 1e-9)
    nah(pl.V['/OUT'][1], 4.4 * 1.03, 1e-9)
    assert '/OUT' in pl.akku_netze


def test_e1_pmos_kleinste_source():
    """Befund E1: P-FET Source an /VBAT 3,0-4,2 V, R_DS(on) erst ab 4,0 V -> V_GS,min = 3,0 V < 4,0 -> warnung."""
    pl = _lader_platine()
    pl.dbe['Q1'] = dict(pl.dbe['Q1'], R_DS_on_Ohm={'4.0': 0.05})
    e = [r for r in el.pruefe_e23(pl) if 'Q1' in r['hinweis']][0]
    assert e['stufe'] == 'warnung' and abs(e['wert'] - 3.0) < 1e-9, e


def test_e20_spitzenstrom():
    """Befund E3: MAX98357A an 5 V / 4 Ohm: P = 25/8 = 3,125 W, I_peak = V/R = 1,25 A (nicht 2,5 A)."""
    teile = {'U1': ('MAX98357A', 'x', {})}
    netze = {'/V5': [('U1', '7', 'VIN', 'power_in')], 'GND': [('U1', '6', 'GND', 'power_in')]}
    pl = _platine(teile, netze, projekt={'elektronik': {'netze': {'/V5': {'V': 5.0}}, 'lautsprecher_Ohm': 4}})
    e = [r for r in el.pruefe_e20(pl) if r['id'] == 'E20'][0]
    assert abs(e['daten']['I_peak_A'] - 1.25) < 1e-9 and ('3.12 W' in e['hinweis'] or '3.13 W' in e['hinweis']), e


if __name__ == '__main__':
    n = 0
    for k, f in list(globals().items()):
        if k.startswith('test_') and callable(f):
            f()
            print('ok', k)
            n += 1
    print(n, 'Tests bestanden')
