"""Kriterium 6 (19.11.2026): Auftragskarten, Hochstufen statt Wiederholen, Laufsperre, Bremse, kurzer Stand.
Aufruf aus maker-bridge-2/:  uv run python tests/test_karten.py"""
import datetime
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mb2 import fragen, karten as K  # noqa: E402


def _projekt():
    d = tempfile.mkdtemp(prefix='mb2_karten_')
    open(os.path.join(d, 'projekt.md'), 'w', encoding='utf-8').write('# p\n')
    return d


def _au(*maengel, freigabe='nicht_druckfertig'):
    return {'maengel': list(maengel), 'freigabe': freigabe}


def test_laufsperre_und_bremse():
    d = _projekt()
    assert K.naechste(d, _au('Kein G-Code (slice_plate)'))['stop'] == 'bremse'          # ohne lauf_start nichts
    t0 = datetime.datetime(2026, 11, 19, 8, 0)
    assert K.lauf_start(d, max_karten=2, jetzt=t0)['ok']
    assert not K.lauf_start(d, jetzt=t0 + datetime.timedelta(hours=1))['ok']             # zweiter Lauf: sofort enden
    for _ in range(2):
        assert 'karte' in K.naechste(d, _au('Kein G-Code (slice_plate)'))
        K.ergebnis(d, _au('Kein G-Code (slice_plate)'))
    r = K.naechste(d, _au('Kein G-Code (slice_plate)'))
    assert r['stop'] == 'bremse' and 'Grenze 2' in r['grund'], r
    K.lauf_ende(d, 'Test')
    assert K.lauf_start(d, jetzt=t0 + datetime.timedelta(hours=1))['ok']                 # nach lauf_ende wieder frei
    # haengengebliebene Sperre laeuft nach sperre_h ab
    assert K.lauf_start(d, jetzt=t0 + datetime.timedelta(hours=5))['ok']


def test_hochstufen_statt_wiederholen():
    """Slicer-Karte: haiku -> sonnet -> opus -> Grundannahme (Leit-Agent) -> Nutzer. Nie zweimal dieselbe Stufe."""
    d = _projekt()
    K.lauf_start(d, max_karten=50)
    m = 'Kein G-Code (slice_plate)'
    folge = []
    while True:
        r = K.naechste(d, _au(m))
        if 'stop' in r:
            break
        folge.append((r['karte']['agent'], r['karte']['stufe']))
        assert r['karte']['modell'] in K.STUFEN
        assert K.ergebnis(d, _au(m), notiz='Profil nicht gefunden')['status'] == 'fehler'   # Mangel bleibt
    assert folge == [('mb2-slicer', 'haiku'), ('mb2-slicer', 'sonnet'), ('mb2-slicer', 'opus'),
                     ('leit', 'grundannahme')], folge
    assert r['stop'] == 'nutzer', r
    assert 'VORVERSUCHE' in K._lade(d, 'karten.json', {})['karten'][-1]['text']              # Vorgeschichte kurz dabei


def test_abnahme_entscheidet_das_audit_nicht_der_agent():
    d = _projekt()
    K.lauf_start(d)
    k = K.naechste(d, _au('Teil haken: Pruefung nicht bestanden: wand 1.2'))['karte']
    assert k['agent'] == 'mb2-cad' and k['stufe'] == 'sonnet' and 'Teil haken' in k['text'], k
    assert K.naechste(d, _au('Kein G-Code'))['stop'] == 'karte_offen'                     # erst Ergebnis, dann neue
    # Agent meldet OK, audit zeigt den Mangel noch (andere Zahl, gleicher Kopf) -> fehler
    assert K.ergebnis(d, _au('Teil haken: Pruefung nicht bestanden: wand 1.5'), notiz='OK')['status'] == 'fehler'
    assert K.naechste(d, _au('Teil haken: Pruefung nicht bestanden: wand 1.5'))['karte']['stufe'] == 'opus'
    assert K.ergebnis(d, _au())['status'] == 'ok'
    # Mangel kommt zurueck (Wippe) -> neue Runde ab Startstufe
    assert K.naechste(d, _au('Teil haken: Pruefung nicht bestanden: wand 1.1'))['karte']['stufe'] == 'sonnet'


def test_vorrang_und_nutzer():
    d = _projekt()
    K.lauf_start(d)
    r = K.naechste(d, _au('Kein G-Code (slice_plate)', 'FEM haken: Bewertung nicht ok', 'Teil haken: x'))
    assert r['karte']['agent'] == 'mb2-cad' and r['karte']['kopf'] == 'Teil haken', r   # Teil vor FEM vor Slicen
    K.ergebnis(d, _au())
    r = K.naechste(d, _au('Katalog X3 Budget gegen Toleranz (0.5, Grenze 0.5): ...'))
    assert r['stop'] == 'nutzer' and 'EINE Frage' in r['grund'], r                       # Widerspruch: Nutzer fragen
    r = K.naechste(d, _au('Anforderung A-GERAET unbewiesen: Abnahme fehlt', freigabe='druckfertig'))
    assert r['stop'] == 'nutzer' and 'Abnahme' in r['grund'], r
    assert K.naechste(d, _au(freigabe='fertig'))['stop'] == 'fertig'


def test_stand_kurz_und_vollstaendig():
    d = _projekt()
    K.lauf_start(d)
    fragen.einreihen(d, 'Stueckzahl?', 'ziel')
    t = K.stand(d, _au(*[f'Katalog M{i} sehr langer Mangeltext ' + 'x' * 400 for i in range(200)]))
    assert len(t.encode('utf-8')) <= K.STAND_MAX, len(t)
    assert 'Stueckzahl?' in t and '195 weitere' in t and 'Lauf: aktiv' in t, t
    assert open(os.path.join(d, 'pruef', 'stand.md'), encoding='utf-8').read() == t


def test_tokens_unbekannt_nie_null():
    d = _projekt()
    K.lauf_start(d)
    K.naechste(d, _au('Kein G-Code'))
    K.ergebnis(d, _au())                                # Host meldet keine Tokens
    K.naechste(d, _au('Keine Druckplatte (cad_plate)'))
    K.ergebnis(d, _au(), tokens=1200)
    r = K.lauf_ende(d)
    assert r['tokens'] == 1200 and r['tokens_unbekannt'] == 1, r
    ko = K.kosten(d)
    assert ko['mb2-slicer/haiku']['tokens_unbekannt'] == 1 and ko['mb2-cad/haiku']['tokens'] == 1200, ko


if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_') and callable(f):
            f()
            print('ok', n)
    print('alle ok')
