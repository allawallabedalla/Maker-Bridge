"""Messkette und Messtechnik (19.11.2026): Aufloesung, GUM-Budget, Referenzmessreihen, V-Matrix-Anbindung.
Aufruf aus maker-bridge-2/:  uv run python tests/test_messkette.py"""
import json
import math
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mb2 import anforderungen as an, befehle, pruefungen   # noqa: E402
from mb2.pruefungen import messkette as mk                 # noqa: E402

TMP = tempfile.mkdtemp(prefix='mb2_messkette_')
REF = {'mittel': 'Pt100 AA + Messbruecke', 'U': 0.02, 'k': 2, 'einheit': '°C',
       'rueckfuehrung': 'DAkkS-Kalibrierschein D-K-00000 (Testdaten)', 'gueltig_bis': '2027-12-31'}
BED = {'T_umgebung_C': 23, 'U_V': 3.3}
MT = {'messbereich': {'min': 0.0, 'max': 100.0, 'einheit': '°C'},
      'genauigkeit': {'max_abs': 0.5, 'einheit': '°C'},
      'linearitaet': {'max_abs': 0.2, 'einheit': '%FS'},
      'hysterese': {'max_abs': 0.2, 'einheit': '%FS'},
      'drift': {'max_abs': 0.1, 'einheit': '°C/Jahr'},
      'wiederholbarkeit': {'max_abs': 0.05, 'einheit': '°C'},
      'bedingungen': {'T_umgebung_C': [20, 26], 'U_V': 3.3}, 'wiederholungen': 10, 'dauer_h': 720}


def reihe(eig, punkte, **kw):
    r = {'id': f'R-{eig}', 'eigenschaft': eig, 'verfahren': 'Test', 'datum': '2026-11-19', 'referenz': dict(REF),
         'bedingungen': dict(BED), 'punkte': punkte}
    r.update(kw)
    return r


# ---------------------------------------------------------------------------------------------- Aufloesung/Budget

def test_quantisierung_16bit():
    a = mk.aufloesung(16, 3.3)
    assert abs(a['q_V'] - 50.35e-6) < 0.01e-6, a['q_V']
    assert abs(a['u_quant_V'] - a['q_V'] / math.sqrt(12)) < 1e-15
    # Mit Rauschen ist die effektive Aufloesung kleiner als die nominale Bitzahl
    b = mk.aufloesung(16, 3.3, rauschen_rms_v=200e-6)
    assert b['effektive_bits'] < 16 and b['rauschfreie_bits'] < b['effektive_bits'], b
    assert b['kleinste_aenderung_V'] > a['q_V'] * 10, b   # 6,6 * 200 uV >> 50 uV


def test_budget_verteilungen_und_einzelbeitraege():
    b = mk.budget([{'name': 'ref', 'wert': 0.02, 'verteilung': 'normal', 'k': 2},     # u = 0,01
                   {'name': 'tol', 'wert': math.sqrt(3) * 0.01, 'verteilung': 'rechteck'},  # u = 0,01
                   {'name': 'roh', 'wert': 0.02, 'verteilung': 'u', 'c': 0.5}], einheit='°C')   # c*u = 0,01
    assert all(abs(z['beitrag'] - 0.01) < 1e-12 for z in b['beitraege']), b['beitraege']
    assert abs(b['u_c'] - math.sqrt(3) * 0.01) < 1e-12 and abs(b['U'] - 2 * b['u_c']) < 1e-12, b
    assert abs(sum(z['anteil_proz'] for z in b['beitraege']) - 100) < 1e-9
    assert 'vereinfacht' in b['modell']


def test_budget_fehlender_wert_ist_kein_ergebnis():
    b = mk.budget([{'name': 'ref', 'wert': 0.01}, {'name': 'sensor', 'wert': None}])
    assert b['u_c'] is None and b['U'] is None and b['fehlt'] == ['sensor'], b


def test_budget_welch_satterthwaite():
    b = mk.budget([{'name': 'typA', 'wert': 0.01, 'freiheitsgrade': 4}])
    assert b['nu_eff'] == 4 and b['k'] == 2.87, b     # GUM Tabelle G.2


