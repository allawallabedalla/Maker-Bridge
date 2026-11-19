"""Widerspruchspruefung X1-X9 (19.11.2026). Aufruf aus maker-bridge-2/:  uv run python tests/test_widerspruch.py"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mb2.pruefungen import widerspruch as W   # noqa: E402

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = os.path.join(BASIS, 'demonstratoren', 'MB2-TEMP-001')
TMP = tempfile.mkdtemp(prefix='mb2_widerspruch_')


def kopie(name, soll_aendern=None, anf_aendern=None, kosten=None, messung=None):
    d = os.path.join(TMP, name)
    shutil.copytree(DEMO, d)
    p = os.path.join(d, 'cad', 'soll.json')
    s = json.load(open(p, encoding='utf-8'))
    if soll_aendern:
        soll_aendern(s['_projekt'])
    json.dump(s, open(p, 'w', encoding='utf-8'), ensure_ascii=False)
    pa = os.path.join(d, 'anforderungen.json')
    a = json.load(open(pa, encoding='utf-8'))
    if anf_aendern:
        anf_aendern(next(x for x in a['anforderungen'] if x['id'] == 'A-MESS-TEMP'))
    json.dump(a, open(pa, 'w', encoding='utf-8'), ensure_ascii=False)
    if kosten is not None:
        json.dump(kosten, open(os.path.join(d, 'kosten.json'), 'w', encoding='utf-8'))
    if messung is not None:
        json.dump(messung, open(os.path.join(d, 'messung.json'), 'w', encoding='utf-8'))
    return {e['id']: e for e in W.pruefe(d, heute='2026-11-19')}


def test_demonstrator_findet_budget_gleich_toleranz():
    e = kopie('demo')
    assert e['X1']['stufe'] == 'ok' and e['X1']['wert'] > 4, e['X1']          # Demo-Referenz U 0,03 gegen 0,5
    assert e['X2']['stufe'] == 'ok', e['X2']
    assert e['X3']['stufe'] == 'warnung', e['X3']                             # ziel_U 0,5 = Toleranz 0,5
    assert e['X9']['stufe'] == 'info', e['X9']


def test_x1_referenz_zu_ungenau():
    m = json.load(open(os.path.join(DEMO, 'messung.json'), encoding='utf-8'))
    for r in m['reihen']:
        r['referenz']['U'] = 0.3
    assert kopie('x1w', messung=m)['X1']['stufe'] == 'warnung'               # 0,5 / 0,3 = 1,7:1
    for r in m['reihen']:
        r['referenz']['U'] = 0.8
    assert kopie('x1f', messung=m)['X1']['stufe'] == 'fehler'


def test_x2_messbereich():
    def bereich(lo, hi):
        return lambda a: a['messtechnik'].update(messbereich={'min': lo, 'max': hi, 'einheit': '°C'})
    assert kopie('x2f', anf_aendern=bereich(-20, 100))['X2']['stufe'] == 'fehler'   # -30 nicht abgedeckt
    assert kopie('x2w', anf_aendern=bereich(-40, 150))['X2']['stufe'] == 'warnung'  # viel zu breit


def test_x3_budget_groesser_toleranz():
    assert kopie('x3', soll_aendern=lambda pj: pj['messkette'].update(ziel_U=0.6))['X3']['stufe'] == 'fehler'
    assert kopie('x3ok', soll_aendern=lambda pj: pj['messkette'].update(ziel_U=0.25))['X3']['stufe'] == 'ok'


def test_x4_bis_x6_ziele():
    def ziele(pj):
        pj['ziele'] = {'stueckzahl': 20, 'aufwand_h_stueck': 3, 'termin': '2026-12-17', 'zeit_h_pro_woche': 10,
                       'fehlerfolge': 'hoch', 'prioritaet': ['kosten', 'qualitaet', 'zeit']}
    e = kopie('ziele', soll_aendern=ziele)
    assert e['X4']['stufe'] == 'warnung' and 'aufwand_h_stueck' in e['X4']['hinweis'], e['X4']
    assert e['X5']['stufe'] == 'fehler' and e['X5']['wert'] == 60 and e['X5']['grenze'] == 40, e['X5']   # 4 Wochen
    assert e['X6']['stufe'] == 'warnung', e['X6']


def test_x7_bus_und_x8_kalibrierung():
    e = kopie('bus', soll_aendern=lambda pj: pj.update(schnittstelle={'bus': 'i2c', 'leitung_m': 5}),
              kosten={'arbeitsschritte': [{'name': 'Bau', 'h': 1, 'quelle': 'x'}]})
    assert e['X7']['stufe'] == 'warnung' and e['X8']['stufe'] == 'warnung', (e['X7'], e['X8'])
    e = kopie('bus2', soll_aendern=lambda pj: pj.update(schnittstelle={'bus': 'spi', 'leitung_m': 0.1}),
              kosten={'arbeitsschritte': [{'name': 'Kalibrierung im Bad', 'h': 2, 'quelle': 'x'}]})
    assert e['X7']['stufe'] == 'ok' and e['X8']['stufe'] == 'ok'


def test_x9_seriennachweis_mit_einem_geraet():
    e = kopie('x9', anf_aendern=lambda a: a.update(text=a['text'] + ' Reproduzierbarkeit zwischen Geraeten.'))
    assert e['X9']['stufe'] == 'fehler', e['X9']


if __name__ == '__main__':
    try:
        for n, f in list(globals().items()):
            if n.startswith('test_') and callable(f):
                f()
                print('ok', n)
        print('alle ok')
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
