"""Demonstrator MB2-TEMP-001 (PT100 + ADS1220): Kennlinie, Messgleichung, Budget, Aussteuerung, Freigabe (19.11.2026).
Aufruf aus maker-bridge-2/:  uv run python tests/test_temp_demonstrator.py

TESTFIXTURE: Die ADC-Kennwerte unten sind Platzhalter, um die Rechnung zu pruefen. Es sind KEINE Datenblattwerte des
ADS1220 und sie werden nirgends als solche verwendet (der Demonstrator selbst hat diese Felder leer).
"""
import copy
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mb2 import anforderungen as an, pruefungen       # noqa: E402
from mb2.pruefungen import messkette as MK            # noqa: E402
from mb2.sensorprofile import rtd                     # noqa: E402

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = os.path.join(BASIS, 'demonstratoren', 'MB2-TEMP-001')
TMP = tempfile.mkdtemp(prefix='mb2_temp001_')
FIX = 'datenblatt: TESTFIXTURE - kein echter Datenblattwert'
ADC_FIX = {'name': 'TESTFIXTURE', 'avdd_V': 3.3, 'rauschen_Vrms': 1e-6, 'verstaerkungsfehler_rel': 1e-4,
           'verstaerkungsdrift_ppm_K': 1, 'offset_V': 2e-6, 'offsetdrift_V_K': 5e-9, 'inl_ppm_fsr': 10,
           'idac_fehlanpassung_rel': 3e-3, 'idac_compliance_rand_V': 0.9, 'pga_rand_V': 0.2, 'pga_formel_geprueft': True,
           'vref_min_V': 0.75, 'vref_max_V': 3.3, 'verstaerkungen': [1, 2, 4, 8, 16, 32, 64, 128],
           'aussteuerung_reserve': 0.05}


def soll_demo():
    return json.load(open(os.path.join(DEMO, 'cad', 'soll.json'), encoding='utf-8'))


def mk_fix(**schaltung):
    mk = copy.deepcopy(soll_demo()['_projekt']['messkette'])
    mk['bauteile']['adc'] = dict(ADC_FIX)
    mk['sensor']['eigenerwaermung_mW_K'] = 1.0
    mk['schaltung'].update(schaltung)
    return mk


# ---------------------------------------------------------------------------------------------- Kennlinie

def test_pt100_kennlinie_iec60751():
    # Grundwerte IEC 60751 (Tabelle, 0,01 Ohm gerundet): -100 60,26 | -20 92,16 | 0 100,00 | 100 138,51
    for t, r in ((-100, 60.26), (-20, 92.16), (0, 100.0), (100, 138.51)):
        assert abs(rtd.r_von_t(t) - r) < 0.006, (t, rtd.r_von_t(t))
    for t in [x / 2 for x in range(-200, 301)]:
        assert abs(rtd.t_von_r(rtd.r_von_t(t)) - t) < 1e-9, t
    assert abs(rtd.klassentoleranz('A', 100) - 0.35) < 1e-12 and abs(rtd.klassentoleranz('A', -20) - 0.19) < 1e-12


# ---------------------------------------------------------------------------------------------- Messgleichung

def test_messgleichung_ideal_und_idac_tausch():
    mk = mk_fix()
    for t in (-20, 0, 40, 100):
        assert abs(rtd.anzeige(t, {}, mk) - t) < 1e-9, t
    # IDAC-Tausch: Fehlanpassung faellt exakt heraus; ohne Tausch Verstaerkungsfehler m/2
    assert abs(rtd.anzeige(100, {'m_idac': 3e-3}, mk) - 100) < 1e-9
    ohne = mk_fix(idac_tausch=False)
    erw = 1.5e-3 * rtd.r_von_t(100) / rtd.drdt(100)
    assert abs((rtd.anzeige(100, {'m_idac': 3e-3}, ohne) - 100) - erw) < 0.01 * erw, rtd.anzeige(100, {'m_idac': 3e-3}, ohne)


