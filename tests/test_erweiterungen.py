"""Erweiterungen 19.11.2026 (aus der Machbarkeitspruefung Durchflusssensor, allgemein gehalten):
Messmodul-Profil (jede Messgroesse), Stroemung FL1-FL4, Beobachtbarkeit X10, Fehlerinjektion und Dichtheit.
Alle Zahlen sind Testwerte (TESTFIXTURE), keine Datenblattwerte. Handrechnungen stehen im Kommentar.
Aufruf aus maker-bridge-2/:  uv run python tests/test_erweiterungen.py"""
import json
import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mb2 import anforderungen as an, pruefungen  # noqa: E402
from mb2.pruefungen import messkette, stroemung, widerspruch  # noqa: E402
from mb2.sensorprofile import modul  # noqa: E402

TMP = tempfile.mkdtemp(prefix='mb2_erw_')
DB = lambda f: 'datenblatt'  # noqa: E731


def nah(a, b, rel=1e-3):
    assert abs(a - b) <= rel * abs(b), f'{a} != {b}'


def _projekt(name, pj, anforderungen=None, text=''):
    d = os.path.join(TMP, name)
    os.makedirs(os.path.join(d, 'cad'), exist_ok=True)
    json.dump({'_projekt': pj}, open(os.path.join(d, 'cad', 'soll.json'), 'w', encoding='utf-8'))
    open(os.path.join(d, 'projekt.md'), 'w', encoding='utf-8').write(f'# {name}\n{text}\n')
    if anforderungen is not None:
        json.dump({'anforderungen': anforderungen}, open(os.path.join(d, 'anforderungen.json'), 'w', encoding='utf-8'))
    return d


MK = {'profil': 'modul_digital', 'einheit': 'ml/min', 'messbereich': {'min': 0, 'max': 40}, 'ziel_U': 3.0,
      'ziel_aufloesung': 0.2, 'k': 2, 'dT_K': 10, 'messrate_Hz': 2, 'mittelung': 4,
      'modul': {'name': 'TESTFIXTURE', 'bereich_min': 0, 'bereich_max': 80,
                'genauigkeit': {'abs': 0.2, 'rel_messwert': 0.05}, 'wiederholbarkeit': 0.05, 'aufloesung': 0.01,
                'tk_rel_je_K': 0.001, 'messzeit_s': 0.1}}


def _e(res, i):
    return next(x for x in res if x['id'] == i)


def test_modulprofil_budget_hand():
    """Bei 40 ml/min: G = 0,2 + 0,05*40 = 2,2 -> u = 2,2/sqrt3 = 1,2702; Wiederholbarkeit 0,05/sqrt4 = 0,025;
    Aufloesung 0,01/sqrt12 = 0,002887; TK 0,001*40*10 = 0,4 -> /sqrt3 = 0,2309. u_c = 1,2912, U = 2,5825."""
    b = modul.budget_bei(MK, 40.0)
    u = math.sqrt((2.2 / math.sqrt(3)) ** 2 + 0.025 ** 2 + (0.01 / math.sqrt(12)) ** 2 + (0.4 / math.sqrt(3)) ** 2)
    nah(b['u_c'], u)
    nah(b['U'], 2 * u)
    r = {x['id']: x for x in modul.pruefe(MK, DB)}
    assert r['MK1']['stufe'] == 'ok' and r['MK1']['daten']['schlechtester_punkt'] == 40.0, r['MK1']
    assert {x['id']: x for x in modul.pruefe(MK, lambda f: None)}['MK1']['stufe'] == 'warnung'   # Herkunft offen
    # MK2: max(0,01, 6,6*0,05/sqrt4 = 0,165) = 0,165 <= 0,2 ok; Ziel 0,1 -> fehler
    nah(r['MK2']['wert'], 0.165)
    assert r['MK2']['stufe'] == 'ok'
    assert _e(modul.pruefe(dict(MK, ziel_aufloesung=0.1), DB), 'MK2')['stufe'] == 'fehler'
    # MK3: Messbereich 0..100 passt nicht in 0..80
    assert r['MK3']['stufe'] == 'ok'
    assert _e(modul.pruefe(dict(MK, messbereich={'min': 0, 'max': 100}), DB), 'MK3')['stufe'] == 'fehler'
    # MK5: 4 x 0,1 s = 0,4 s <= 0,5 s (2 Hz) ok; 5 Hz -> 0,2 s -> fehler
    assert r['MK5']['stufe'] == 'ok'
    assert _e(modul.pruefe(dict(MK, messrate_Hz=5), DB), 'MK5')['stufe'] == 'fehler'


