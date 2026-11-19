"""Bricklayers-Nachbearbeitung an synthetischem G-Code (von Hand nachvollziehbar). Aufruf:
.venv/Scripts/python.exe tests/test_bricklayers.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from mb2 import bricklayers as b  # noqa: E402


def schicht(nr, z, objekte, innen=2):
    """Eine Schicht: je Objekt `innen` Innenwaende (je eigene Linie, durch Fahrt getrennt) + Aussenwand."""
    zz = [';LAYER_CHANGE', f';Z:{z}', ';HEIGHT:0.2', f'G1 Z{z} F720']
    for o in objekte:
        zz += [f'M486 S{o}', ';TYPE:Perimeter']
        for j in range(innen):
            zz += [f'G1 X{10 + j} Y10 F9000', ';WIDTH:0.45', 'G1 F3000',
                   f'G1 X{20 + j} Y10 E1.0', f'G1 X{20 + j} Y20 E1.0']
        zz += ['G1 X5 Y5 F9000', ';TYPE:External perimeter', 'G1 X30 Y5 E1.0', 'G1 X30 Y30 E1.0', 'M486 S-1']
    return zz


def code(innen=2):
    zz = ['M83 ; relative']
    for i, z in enumerate((0.2, 0.4, 0.6), start=1):
        zz += schicht(i, z, [0, 1], innen)
    return zz


def zeilen_von(neu, marke):
    return [i for i, z in enumerate(neu) if z.endswith(marke)]


def test_paritaet_und_schichten():
    alt = code(innen=2)
    neu, st = b.bearbeiten(alt, {0})
    # Objekt 0, je Schicht 2 Innenwaende: j=0 Abstand 2 (bleibt), j=1 Abstand 1 (hoch).
    # Schicht 1: hoch mit 1,5 x E; Schicht 2: hoch; Schicht 3 (letzte): nicht hoch, 0,5 x E
    assert st['angehoben'] == 2, st
    assert st['erste_schicht'] == 1 and st['letzte_schicht'] == 1, st
    hoch = [neu[i] for i in zeilen_von(neu, '; bricklayers')]
    assert hoch == ['G1 Z0.300 ; bricklayers', 'G1 Z0.500 ; bricklayers'], hoch
    zur = [neu[i] for i in zeilen_von(neu, '; bricklayers zurueck')]
    assert zur == ['G1 Z0.200 ; bricklayers zurueck', 'G1 Z0.400 ; bricklayers zurueck'], zur
    # E der angehobenen Linie in Schicht 1 = 1,5
    i = zeilen_von(neu, '; bricklayers')[0]
    assert neu[i + 1] == 'G1 X21 Y10 E1.50000', neu[i + 1]
    # letzte Schicht: Linie j=1 von Objekt 0 mit E 0,5, kein Z-Wechsel
    n3 = max(i for i, z in enumerate(neu) if z == ';Z:0.6')
    rest = neu[n3:]
    assert 'G1 X21 Y10 E0.50000' in rest and not any('bricklayers' in z for z in rest)
    pr = b.pruefen(alt, neu, {0})
    # Extrusion: +0,5 (Schicht 1, 2 Bewegungen x 0,5... ) -> 2*0.5 - 2*0.5 = 0 netto
    assert pr['ok'], pr
    assert abs(pr['extrusion_aenderung_pct']) < 1e-6, pr
    print('ok test_paritaet_und_schichten')


def test_nur_gewaehlte_objekte():
    alt = code(innen=1)
    neu, st = b.bearbeiten(alt, {1})
    i = zeilen_von(neu, '; bricklayers')[0]
    # vor der Anhebung muss zuletzt M486 S1 stehen
    obj = [z for z in neu[:i] if z.startswith('M486 S')][-1]
    assert obj == 'M486 S1', obj
    assert st['angehoben'] == 2 and st['letzte_schicht'] == 1, st   # Schicht 1 (1,5 x) + 2 hoch, 3 = letzte
    print('ok test_nur_gewaehlte_objekte')


def test_leer_und_absolut():
    alt = code()
    assert b.bearbeiten(alt, set())[0] is alt
    try:
        b.bearbeiten(['M82'] + alt[1:], {0})
    except RuntimeError:
        print('ok test_leer_und_absolut')
        return
    raise AssertionError('absolute Extrusion nicht erkannt')


def test_zuordnung_ueber_lage():
    """G-Code-Objekte in anderer Reihenfolge und um (+5, -3) verschoben (--center) -> trotzdem richtig zugeordnet."""
    def obj(i, x0, y0, x1, y1, zmax):
        return [f'M486 S{i}', f'G1 X{x0} Y{y0} Z{zmax} F9000', f'G1 X{x1} Y{y1} E1.0', 'M486 S-1']
    g = ['M83'] + obj(0, 105, 7, 115, 17, 2.0) + obj(1, 15, 7, 95, 87, 37.0)
    teile = {'gross': [10, 10, 0, 90, 90, 37.0], 'klein': [100, 10, 0, 110, 20, 2.0]}
    assert b.objekt_zuordnung(g, teile) == {'gross': 1, 'klein': 0}
    try:
        b.objekt_zuordnung(g, {'gross': [10, 10, 0, 90, 90, 37.0], 'klein': [100, 10, 0, 110, 20, 9.0]})
    except RuntimeError:
        print('ok test_zuordnung_ueber_lage')
        return
    raise AssertionError('unsichere Zuordnung nicht erkannt')


def test_meta():
    m = b.meta_ascii(['G1 X1', '; printer_model = MK4IS', '; max_layer_z = 37'])
    assert m == {'printer_model': 'MK4IS', 'max_layer_z': '37'}, m
    print('ok test_meta')


if __name__ == '__main__':
    for f in (test_paritaet_und_schichten, test_nur_gewaehlte_objekte, test_leer_und_absolut, test_zuordnung_ueber_lage,
              test_meta):
        f()
    print('alle ok')
