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
    # 100 ml/min: Re ~ 2118 -> Uebergang: keine Formel, FL2 uebersprungen
    d2 = _projekt('fl2', {'stroemung': {'medium': WASSER, 'kanaele': [dict(k, Q_max_ml_min=100)]}, '_herkunft': HK})
    r2 = {x['id']: x for x in stroemung.pruefe(d2)}
    assert r2['FL1']['stufe'] == 'warnung' and 'Uebergang' in r2['FL1']['hinweis'], r2['FL1']
    assert r2['FL2']['stufe'] == 'uebersprungen'
    # 200 ml/min: Re = 998*4,244*1e-3/1e-3 = 4236 -> turbulent, Blasius lambda = 0,3164 Re^-0,25,
    # dp = lambda (L/d) rho v^2/2 + zeta rho v^2/2 (Einzelverlust zeta 0,5)
    k3 = dict(k, Q_max_ml_min=200, einzelverluste=[{'name': 'Verschraubung', 'zeta': 0.5}])
    d3 = _projekt('fl3', {'stroemung': {'medium': WASSER, 'kanaele': [k3]}, '_herkunft': HK})
    r3 = {x['id']: x for x in stroemung.pruefe(d3)}
    v = 200e-6 / 60 / (math.pi * 0.25e-6)
    Re = 998 * v * 1e-3 / 1e-3
    lam = 0.3164 * Re ** -0.25
    assert r3['FL1']['stufe'] == 'info' and 'turbulent' in r3['FL1']['hinweis'], r3['FL1']
    nah(r3['FL2']['daten']['dp_Pa'], lam * 10 * 998 * v * v / 2 + 0.5 * 998 * v * v / 2)
    assert r3['FL2']['stufe'] == 'fehler'                       # weit ueber 100 Pa
    # Colebrook mit Rauigkeit 0 (hydraulisch glatt) liegt bei Re 4236 nahe Blasius (< 5 %)
    lc = stroemung.lambda_turbulent(Re, 1e-3, 0.0)
    assert abs(lc / lam - 1) < 0.05, (lc, lam)
    assert stroemung.lambda_turbulent(2e5, 1e-3) is None       # glatt ueber 1e5: Rauigkeit noetig
    assert stroemung.lambda_turbulent(2e5, 1e-3, 0.0015) > stroemung.lambda_turbulent(2e5, 1e-3, 0.0)
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
        'daten': {'datensatz_bytes': 16, 'intervall_s': 60, 'speicher_bytes': 4194304, 'aufbewahrung_h': 720,
                  'uebertragung': {'pakete_je_h': 60, 'nutzdaten_bytes_je_paket': 51, 'luftzeit_s_je_paket': 0.37,
                                   'duty_max': 0.01}, 'schreibzyklen_max': 100000, 'schreibblock_bytes': 4096,
                  'puffer_datensaetze': 64}, 'lebensdauer_h': 20000,
        '_herkunft': dict(HK, messkette='datenblatt: TESTFIXTURE')}}
    funde = P._weglassprobe('wp_erw', soll, ['messkette', 'stroemung', 'daten'])
    assert not funde, f'Entfernte Angabe macht ein Ergebnis besser: {funde[:10]}'
    abst = P._randprobe('rp_erw', soll, ('messkette', 'stroemung', 'daten'))
    assert not abst, f'Abstuerze bei Randwerten: {abst[:10]}'


def test_datenbudget_hand():
    """16 B je Sekunde = 57 600 B/h; 720 h = 41 472 000 B gegen 4 MiB x 0,8 = 3 355 443 B -> fehler, voll nach 58 h.
    Alle 60 s: 960 B/h x 720 = 691 200 B -> ok. Funk: 60 Pakete x 51 B = 3060 B/h; Luftzeit 60 x 0,37 = 22,2 s/h
    gegen 1 % = 36 s/h. Flash: jede Sekunde ein 4-KiB-Block, 20 000 h: 3600 x 4096 x 20000 / 4 MiB = 70 312 Vollzyklen
    (> 50 % von 100 000 -> warnung); mit 64 Saetzen Puffer 56,25 Schreibvorgaenge/h -> 1098,6 -> ok."""
    from mb2.pruefungen import daten
    D = {'datensatz_bytes': 16, 'intervall_s': 1, 'speicher_bytes': 4194304, 'reserve_anteil': 0.2, 'aufbewahrung_h': 720,
         'uebertragung': {'pakete_je_h': 60, 'nutzdaten_bytes_je_paket': 51, 'luftzeit_s_je_paket': 0.37, 'duty_max': 0.01},
         'schreibzyklen_max': 100000, 'schreibblock_bytes': 4096, 'puffer_datensaetze': 1}

    def lauf(d, **pj):
        return {e['id']: e for e in daten.pruefe(_projekt('ds', dict({'daten': d, 'lebensdauer_h': 20000}, **pj)))}
    r = lauf(D)
    assert r['DS1']['stufe'] == 'fehler' and r['DS1']['wert'] == 41472000 and 'voll nach 58 h' in r['DS1']['hinweis'], r['DS1']
    assert r['DS2']['stufe'] == 'fehler', r['DS2']                               # 57 600 B/h passen nicht in 3060 B/h
    assert r['DS3']['stufe'] == 'warnung' and abs(r['DS3']['wert'] - 70312.5) < 0.1, r['DS3']
    r = lauf(dict(D, intervall_s=60, puffer_datensaetze=64))
    assert r['DS1']['stufe'] == 'ok' and r['DS1']['wert'] == 691200, r['DS1']
    assert r['DS2']['stufe'] == 'ok' and abs(r['DS2']['wert'] - 22.2) < 1e-9, r['DS2']
    assert r['DS3']['stufe'] == 'ok', r['DS3']
    r = lauf(dict(D, intervall_s=60, uebertragung=dict(D['uebertragung'], pakete_je_h=120)))
    assert r['DS2']['stufe'] == 'fehler' and abs(r['DS2']['wert'] - 44.4) < 1e-9, r['DS2']   # 44,4 s/h > 36 s/h
    # Kanal nicht angegeben -> hoechstens warnung
    r = lauf(dict(D, intervall_s=60, uebertragung={'pakete_je_h': 60, 'nutzdaten_bytes_je_paket': 51}))
    assert r['DS2']['stufe'] == 'warnung', r['DS2']
    # ohne Lebensdauer kein DS3
    assert {e['id']: e for e in daten.pruefe(_projekt('ds0', {'daten': D}))}['DS3']['stufe'] == 'uebersprungen'
    # Merkmal aus dem Text -> Ausloeser
    d = _projekt('ds_text', {}, text='Datenlogger fuer Messwerte')
    ds = [e for l in pruefungen.alle(d)['module'].values() for e in l if e['id'] == 'DS1']
    assert ds and ds[0]['stufe'] == 'fehler' and ds[0].get('ausloeser') == 'daten', ds