def test_korrelation():
    z = [{'name': 'a', 'wert': 0.01}, {'name': 'b', 'wert': 0.01}]
    voll = mk.budget(z, korrelationen=[{'a': 'a', 'b': 'b', 'r': 1}])
    gegen = mk.budget(z, korrelationen=[{'a': 'a', 'b': 'b', 'r': -1}])
    assert abs(voll['u_c'] - 0.02) < 1e-12 and gegen['u_c'] < 1e-9, (voll['u_c'], gegen['u_c'])


def test_messkette_berechnen_bezugspunkte():
    # Sensor 10 mV/°C, Verstaerkung 10 -> 0,1 V/°C am ADC; 16 Bit, 3,3 V
    b = mk.messkette_berechnen(16, 3.3, 100e-6, 1.65e-3, gain=10, sensor_uncertainty=0.1,
                               empfindlichkeit_v_je_einheit=0.01, u_offset_v=50e-6, einheit='°C')
    z = {x['name']: x for x in b['beitraege']}
    assert abs(z['adc_quantisierung']['beitrag'] - mk.aufloesung(16, 3.3)['u_quant_V'] / 0.1) < 1e-12
    assert abs(z['adc_rauschen']['beitrag'] - 100e-6 / 0.1) < 1e-12        # getrennt von Quantisierung
    assert abs(z['adc_referenz']['beitrag'] - 1.65e-3 / 0.1) < 1e-12       # relativ 0,05 % auf Vollausschlag
    assert abs(z['offset']['beitrag'] - 50e-6 / 0.01) < 1e-12              # eingangsbezogen, c = 1/S
    assert abs(z['sensorelement']['beitrag'] - 0.1) < 1e-12
    assert b['dominant'] == 'sensorelement' and b['U'] > 0.2, b


# ---------------------------------------------------------------------------------------------- Messreihen

def test_ohne_reihe_unbewiesen():
    b = mk.bewerte_reihe(None, 'genauigkeit', MT)
    assert b['status'] == 'unbewiesen' and b['grund'] == 'ohne_referenzmessung', b


def test_referenz_ohne_rueckfuehrung_oder_unsicherheit():
    r = reihe('genauigkeit', [{'ref': x, 'ist': x} for x in (0, 50, 100)])
    r['referenz'].pop('rueckfuehrung')
    assert mk.bewerte_reihe(r, 'genauigkeit', MT)['grund'] == 'referenz_nicht_rueckfuehrbar'
    r = reihe('genauigkeit', [{'ref': x, 'ist': x} for x in (0, 50, 100)])
    r['referenz'].pop('U')
    assert mk.bewerte_reihe(r, 'genauigkeit', MT)['grund'] == 'referenz_ohne_unsicherheit'
    r = reihe('genauigkeit', [{'ref': x, 'ist': x} for x in (0, 50, 100)], datum='2028-01-02')
    assert mk.bewerte_reihe(r, 'genauigkeit', MT)['grund'] == 'referenz_abgelaufen'


def test_bedingungen_abweichend():
    r = reihe('genauigkeit', [{'ref': x, 'ist': x} for x in (0, 50, 100)], bedingungen={'T_umgebung_C': 30})
    b = mk.bewerte_reihe(r, 'genauigkeit', MT)
    assert b['grund'] == 'bedingungen_abweichend' and 'U_V fehlt' in b['text'] and '30' in b['text'], b


def test_genauigkeit_schutzband():
    ok = mk.bewerte_reihe(reihe('genauigkeit', [{'ref': x, 'ist': x + 0.3} for x in (0, 50, 100)]), 'genauigkeit', MT)
    assert ok['status'] == 'bewiesen' and abs(ok['kennwert'] - 0.3) < 1e-9 and abs(ok['U_pruef'] - 0.02) < 1e-12, ok
    grau = mk.bewerte_reihe(reihe('genauigkeit', [{'ref': x, 'ist': x + 0.49} for x in (0, 50, 100)]),
                            'genauigkeit', MT)
    assert grau['status'] == 'vorbehalt', grau            # 0,49 + 0,02 > 0,5
    schlecht = mk.bewerte_reihe(reihe('genauigkeit', [{'ref': 0, 'ist': 0.6}, {'ref': 50, 'ist': 50},
                                                      {'ref': 100, 'ist': 100}]), 'genauigkeit', MT)
    assert schlecht['status'] == 'verletzt', schlecht


