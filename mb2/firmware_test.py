"""Firmware-Hosttests (seit 19.11.2026): die Rechenlogik eines Geraets auf dem PC pruefen, bevor es gebaut ist.

Warum: Durchfluss-, Volumen-, Plausibilitaets- und Diagnose-Logik laeuft im Geraet. Ohne Hosttest zeigt erst die
Abnahme am fertigen Geraet, ob die Rechnung stimmt - zu spaet und ohne Fehlerinjektion fuer seltene Faelle.

Voraussetzung im Projekt: Rechenlogik ohne Hardwarezugriff in eigenen Dateien (z. B. ``logik.c``/``rechnung.h``),
Hardware nur ueber duenne Schichten. Dann:

soll.json ``_projekt.firmware.hosttest``:
    {"quellen": ["firmware/logik.c"], "test": "firmware/test_host.c", "sprache": "c|cpp", "flags": ["-O1"]}
Das Testprogramm gibt je Fall eine Zeile aus (stdout):
    MB2 {"fall": "Volumen 60 s bei 10 ml/min", "art": "wert", "ist": 10.0, "soll": 10.0, "tol": 0.01}
    MB2 {"fall": "Verstopfung", "art": "fehlerinjektion", "fehler": "Verstopfung", "ist": 1, "soll": 1}
    MB2 {"fall": "Normalbetrieb 1 h simuliert", "art": "fehlalarm", "ist": 0, "soll": 0}
art: wert (|ist - soll| <= tol) | fehlerinjektion (Fehler in Software eingespielt, ist = erkannt 0/1) |
fehlalarm (ist = Alarme im fehlerfreien Verlauf, <= soll). Exit-Code != 0 oder keine MB2-Zeile = nicht bestanden.
Ergebnis: pruef/firmware_test.json mit Hash der Quellen (aendert sich eine Quelle, gilt der Test als veraltet).
"""
import hashlib
import json
import os
import subprocess
import tempfile

from . import werkzeuge


def _pfad(pdir, p):
    return p if os.path.isabs(p) else os.path.join(pdir, p)


def quellen_hash(pdir, ht):
    h = hashlib.sha256()
    for p in sorted(set((ht.get('quellen') or []) + [ht.get('test', '')])):
        q = _pfad(pdir, p)
        h.update(p.encode())
        h.update(open(q, 'rb').read() if os.path.isfile(q) else b'<fehlt>')
    return h.hexdigest()[:16]


def bewerte_fall(f):
    art = f.get('art', 'wert')
    ist, soll = f.get('ist'), f.get('soll')
    if not isinstance(ist, (int, float)) or not isinstance(soll, (int, float)):
        return False
    if art == 'wert':
        return abs(ist - soll) <= float(f.get('tol', 0))
    if art == 'fehlerinjektion':
        return ist == 1
    if art == 'fehlalarm':
        return ist <= soll
    return False


def laufen(pdir, ht, timeout=120):
    """Uebersetzen, ausfuehren, Faelle bewerten, pruef/firmware_test.json schreiben."""
    cpp = ht.get('sprache') == 'cpp'
    cc = werkzeuge.c_compiler(cpp)
    erg = {'quellen_hash': quellen_hash(pdir, ht), 'compiler': cc, 'faelle': [], 'ok': False}
    if not cc:
        erg['fehler'] = 'kein C/C++-Compiler (gcc/clang; Windows: MSYS2) - Hosttest nicht ausgefuehrt'
    else:
        fehlt = [p for p in (ht.get('quellen') or []) + [ht.get('test')] if not p or not os.path.isfile(_pfad(pdir, p))]
        if fehlt:
            erg['fehler'] = f'Dateien fehlen: {fehlt}'
        else:
            with tempfile.TemporaryDirectory() as t:
                exe = os.path.join(t, 'hosttest.exe')
                q = [_pfad(pdir, p) for p in ht['quellen']] + [_pfad(pdir, ht['test'])]
                inc = sorted({os.path.dirname(x) for x in q})
                c = subprocess.run([cc, *ht.get('flags', []), *[f'-I{i}' for i in inc], *q, '-o', exe, '-lm'],
                                   capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
                if c.returncode != 0:
                    erg['fehler'] = 'Uebersetzen gescheitert: ' + (c.stderr or c.stdout)[-1500:]
                else:
                    r = subprocess.run([exe], capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
                    erg['exit'] = r.returncode
                    for z in r.stdout.splitlines():
                        if z.startswith('MB2 '):
                            try:
                                f = json.loads(z[4:])
                            except ValueError:
                                f = {'fall': z[4:80], 'art': 'kaputt'}
                            f['bestanden'] = bewerte_fall(f)
                            erg['faelle'].append(f)
                    if r.returncode != 0:
                        erg['fehler'] = f'Testprogramm endete mit {r.returncode}: {r.stderr[-500:]}'
                    elif not erg['faelle']:
                        erg['fehler'] = 'keine MB2-Zeile ausgegeben'
                    erg['ok'] = not erg.get('fehler') and all(f['bestanden'] for f in erg['faelle'])
    os.makedirs(os.path.join(pdir, 'pruef'), exist_ok=True)
    json.dump(erg, open(os.path.join(pdir, 'pruef', 'firmware_test.json'), 'w', encoding='utf-8'), indent=1,
              ensure_ascii=False)
    return erg
