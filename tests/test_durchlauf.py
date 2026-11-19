"""Kriterium 5 (19.11.2026): ein Projekt von der Idee bis zur Freigabe, ohne Handeingriff ausser den Nutzerantworten.

Beispiel: Wandhaken fuer eine Jacke (PETG, innen). Die Arbeit der Agenten (Lastenheft ergaenzen, CAD-Skript,
FEM-Lastfall, Nachbessern) ist hier geskriptet - geprueft wird, dass die BRIDGE den Ablauf traegt:
    1. project_new mit Zielen und Einsatz -> eingaben_offen nennt, was fehlt (kosten.json)
    2. Entwurf v1 (zu schwach) -> audit meldet den FEM-Mangel, Freigabe nicht_druckfertig
    3. Nachbessern v2 -> FEM ok; vor dem Slicen blockieren nur noch Druckplatte/G-Code und die Abnahme
    4. Slicen (PrusaSlicer) -> druckfertig
    5. Abnahme am Geraet eingetragen -> fertig
Ohne PrusaSlicer endet der Test nach Schritt 3 mit 'werkzeug_fehlt' (nie als bestanden).
Aufruf aus maker-bridge-2/:  uv run python tests/test_durchlauf.py"""
import json
import os
import sys
import tempfile

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HIER))
sys.path.insert(0, HIER)
from _nachweis import NichtAusgefuehrt  # noqa: E402

from mb2 import befehle as B, pruefungen, werkzeuge  # noqa: E402

P = 'wandhaken'
HAKEN = '''from build123d import Align, Box, Pos
MIN = (Align.CENTER, Align.MIN, Align.MIN)
B, H = {b}, {h}                         # Armbreite und -hoehe in mm
platte = Box(30, 4, 50, align=MIN)
arm = Pos(0, 4, 0) * Box(B, 30, H, align=MIN)
spitze = Pos(0, 30, H) * Box(B, 4, 8, align=MIN)
teil = platte + arm + spitze
druck = (0, 90, 0)                      # auf der Seite: Profil liegt in der Druckebene, keine Ueberhaenge
'''