def test_zweipunktkalibrierung_beweist_keine_linearitaet():
    b = mk.bewerte_reihe(reihe('linearitaet', [{'ref': 0, 'ist': 0}, {'ref': 100, 'ist': 100}]), 'linearitaet', MT)
    assert b['status'] == 'unbewiesen' and b['grund'] == 'verfahren_unzureichend', b


def test_linearitaet_mehrpunkt_in_fs():
    # Kennlinie mit Bauch: Mitte +0,3 °C -> Restfehler zur Ausgleichsgeraden ~0,18 °C = 0,18 %FS
    pk = [{'ref': x, 'ist': x + 0.3 * (1 - ((x - 50) / 50) ** 2)} for x in (0, 25, 50, 75, 100)]
    b = mk.bewerte_reihe(reihe('linearitaet', pk), 'linearitaet', MT)
    assert b['einheit'] == '%FS' and 0.1 < b['kennwert'] < 0.2, b
    assert b['status'] in ('bewiesen', 'vorbehalt'), b


def test_hysterese_braucht_auf_und_ab():
    nur_auf = [{'ref': x, 'ist': x, 'richtung': 'auf'} for x in (0, 50, 100)]
    assert mk.bewerte_reihe(reihe('hysterese', nur_auf), 'hysterese', MT)['grund'] == 'verfahren_unzureichend'
    pk = nur_auf + [{'ref': x, 'ist': x + 0.4, 'richtung': 'ab'} for x in (0, 50, 100)]
    b = mk.bewerte_reihe(reihe('hysterese', pk), 'hysterese', MT)
    assert b['status'] == 'verletzt' and abs(b['kennwert'] - 0.4) < 1e-9, b     # 0,4 %FS > 0,2


def test_drift_braucht_zeitraum_und_rechnet_auf_jahr():
    kurz = [{'ref': 25, 'ist': 25, 't_h': t} for t in (0, 24, 48)]
    assert mk.bewerte_reihe(reihe('drift', kurz), 'drift', MT)['grund'] == 'verfahren_unzureichend'
    lang = [{'ref': 25, 'ist': 25 + 0.01 * t / 720, 't_h': t} for t in (0, 360, 720)]    # 0,01 °C je Monat
    b = mk.bewerte_reihe(reihe('drift', lang), 'drift', MT)
    assert abs(b['kennwert'] - 0.01 * 8766 / 720) < 1e-9 and b['status'] == 'verletzt', b   # 0,12 °C/Jahr > 0,1


def test_wiederholbarkeit_mindestanzahl():
    wenig = [{'ref': 25, 'ist': 25 + 0.01 * i} for i in range(5)]
    assert mk.bewerte_reihe(reihe('wiederholbarkeit', wenig), 'wiederholbarkeit', MT)['grund'] == \
        'verfahren_unzureichend'
    genug = [{'ref': 25, 'ist': 25 + (0.02 if i % 2 else -0.02)} for i in range(10)]
    b = mk.bewerte_reihe(reihe('wiederholbarkeit', genug), 'wiederholbarkeit', MT)
    assert b['status'] == 'bewiesen' and b['kennwert'] < 0.05, b


def test_einheit_unpassend():
    mt = dict(MT, genauigkeit={'max_abs': 0.5, 'einheit': 'K'})
    b = mk.bewerte_reihe(reihe('genauigkeit', [{'ref': x, 'ist': x} for x in (0, 50, 100)]), 'genauigkeit', mt)
    assert b['grund'] == 'einheit_unpassend', b


# ---------------------------------------------------------------------------------------------- V-Matrix

def _projekt(name, messkette=None):
    befehle.PROJEKTE = TMP
    einsatz = {'T_max_C': 35, 'material': 'PETG'}
    if messkette:
        einsatz['messkette'] = messkette
    befehle.project_new(name, 'Temperatursensor fuer den Schaltschrank', '', einsatz)
    return os.path.join(TMP, name)