def test_sensitivitaeten_numerisch_gegen_analytisch():
    mk = mk_fix()
    b = rtd.budget_bei(mk, 100, lambda f: 'datenblatt')
    z = {x['name']: x for x in b['beitraege']}
    r, s = rtd.r_von_t(100), rtd.drdt(100)
    assert abs(z['dR_ref_rel']['c'] - (-r / s)) < 1e-3 * r / s, z['dR_ref_rel']          # R_mess = R / (1 + d)
    assert abs(z['dR_leitung']['c'] - 1 / s) < 1e-4, z['dR_leitung']                       # Leitungsdifferenz voll
    assert abs(z['dt_sensor']['c'] - 1.0) < 1e-6                                           # Element 1:1
    assert abs(z['m_idac']['c']) < 1e-6                                                    # Tausch
    # TK R_ref: 10 ppm/K * 17 K (T_kal 23, Elektronik 10 ... 40) als Rechteck
    assert abs(z['tk_ref_rel']['u_i'] - 10e-6 * 17 / math.sqrt(3)) < 1e-12, z['tk_ref_rel']
    assert abs(z['tk_ref_rel']['beitrag'] - 10e-6 * 17 / math.sqrt(3) * r / s) < 1e-6
    # Quantisierung getrennt vom Rauschen, Rauschen durch sqrt(mittelung)
    assert abs(z['v_rausch']['u_i'] - 1e-6 / math.sqrt(2)) < 1e-15
    assert abs(z['v_quant']['u_i'] - rtd.lsb_eingang(mk) / 2 / math.sqrt(3)) < 1e-18
    assert b['nichtlinear_max'] < 0.01 and 'unkorreliert' in b['korrelationen_hinweis'], b


def test_budget_dokumentation_vollstaendig():
    e = {x['id']: x for x in rtd.pruefe(mk_fix(), lambda f: 'datenblatt')}
    d = e['MK1']['daten']
    assert e['MK1']['stufe'] == 'ok' and d['U'] < 0.5 and abs(d['U'] - d['k'] * d['u_c']) < 1e-12, e['MK1']
    for z in d['beitraege']:
        for f in ('name', 'wert', 'verteilung', 'u_i', 'c', 'beitrag', 'anteil_proz', 'herkunft', 'einheit_eingang'):
            assert f in z, (f, z)
    assert abs(sum(z['anteil_proz'] for z in d['beitraege']) - 100) < 1e-6
    assert 'vereinfacht' in d['modell'] and 'Monte' in d['modell'] and len(d['je_temperatur']) == 13
    assert {'dt_sensor', 'dR_ref_rel', 'tk_ref_rel', 'm_idac', 'v_rausch', 'v_quant', 'e_gain', 'dR_leitung',
            'e_gaindrift', 'v_offsetdrift', 'dt_selbst'} <= {z['name'] for z in d['beitraege']}


def test_fehlende_adc_daten_kein_budget():
    mk = soll_demo()['_projekt']['messkette']
    e = {x['id']: x for x in rtd.pruefe(mk, lambda f: None)}
    assert e['MK1']['stufe'] == 'uebersprungen' and 'v_rausch' in e['MK1']['hinweis'], e['MK1']
    assert e['MK2']['stufe'] == 'uebersprungen' and e['MK4-PGA']['stufe'] == 'uebersprungen'


def test_vernachlaessigt_nur_mit_begruendung_und_warnung():
    mk = mk_fix()
    mk['vernachlaessigt'] = {'dt_selbst': 'TESTFIXTURE-Begruendung'}
    e = {x['id']: x for x in rtd.pruefe(mk, lambda f: 'datenblatt')}
    assert e['MK1']['stufe'] == 'warnung' and 'vernachlaessigt' in e['MK1']['hinweis'], e['MK1']
    assert 'dt_selbst' not in {z['name'] for z in e['MK1']['daten']['beitraege']}


def test_aufloesung_effektiv_nicht_nominal():
    e = {x['id']: x for x in rtd.pruefe(mk_fix(), lambda f: 'datenblatt')}
    h = e['MK2']['hinweis']
    eff = float(h.split('effektiv ')[1].split(' Bit')[0])
    assert eff < 24 and e['MK2']['wert'] < 0.05 and e['MK2']['stufe'] == 'ok', h
    zu_rauschig = mk_fix()
    zu_rauschig['bauteile']['adc']['rauschen_Vrms'] = 3e-6
    e = {x['id']: x for x in rtd.pruefe(zu_rauschig, lambda f: 'datenblatt')}
    assert e['MK2']['stufe'] == 'fehler', e['MK2']


