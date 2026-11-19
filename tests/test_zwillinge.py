"""Kriterium 4 (19.11.2026): Tests an privaten Projekten (projects/ liegt nicht im Repository) laufen nur auf dem
Rechner des Nutzers. Damit dort nichts Ungeprueftes bleibt, muss jede Pruef-ID, die ein privater Test behauptet, auch
von einem oeffentlichen Test (synthetisch, ohne projects/) genannt werden.
Aufruf aus maker-bridge-2/:  uv run python tests/test_zwillinge.py"""
import ast
import glob
import os
import re

HIER = os.path.dirname(os.path.abspath(__file__))
ID = re.compile(r"""['"]([A-Z]{1,2}\d{1,2})(?:-[A-Z]+)?['"]""")


def _funktionen():
    for f in sorted(glob.glob(os.path.join(HIER, 'test_*.py'))):
        src = open(f, encoding='utf-8').read()
        for n in ast.parse(src).body:
            if isinstance(n, ast.FunctionDef):            # auch Hilfsfunktionen (Ablauf in _ablauf o. ae.)
                yield os.path.basename(f), n.name, ast.get_source_segment(src, n)


def _privat(seg):
    return bool(re.search(r"beispielprojekt\(|_echt\(|_kopie\(|PROJEKTE\b|'projects'|pdir\('", seg))


def test_private_ids_haben_oeffentlichen_zwilling():
    privat, oeffentlich = {}, set()
    for datei, name, seg in _funktionen():
        ids = set(ID.findall(seg))
        if _privat(seg):
            for i in ids:
                privat.setdefault(i, []).append(f'{datei}::{name}')
        else:
            oeffentlich |= ids
    assert privat, 'keine privaten Tests gefunden - Erkennung pruefen'
    ohne = {i: w for i, w in privat.items() if i not in oeffentlich}
    assert not ohne, f'nur an privaten Projekten geprueft (oeffentlichen Test ergaenzen): {ohne}'


if __name__ == '__main__':
    test_private_ids_haben_oeffentlichen_zwilling()
    print('alle ok')
