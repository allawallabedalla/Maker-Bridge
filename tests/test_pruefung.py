"""Die Pruefungen muessen echte Fehler finden und gute Teile durchlassen. Aufruf: python -m pytest tests -q
(oder python tests/test_pruefung.py)"""
import os
import sys

from build123d import Align, Box, Cylinder, Pos

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mb2 import cad  # noqa: E402

MIN = (Align.CENTER, Align.CENTER, Align.MIN)


def dose(wand):
    return Box(40, 30, 20, align=MIN) - Pos(0, 0, 2) * Box(40 - 2 * wand, 30 - 2 * wand, 20, align=MIN)


def test_gute_wand():
    r = cad.pruefen(dose(2.0))
    assert r['ok'], r['fehler']
    assert abs(r['wand_min_mm'] - 2.0) < 0.01


def test_duenne_wand():
    r = cad.pruefen(dose(1.2))
    assert not r['ok']
    assert abs(r['wand_min_mm'] - 1.2) < 0.01
    assert any('Wand' in f for f in r['fehler'])


def test_enger_spalt():
    klotz = Box(30, 20, 10, align=MIN) - Pos(0, 0, 2) * Box(0.3, 20, 10, align=MIN)   # 0,3-mm-Schlitz
    r = cad.pruefen(klotz)
    assert any('Spalt' in f for f in r['fehler']), r
    assert abs(r['spalt_min_mm'] - 0.3) < 0.01


def test_kollision_und_soll():
    d = dose(2.0)
    r = cad.pruefen(d, {'zu_gross': Pos(0, 0, 2) * Box(37, 10, 5, align=MIN)},
                    {'bbox_mm': [40, 30, 21], 'volumen_mm3': 1.0})
    t = ' '.join(r['fehler'])
    assert 'Kollision mit zu_gross' in t and 'Bounding Box Z' in t and 'Volumen' in t


def test_runder_dom_keine_fehlalarme():
    teil = Box(30, 30, 2, align=MIN) + Pos(0, 0, 2) * Cylinder(3.25, 6, align=MIN)
    teil -= Pos(0, 0, 2.5) * Cylinder(1.25, 6, align=MIN)
    r = cad.pruefen(teil)
    assert r['ok'], r['fehler']
    assert abs(r['wand_min_mm'] - 2.0) < 0.02     # (6,5 - 2,5) / 2


if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_'):
            f()
            print('ok', n)
    print('alle ok')