def test_modulprofil_ohne_angaben_kein_ok():
    m = json.loads(json.dumps(MK))
    del m['modul']['tk_rel_je_K']
    r = _e(modul.pruefe(m, DB), 'MK1')
    assert r['stufe'] == 'uebersprungen' and 'tk_rel_je_K' in r['hinweis'], r
    m = json.loads(json.dumps(MK))
    m['modul']['genauigkeit'] = {}
    assert _e(modul.pruefe(m, DB), 'MK1')['stufe'] == 'uebersprungen'
    # kalibriert: u_kal ersetzt die Datenblatt-Genauigkeit
    k = dict(MK, modus='kalibriert', kalibrierung={'u_kal': 0.1})
    assert 'Modul-Genauigkeit' not in json.dumps(modul.budget_bei(k, 40.0)['beitraege'])
    # ueber messkette.pruefe im Projekt
    d = _projekt('mk_modul', {'messkette': MK, '_herkunft': {'messkette': 'datenblatt: TESTFIXTURE'}})
    assert _e(messkette.pruefe(d), 'MK1')['stufe'] == 'ok'


WASSER = {'name': 'TESTFIXTURE Wasser', 'viskositaet_Pa_s': 1.0e-3, 'dichte_kg_m3': 998.0}
HK = {'stroemung.medium': 'datenblatt: TESTFIXTURE Stofftabelle'}


def test_stroemung_hand():
    """d 1 mm, L 10 mm, 1 ml/min: v = 1,667e-8/7,854e-7 = 0,02122 m/s; Re = 998*0,02122*1e-3/1e-3 = 21,2;
    dp = 128*1e-3*0,01*1,667e-8/(pi*1e-12) = 6,79 Pa; L_e = 0,06*21,2*1 = 1,27 mm."""
    k = {'name': 'Messkanal', 'd_mm': 1.0, 'L_mm': 10, 'Q_min_ml_min': 1, 'Q_max_ml_min': 1, 'dp_max_Pa': 100,
         'einlauf_vor_sensor_mm': 0.5, 'dp_sensor_aufloesung_Pa': 2}
    d = _projekt('fl', {'stroemung': {'medium': WASSER, 'kanaele': [k]}, '_herkunft': HK})
    r = {x['id']: x for x in stroemung.pruefe(d)}
    Q = 1e-6 / 60
    nah(r['FL1']['wert'], round(998 * (Q / (math.pi * 0.25e-6)) * 1e-3 / 1e-3, 1), 1e-2)
    assert r['FL1']['stufe'] == 'ok'
    nah(r['FL2']['wert'], 128 * 1e-3 * 0.01 * Q / (math.pi * 1e-12))
    assert r['FL2']['stufe'] == 'ok'
    assert r['FL3']['stufe'] == 'warnung' and nah(r['FL3']['grenze'], 0.06 * r['FL1']['wert'] * 1.0, 1e-2) is None
    assert r['FL4']['stufe'] == 'warnung', r['FL4']          # 6,8 Pa < 10 x 2 Pa: Differenzdruck ungeeignet
    # 200 ml/min: Re ~ 4240 -> nicht laminar, FL2 rechnet nicht weiter
    k2 = dict(k, Q_max_ml_min=200)
    d2 = _projekt('fl2', {'stroemung': {'medium': WASSER, 'kanaele': [k2]}, '_herkunft': HK})
    r2 = {x['id']: x for x in stroemung.pruefe(d2)}
    assert r2['FL1']['stufe'] == 'warnung' and 'turbulent' in r2['FL1']['hinweis'], r2['FL1']
    assert r2['FL2']['stufe'] == 'uebersprungen'
    # Rechteckkanal 2 x 0,5 mm: dp = 12 mu L Q / (w h^3 (1 - 0,63 h/w))
    k3 = {'name': 'Schlitz', 'b_mm': 2, 'h_mm': 0.5, 'L_mm': 10, 'Q_max_ml_min': 1, 'dp_max_Pa': 100}
    nah(stroemung.druckverlust(k3, 1e-3, Q), 12 * 1e-3 * 0.01 * Q / (2e-3 * 0.5e-3 ** 3 * (1 - 0.63 * 0.25)))


