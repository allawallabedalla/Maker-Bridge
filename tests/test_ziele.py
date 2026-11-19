"""Projektziele (KPIs) beim Projektstart und Pruefungen K1-K4 (19.11.2026).
Aufruf aus maker-bridge-2/:  uv run python tests/test_ziele.py"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mb2 import anforderungen as an, befehle, pruefungen   # noqa: E402
from mb2.pruefungen import kpi                             # noqa: E402

TMP = tempfile.mkdtemp(prefix='mb2_ziele_')
ZIELE = {'zielkosten_eur_stueck': 40, 'stueckzahl': 5, 'termin': '2027-03-31', 'aufwand_h_stueck': 3,
         'fehlerfolge': 'mittel', 'prioritaet': ['qualitaet', 'kosten', 'zeit'], 'pruefmittel': ['TESTFIXTURE']}


def neu(name, ziele):
    befehle.PROJEKTE = TMP
    r = befehle.project_new(name, 'Testgeraet', '', {'T_max_C': 30}, ziele)
    return os.path.join(TMP, name), r


def nach_id(d):
    return {e['id']: e for e in kpi.pruefe(d, heute='2026-11-19')}


def test_project_new_fragt_ziele_ab():
    d, r = neu('z_leer', None)
    assert set(r['ziele_offen']) == set(befehle.ZIEL_FELDER), r
    assert '## Ziele (KPIs)' in open(os.path.join(d, 'projekt.md'), encoding='utf-8').read()
    e = nach_id(d)
    assert all(e[i]['stufe'] == 'uebersprungen' for i in ('K1', 'K2', 'K3', 'K4')), e


def test_ziele_mit_kosten_und_aufwand():
    d, r = neu('z_voll', ZIELE)
    assert not r['ziele_offen'], r
    ids = {a['id'] for a in json.load(open(os.path.join(d, 'anforderungen.json'), encoding='utf-8'))['anforderungen']}
    assert {'S-KOSTEN', 'S-AUFWAND'} <= ids, ids
    json.dump({'posten': [{'name': 'A', 'menge': 2, 'preis_eur': 10, 'quelle': 'TESTFIXTURE'},
                          {'name': 'B', 'menge': 1, 'preis_eur': 15, 'quelle': 'TESTFIXTURE'}],
               'arbeitsschritte': [{'name': 'Bau', 'h': 1, 'quelle': 'TESTFIXTURE'},
                                   {'name': 'Abgleich', 'h': 2.5, 'quelle': 'TESTFIXTURE'}]},
              open(os.path.join(d, 'kosten.json'), 'w', encoding='utf-8'))
    e = nach_id(d)
    assert e['K1']['stufe'] == 'ok' and e['K1']['wert'] == 35, e['K1']
    assert e['K2']['stufe'] == 'fehler' and e['K2']['wert'] == 3.5, e['K2']          # 3,5 h > 3 h
    assert e['K3']['stufe'] == 'ok' and e['K4']['stufe'] == 'ok'


def test_luecken_zaehlen_nicht_als_null():
    d, _ = neu('z_luecke', ZIELE)
    json.dump({'posten': [{'name': 'A', 'menge': 1, 'preis_eur': 10, 'quelle': 'x'}, {'name': 'B', 'menge': 1}],
               'arbeitsschritte': [{'name': 'Bau', 'h': 1}]},
              open(os.path.join(d, 'kosten.json'), 'w', encoding='utf-8'))
    e = nach_id(d)
    assert e['K1']['stufe'] == 'warnung' and 'B: preis_eur fehlt' in e['K1']['hinweis'], e['K1']
    assert e['K2']['stufe'] == 'warnung' and 'Quelle fehlt' in e['K2']['hinweis'], e['K2']


def test_unbekannt_ist_risiko_und_prioritaet_eindeutig():
    d, _ = neu('z_unb', {**ZIELE, 'zielkosten_eur_stueck': 'unbekannt', 'termin': '2026-01-01',
                          'prioritaet': ['qualitaet', 'qualitaet', 'kosten']})
    e = nach_id(d)
    assert e['K1']['stufe'] == 'warnung' and 'unbekannt' in e['K1']['hinweis'], e['K1']
    assert e['K3']['stufe'] == 'fehler' and e['K4']['stufe'] == 'fehler', (e['K3'], e['K4'])
    ids = {a['id'] for a in json.load(open(os.path.join(d, 'anforderungen.json'), encoding='utf-8'))['anforderungen']}
    assert 'S-KOSTEN' not in ids                                        # kein Ziel "<= unbekannt EUR"


def test_ausloeser_ziele():
    """Ziele gesetzt, aber kosten.json fehlt -> K1/K2 uebersprungen -> Ausloeser macht fehler daraus."""
    d, _ = neu('z_ausl', ZIELE)
    k = {e['id']: e for e in pruefungen.alle(d)['module']['kpi']}
    assert k['K1']['stufe'] == 'fehler' and k['K1'].get('ausloeser') == 'ziele', k['K1']
    z = {x['id']: x for x in an.pruefen(d)['anforderungen']}
    assert z['S-KOSTEN']['status'] == 'unbewiesen', z['S-KOSTEN']   # fehlende Eingabe, kein Grenzverstoss


if __name__ == '__main__':
    try:
        for n, f in list(globals().items()):
            if n.startswith('test_') and callable(f):
                f()
                print('ok', n)
        print('alle ok')
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
