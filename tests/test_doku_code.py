"""Kriterium 2 (19.11.2026): Doku = Code. OCW_PRUEFKATALOG.md wird gegen den Code und die Tests geprueft.
Aufruf aus maker-bridge-2/:  uv run python tests/test_doku_code.py"""
import glob
import os
import re

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META = {'A0', 'E0'}       # Ausloeser-Meta-Ergebnis bzw. Modulabsturz, keine Fachpruefung


def _katalog():
    kat = {}
    for z in open(os.path.join(BASIS, 'OCW_PRUEFKATALOG.md'), encoding='utf-8'):
        m = re.match(r'^\| ([A-Z]{1,3})(\d{1,2})(?:[–-]([A-Z]{1,3})?(\d{1,2}))? \|', z)
        if not m:
            continue
        u = z.rstrip().rstrip('|').split('|')[-1]
        st = 'ungetestet' if 'ungetestet' in u else '✅' if '✅' in u else '◐' if '◐' in u else 'offen'
        pre, a, b = m.group(1), int(m.group(2)), int(m.group(4) or m.group(2))
        for n in range(a, b + 1):
            kat[f'{pre}{n}'] = st
    return kat


def _code_text():
    return ''.join(open(f, encoding='utf-8').read() for f in glob.glob(os.path.join(BASIS, 'mb2', '**', '*.py'),
                                                                        recursive=True))


def _ausgegeben(text):
    ids = set(re.findall(r"""\b(?:ergebnis|uebersprungen|_e|_u)\(\s*f?['"]([A-Z]{1,3}\d{1,2})['"(]""", text))
    ids |= set(re.findall(r"""\(\s*'([A-Z]{1,3}\d{1,2})',\s*'[A-Z][a-zäöüß ][^']*',\s*'""", text))   # Tupel (ID, Titel, ...)
    return ids - META


def test_umgesetzt_steht_im_code():
    text = _code_text()
    fehlt = [k for k, s in _katalog().items() if s != 'offen' and f"'{k}'" not in text and f"'{k}-" not in text]
    assert not fehlt, f'Katalog sagt umgesetzt, Code kennt die ID nicht: {fehlt}'


def test_jede_ausgegebene_id_steht_im_katalog():
    kat = _katalog()
    ohne = sorted(i for i in _ausgegeben(_code_text()) if i not in kat)
    assert not ohne, f'Code gibt Pruef-IDs aus, die im Katalog fehlen: {ohne}'


def test_offen_wird_nicht_ausgegeben():
    aus = _ausgegeben(_code_text())
    falsch = [k for k, s in _katalog().items() if s == 'offen' and k in aus]
    assert not falsch, f'Katalog sagt offen, Code gibt die Pruefung aber aus: {falsch}'


def test_umgesetzt_heisst_getestet():
    tests = ''.join(open(f, encoding='utf-8').read() for f in glob.glob(os.path.join(BASIS, 'tests', '*.py')))
    ohne = [k for k, s in _katalog().items() if s == '✅' and f"'{k}'" not in tests and f'"{k}"' not in tests and f"'{k}-" not in tests]
    veraltet = [k for k, s in _katalog().items() if s == 'ungetestet' and (f"'{k}'" in tests or f'"{k}"' in tests)]
    assert not veraltet, f'Katalog sagt "ungetestet", es gibt aber einen Test - auf ✅ setzen: {veraltet}'
    assert not ohne, f'"✅ umgesetzt" ohne einen Test, der die ID nennt (auf "ungetestet" stellen oder Test schreiben): {ohne}'


if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_') and callable(f):
            f()
            print('ok', n)
    print('alle ok')
