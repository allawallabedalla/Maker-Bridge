"""Einlegeteile mit Druckpause (EL1-EL5, 20.11.2026): Lage aus dem CAD, Pausenschicht, Temperatur, 3MF-Pausen,
Nachweis im G-Code. Slicen selbst braucht PrusaSlicer (Nutzer-Rechner); hier wird der G-Code-Nachweis mit einem
G-Code im Format von PrusaSlicer 2.9.7 geprueft (;Z:, ;PAUSE_PRINT, M601, M73 laut Quellcode).
Aufruf aus maker-bridge-2/:  uv run python tests/test_einlegen.py"""
import json
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mb2 import anforderungen as an, befehle as B, slicer  # noqa: E402
from mb2.pruefungen import einlegen as EL  # noqa: E402

SKRIPT = '''from build123d import Align, Box, Cylinder, Pos
MIN = (Align.CENTER, Align.CENTER, Align.MIN)
teil = Box(20, 20, 10, align=MIN) - Pos(0, 0, 2) * Cylinder(3.1, {tasche}, align=MIN)
platzhalter = {{"Magnet_1": Pos(0, 0, 2) * Cylinder(3.0, {magnet}, align=MIN)}}
quellen = {{"Magnet_1": "zeichnung: TESTFIXTURE Datenblatt Seite 1"}}
'''


def _projekt(name, tasche=3.2, magnet=3.0, einlegen='eingedruckt', druck=None, T_max=80):
    alt = B.PROJEKTE
    B.PROJEKTE = tempfile.mkdtemp(prefix='mb2_el_')
    try:
        B.project_new(name, 'Halter mit eingedrucktem Magnet', '', einsatz={'material': 'PETG'})
        d = os.path.join(B.PROJEKTE, name)
        open(os.path.join(d, 'cad', 'halter.py'), 'w').write(SKRIPT.format(tasche=tasche, magnet=magnet))
        s = json.load(open(os.path.join(d, 'cad', 'soll.json')))
        s['halter'] = {'einlegeteile': [{'name': 'Magnet_1', 'art': 'magnet', 'einlegen': einlegen, 'T_max_C': T_max,
                                         'polung': 'Nordpol nach oben'}]}
        if druck:
            s['_projekt']['druck'] = druck
        json.dump(s, open(os.path.join(d, 'cad', 'soll.json'), 'w'))
        r = B.cad_build(name, 'halter')
        assert r['ok'], r.get('fehler')
        return d, r
    finally:
        B.PROJEKTE = alt


RASTER = {'erste_schicht_mm': 0.2, 'schicht_mm': 0.2, 'bett_C': 85}


def _el(d):
    return {e['id']: e for e in EL.pruefe(d)}


def test_lage_und_pausenschicht():
    """Tasche 2 ... 5,2 mm, Magnet 2 ... 5,0 mm. Raster 0,2: deckende Schicht = erste mit Mitte > 5,2 -> Schicht 27
    (5,2 ... 5,4), Pause bei print_z 5,4; gedruckt bis 5,2, Luft 0,2 mm -> ok."""
    d, r = _projekt('el1', druck=RASTER)
    g = r['einlegeteile'][0]
    assert abs(g['z_unten_mm'] - 2.0) < 1e-6 and abs(g['z_oben_mm'] - 5.0) < 1e-6 and abs(g['decke_mm'] - 5.2) < 1e-6, g
    assert not g['offen'] and abs(g['spannweite_mm'] - 6.0) < 1e-3, g
    assert EL.pausenschicht(5.2, 0.2, 0.2) == (27, 5.2, 5.4)
    e = _el(d)
    assert e['EL1']['stufe'] == 'ok' and abs(e['EL1']['wert'] - 0.2) < 1e-6 and e['EL1']['daten']['print_z'] == 5.4, e['EL1']
    assert e['EL2']['stufe'] == 'info' and abs(e['EL2']['wert'] - 6.0) < 1e-3, e['EL2']   # Schicht 27 ueberspannt 6 mm
    assert e['EL3']['stufe'] == 'fehler', e['EL3']                       # Bett 85 C >= Magnet 80 C
    assert e['EL4']['stufe'] == 'uebersprungen'                          # noch nicht gesliced
    plan = EL.pausen(d, ['halter'])
    assert plan == [{'print_z': 5.4, 'teile': ['halter'], 'text': '1x Magnet_1 in halter (Nordpol nach oben)'}], plan
    # Magnet bis zur Decke (5,2): Luft 0 -> warnung. Decke 5,29: Schicht 27 (Mitte 5,3) deckt schon ab, gedruckt
    # bis 5,2 -> Magnet bis 5,25 ragt in die deckende Schicht -> fehler
    d2, _ = _projekt('el2', tasche=3.2, magnet=3.2, druck=RASTER, T_max=120)
    assert _el(d2)['EL1']['stufe'] == 'warnung' and _el(d2)['EL3']['stufe'] == 'ok'
    d3, _ = _projekt('el3', tasche=3.29, magnet=3.25, druck=RASTER)
    e3 = _el(d3)['EL1']
    assert e3['stufe'] == 'fehler' and 'Duese' in e3['hinweis'], e3
    # Decke 5,31 (nicht auf Schichtgrenze): Schicht 28 deckt, gedruckt bis 5,4, Luft ok, aber warnung (Decke verlegen)
    d5, _ = _projekt('el3b', tasche=3.31, magnet=3.0, druck=RASTER, T_max=120)
    assert _el(d5)['EL1']['stufe'] == 'warnung' and 'Schichtgrenze' in _el(d5)['EL1']['hinweis']
    # ohne Schichtraster: nicht gerechnet
    d4, _ = _projekt('el4')
    assert _el(d4)['EL1']['stufe'] == 'uebersprungen'