def test_uebersteuerung_und_grenzen():
    e16 = {x['id']: x for x in rtd.pruefe(mk_fix(), lambda f: 'datenblatt')}
    assert e16['MK3']['stufe'] == 'ok' and abs(e16['MK3']['wert'] - 0.6715) < 1e-3, e16['MK3']
    assert 'groesste zulaessige Verstaerkung 16' in e16['MK3']['hinweis']
    for i in ('MK4-REF', 'MK4-IDAC', 'MK4-PGA', 'MK4-SELBST'):
        assert e16[i]['stufe'] == 'ok', e16[i]
    e32 = {x['id']: x for x in rtd.pruefe(mk_fix(gain=32), lambda f: 'datenblatt')}
    assert e32['MK3']['stufe'] == 'fehler' and e32['MK3']['wert'] > 1, e32['MK3']
    # IDAC-Compliance: zu grosser R_ref hebt die Pins ueber AVDD - Rand
    gross = {x['id']: x for x in rtd.pruefe(mk_fix(R_ref_ohm=2500), lambda f: 'datenblatt')}
    assert gross['MK4-IDAC']['stufe'] == 'fehler', gross['MK4-IDAC']
    # PGA-Formel nicht bestaetigt -> hoechstens warnung
    mk = mk_fix()
    mk['bauteile']['adc']['pga_formel_geprueft'] = False
    assert {x['id']: x for x in rtd.pruefe(mk, lambda f: 'datenblatt')}['MK4-PGA']['stufe'] == 'warnung'


# ---------------------------------------------------------------------------------------------- Demonstrator

def _kopie(name):
    d = os.path.join(TMP, name)
    shutil.copytree(DEMO, d)
    an.abnahme_erzeugen(d)
    return d


def test_demonstrator_ehrlicher_stand():
    d = _kopie('demo')
    v = an.pruefen(d)
    z = {x['id']: x for x in v['anforderungen']}
    assert v['messtechnische_freigabe']['status'] == 'nicht_freigegeben' and v['freigabe'] != 'fertig', v['freigabe']
    a = z['A-MESS-TEMP']
    assert a['status'] == 'unbewiesen', a['status']                       # fehlende Daten sind kein Grenzverstoss
    mess = {n['eigenschaft']: n for n in a['nachweise']}
    for e in ('genauigkeit', 'linearitaet', 'hysterese', 'wiederholbarkeit', 'messbereich'):
        assert mess[e]['status'] == 'unbewiesen' and 'demonstrationsdaten_nicht_rueckfuehrbar' in mess[e]['gruende']
        assert mess[e]['auswertung_status'] == 'bewiesen' and mess[e]['kennwert'] is not None, mess[e]
    assert mess['drift']['grund'] == 'ohne_referenzmessung'
    assert z['S-MESSKETTE']['status'] == 'unbewiesen' and z['K-FIRMWARE']['status'] == 'bewiesen'
    prot = open(os.path.join(d, 'pruef', 'messprotokoll.md'), encoding='utf-8').read()
    for s in ('gemessen', 'zulaessig', 'U_pruef', 'Akzeptanzgrenze', 'ILAC-G8', 'Fehlentscheidung',
              'demonstrationsdaten_nicht_rueckfuehrbar', 'nicht_freigegeben'):
        assert s in prot, s