def test_stroemung_ohne_stoffwerte_und_ausloeser():
    d = _projekt('fl_leer', {'stroemung': {'medium': {}, 'kanaele': [{'d_mm': 1, 'L_mm': 10, 'Q_max_ml_min': 1}]}})
    assert all(x['stufe'] == 'uebersprungen' for x in stroemung.pruefe(d))
    # Merkmal fluid aus dem Text, ohne stroemung-Angaben -> Ausloeser-Fehler (nicht still uebersprungen)
    d = _projekt('fl_text', {}, text='Durchflusssensor fuer einen Schlauch')
    k = pruefungen.alle(d)                       # Ausloeser greifen nur im Gesamtlauf
    fl = [e for l in k['module'].values() for e in l if e['id'] == 'FL1']
    assert fl and fl[0]['stufe'] == 'fehler' and fl[0].get('ausloeser') == 'fluid', fl
    # geschaetzte Stoffwerte -> hoechstens warnung
    d = _projekt('fl_sch', {'stroemung': {'medium': WASSER, 'kanaele': [{'d_mm': 1, 'L_mm': 10, 'Q_max_ml_min': 1,
                                                                         'dp_max_Pa': 100}]},
                            '_herkunft': {'stroemung.medium': 'geschaetzt'}})
    assert all(x['stufe'] != 'ok' for x in stroemung.pruefe(d) if x['id'] in ('FL1', 'FL2'))


ERK = {'id': 'A-DIAG', 'ebene': 'system', 'herkunft': 'TESTFIXTURE', 'text': 'Erkennt Leck und Verstopfung',
       'fehlalarm_max': 0, 'normalbetrieb_h': 24,
       'erkennung': [{'fehler': 'Leck nach dem Sensor', 'herbeifuehren': 'Schlauch hinter dem Sensor loesen',
                      'reaktion_s': 30, 'braucht_eine_von': [['durchfluss_ein', 'durchfluss_aus'], ['druck', 'pumpe']]},
                     {'fehler': 'Verstopfung', 'herbeifuehren': 'Schlauch abklemmen', 'reaktion_s': 10,
                      'braucht_eine_von': [['durchfluss', 'pumpe']]}],
       'dichtheit': {'pruefdruck_bar': 0.5, 'dauer_min': 10, 'abfall_max_mbar': 5},
       'nachweise': []}


def test_x10_beobachtbarkeit():
    d = _projekt('x10', {'messgroessen': ['durchfluss', 'temperatur', 'pumpe']}, [ERK])
    r = [x for x in widerspruch.pruefe(d) if x['id'] == 'X10']
    st = {x['titel'].split(': ')[1].split(' (')[0]: x['stufe'] for x in r}
    assert st == {'Leck nach dem Sensor': 'fehler', 'Verstopfung': 'ok'}, st      # Leck hinter dem Sensor unsichtbar
    d = _projekt('x10b', {'messgroessen': ['durchfluss', 'pumpe', 'druck']}, [ERK])
    assert all(x['stufe'] == 'ok' for x in widerspruch.pruefe(d) if x['id'] == 'X10')
    ohne = dict(ERK, erkennung=[{'fehler': 'X', 'herbeifuehren': 'y', 'reaktion_s': 1}])
    d = _projekt('x10c', {'messgroessen': ['durchfluss']}, [ohne])
    assert [x['stufe'] for x in widerspruch.pruefe(d) if x['id'] == 'X10'] == ['warnung']
    d = _projekt('x10d', {}, [ERK])
    assert [x['stufe'] for x in widerspruch.pruefe(d) if x['id'] == 'X10'] == ['uebersprungen']


