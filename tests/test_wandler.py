"""Sensorprofil wandler (19.11.2026): Messprinzipien als Modellgleichung, GUM linear + Monte-Carlo (JCGM 101).
Handrechnungen im Kommentar, alle Parameter TESTFIXTURE.
Aufruf aus maker-bridge-2/:  uv run python tests/test_wandler.py"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mb2.sensorprofile import wandler as W  # noqa: E402

DB = lambda f: 'datenblatt'  # noqa: E731


def nah(a, b, rel=1e-4):
    assert abs(a - b) <= rel * abs(b), f'{a} != {b}'


def test_beer_lambert_hand():
    """I 0,5, I0 1, eps 100 L/(mol cm), l 1 cm: c = lg2/100 = 0,0030103 mol/L.
    dc/dI = -1/(ln10 I eps l) = -0,0086859 x u 0,001; dc/dI0 = 0,0043429 x 0,001; dc/deps = -c/eps x 2/sqrt3;
    dc/dl = -c/l x 0,01/sqrt3."""
    mk = {'profil': 'wandler', 'prinzip': 'beer_lambert', 'einheit': 'mol/L', 'ziel_U': 1e-4,
          'eingaben': {'I': {'wert': 0.5, 'u': {'wert': 0.002, 'verteilung': 'normal', 'k': 2}},
                       'I0': {'wert': 1.0, 'u': {'wert': 0.002, 'verteilung': 'normal', 'k': 2}},
                       'eps': {'wert': 100.0, 'u': {'wert': 2.0, 'verteilung': 'rechteck'}},
                       'l': {'wert': 1.0, 'u': {'wert': 0.01, 'verteilung': 'rechteck'}}}}
    b = W.budget_bei(mk, {})
    c = math.log10(2) / 100
    nah(b['y'], c)
    u = math.sqrt((0.001 / (math.log(10) * 0.5 * 100)) ** 2 + (0.001 / (math.log(10) * 100)) ** 2 +
                  (c / 100 * 2 / math.sqrt(3)) ** 2 + (c * 0.01 / math.sqrt(3)) ** 2)
    nah(b['u_c'], u, 1e-3)
    r = {e['id']: e for e in W.pruefe(mk, DB)}
    assert r['MK1']['stufe'] == 'ok' and r['MK2']['stufe'] == 'info', r
    assert {e['id']: e for e in W.pruefe(mk, lambda f: None)}['MK1']['stufe'] == 'warnung'     # Herkunft offen
    m = dict(mk)
    m['eingaben'] = dict(mk['eingaben'], eps={'wert': 100.0})                                    # u fehlt -> fester Parameter
    assert W.budget_bei(m, {})['u_c'] < b['u_c']
    m['eingaben'] = dict(mk['eingaben'], eps={'wert': 100.0, 'u': {'wert': None}})
    assert {e['id']: e for e in W.pruefe(m, DB)}['MK1']['stufe'] == 'uebersprungen'


def test_amperometrisch_und_differenzdruck_hand():
    # c = I delta / (n F A D) = 1e-6 * 1e-5 / (2 * 96485,33212 * 1e-6 * 1e-9) = 0,051821 mol/m3
    mk = {'prinzip': 'amperometrisch_grenzstrom', 'eingaben': {
        'I': {'wert': 1e-6}, 'delta': {'wert': 1e-5}, 'n': {'wert': 2}, 'A': {'wert': 1e-6}, 'D': {'wert': 1e-9}}}
    nah(W.budget_bei(mk, {})['y'], 1e-11 / (2 * 96485.33212 * 1e-15))
    # Q = dp pi d^4 / (128 mu L): 6,79 Pa, d 1 mm, L 10 mm, mu 1 mPa s -> 1,6665e-8 m3/s = 0,9999 ml/min (faktor 6e7)
    mk = {'prinzip': 'differenzdruck_laminar', 'faktor': 6e7, 'eingaben': {
        'dp': {'wert': 6.79}, 'd': {'wert': 1e-3}, 'L': {'wert': 1e-2}, 'mu': {'wert': 1e-3}}}
    nah(W.budget_bei(mk, {})['y'], 6.79 * math.pi * 1e-12 / (128 * 1e-3 * 1e-2) * 6e7)   # 128 mu L = 1,28e-6


def test_nichtlinear_monte_carlo():
    """King: v = ((E^2 - A)/B)^(1/n) nahe E^2 = A ist stark nichtlinear -> Monte-Carlo, U >= linear."""
    mk = {'prinzip': 'kings_law', 'einheit': 'm/s', 'ziel_U': 10,
          'eingaben': {'E': {'wert': 1.02, 'u': {'wert': 0.01, 'verteilung': 'normal', 'k': 2}},
                       'A': {'wert': 1.0}, 'B': {'wert': 0.5}, 'n': {'wert': 0.45}}}
    b = W.budget_bei(mk, {})
    assert 'monte_carlo' in b and b['U'] >= b['U_lin'] and b['nichtlinear_max'] > 0.05, b.get('nichtlinear_max')
    # linear_tk bleibt linear in s -> kein Monte-Carlo
    lt = {'prinzip': 'linear_tk', 'eingaben': {'s': {'wert': 1.5, 'u': {'wert': 0.001}}, 's0': {'wert': 0.5},
                                               'S': {'wert': 0.1}, 'alpha': {'wert': 0.002}, 'T': {'wert': 30},
                                               'T0': {'wert': 20}}}
    b = W.budget_bei(lt, {})
    nah(b['y'], 1.0 / (0.1 * 1.02))
    assert 'monte_carlo' not in b
    try:
        W.pruefe({'prinzip': 'gibts_nicht'}, DB)
    except ValueError:
        raise AssertionError('unbekanntes Prinzip darf nicht abstuerzen')


if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_') and callable(f):
            f()
            print('ok', n)
    print('alle ok')
