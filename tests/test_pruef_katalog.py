"""Integrationstest der Katalog-Pruefungen: fem.py-Ausgabe -> Leser in mehreren Modulen, Befehl pruefkatalog und
Einbau in audit. Aufruf aus maker-bridge-2/:  .venv/Scripts/python.exe tests/test_pruef_katalog.py
Ein kleiner CalculiX-Lauf (Kragarm, Sekunden), sonst nur Lesen. Echte Projekte: nur pruefungen.alle in Kopien."""
import json
import math
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _nachweis import beispielprojekt, lang  # noqa: E402,F401

from mb2 import befehle, fem, pruefungen           # noqa: E402
from mb2.pruefungen import fem_plausi, schwingung   # noqa: E402

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix='mb2_katalog_')
LK, B = 60.0, 4.0


def nach_id(liste, id, teil=None):
    return [e for e in liste if e['id'] == id and (teil is None or e.get('teil') == teil)]


def kragarm_projekt(name, soll):
    d = os.path.join(TMP, name)
    for sub in ('cad', 'fem', 'out', 'electronics', 'print'):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    spec = {'koerper': [{'box': [0, 0, 0, LK, B, B], 'material': 'PETG', 'name': 'arm'}], 'netz': {'groesse': 1.0},
            'lagerung': [{'wo': {'ebene': ['x', 0]}, 'fest': 'xyz'}], 'schwerkraft': True,
            'lasten': [{'name': 'spitze', 'wo': {'ebene': ['x', LK]}, 'kraft_N': [0, 0, -1.0]}]}
    json.dump(spec, open(os.path.join(d, 'fem', 'g.json'), 'w'))
    json.dump(soll, open(os.path.join(d, 'cad', 'soll.json'), 'w'))
    return d


def test_schwerkraft_fem_nach_schwingung():
    """fem.py schreibt Lastfall 'eigengewicht' -> schwingung S1 findet ihn (Name) und rechnet 15,76/sqrt(delta).
    Hand: q = rho A g = 1,27e-9*16*9810 = 1,9934e-4 N/mm, w = qL^4/(8EI) = 0,007569 mm -> S1 = 15,76/sqrt(w)
    = 181,1 Hz; Kragarm exakt 1,875^2/(2 pi) sqrt(EI/(rho A L^4)) = 225,2 Hz. S1 (Einmassen-Naeherung mit
    max. Verschiebung) muss darunter liegen (konservativ), Rayleigh aus fem.py nahe 225 Hz."""
    d = kragarm_projekt('kragarm', {'arm': {'material': 'PETG'}})
    e = fem.mechanik(d, 'g')
    json.dump(e, open(os.path.join(d, 'fem', 'g.erg.json'), 'w'), default=str)
    lf = e['lastfaelle']
    assert 'eigengewicht' in lf and 'spitze' in lf, list(lf)
    from mb2.material import MATERIAL
    E, I, rho, A = MATERIAL['PETG']['E_MPa'], B ** 4 / 12, 1270e-12, B * B   # PETG E 1500 seit 19.11.2026
    w = rho * A * 9810 * LK ** 4 / (8 * E * I)
    f_exakt = 1.875 ** 2 / (2 * math.pi) * math.sqrt(E * I / (rho * A * LK ** 4))
    # Kontrolle der Formel selbst gegen die Handwerte mit E 2000 (w 0,007569 mm, f 225,2 Hz) - skaliert mit E
    assert abs(w * E / 2000 - 0.007569) < 2e-6 and abs(f_exakt * math.sqrt(2000 / E) - 225.2) < 0.2, (w, f_exakt)
    d_fem = lf['eigengewicht']['max_verschiebung_mm']
    assert abs(d_fem / w - 1) < 0.05, (d_fem, w)
    r = schwingung.pruefe(d)
    s1 = [x for x in nach_id(r, 'S1', 'arm') if 'FEM' in x['titel']]
    assert len(s1) == 1, [x['titel'] for x in nach_id(r, 'S1')]
    assert abs(s1[0]['wert'] - 15.76 / math.sqrt(d_fem)) < 0.2, (s1[0]['wert'], d_fem)
    assert 0.75 * f_exakt < s1[0]['wert'] < f_exakt, (s1[0]['wert'], f_exakt)
    assert abs(lf['eigengewicht']['rayleigh_f1_Hz'] / f_exakt - 1) < 0.04
    # F23 liest das Gleichgewicht aus derselben Ausgabe: Last gesamt = -q L (Eigengewicht)
    f23 = nach_id(fem_plausi.pruefe(d), 'F23')
    assert f23 and all(x['stufe'] == 'ok' for x in f23), f23
    print('   S1', s1[0]['wert'], 'Hz (Hand 15,76/sqrt(%.5f) = %.1f), exakt %.1f' % (d_fem, 15.76 / math.sqrt(d_fem),
                                                                                   f_exakt))
    return d