def test_fehlerinjektion_und_dichtheit_als_abnahme():
    d = _projekt('fi', {}, [ERK])
    an.erzeugen(d)
    a = next(x for x in json.load(open(os.path.join(d, 'anforderungen.json'), encoding='utf-8'))['anforderungen']
             if x['id'] == 'A-DIAG')
    refs = [n['ref'] for n in a['nachweise']]
    assert refs == ['AB-FI-A-DIAG-1', 'AB-FI-A-DIAG-2', 'AB-FA-A-DIAG', 'AB-DICHT-A-DIAG'], refs
    an.erzeugen(d)                                                   # zweimal: nichts doppelt
    assert len(json.load(open(os.path.join(d, 'anforderungen.json'), encoding='utf-8'))['anforderungen'][0]['nachweise']) == 4
    ab = an.abnahme_erzeugen(d)
    assert not ab['probleme'], ab['probleme']
    v = an.pruefen(d, katalog={})
    z = next(x for x in v['anforderungen'] if x['id'] == 'A-DIAG')
    assert z['status'] == 'unbewiesen' and not z['matrix_maengel'], z
    for s, ist in (('AB-FI-A-DIAG-1', 1), ('AB-FI-A-DIAG-2', 1), ('AB-FA-A-DIAG', 0), ('AB-DICHT-A-DIAG', 2.0)):
        an.abnahme_eintragen(d, s, ist)
    z = next(x for x in an.pruefen(d, katalog={})['anforderungen'] if x['id'] == 'A-DIAG')
    assert z['status'] == 'bewiesen', z
    an.abnahme_eintragen(d, 'AB-FA-A-DIAG', 3)                       # Fehlalarme -> verletzt
    assert next(x for x in an.pruefen(d, katalog={})['anforderungen'] if x['id'] == 'A-DIAG')['status'] == 'verletzt'
    # Fehler ohne "herbeifuehren": nicht nachweisbar -> Matrix-Mangel
    d2 = _projekt('fi2', {}, [dict(ERK, erkennung=[{'fehler': 'Sensorbruch'}], dichtheit=None)])
    an.erzeugen(d2)
    m = next(x for x in an.pruefen(d2, katalog={})['anforderungen'] if x['id'] == 'A-DIAG')['matrix_maengel']
    assert any('herbeifuehren fehlt' in x for x in m) and any('reaktion_s' in x for x in m), m



def test_proben_fuer_die_erweiterungen():
    """Weglass- und Randwert-Probe (tests/test_keine_scheinsicherheit.py) auf Modulprofil und Stroemung."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import test_keine_scheinsicherheit as P
    soll = {'_projekt': {'messkette': MK, 'stroemung': {'medium': WASSER, 'kanaele': [
        {'name': 'K', 'd_mm': 1.0, 'L_mm': 10, 'Q_min_ml_min': 1, 'Q_max_ml_min': 20, 'dp_max_Pa': 1000,
         'einlauf_vor_sensor_mm': 5, 'dp_sensor_aufloesung_Pa': 0.1}]},
        '_herkunft': dict(HK, messkette='datenblatt: TESTFIXTURE')}}
    funde = P._weglassprobe('wp_erw', soll, ['messkette', 'stroemung'])
    assert not funde, f'Entfernte Angabe macht ein Ergebnis besser: {funde[:10]}'
    abst = P._randprobe('rp_erw', soll, ('messkette', 'stroemung'))
    assert not abst, f'Abstuerze bei Randwerten: {abst[:10]}'


if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_') and callable(f):
            f()
            print('ok', n)
    print('alle ok')
