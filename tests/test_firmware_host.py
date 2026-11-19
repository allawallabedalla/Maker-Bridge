"""Firmware-Hosttest FW2/FW3 (19.11.2026): Rechenlogik am PC, Fehlerinjektion in Software, veraltete Ergebnisse.
Beispiel-Logik (TESTFIXTURE): Volumen integrieren, Verstopfung erkennen (Durchfluss faellt bei laufender Pumpe).
Aufruf aus maker-bridge-2/:  uv run python tests/test_firmware_host.py"""
import json
import os
import sys
import tempfile

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HIER))
sys.path.insert(0, HIER)
from _nachweis import NichtAusgefuehrt  # noqa: E402

from mb2 import firmware_test as ft, werkzeuge  # noqa: E402
from mb2.pruefungen import firmware  # noqa: E402

LOGIK = r'''
#include "logik.h"
double volumen_ml(const double *q_ml_min, int n, double dt_s) {
    double v = 0; for (int i = 0; i < n; i++) v += q_ml_min[i] * dt_s / 60.0; return v;
}
int verstopft(double q_ml_min, int pumpe_an, double q_min) { return pumpe_an && q_ml_min < q_min; }
'''
KOPF = 'double volumen_ml(const double *q, int n, double dt_s);\nint verstopft(double q, int pumpe_an, double q_min);\n'
TEST = r'''
#include <stdio.h>
#include "logik.h"
int main(void) {
    double q[60]; for (int i = 0; i < 60; i++) q[i] = 10.0;
    printf("MB2 {\"fall\": \"Volumen 60 s bei 10 ml/min\", \"art\": \"wert\", \"ist\": %.6f, \"soll\": 10.0, \"tol\": 1e-9}\n",
           volumen_ml(q, 60, 1.0));
    printf("MB2 {\"fall\": \"Verstopfung\", \"art\": \"fehlerinjektion\", \"fehler\": \"Verstopfung\", \"ist\": %d, \"soll\": 1}\n",
           verstopft(0.1, 1, 1.0));
    int alarme = 0; for (int i = 0; i < 3600; i++) alarme += verstopft(10.0, 1, 1.0);
    printf("MB2 {\"fall\": \"Normalbetrieb 1 h\", \"art\": \"fehlalarm\", \"ist\": %d, \"soll\": 0}\n", alarme);
    return 0;
}
'''
HT = {'quellen': ['firmware/logik.c'], 'test': 'firmware/test_host.c', 'sprache': 'c'}


def _projekt(logik=LOGIK, mit_leck=False):
    d = tempfile.mkdtemp(prefix='mb2_fwhost_')
    os.makedirs(os.path.join(d, 'firmware'))
    os.makedirs(os.path.join(d, 'cad'))
    for n, t in (('logik.c', logik), ('logik.h', KOPF), ('test_host.c', TEST)):
        open(os.path.join(d, 'firmware', n), 'w').write(t)
    json.dump({'_projekt': {'firmware': {'pfad': 'firmware', 'konstanten': {}, 'hosttest': HT}}},
              open(os.path.join(d, 'cad', 'soll.json'), 'w'))
    erk = [{'fehler': 'Verstopfung'}] + ([{'fehler': 'Leck'}] if mit_leck else [])
    json.dump({'anforderungen': [{'id': 'A-DIAG', 'ebene': 'system', 'erkennung': erk, 'nachweise': []}]},
              open(os.path.join(d, 'anforderungen.json'), 'w'))
    return d


def _st(d):
    return {e['id']: e for e in firmware.pruefe(d) if e['id'] in ('FW2', 'FW3')}


def test_hosttest_bestanden_veraltet_und_fehlerhaft():
    if not werkzeuge.c_compiler():
        raise NichtAusgefuehrt('werkzeug_fehlt', 'C-Compiler (gcc/clang) fehlt')
    d = _projekt()
    r = _st(d)
    assert r['FW2']['stufe'] == 'uebersprungen' and 'nie gelaufen' in r['FW2']['hinweis'], r
    e = ft.laufen(d, HT)
    assert e['ok'] and len(e['faelle']) == 3, e
    r = _st(d)
    assert r['FW2']['stufe'] == 'ok' and r['FW3']['stufe'] == 'ok', r
    # Quelle geaendert -> Ergebnis veraltet
    open(os.path.join(d, 'firmware', 'logik.c'), 'a').write('\n/* geaendert */\n')
    assert 'veraltet' in _st(d)['FW2']['hinweis']
    # Rechenfehler (Minuten statt Sekunden) -> FW2 fehler
    d2 = _projekt(LOGIK.replace('/ 60.0', '/ 1.0'))
    assert not ft.laufen(d2, HT)['ok']
    assert _st(d2)['FW2']['stufe'] == 'fehler'
    # Anforderung verlangt auch Leck-Erkennung, kein Fall dafuer -> FW3 fehler
    d3 = _projekt(mit_leck=True)
    ft.laufen(d3, HT)
    r = _st(d3)
    assert r['FW2']['stufe'] == 'ok' and r['FW3']['stufe'] == 'fehler' and 'Leck' in r['FW3']['hinweis'], r
    # Uebersetzungsfehler -> nicht bestanden, mit Meldung
    d4 = _projekt('kaputt(')
    e = ft.laufen(d4, HT)
    assert not e['ok'] and 'Uebersetzen' in e['fehler'], e


def test_ohne_hosttest_ausloeser():
    """Projekt mit Firmware, aber ohne Hosttest: FW2 uebersprungen -> im Gesamtlauf Ausloeser-Fehler."""
    from mb2 import pruefungen
    d = _projekt()
    s = json.load(open(os.path.join(d, 'cad', 'soll.json')))
    del s['_projekt']['firmware']['hosttest']
    json.dump(s, open(os.path.join(d, 'cad', 'soll.json'), 'w'))
    fw2 = [e for l in pruefungen.alle(d)['module'].values() for e in l if e['id'] == 'FW2']
    assert fw2 and fw2[0]['stufe'] == 'fehler' and fw2[0].get('ausloeser') == 'firmware', fw2


if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_') and callable(f):
            f()
            print('ok', n)
    print('alle ok')