def test_alle_module_synthetisch():
    """Alle Module laufen auf dem Kragarm-Projekt ohne Modulfehler; Zaehlung = Summe der Ergebnisse."""
    d = os.path.join(TMP, 'kragarm')
    r = pruefungen.alle(d)
    assert set(r['module']) - {'ausloeser'} == set(pruefungen.MODULE), list(r['module'])
    modfehler = [x for l in r['module'].values() for x in l if x['id'] in pruefungen.MODULE]
    assert not modfehler, modfehler
    n = sum(len(l) for l in r['module'].values())
    assert sum(r['zaehlung'].values()) == n
    for l in r['module'].values():
        for x in l:
            assert x['id'] and x['stufe'] in pruefungen.STUFEN, x
            assert x['stufe'] == 'uebersprungen' or x['quelle'], ('Quelle fehlt', x)
    assert os.path.exists(os.path.join(d, 'pruef', 'katalog.json'))


def test_befehl_und_audit():
    """pruefkatalog + audit: D1 mit T_max 75 C bei PETG (Tg 80): Abstand 5 K < 20 K -> fehler -> Mangel im Audit.
    Warnungen erscheinen in katalog_warnungen, die bisherigen Audit-Schluessel bleiben."""
    d = kragarm_projekt('audit_d1', {'_projekt': {'T_max_C': 75}, 'arm': {'material': 'PETG'}})
    alt = befehle.PROJEKTE
    befehle.PROJEKTE = TMP
    try:
        k = befehle.pruefkatalog('audit_d1')
        assert any(z.startswith('D1 [arm]') for z in k['fehler']), k['fehler']
        assert sum(k['zaehlung'].values()) == sum(len(l) for l in
                                                  json.load(open(k['datei'], encoding='utf-8')).values())
        a = befehle.audit('audit_d1')
        for key in ('messbar_ok', 'maengel', 'teile', 'fem', 'kicad', 'slicen', 'bilder', 'offen_fuer_pruefer',
                    'katalog', 'katalog_warnungen'):
            assert key in a, key
        assert not a['messbar_ok']
        assert any(m.startswith('Katalog D1 [arm]') for m in a['maengel']), a['maengel']
        assert a['katalog']['zaehlung']['fehler'] >= 1
        assert isinstance(a['katalog_warnungen'], list)
        assert len(a['katalog_warnungen']) == a['katalog']['zaehlung']['warnung']
        # Abstand 30 K -> ok, kein Katalog-Mangel aus D1
        json.dump({'_projekt': {'T_max_C': 50}, 'arm': {'material': 'PETG'}},
                  open(os.path.join(d, 'cad', 'soll.json'), 'w'))
        a = befehle.audit('audit_d1')
        assert not any(m.startswith('Katalog D1') for m in a['maengel']), a['maengel']
    finally:
        befehle.PROJEKTE = alt


