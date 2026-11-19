"""Feldfaelle als Regressionstests (V-Modell, rechte Seite ganz oben): jede Messung, bei der mb2 zu optimistisch war,
liegt als JSON unter tests/feldfaelle/ (geschrieben von feld_abgleich). Das aktuelle Modell darf mit denselben
Eingaben nicht optimistischer sein als gemessen + Toleranz.  Aufruf: uv run python tests/test_feldfaelle.py"""
import glob
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mb2 import pruefungen   # noqa: E402

HIER = os.path.dirname(os.path.abspath(__file__))


def _vorhersage(fall):
    d = tempfile.mkdtemp(prefix='mb2_feldfall_')
    try:
        for sub in ('cad', 'out', 'fem', 'electronics', 'print'):
            os.makedirs(os.path.join(d, sub))
        json.dump({'_projekt': fall['soll_projekt']}, open(os.path.join(d, 'cad', 'soll.json'), 'w', encoding='utf-8'))
        r = pruefungen.alle(d)
        e = next(x for l in r['module'].values() for x in l if x['id'] == fall['pruefung'] and x.get('daten'))
        return (e['daten'] or {}).get(fall['schluessel']) if fall.get('schluessel') else e['wert']
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_feldfaelle():
    faelle = sorted(glob.glob(os.path.join(HIER, 'feldfaelle', '*.json')))
    for p in faelle:
        f = json.load(open(p, encoding='utf-8'))
        v = _vorhersage(f)
        grenze = f['gemessen_umgerechnet'] + f['toleranz']
        assert v is not None and v <= grenze, (os.path.basename(p), f'Vorhersage {v} > gemessen {f["gemessen_umgerechnet"]} '
                                                                    f'+ Toleranz {f["toleranz"]}')
        print(f'   {os.path.basename(p)}: Vorhersage {v:.1f} <= {grenze:.1f}')
    print(f'   {len(faelle)} Feldfaelle')


if __name__ == '__main__':
    test_feldfaelle()
    print('alle ok')
