"""Ergebnis-Cache fuer teure Befehle (cad_build, fem_*): gleiche Eingaben -> gespeichertes Ergebnis statt neu rechnen.

Schluessel = SHA-256 ueber alle Eingabedateien UND den Quelltext von mb2/*.py. Damit rechnet jede Aenderung an
Skript, Sollmassen, STEP, Lastfall oder an den Pruefungen selbst neu. Lieber zu oft neu als ein veraltetes Ergebnis.
Treffer nur, wenn alle Ausgabedateien des gespeicherten Ergebnisses noch existieren."""
import glob
import hashlib
import json
import os

MB2 = os.path.dirname(os.path.abspath(__file__))


def schluessel(dateien, extra=None):
    h = hashlib.sha256()
    for p in sorted(glob.glob(os.path.join(MB2, '*.py'))):
        h.update(os.path.basename(p).encode())
        h.update(open(p, 'rb').read())
    for p in sorted(set(os.path.normcase(os.path.abspath(d)) for d in dateien)):
        h.update(p.encode())
        h.update(open(p, 'rb').read() if os.path.isfile(p) else b'<fehlt>')
    h.update(json.dumps(extra, sort_keys=True, default=str).encode())
    return h.hexdigest()


def _ausgaben(obj):
    """Alle Dateipfade im Ergebnis (Strings mit Endung .png/.step/.3mf/.json)."""
    if isinstance(obj, dict):
        return [p for v in obj.values() for p in _ausgaben(v)]
    if isinstance(obj, list):
        return [p for v in obj for p in _ausgaben(v)]
    if isinstance(obj, str) and obj.lower().endswith(('.png', '.step', '.3mf', '.json')) and os.path.isabs(obj):
        return [obj]
    return []


def treffer(erg_pfad, key):
    if not os.path.isfile(erg_pfad):
        return None
    try:
        erg = json.load(open(erg_pfad, encoding='utf-8'))
    except ValueError:
        return None
    if erg.get('_cache') != key or not all(os.path.isfile(p) for p in _ausgaben(erg)):
        return None
    erg['aus_cache'] = True
    return erg


def merken(erg_pfad, erg, key):
    erg['_cache'] = key
    json.dump(erg, open(erg_pfad, 'w', encoding='utf-8'), indent=1, ensure_ascii=False, default=str)
    return erg


def cad_eingaben(pdir):
    """Alles, was ein Teil-Skript lesen kann: cad/ komplett + Platinendaten."""
    d = [p for p in glob.glob(os.path.join(pdir, 'cad', '**', '*'), recursive=True)
         if os.path.isfile(p) and '__pycache__' not in p]
    return d + [os.path.join(pdir, 'electronics', 'board.step'), os.path.join(pdir, 'electronics', 'board_info.json')]


def fem_eingaben(pdir, fall):
    """Lastfall-JSON + jede darin genannte STEP-Datei (relativ zum Projekt oder absolut)."""
    spec_pfad = os.path.join(pdir, 'fem', fall + '.json')
    spec = json.load(open(spec_pfad, encoding='utf-8'))
    steps = []

    def such(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if 'step' in k and isinstance(v, str):
                    steps.append(v if os.path.isabs(v) else os.path.join(pdir, v))
                else:
                    such(v)
        elif isinstance(o, list):
            for v in o:
                such(v)
    such(spec)
    return [spec_pfad] + steps