def _json(d, f, daten=None):
    p = os.path.join(d, f)
    if daten is None:
        return json.load(open(p, encoding='utf-8'))
    json.dump(daten, open(p, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)


def _entwurf(d, b, h):
    open(os.path.join(d, 'cad', 'haken.py'), 'w', encoding='utf-8').write(HAKEN.format(b=b, h=h))
    s = _json(d, 'cad/soll.json')
    s['haken'] = {'volumen_mm3': 30 * 4 * 50 + b * 30 * h + b * 4 * 8, 'bbox_mm': [30, 34, max(50, h + 8)],
                  'material': 'PETG',
                  # Balken-Gegenprobe M3: Kragarm L 30 mm ab Wand, Last-Schwerpunkt 21 mm vor der Wand
                  'balken': [{'fall': 'haken', 'last': 'jacke', 'art': 'kragarm', 'L_mm': 30, 'a_mm': 21, 'b_mm': b,
                              'h_mm': h}]}
    _json(d, 'cad/soll.json', s)
    e = B.cad_build(P, 'haken')
    assert e['ok'], e.get('fehler')
    _json(d, 'fem/haken.json', {                            # Last auf der Armoberseite vor der Spitze
        'koerper': [{'step': 'out/haken.step', 'material': 'PETG'}], 'netz': {'groesse': 1.5},
        'lagerung': [{'wo': {'ebene': ['y', 0.0]}, 'fest': 'xyz'}],
        'lasten': [{'name': 'jacke', 'wo': {'ebene': ['z', float(h)], 'box': [-b, 20, h - 1, b, 30.5, h + 1]},
                    'kraft_N': [0, 0, -20]}]})
    f = B.fem_mech(P, 'haken')
    return e, f


def test_durchlauf_idee_bis_freigabe():
    alt = B.PROJEKTE
    B.PROJEKTE = tempfile.mkdtemp(prefix='mb2_durchlauf_')
    try:
        _ablauf()
    finally:
        B.PROJEKTE = alt


def _ablauf():
    if not werkzeuge.ccx():
        raise NichtAusgefuehrt('werkzeug_fehlt', 'CalculiX (ccx) fehlt')
    # ---- 1. Nutzerantworten -> Projekt
    r = B.project_new(P, 'Haken fuer eine Jacke an der Innenwand', 'haelt eine Jacke',
                      einsatz={'aussen': False, 'T_min_C': 15, 'T_max_C': 30, 'farbe': 'grau', 'material': 'PETG',
                               'lebensdauer_h': 20000,
                               '_herkunft': {'T_min_C': 'gemessen: Raumthermometer Flur',
                                             'T_max_C': 'gemessen: Raumthermometer Flur',
                                             'material': 'datenblatt: Prusament PETG TDS'}},
                      ziele={'zielkosten_eur_stueck': 1, 'stueckzahl': 1, 'termin': '2099-12-31', 'aufwand_h_stueck': 1,
                             'fehlerfolge': 'gering', 'prioritaet': ['qualitaet', 'zeit', 'kosten'],
                             'pruefmittel': ['Kofferwaage'], 'zeit_h_pro_woche': 2})
    d = r['projekt']
    offen = B.eingaben_offen(P)
    assert any(x.startswith('K1') for x in offen['pflicht_fehlt']), offen['pflicht_fehlt']   # kosten.json fehlt
    ids = {a['id'] for a in _json(d, 'anforderungen.json')['anforderungen']}
    assert 'A-MONTAGE' not in ids, ids                       # ohne Elektronik keine Adern/Stecker-Abnahme

    # ---- Agent: Lastenheft (Wunsch -> Zahl), Kosten, Modellrisiko
    a = _json(d, 'anforderungen.json')
    a['anforderungen'] += [
        {'id': 'W-JACKE', 'ebene': 'stakeholder', 'herkunft': 'Nutzer 19.11.2026', 'text': 'Eine Jacke haengt sicher.',
         'nachweise': [{'art': 'abnahme', 'ref': 'AB-LAST', 'stufe': 'abnahme'}]},
        {'id': 'A-LAST', 'ebene': 'system', 'eltern': ['W-JACKE'], 'herkunft': 'Nutzer 19.11.2026',
         'herleitung': 'Jacke 1 kg -> 9,81 N; Ruck beim Abnehmen x 2 -> 20 N Auslegungslast',
         'text': 'Haken traegt 20 N an der Spitze ohne Bruch.',
         'nachweise': [{'art': 'abnahme', 'ref': 'AB-LAST', 'stufe': 'abnahme'}]}]
    for x in a['anforderungen']:
        if x['id'] == 'A-GERAET':
            x.update(eltern=['W-JACKE'], herleitung='Idee aus projekt.md')
        if x['id'] == 'S-FEST':
            for n in x['nachweise']:
                if n['art'] == 'fem':
                    n['modell'] = {'frage': 'Haelt der Arm 20 N?', 'einsatz': 'Druckfreigabe', 'einfluss': 'mittel',
                                   'folge': 'gering'}
    _json(d, 'anforderungen.json', a)
    ab = _json(d, 'abnahme.json')
    ab['schritte'].append({'id': 'AB-LAST', 'anforderung': 'A-LAST', 'ist': None,
                           'anweisung': '2 kg (Kofferwaage) 1 min an die Hakenspitze haengen',
                           'soll': {'groesse': 'gehalten', 'op': '==', 'wert': 1, 'einheit': 'ja=1'}})
    _json(d, 'abnahme.json', ab)
    _json(d, 'kosten.json', {'posten': [{'name': 'PETG 15 g', 'menge': 1, 'preis_eur': 0.4, 'quelle': 'Spule 25 EUR/kg'}],
                             'arbeitsschritte': [{'name': 'Drucken, entgraten', 'h': 0.2, 'quelle': 'geschaetzt'}]})

    # ---- 2. Entwurf v1: Arm 10 x 6 mm -> zu schwach
    _, f1 = _entwurf(d, 10, 6)
    au = B.audit(P)
    assert au['freigabe'] == 'nicht_druckfertig', au['freigabe']
    assert any(m.startswith('FEM haken') for m in au['maengel']), au['maengel']
    # Leit-Agent im Kartenbetrieb: die naechste Karte geht an den FEM-Agenten, Abnahme macht das audit
    assert B.lauf_start(P)['ok']
    k = B.karte_naechste(P)
    assert k['karte']['agent'] == 'mb2-fem' and k['karte']['kopf'] == 'FEM haken', k

    # ---- 3. Nachbessern v2: Arm 14 x 10 mm
    _, f2 = _entwurf(d, 14, 10)
    assert f2['bewertung']['ok'], f2['bewertung']
    assert B.karte_ergebnis(P, 'Arm 14 x 10 mm')['status'] == 'ok'
    B.lauf_ende(P, 'Test')
    assert 'Freigabe' in open(os.path.join(d, 'pruef', 'stand.md'), encoding='utf-8').read()
    m3 = [e for e in pruefungen.alle(d, ('mechanik',))['module']['mechanik'] if e['id'] == 'M3' and 'Weg' in e['titel']]
    # Hand: d = F a^3 / (3 E I) = 20 * 21^3 / (3 * 1500 * 14 * 10^3 / 12) = 0,0353 mm. FEM liegt ~50 % hoeher: Arm
    # gedrungen (a/h = 2,1 -> Schubverformung, die Euler-Bernoulli nicht kennt) und 4-mm-Platte als weiche Einspannung.
    # M3 muss das als warnung melden (nicht ok, nicht uebersprungen).
    assert m3 and abs(m3[0]['grenze'] - 20 * 21 ** 3 / (3 * 1500 * 14 * 10 ** 3 / 12)) < 1e-3, m3
    assert m3[0]['stufe'] == 'warnung' and 0.3 < m3[0]['daten']['abweichung'] < 0.8, m3
    assert B.cad_plate(P, ['haken'])
    au = B.audit(P)
    rest = [m for m in au['maengel'] if not m.startswith(('Kein G-Code', 'Anforderung'))]
    assert all('M9' in m or 'gesliced' in m for m in rest), rest        # M9 rechnet ohne Slice mit 15 % Fuellung
    try:
        werkzeuge.prusa_slicer()
    except RuntimeError as ex:
        raise NichtAusgefuehrt('werkzeug_fehlt', f'PrusaSlicer fehlt - Durchlauf bis vor dem Slicen bestanden ({ex})')

    # ---- 4. Slicen: Arm voll aus Perimetern (10 mm / (2 x 0,45 mm) -> 12 Perimeter)
    sl = B.slice_plate(P, perimeter=12)
    assert sl.get('ok'), sl.get('probleme')
    au = B.audit(P)
    assert au['freigabe'] == 'druckfertig', au['maengel']

    # ---- 5. Abnahme am Geraet (Nutzerantworten)
    for s in _json(d, 'abnahme.json')['schritte']:
        B.abnahme_eintragen(P, s['id'], 1 if s['soll'].get('op') == '==' and s['soll'].get('wert') == 1 else
                            s['soll'].get('wert'), 'TESTFIXTURE Durchlauf')
    au = B.audit(P)
    assert au['freigabe'] == 'fertig', [m for m in au['maengel']]


if __name__ == '__main__':
    test_durchlauf_idee_bis_freigabe()
    print('alle ok')
