"""Alle Tests JE FUNKTION ausfuehren und jedes Ergebnis KLASSIFIZIEREN (seit 19.11.2026).

Grundsatz wie im V-Modell: Ein nicht ausgefuehrter Test ist NICHT bestanden. Jede Testfunktion bekommt eine Klasse:

    bestanden                Funktion lief ohne Ausnahme durch
    werkzeug_fehlt           externer Loeser/Werkzeug fehlt (CalculiX, Elmer, PrusaSlicer, KiCad, g++ ...)
    beispielprojekt_fehlt    braucht projects/<name>, das nicht im Repository liegt (tests/_nachweis.beispielprojekt)
    lauf_nicht_angefordert   langer Lauf nur auf Anforderung (MB2_LANG=1)
    fehlgeschlagen           Assertion oder Ausnahme ohne erkannte Ursache -> moeglicher Softwarefehler, untersuchen
    zeitueberschreitung      Datei laenger als --timeout

Jede Datei laeuft in einem eigenen Prozess; die Funktionen darin in Definitionsreihenfolge (manche bauen aufeinander auf).
Exit-Code 0 nur, wenn ALLE Funktionen bestanden sind.

Aufruf aus maker-bridge-2/:  uv run python tests/alle.py [--timeout 900] [--json pruef/tests.json] [datei ...]
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
RANG = ('bestanden', 'lauf_nicht_angefordert', 'beispielprojekt_fehlt', 'werkzeug_fehlt', 'zeitueberschreitung',
        'fehlgeschlagen')
MUSTER = (
    ('werkzeug_fehlt', r'(CalculiX|Elmer|PrusaSlicer|KiCad|kicad-cli|Blender|ccx|g\+\+)[^\n]{0,40}fehlt'),
    # nur die bekannten, nicht oeffentlichen Beispielprojekte - ein Tippfehler im Namen ist ein echter Fehler
    ('beispielprojekt_fehlt', r"Projekt '(testdose|schnapphaken|stifthalter-fem|frag-mich-alles-gehaeuse|"
                              r"bodenklima-sondenkopf|bodenklima-system)' gibt es nicht"),
)
TREIBER = r'''
import contextlib, importlib.util, io, json, os, shutil, sys, time, traceback
datei, wurzel = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.dirname(datei)); sys.path.insert(0, wurzel); os.chdir(wurzel)
def aus(d): print('@@' + json.dumps(d), flush=True)
spec = importlib.util.spec_from_file_location('testmodul', datei)
mod = importlib.util.module_from_spec(spec)
try:
    with contextlib.redirect_stdout(io.StringIO()):
        spec.loader.exec_module(mod)
except BaseException as e:
    aus({'funktion': '<import>', 'ausnahme': f'{type(e).__name__}: {e}', 'klasse': getattr(e, 'klasse', None)})
    sys.exit(0)
funktionen = [(n, f) for n, f in list(vars(mod).items())
              if n.startswith('test_') and callable(f) and getattr(f, '__module__', '') == 'testmodul']
if not funktionen:   # Tests auf Modulebene (laufen beim Import) - der Import ist der Test
    aus({'funktion': '<modulebene>', 'ausnahme': None, 'klasse': 'bestanden'})
for n, f in funktionen:
    t0 = time.time(); buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            f()
        aus({'funktion': n, 'ausnahme': None, 'klasse': 'bestanden', 'dauer_s': round(time.time() - t0, 2)})
    except BaseException as e:
        aus({'funktion': n, 'ausnahme': f'{type(e).__name__}: {e}'[:400], 'klasse': getattr(e, 'klasse', None),
             'dauer_s': round(time.time() - t0, 2)})
tmp = getattr(mod, 'TMP', None)
if isinstance(tmp, str) and os.path.basename(tmp).startswith(('mb2_', 'tmp')):
    shutil.rmtree(tmp, ignore_errors=True)
'''


def klassifiziere(ergebnis):
    if ergebnis.get('klasse'):
        return ergebnis['klasse']
    for k, m in MUSTER:
        if re.search(m, ergebnis.get('ausnahme') or ''):
            return k
    return 'fehlgeschlagen'


def lauf(datei, timeout):
    try:
        p = subprocess.run([sys.executable, '-c', TREIBER, datei, os.path.dirname(HIER)], capture_output=True,
                           text=True, encoding='utf-8', errors='replace', timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return [{'funktion': '<datei>', 'klasse': 'zeitueberschreitung', 'ausnahme': f'> {timeout} s'}]
    erg = [json.loads(z[2:]) for z in p.stdout.splitlines() if z.startswith('@@')]
    if not erg:
        erg = [{'funktion': '<datei>', 'ausnahme': (p.stderr or p.stdout)[-400:], 'klasse': None}]
    for e in erg:
        e['klasse'] = klassifiziere(e)
    return erg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--timeout', type=int, default=900)
    ap.add_argument('--json')
    ap.add_argument('dateien', nargs='*')
    a = ap.parse_args()
    dateien = [os.path.abspath(d) for d in a.dateien] or sorted(glob.glob(os.path.join(HIER, 'test_*.py')))
    alle, je_datei = [], []
    for f in dateien:
        erg = lauf(f, a.timeout)
        z = {}
        for e in erg:
            z[e['klasse']] = z.get(e['klasse'], 0) + 1
            alle.append({'datei': os.path.basename(f), **e})
        schlimmste = max((e['klasse'] for e in erg), key=RANG.index)
        je_datei.append({'datei': os.path.basename(f), 'klasse': schlimmste, 'zaehlung': z})
        print(f'{schlimmste:22s} {os.path.basename(f):32s} ' + ', '.join(f'{k} {v}' for k, v in sorted(z.items())))
        for e in erg:
            if e['klasse'] != 'bestanden':
                print(f'    {e["klasse"]:22s} {e["funktion"]}: {(e.get("ausnahme") or "")[:110]}')
    gesamt = {}
    for e in alle:
        gesamt[e['klasse']] = gesamt.get(e['klasse'], 0) + 1
    print('\nFunktionen: ' + ', '.join(f'{k}: {v}' for k, v in sorted(gesamt.items())))
    if a.json:
        os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True)
        json.dump({'dateien': je_datei, 'funktionen': alle, 'zaehlung': gesamt}, open(a.json, 'w', encoding='utf-8'),
                  indent=1, ensure_ascii=False)
    sys.exit(0 if set(gesamt) <= {'bestanden'} else 1)


if __name__ == '__main__':
    main()