def _echt_machen(d, kalibrierschein='TESTFIXTURE-KEIN-NACHWEIS', gueltig_bis='2027-12-31'):
    """Fixture: Demonstrator mit TESTFIXTURE-ADC-Daten und als rueckfuehrbar markierten Reihen (nur im Test)."""
    p = os.path.join(d, 'cad', 'soll.json')
    s = json.load(open(p, encoding='utf-8'))
    mk = s['_projekt']['messkette']
    mk['bauteile']['adc'] = dict(ADC_FIX)
    mk['sensor']['eigenerwaermung_mW_K'] = 1.0
    h = s['_projekt']['_herkunft']
    for k in list(h):
        if k.startswith('messkette'):
            h[k] = FIX
    json.dump(s, open(p, 'w', encoding='utf-8'), ensure_ascii=False)
    pa = os.path.join(d, 'anforderungen.json')
    a = json.load(open(pa, encoding='utf-8'))
    for x in a['anforderungen']:
        if x['id'] == 'A-MESS-TEMP':
            x['messtechnik']['drift'] = {'max_abs': 0.1, 'einheit': '°C/Jahr'}
    json.dump(a, open(pa, 'w', encoding='utf-8'), ensure_ascii=False)
    pm = os.path.join(d, 'messung.json')
    m = json.load(open(pm, encoding='utf-8'))
    drift = copy.deepcopy(m['reihen'][1])
    drift.update(id='R-DRI-1', eigenschaft='drift',
                 punkte=[{'ref': 25, 'ist': 25.08 + 1e-6 * t, 't_h': t} for t in (0, 360, 720)])
    m['reihen'].append(drift)
    for r in m['reihen']:
        r['datenstatus'] = 'rueckfuehrbar_gemessen'
        r.update(sensor_id='TESTFIXTURE-DUT', seriennummer='TESTFIXTURE-0001')
        r['referenz'] = {'mittel': 'TESTFIXTURE', 'seriennummer': 'TESTFIXTURE-SN', 'U': 0.03, 'k': 2,
                         'einheit': '°C', 'kalibrierschein': kalibrierschein, 'rueckfuehrung': 'TESTFIXTURE',
                         'gueltig_bis': gueltig_bis}
    json.dump(m, open(pm, 'w', encoding='utf-8'), ensure_ascii=False)


def test_negativ_ohne_kalibrierschein_keine_freigabe():
    """Elektronik/Messkette/Firmware bestanden, Reihen ohne Kalibrierschein -> keine messtechnische Freigabe."""
    d = _kopie('neg')
    _echt_machen(d, kalibrierschein=None)
    k = pruefungen.alle(d)['module']
    assert all(e['stufe'] == 'ok' for e in k['messkette']), [(e['id'], e['stufe'], e['hinweis'][:80]) for e in k['messkette']]
    v = an.pruefen(d, k)
    z = {x['id']: x for x in v['anforderungen']}
    assert z['S-MESSKETTE']['status'] == 'bewiesen' and z['S-SCHALTUNG']['status'] == 'bewiesen', \
        (z['S-MESSKETTE']['nachweise'], z['S-SCHALTUNG']['nachweise'])
    mf = v['messtechnische_freigabe']
    assert mf['status'] == 'nicht_freigegeben' and 'nachweisdaten_unvollstaendig' in ' '.join(mf['gruende']), mf


def test_abgelaufene_referenz_keine_freigabe():
    d = _kopie('alt')
    _echt_machen(d, gueltig_bis='2026-01-01')
    v = an.pruefen(d)
    assert v['messtechnische_freigabe']['status'] == 'nicht_freigegeben'
    assert 'referenz_abgelaufen' in ' '.join(v['messtechnische_freigabe']['gruende'])


def test_freigabe_nur_durch_mensch_und_an_stand_gebunden():
    d = _kopie('voll')
    _echt_machen(d)
    v = an.pruefen(d)
    mf = v['messtechnische_freigabe']
    assert mf['status'] == 'bereit_zur_menschlichen_freigabe', mf          # Software gibt nie selbst frei
    assert an.messtechnik_freigeben(d, 'TESTFIXTURE Pruefer')['status'] == 'freigegeben'
    pm = os.path.join(d, 'messung.json')
    m = json.load(open(pm, encoding='utf-8'))
    m['reihen'][0]['punkte'][0]['ist'] += 0.001
    json.dump(m, open(pm, 'w', encoding='utf-8'), ensure_ascii=False)
    assert an.pruefen(d)['messtechnische_freigabe']['status'] == 'bereit_zur_menschlichen_freigabe'   # Stand geaendert
    d2 = _kopie('verweigert')
    try:
        an.messtechnik_freigeben(d2, 'TESTFIXTURE Pruefer')
        raise AssertionError('Freigabe trotz fehlender Nachweise')
    except RuntimeError:
        pass


