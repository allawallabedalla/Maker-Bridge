"""FEM ohne Loeser pruefen: Netz, Auswahlen und CalculiX-Eingabe fuer einen Kragbalken (Box-Koerper, kein Projekt
noetig). Braucht nur Gmsh, kein CalculiX. Aufruf aus maker-bridge-2/:  uv run python tests/test_fem_vorbereitung.py

Frueher las der Test das Beispielprojekt projects/stifthalter-fem (nicht im Repository) und rief _inp mit dem alten
Lagerformat (knoten, achsen) auf. Jetzt baut er seinen Fall selbst und nutzt das aktuelle Format (knoten, achsen, weg).
"""
import os
import shutil
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mb2 import fem                      # noqa: E402
from mb2.material import DRUCKSTOFFE     # noqa: E402

TMP = tempfile.mkdtemp(prefix='mb2_femvorb_')
SPEC = {'koerper': [{'box': [0, 0, 0, 40, 10, 4], 'material': 'PETG', 'name': 'balken'}],
        'netz': {'groesse': 2.0},
        'lagerung': [{'wo': {'ebene': ['x', 0.0]}, 'fest': 'xyz'}],
        'lasten': [{'name': 'spitze', 'wo': {'ebene': ['x', 40.0]}, 'kraft_N': [0, 0, -5]}]}


def _vorbereiten():
    kn, tets, kp, namen, vol = fem.netz(TMP, SPEC, 2)
    return kn, tets, kp, namen, vol, fem.randflaechen(tets)


def test_netz_und_auswahl():
    kn, tets, kp, namen, vol, rand = _vorbereiten()
    assert tets.shape[1] == 10 and len(kn) > 0, tets.shape
    assert abs(vol.sum() - 40 * 10 * 4) < 1.0, vol
    for l in SPEC['lagerung'] + SPEC['lasten']:
        t, f = fem.auswahl(l['wo'], kn, tets, kp, namen, rand)
        k = fem._flaechen_knoten(tets, t, f)
        assert len(t) > 0 and len(k) > 0, l
        x = kn[k, 0]
        assert np.allclose(x, l['wo']['ebene'][1], atol=1e-6), (l, x.min(), x.max())


def test_inp_und_jacobi():
    kn, tets, kp, namen, _, rand = _vorbereiten()
    mats = [k['material'].upper() for k in SPEC['koerper']]
    druck = np.isin(np.array(mats)[kp], DRUCKSTOFFE)
    sel = lambda wo: fem._flaechen_knoten(tets, *fem.auswahl(wo, kn, tets, kp, namen, rand))  # noqa: E731
    fest = [(sel(l['wo']), l.get('fest', 'xyz'), l.get('weg')) for l in SPEC['lagerung']]
    lasten = [(l['name'], sel(l['wo']), np.array(l['kraft_N'], float)) for l in SPEC['lasten']]
    inp = fem._inp(kn, tets, kp, mats, druck, fest, lasten, False, SPEC, rand, namen)
    assert inp.count('*STEP') == len(lasten) and '*ELEMENT, TYPE=C3D10' in inp, inp[:300]
    # Altes Lagerformat (knoten, achsen) wird weiter angenommen
    alt = fem._inp(kn, tets, kp, mats, druck, [(f[0], f[1]) for f in fest], lasten, False, SPEC, rand, namen)
    assert alt == inp
    # Jacobi-Vorzeichen der Tet10-Ecken: alle Volumina positiv
    e = tets[:, :4]
    v = np.einsum('ij,ij->i', np.cross(kn[e[:, 1]] - kn[e[:, 0]], kn[e[:, 2]] - kn[e[:, 0]]), kn[e[:, 3]] - kn[e[:, 0]])
    assert (v > 0).all(), int((v <= 0).sum())


if __name__ == '__main__':
    try:
        for n, f in list(globals().items()):
            if n.startswith('test_') and callable(f):
                f()
                print('ok', n)
        print('alle ok')
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