def _anforderung(d, nachweise):
    p = os.path.join(d, 'anforderungen.json')
    a = json.load(open(p, encoding='utf-8'))
    a['anforderungen'].append({'id': 'A-MESS', 'ebene': 'system', 'herkunft': 'Nutzer 19.11.2026',
                               'text': 'Temperatur 0 ... 100 °C mit +-0,5 °C', 'messtechnik': MT,
                               'nachweise': nachweise})
    json.dump(a, open(p, 'w', encoding='utf-8'), ensure_ascii=False)


def test_vmatrix_fehlende_messnachweise_sind_maengel():
    d = _projekt('mk_ohne')
    _anforderung(d, [{'art': 'abnahme', 'ref': 'AB-FUNKTION', 'stufe': 'abnahme'}])
    z = next(x for x in an.pruefen(d)['anforderungen'] if x['id'] == 'A-MESS')
    fehlend = [m for m in z['matrix_maengel'] if 'ohne Nachweis art=messung' in m]
    assert len(fehlend) == 6 and z['status'] != 'bewiesen', z['matrix_maengel']


def test_vmatrix_messung_ohne_reihe_unbewiesen_mit_grund():
    d = _projekt('mk_reihe')
    _anforderung(d, [{'art': 'messung', 'ref': f'R-{e}', 'eigenschaft': e, 'stufe': 'abnahme'}
                     for e in mk.EIGENSCHAFTEN])
    v = an.pruefen(d)
    z = next(x for x in v['anforderungen'] if x['id'] == 'A-MESS')
    assert not z['matrix_maengel'], z['matrix_maengel']
    assert z['status'] == 'unbewiesen' and all(n['grund'] == 'ohne_referenzmessung' for n in z['nachweise']), z
    # Genauigkeit nachweisen: nur dieser Nachweis wird gruen, die Anforderung bleibt unbewiesen
    an.messreihe_eintragen(d, reihe('genauigkeit', [{'ref': x, 'ist': x + 0.1} for x in (0, 50, 100)]))
    z = next(x for x in an.pruefen(d)['anforderungen'] if x['id'] == 'A-MESS')
    g = next(n for n in z['nachweise'] if n['eigenschaft'] == 'genauigkeit')
    assert g['status'] == 'bewiesen' and abs(g['kennwert'] - 0.1) < 1e-9 and z['status'] == 'unbewiesen', z


def test_katalog_mk_und_ausloeser():
    # Messtechnische Anforderung ohne Messkette im soll -> MK1/MK2 uebersprungen -> Ausloeser 'messung' -> fehler
    d = os.path.join(TMP, 'mk_reihe')
    k = pruefungen.alle(d)
    mk1 = [e for e in k['module']['messkette'] if e['id'] == 'MK1']
    assert mk1 and mk1[0]['stufe'] == 'fehler' and 'messung' in k['merkmale'], (mk1, k['merkmale'])
    # Mit Messkette: Budget gerechnet, S-MESSKETTE im Lastenheft
    kette = {'adc_bits': 16, 'v_ref_V': 3.3, 'adc_rauschen_V': 100e-6, 'u_ref_V': 1.65e-3, 'verstaerkung': 10,
             'empfindlichkeit_V_je_einheit': 0.01, 'sensor_u': 0.1, 'einheit': '°C', 'ziel_U': 0.5,
             'ziel_aufloesung': 0.05, 'messbereich': {'min': 0, 'max': 100}, 'offset_V_am_adc': 0.1,
             '_herkunft': {}}
    d2 = _projekt('mk_kette', kette)
    erg = {e['id']: e for e in pruefungen.alle(d2)['module']['messkette']}
    assert erg['MK1']['stufe'] in ('ok', 'warnung') and erg['MK1']['wert'] < 0.5, erg['MK1']
    assert erg['MK1']['daten']['beitraege'], erg['MK1']
    assert erg['MK3']['stufe'] == 'fehler', erg['MK3']     # 0,1 V + 10 * 0,01 * 100 = 10,1 V > 3,3 V
    ids = {a['id'] for a in json.load(open(os.path.join(d2, 'anforderungen.json'), encoding='utf-8'))['anforderungen']}
    assert 'S-MESSKETTE' in ids, ids


if __name__ == '__main__':
    try:
        for n, f in list(globals().items()):
            if n.startswith('test_') and callable(f):
                f()
                print('ok', n)
        print('alle ok')
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