def test_nachher_einsetzen():
    """Nachher einsetzen geht nur, wenn die Tasche oben offen ist."""
    d, _ = _projekt('el5', einlegen='nachher', druck=RASTER)
    assert _el(d)['EL1']['stufe'] == 'fehler'                            # Tasche geschlossen
    d2, r = _projekt('el6', tasche=8.0, magnet=3.0, einlegen='nachher', druck=RASTER)   # Tasche bis oben (2 + 8 = 10)
    assert r['einlegeteile'][0]['offen'] and _el(d2)['EL1']['stufe'] == 'ok'
    assert EL.pausen(d2, ['halter']) == []


def test_3mf_pausen_und_gcode_nachweis():
    d, _ = _projekt('el7', druck=RASTER, T_max=120)
    plan = EL.pausen(d, ['halter'])
    xml = EL.pausen_xml(plan)
    w = ET.fromstring(xml)
    c = w.find('code')
    assert w.tag == 'custom_gcodes_per_print_z' and w.get('bed_idx') == '0', xml
    assert c.get('type') == '1' and c.get('gcode') == 'M601' and float(c.get('print_z')) == 5.4, xml
    assert w.find('mode').get('value') == 'SingleExtruder'
    # Kopie der Platte mit der XML
    p3 = os.path.join(d, 'print', 'test.3mf')
    with zipfile.ZipFile(p3, 'w') as z:
        z.writestr('3D/3dmodel.model', '<model/>')
    ziel = slicer.mit_pausen(p3, xml, os.path.join(d, 'print', 'test_pausen.3mf'))
    with zipfile.ZipFile(ziel) as z:
        assert '3D/3dmodel.model' in z.namelist() and z.read('Metadata/Prusa_Slicer_custom_gcode_per_print_z.xml').decode() == xml
    # G-Code im PrusaSlicer-Format: Pause vor ;Z:5.4, M73 Restzeit 120 -> 80 min
    g = ['M73 P0 R120', ';LAYER_CHANGE', ';Z:5.2', 'G1 X1', 'M73 P33 R80', ';PAUSE_PRINT', 'M117 1x Magnet_1',
         'M601', ';LAYER_CHANGE', ';Z:5.4', 'G1 X2', 'M73 P100 R0']
    open(os.path.join(d, 'print', 'el7.gcode'), 'w').write('\n'.join(g) + '\n')
    e = _el(d)
    assert e['EL4']['stufe'] == 'ok' and e['EL5']['wert'] == 40 and 'nach ca. 40 min' in e['EL5']['hinweis'], (e['EL4'], e['EL5'])
    # Pause fehlt -> fehler (NICHT drucken)
    open(os.path.join(d, 'print', 'el7.gcode'), 'w').write('\n'.join(x for x in g if x not in (';PAUSE_PRINT', 'M601')))
    assert _el(d)['EL4']['stufe'] == 'fehler'


def test_anforderung_und_abnahme():
    d, _ = _projekt('el8', druck=RASTER)
    a = {x['id']: x for x in an.standard(d)}
    nw = {n['ref']: n for n in a['S-EINLEGEN-halter']['nachweise']}
    assert set(nw) == {'EL1', 'EL4', 'AB-EL-halter'} and 'Polung' in nw['AB-EL-halter']['anweisung'], nw


if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_') and callable(f):
            f()
            print('ok', n)
    print('alle ok')
