"""V-Modell: Anforderungen, Beweispflicht, Herkunft, Abnahme, Feldabgleich, Firmware-Konstanten (15.11.2026).
Aufruf aus maker-bridge-2/:  uv run python tests/test_anforderungen.py"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mb2 import anforderungen as an, befehle, pruefungen   # noqa: E402
from mb2.pruefungen import firmware                        # noqa: E402

TMP = tempfile.mkdtemp(prefix='mb2_vmodell_')
FUNK = {'r_m': 830, 'f_MHz': 868, 'P_t_dBm': 14, 'P_rx_min_dBm': -132, 'G_t_dBi': 2, 'umgebung': 'dorf',
        'hindernisse': ['ziegel_dach'], 'kabel': [{'typ': 'rg174', 'm': 3}], 'magnetfuss_ohne_blech': True}


def neu(name, einsatz):
    befehle.PROJEKTE = TMP
    befehle.project_new(name, 'LoRa-Bodensensor im Garten', '', einsatz)
    return os.path.join(TMP, name)


def zeile(v, id):
    return next(z for z in v['anforderungen'] if z['id'] == id)


def test_project_new_legt_lastenheft_an():
    d = neu('vm_funk', {'aussen': True, 'T_min_C': -20, 'T_max_C': 35, 'farbe': 'weiss', 'material': 'ASA',
                        'elektronik': {'funk': FUNK}})
    a = json.load(open(os.path.join(d, 'anforderungen.json'), encoding='utf-8'))['anforderungen']
    ids = {x['id'] for x in a}
    assert {'A-GERAET', 'A-MONTAGE', 'A-FUNK', 'S-FUNK', 'S-DRUCK', 'S-TEMP'} <= ids, ids
    ab = json.load(open(os.path.join(d, 'abnahme.json'), encoding='utf-8'))
    assert {'AB-FUNK', 'AB-ANSCHLUSS', 'AB-FUNKTION'} <= {s['id'] for s in ab['schritte']}, ab


def test_beweispflicht_und_freigabe():
    """Ohne Teile/Slice ist nichts bewiesen -> nicht_druckfertig. Bodenklima-Funk (E16 fehler) -> S-FUNK verletzt,
    Eltern A-FUNK erbt 'verletzt'."""
    d = os.path.join(TMP, 'vm_funk')
    v = an.pruefen(d)
    assert v['freigabe'] == 'nicht_druckfertig', v['freigabe']
    assert zeile(v, 'S-FUNK')['status'] == 'verletzt', zeile(v, 'S-FUNK')
    assert zeile(v, 'A-FUNK')['status'] == 'verletzt' and 'S-FUNK' in zeile(v, 'A-FUNK').get('wegen_kind', [])
    assert zeile(v, 'S-DRUCK')['status'] == 'unbewiesen'
    assert os.path.exists(os.path.join(d, 'pruef', 'v_matrix.json'))


def test_herkunft_vorbehalt():
    """Bestandener Nachweis auf geschaetzter Eingabe ist nur 'vorbehalt'; fehlender Wert ist 'unbewiesen'."""
    soll = {'_projekt': {'T_max_C': 35, '_herkunft': {'T_max_C': 'geschaetzt: Sommer'}}}
    assert an.schwaechste_herkunft(soll, ['T_max_C'])[0] == 'geschaetzt'
    soll['_projekt']['_herkunft']['T_max_C'] = 'gemessen: Logger 2026'
    assert an.schwaechste_herkunft(soll, ['T_max_C'])[0] == 'gemessen'
    assert an.schwaechste_herkunft(soll, ['T_min_C'])[0] == 'fehlt'
    soll['_projekt']['elektronik'] = {'funk': {'r_m': 830}}
    soll['_projekt']['_herkunft']['elektronik.funk'] = 'gemessen: Karte'
    assert an.schwaechste_herkunft(soll, ['elektronik.funk.r_m'])[0] == 'gemessen'   # Elternfeld deckt Kind ab
    assert an.schwaechste_herkunft({'_projekt': {'x': 1}}, ['x'])[0] is None         # Herkunft offen


def test_reserve_gegen_unsicherheit():
    # E16-Reserve 12 dB, Herkunft geschaetzt (10 dB) -> reicht; angenommen (15 dB) -> zu knapp
    e = {'id': 'E16', 'wert': 12.0, 'grenze': 10, 'einheit': 'dB'}
    assert an._reserve_ok(e, 'geschaetzt')[0] is True
    assert an._reserve_ok(e, 'angenommen')[0] is False
    # relativ: Wert 2,4 gegen Grenze 2 = 20 % Reserve; datenblatt 10 % ok, geschaetzt 30 % zu knapp
    e = {'id': 'M1', 'wert': 2.4, 'grenze': 2.0, 'einheit': ''}
    assert an._reserve_ok(e, 'datenblatt')[0] is True and an._reserve_ok(e, 'geschaetzt')[0] is False


def test_abnahme_lageunabhaengig():
    assert an.lageabhaengig('Kabel von links nach rechts einklemmen')
    assert an.lageabhaengig('links Pin 1 (Dreieck): weiss') is None
    assert an.lageabhaengig('J2 Pin 1 = FRQ (weiss)') is None
    d = os.path.join(TMP, 'vm_funk')
    ab = json.load(open(os.path.join(d, 'abnahme.json'), encoding='utf-8'))
    ab['schritte'].append({'id': 'AB-X', 'anforderung': 'A-MONTAGE', 'anweisung': 'oben die rote Ader', 'soll': {}})
    json.dump(ab, open(os.path.join(d, 'abnahme.json'), 'w', encoding='utf-8'))
    r = an.abnahme_erzeugen(d)
    assert any(p.startswith('AB-X') and 'kein messbares Soll' in p for p in r['probleme']), r


def test_abnahme_eintragen_beweist():
    d = os.path.join(TMP, 'vm_funk')
    s = an.abnahme_eintragen(d, 'AB-FUNK', -17.0, 'Garten, Antenne auf Unterlegscheibe')
    assert s['ok'] is False                             # -17 < -5
    v = an.pruefen(d)
    n = next(x for x in zeile(v, 'A-FUNK')['nachweise'] if x['ref'] == 'AB-FUNK')
    assert n['status'] == 'verletzt', n
    s = an.abnahme_eintragen(d, 'AB-FUNK', -3.0)
    assert s['ok'] is True


def test_feldabgleich_schreibt_feldfall():
    """Bodenklima-Feldfall: SNR -17 dB -> P_rx = -17 + (-117) = -134 dBm. Altes Modell (umgebung 'frei') sagt
    P_rx ~ -84 dBm voraus -> 50 dB zu optimistisch -> Feldfall. Neues Modell (dorf + Dach + Kabel) liegt im Rahmen."""
    ordner = os.path.join(TMP, 'feldfaelle')
    d = neu('vm_alt', {'aussen': True, 'material': 'ASA', 'elektronik': {'funk': dict(FUNK, umgebung='frei',
                                                                                        hindernisse=[], kabel=[],
                                                                                        magnetfuss_ohne_blech=False)}})
    an.feld_eintragen(d, 'snr_dB', -17.0, 'dB', 'Garten 830 m', 'Basis werte.json 15.11.2026')
    r = an.feld_abgleich(d, feldfall_ordner=ordner)
    z = r['abgleich'][0]
    assert z['urteil'] == 'zu_optimistisch' and r['neue_feldfaelle'], r
    assert abs(z['gemessen_umgerechnet'] - (-134.0)) < 0.1, z
    d2 = os.path.join(TMP, 'vm_funk')
    an.feld_eintragen(d2, 'snr_dB', -17.0, 'dB')
    r2 = an.feld_abgleich(d2, feldfall_ordner=ordner)
    assert r2['abgleich'][-1]['urteil'] in ('passt', 'zu_pessimistisch'), r2


def test_firmware_konstante_gegen_soll():
    d = neu('vm_fw', {'material': 'ASA', 'elektronik': {'funk': dict(FUNK, P_t_dBm=22)},
                      'firmware': {'pfad': 'firmware', 'konstanten': {
                          'FUNK_LEISTUNG_DBM': {'datei': 'config.h', 'soll_aus': 'elektronik.funk.P_t_dBm'}}}})
    os.makedirs(os.path.join(d, 'firmware'))
    open(os.path.join(d, 'firmware', 'config.h'), 'w').write('#define FUNK_LEISTUNG_DBM 14 // reicht laut Abschaetzung\n')
    e = firmware.pruefe(d)[0]
    assert e['stufe'] == 'fehler' and e['wert'] == 14 and e['grenze'] == 22, e
    open(os.path.join(d, 'firmware', 'config.h'), 'w').write('#define FUNK_LEISTUNG_DBM 22\n')
    assert firmware.pruefe(d)[0]['stufe'] == 'ok'
    # Firmware im Text erwaehnt, aber keine Angabe -> Ausloeser macht FW1 zum fehler
    d3 = neu('vm_fw_leer', {'material': 'PETG'})
    open(os.path.join(d3, 'projekt.md'), 'a', encoding='utf-8').write('\nFirmware: sensor.ino\n')
    fw = [x for x in pruefungen.alle(d3)['module']['firmware'] if x['id'] == 'FW1']
    assert fw and fw[0]['stufe'] == 'fehler', fw


def test_stakeholder_wunsch_und_herleitung():
    """Wunsch (stakeholder) -> messbare Spezifikation (system) mit herleitung; ohne beides Matrix-Mangel."""
    d = neu('vm_stakeholder', {'T_max_C': 30, 'material': 'PETG'})
    p = os.path.join(d, 'anforderungen.json')
    a = json.load(open(p, encoding='utf-8'))
    a['anforderungen'] += [
        {'id': 'W-FOERDERN', 'ebene': 'stakeholder', 'herkunft': 'Kunde 19.11.2026', 'text': 'Pumpe foerdert genug',
         'nachweise': [{'art': 'abnahme', 'ref': 'AB-FUNKTION', 'stufe': 'abnahme'}]},
        {'id': 'A-LEISTUNG', 'ebene': 'system', 'herkunft': 'abgeleitet aus W-FOERDERN',
         'text': 'Motor >= 70 W', 'nachweise': [{'art': 'abnahme', 'ref': 'AB-FUNKTION', 'stufe': 'abnahme'}]}]
    json.dump(a, open(p, 'w', encoding='utf-8'), ensure_ascii=False)
    z = {x['id']: x for x in an.pruefen(d)['anforderungen']}
    m = ' '.join(z['A-LEISTUNG']['matrix_maengel'])
    assert 'Stakeholder-Wunsch' in m and 'herleitung' in m, m
    assert any('Stakeholder-Wunsch' in ' '.join(z[i]['matrix_maengel']) for i in ('A-GERAET', 'A-MONTAGE'))
    for x in a['anforderungen']:
        if x['ebene'] == 'system':
            x['eltern'] = ['W-FOERDERN']
            x['herleitung'] = 'P = rho g Q H = 63 W, mit Reserve 70 W'
    json.dump(a, open(p, 'w', encoding='utf-8'), ensure_ascii=False)
    z = {x['id']: x for x in an.pruefen(d)['anforderungen']}
    assert not z['A-LEISTUNG']['matrix_maengel'], z['A-LEISTUNG']['matrix_maengel']
    assert not z['W-FOERDERN']['matrix_maengel'], z['W-FOERDERN']['matrix_maengel']


def test_audit_meldet_freigabe():
    alt = befehle.PROJEKTE
    befehle.PROJEKTE = TMP
    try:
        a = befehle.audit('vm_funk')
        assert a['freigabe'] == 'nicht_druckfertig' and not a['messbar_ok'], a['freigabe']
        assert any(m.startswith('Anforderung S-FUNK') for m in a['maengel']), a['maengel']
        assert a['v_matrix'] and a['v_matrix']['offen_abnahme'], a['v_matrix']
    finally:
        befehle.PROJEKTE = alt


if __name__ == '__main__':
    try:
        for n, f in list(globals().items()):
            if n.startswith('test_') and callable(f):
                f()
                print('ok', n)
        print('alle ok')
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