def test_ilac_g8_regel_im_ergebnis():
    mt = json.load(open(os.path.join(DEMO, 'anforderungen.json'), encoding='utf-8'))['anforderungen'][1]['messtechnik']
    r = {'id': 'R', 'eigenschaft': 'genauigkeit', 'datenstatus': 'rueckfuehrbar_gemessen', 'sensor_id': 'TESTFIXTURE',
         'seriennummer': 'TESTFIXTURE', 'datum': '2026-11-19', 'verfahren': 'TESTFIXTURE',
         'referenz': {'mittel': 'T', 'seriennummer': 'T', 'kalibrierschein': 'T', 'rueckfuehrung': 'T', 'U': 0.1,
                      'k': 2, 'einheit': '°C', 'gueltig_bis': '2027-01-01'},
         'bedingungen': {'T_umgebung_C': 23, 'U_versorgung_V': 3.3, 'einschwingzeit_min_s': 600, 'messrate_Hz': 5}}
    for abw, st in ((0.30, 'bewiesen'), (0.45, 'vorbehalt'), (0.55, 'verletzt')):
        r['punkte'] = [{'ref': t, 'ist': t + abw} for t in (-20, 40, 100)]
        b = MK.bewerte_reihe(r, 'genauigkeit', mt)
        assert b['status'] == st and abs(b['kennwert'] - abw) < 1e-9 and abs(b['akzeptanzgrenze'] - 0.4) < 1e-9, b
        assert b['grenze'] == 0.5 and abs(b['U_pruef'] - 0.1) < 1e-9 and 'ILAC-G8' in b['entscheidungsregel']
        assert b['fehlentscheidung'], b
    r['bedingungen']['einschwingzeit_min_s'] = 120
    assert 'bedingungen_abweichend' in MK.bewerte_reihe(r, 'genauigkeit', mt)['gruende']


# ---------------------------------------------------------------------------------------------- Firmware

def test_firmware_rechnung_auf_dem_pc():
    """rtd_rechnung.h mit g++ uebersetzen und gegen das Python-Modell pruefen (fehlt g++: Test NICHT bestanden)."""
    if not shutil.which('g++'):
        raise RuntimeError('g++ fehlt - Firmware-Rechnung nicht geprueft')
    fw = os.path.join(DEMO, 'firmware', 'mb2_temp_001')
    src = os.path.join(TMP, 't.cpp')
    exe = os.path.join(TMP, 't')
    open(src, 'w').write('#include <cstdio>\n#include <cstdlib>\n#include "rtd_rechnung.h"\n#include "config.h"\n'
                         'int main(int c, char** v){ for(int i=1;i+1<c;i+=2){ double r,t; '
                         'int f=rtd_rechnen((int32_t)atol(v[i]),(int32_t)atol(v[i+1]),IDAC_TAUSCH,RREF_OHM,PGA_GAIN,'
                         'RTD_R0_OHM,&r,&t); printf("%d %.12f %.12f\\n",f,r,t);} '
                         'printf("%d\\n",(int)rtd_vorzeichen24(0xFFFFFFu)); return 0; }\n')
    subprocess.run(['g++', '-O2', '-Wall', '-Werror', '-I', fw, src, '-o', exe], check=True)
    mk = soll_demo()['_projekt']['messkette']
    g, rref = mk['schaltung']['gain'], mk['schaltung']['R_ref_ohm']
    args, erw = [], []
    for t in (-20, 0, 23.5, 100):
        code = round(g * rtd.r_von_t(t) / (2 * rref) * 2 ** 23)
        args += [str(code), str(code)]
        erw.append(rtd.t_von_r(code / 2 ** 23 * 2 * rref / g))
    args += [str(0x7FFFFF), str(0x7FFFFF), '1000', '1000']        # uebersteuert / unplausibel (R viel zu klein)
    zeilen = subprocess.run([exe] + args, capture_output=True, text=True, check=True).stdout.split('\n')
    for z, t in zip(zeilen, erw):
        f, _, tc = z.split()
        assert int(f) == 0 and abs(float(tc) - t) < 1e-9, (z, t)
    assert int(zeilen[4].split()[0]) & 1 and int(zeilen[5].split()[0]) & 2, zeilen
    assert zeilen[6].strip() == '-1'


if __name__ == '__main__':
    try:
        for n, f in list(globals().items()):
            if n.startswith('test_') and callable(f):
                f()
                print('ok', n)
        print('alle ok')
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