def test_ausloeser_stilles_ueberspringen_wird_fehler():
    """Muster A (Audit 15.11.2026): projekt.md nennt LoRa + Garten, soll.json hat weder funk noch aussen ->
    E16 (Funk) und W6 (Sonne) duerfen nicht still 'uebersprungen' bleiben, sondern sind 'fehler'. Ein ausdruecklicher
    Verzicht in _projekt.nicht_relevant macht daraus 'info' mit Begruendung."""
    d = kragarm_projekt('ausloeser', {'arm': {'material': 'PETG'}})
    open(os.path.join(d, 'projekt.md'), 'w', encoding='utf-8').write('LoRa-Sensor fuer den Garten')
    r = pruefungen.alle(d)
    alles = [x for l in r['module'].values() for x in l]
    for i in ('E16', 'W6'):
        treffer = [x for x in alles if x['id'] == i or (x['id'] == 'E1-E25' and i.startswith('E'))]
        assert treffer and all(x['stufe'] == 'fehler' for x in treffer), (i, treffer)
    assert {'funk', 'aussen'} <= set(r['merkmale']), r['merkmale']
    assert r['hochgestuft'] >= 2 and not r['ok']
    json.dump({'_projekt': {'nicht_relevant': {'W6': 'steht unter dem Vordach'}}, 'arm': {'material': 'PETG'}},
              open(os.path.join(d, 'cad', 'soll.json'), 'w'))
    r = pruefungen.alle(d)
    w6 = [x for l in r['module'].values() for x in l if x['id'] == 'W6']
    assert w6 and all(x['stufe'] == 'info' and 'Vordach' in x['hinweis'] for x in w6), w6


def test_project_new_einsatz_und_eingaben_offen():
    """project_new schreibt Einsatzbedingungen nach soll.json/projekt.md; offene Vorlagenzeilen loesen keine Merkmale aus;
    eingaben_offen trennt fehlende Eingaben (Funk ohne Strecke) von 'wartet auf Entwurf' (noch keine Teile)."""
    alt = befehle.PROJEKTE
    befehle.PROJEKTE = TMP
    try:
        r = befehle.project_new('neu_funk', 'LoRa-Sensor', '', {'aussen': True, 'T_min_C': -20, 'T_max_C': 35,
                                                                 'farbe': 'weiss', 'material': 'ASA'})
        assert 'akku_mAh' in r['offen'] and 'aussen' not in r['offen'], r
        s = json.load(open(os.path.join(TMP, 'neu_funk', 'cad', 'soll.json'), encoding='utf-8'))
        assert s['_projekt']['T_min_C'] == -20 and s['_projekt']['nicht_relevant'] == {}, s
        e = befehle.eingaben_offen('neu_funk')
        assert 'akku' not in e['merkmale'] and 'handgeraet' not in e['merkmale'], e['merkmale']   # Vorlage zaehlt nicht
        assert any(z.startswith('E1-E25') and 'funk' in z for z in e['pflicht_fehlt']), e
        assert any(z.startswith('D1') for z in e['wartet_auf_entwurf']), e
        assert not e['fertig']
    finally:
        befehle.PROJEKTE = alt


def test_echte_projekte():
    """alle() auf Kopien jedes Projekts unter projects/: kein Modulfehler, keine FEM-Rechnung (Laufzeit < 60 s)."""
    for p in sorted(os.listdir(beispielprojekt(os.path.join(HIER, 'projects')))):
        src = os.path.join(HIER, 'projects', p)
        if not os.path.isdir(src):
            continue
        d = os.path.join(TMP, 'echt_' + p)
        shutil.copytree(src, d, ignore=shutil.ignore_patterns('*.frd', '*.inp', '*.dat', '*.vtu', '*.msh', 'veraltet', 'pruef'))
        t0 = time.time()
        r = pruefungen.alle(d)
        dt = time.time() - t0
        modfehler = [x for l in r['module'].values() for x in l if x['id'] in pruefungen.MODULE]
        assert not modfehler, (p, modfehler)
        assert dt < 60, (p, dt)
        print(f'   {p}: {dt:.1f} s {r["zaehlung"]}')


if __name__ == '__main__':
    try:
        for n, f in list(globals().items()):
            if n.startswith('test_') and callable(f):
                f()
                print('ok', n)
        print('alle ok')
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
