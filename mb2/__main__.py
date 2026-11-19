"""CLI: python -m mb2 <befehl> [JSON | key=value ...]   (ohne Befehl: Liste)"""
import json
import sys
import traceback

from .befehle import BEFEHLE


def _args(rest):
    if len(rest) == 1 and rest[0].lstrip().startswith('{'):
        return json.loads(rest[0])
    out = {}
    for a in rest:
        k, _, v = a.partition('=')
        try:
            out[k] = json.loads(v)
        except ValueError:
            out[k] = v
    return out


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in BEFEHLE:
        for n, f in BEFEHLE.items():
            print(f'{n:22s} {f.__doc__.strip().splitlines()[0]}')
        return 0 if len(sys.argv) < 2 else 2
    try:
        erg = {'ok_aufruf': True, 'ergebnis': BEFEHLE[sys.argv[1]](**_args(sys.argv[2:]))}
    except Exception as e:  # noqa: BLE001 - Fehler als JSON an den Aufrufer
        erg = {'ok_aufruf': False, 'fehler': f'{type(e).__name__}: {e}', 'trace': traceback.format_exc()[-1500:]}
    sys.stdout.write(json.dumps(erg, ensure_ascii=False, indent=1, default=str) + '\n')
    return 0 if erg['ok_aufruf'] else 1


if __name__ == '__main__':
    sys.exit(main())
