"""Stichproben-Validierung: einzelne Realmessungen gegen Modellvorhersagen (19.11.2026).
Aufruf aus maker-bridge-2/:  uv run python tests/test_stichproben.py"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mb2 import anforderungen as an, befehle, glaubwuerdigkeit as gw, stichproben as sp   # noqa: E402

TMP = tempfile.mkdtemp(prefix='mb2_stich_')
FUNK = {'r_m': 830, 'f_MHz': 868, 'P_t_dBm': 14, 'P_rx_min_dBm': -132, 'G_t_dBi': 2, 'G_r_dBi': 0,
        'umgebung': 'dorf', 'hindernisse': [], 'kabel': []}
KAT = {'elektronik': [{'id': 'E16', 'stufe': 'ok', 'wert': 20.0, 'grenze': 10, 'einheit': 'dB',
                       'daten': {'P_rx_dBm': -112.0}}]}
M = {'art': 'katalog', 'ref': 'E16', 'groesse': 'P_rx_dBm', 'merkmale': ['elektronik.funk.r_m']}


def punkt(r, D, S=None, u_D=2.0, status='gemessen'):
    p = {'bedingungen': {'elektronik.funk.r_m': r}, 'D': D, 'u_D': u_D, 'u_input': 3.0, 'u_num': 0.0,
         'datenstatus': status}
    if S is not None:
        p['S'] = S
    return p


def test_einzelpunkt_metrik_und_regeln():
    pj = {'elektronik': {'funk': FUNK}}
    # S aus aktueller Vorhersage (gleiche Bedingung 830 m): E = -112 - (-114) = 2, u_val = sqrt(9 + 4) = 3,6 -> ok
    e = sp.bewerte_modell({**M, 'punkte': [punkt(830, -114.0)]}, pj, KAT)
    assert e['status'] == 'validiert' and e['punkte'][0]['S_aus'], e
    # ein Punkt daneben (E = 12 > 2*3,6) -> widerlegt
    e = sp.bewerte_modell({**M, 'punkte': [punkt(830, -114.0), punkt(500, -120.0, S=-108.0)]}, pj, KAT)
    assert e['status'] == 'widerlegt', e
    # Entwurf (830 m) ausserhalb des gemessenen Bereichs 100 ... 400 m -> extrapolation
    e = sp.bewerte_modell({**M, 'punkte': [punkt(100, -95, S=-96), punkt(400, -105, S=-104)]}, pj, KAT)
    assert e['status'] == 'extrapolation' and '830' in e['text'], e
    # ohne Messunsicherheit oder Demodaten: nicht gewertet
    e = sp.bewerte_modell({**M, 'punkte': [punkt(830, -114.0, u_D=None), punkt(830, -114, status='simuliert')]}, pj, KAT)
    assert e['status'] == 'ohne_punkte', e


def test_wirkung_in_der_v_matrix_und_vorschlag():
    befehle.PROJEKTE = TMP
    befehle.project_new('st', 'LoRa-Sensor', '', {'T_max_C': 30, 'elektronik': {'funk': FUNK}})
    d = os.path.join(TMP, 'st')
    def e16():
        z = {x['id']: x for x in an.pruefen(d, katalog=KAT)['anforderungen']}
        return next(n for n in z['S-FUNK']['nachweise'] if n['ref'] == 'E16')
    sp.eintragen(d, 'funk', punkt(830, -114.0), **{k: M[k] for k in ('art', 'ref', 'groesse', 'merkmale')})
    assert 'validiert' in e16()['beleg'], e16()
    sp.eintragen(d, 'funk', punkt(500, -120.0, S=-108.0))
    assert e16()['status'] == 'unbewiesen' and 'durchgefallen' in e16()['beleg'], e16()
    vs = sp.vorschlagen(d, KAT)
    assert vs and 'E16' in vs[0], vs


def test_fem_stichproben_als_vergleich():
    m = {'frage': 'x', 'einsatz': 'y', 'einfluss': 'hoch', 'folge': 'mittel'}
    stich = {'punkte': [{'E': 0.1, 'S': 1.1, 'D': 1.0, 'u_D': 0.1, 'u_num': 0.05, 'u_input': 0.05}]}
    mm = an._mit_stichproben(m, stich)
    met = gw.vv20_metrik(mm['validierung'])
    assert met['beidseitig'] and met['E_max_rel'] < 1, met
    assert an._mit_stichproben({**m, 'validierung': {'beleg': 'eigen'}}, stich)['validierung']['beleg'] == 'eigen'


if __name__ == '__main__':
    try:
        for n, f in list(globals().items()):
            if n.startswith('test_') and callable(f):
                f()
                print('ok', n)
        print('alle ok')
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