def test_nicht_gedruckte_teile():
    """Teil 'kanal' wird extern gefertigt (CNC, sigma 0,01 mm laut Anbieter): T1 nutzt dieses Modell statt des MK4.
    Bohrung 1,00 +/- 0,05: C_pk = 0,05 / (3 x 0,01) = 1,67 -> ok. Dasselbe Mass auf dem MK4 -> nicht ok."""
    from build123d import Box
    from mb2 import cad
    from mb2.pruefungen import toleranz
    tol = [{'name': 'Kanal', 'nenn_mm': 1.0, 'tol_mm': 0.05, 'art': 'bohrung'}]
    ext = {'verfahren': 'extern', 'fertigung': {'name': 'CNC Alu', 'sigma_mm': 0.01, 'wand_min_mm': 0.5},
           'toleranzen': tol, '_herkunft': {'fertigung': 'datenblatt: TESTFIXTURE Anbieter'}}

    def proj(name, ts):
        d = os.path.join(TMP, name)
        os.makedirs(os.path.join(d, 'cad'), exist_ok=True)
        os.makedirs(os.path.join(d, 'out'), exist_ok=True)
        json.dump({'_projekt': {'material': 'PETG'}, 'kanal': ts}, open(os.path.join(d, 'cad', 'soll.json'), 'w'))
        json.dump({'ok': True, 'bbox_mm': [10, 10, 10], 'druck_drehung': [0, 0, 0]},
                  open(os.path.join(d, 'out', 'kanal.pruefung.json'), 'w'))
        open(os.path.join(d, 'projekt.md'), 'w').write('# p\n')
        return d
    t1 = lambda d: next(e for e in toleranz.pruefe(d) if e['id'] == 'T1')  # noqa: E731
    r = t1(proj('vf_ext', ext))
    assert r['stufe'] == 'ok' and abs(r['wert'] - 1.67) < 0.01 and 'CNC Alu' in r['hinweis'], r
    assert not [e for e in toleranz.pruefe(proj('vf_ext2', ext)) if e['id'] == 'T4' and e.get('teil') == 'kanal']
    assert t1(proj('vf_fdm', {'toleranzen': tol}))['stufe'] != 'ok'                          # MK4 schafft es nicht
    assert t1(proj('vf_oh', dict(ext, _herkunft={})))['stufe'] == 'warnung'                  # Herkunft offen
    assert t1(proj('vf_ohne', dict(ext, fertigung={'name': 'CNC'})))['stufe'] == 'uebersprungen'
    # Wandgrenze des Verfahrens statt 1,8 mm
    platte = Box(20, 20, 1.0)
    assert any('Wand' in f or 'wand' in f for f in cad.pruefen(platte, soll={})['fehler'])
    assert not any('wand' in f.lower() for f in cad.pruefen(platte, soll=ext)['fehler'])
    # Wareneingangspruefung als Anforderung mit Abnahme
    d = proj('vf_anf', ext)
    a = {x['id']: x for x in an.standard(d)}
    assert 'S-FERTIGUNG-kanal' in a, list(a)
    nw = {n['ref']: n for n in a['S-FERTIGUNG-kanal']['nachweise']}
    assert nw['AB-WE-kanal']['kriterium']['groesse'] == 'ausser_toleranz' and 'Kanal 1.0' in nw['AB-WE-kanal']['anweisung']


if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_') and callable(f):
            f()
            print('ok', n)
    print('alle ok')
