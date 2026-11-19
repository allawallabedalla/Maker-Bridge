"""Firmware-Konstanten gegen die Pruefannahmen (FW1, seit 15.11.2026).

Bodenklima: Die Firmware sendete mit ``FUNK_LEISTUNG_DBM 14 // reicht laut Abschaetzung`` – eine Konstante mit
Pruefwirkung, die keine Pruefung je gesehen hat. Firmware gehoert zum Entwurf (V-Modell: Komponente).

soll.json ``_projekt.firmware``:
    {"pfad": "firmware/sensor",                      # relativ zum Projekt oder absolut
     "konstanten": {"FUNK_LEISTUNG_DBM": {"datei": "config.h", "soll_aus": "elektronik.funk.P_t_dBm"},
                    "IDAC_UA": {"datei": "config.h", "soll_aus": "messkette.schaltung.I_idac_A", "faktor": 1e6},
                    "PERIODE_MS": {"datei": "config.h", "soll_aus": "...messrate_Hz", "kehrwert": true, "faktor": 1000},
                    "FUNK_SF": {"datei": "funk.h", "soll": 12, "herkunft": "berechnet: E16"}}}
FW1 liest ``#define NAME wert`` (bzw. ``const ... NAME = wert;``) und vergleicht mit dem soll-Wert (direkt ``soll``
oder aus einem anderen soll-Feld ``soll_aus``). Abweichung = fehler (die Pruefungen rechnen mit etwas anderem, als
das Geraet tut). Datei fehlt = uebersprungen (Ausloeser 'firmware' macht daraus einen fehler).

FW2 Hosttest der Rechenlogik (seit 19.11.2026, ``mb2/firmware_test.py``, Befehl ``firmware_test``): Ergebnis vorhanden,
zum aktuellen Quellstand (Hash) und alle Faelle bestanden. Veraltet oder nie gelaufen -> uebersprungen.
FW3 Fehlerinjektion in Software: jeder Fehler aus ``erkennung`` der Anforderungen hat einen bestandenen Fall
art=fehlerinjektion; gibt es Erkennungen, braucht es ausserdem einen Fehlalarm-Fall.
"""
import os
import re

from . import ergebnis, projekt_soll, uebersprungen

Q = 'mb2/pruefungen/firmware.py (Konsistenz Firmware <-> Pruefannahmen)'
T = 'Firmware-Konstante'


ZAHL = r'([-+]?(?:0[xX][0-9a-fA-F]+|(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?))[uUlLfF]*\b'


def _wert_aus_datei(text, name):
    """Zahl aus #define NAME wert bzw. NAME = wert; versteht Hex (0x10), Exponent (-1.5e-6) und Endungen (u, f, L)."""
    m = re.search(rf'^\s*#\s*define\s+{re.escape(name)}\s+\(?\s*{ZAHL}', text, re.M) or \
        re.search(rf'\b{re.escape(name)}\s*=\s*\(?\s*{ZAHL}', text)
    if not m:
        return None
    v = m.group(1)
    if v.lstrip('+-').lower().startswith('0x'):
        return int(v, 16)
    return float(v) if any(c in v for c in '.eE') else int(v)


def _feld(d, pfad):
    for t in pfad.split('.'):
        if not isinstance(d, dict) or t not in d:
            return None
        d = d[t]
    return d


def _hosttest(pdir, pj):
    import json as _j
    from ..firmware_test import quellen_hash
    out = []
    ht = (pj.get('firmware') or {}).get('hosttest')
    if not ht:
        return [uebersprungen('FW2', 'Hosttest Rechenlogik', 'firmware.hosttest {quellen, test} fehlt - Rechenlogik '
                              'ungeprueft bis zur Abnahme am Geraet', Q),
                uebersprungen('FW3', 'Fehlerinjektion in Software', 'kein Hosttest', Q)]
    p = os.path.join(pdir, 'pruef', 'firmware_test.json')
    erg = _j.load(open(p, encoding='utf-8')) if os.path.exists(p) else None
    if erg is None:
        return [uebersprungen('FW2', 'Hosttest Rechenlogik', 'nie gelaufen (Befehl firmware_test)', Q),
                uebersprungen('FW3', 'Fehlerinjektion in Software', 'Hosttest nie gelaufen', Q)]
    if erg.get('quellen_hash') != quellen_hash(pdir, ht):
        return [uebersprungen('FW2', 'Hosttest Rechenlogik', 'veraltet: Quellen seit dem letzten Lauf geaendert '
                              '(firmware_test neu)', Q),
                uebersprungen('FW3', 'Fehlerinjektion in Software', 'Hosttest veraltet', Q)]
    fs = erg.get('faelle') or []
    schlecht = [f.get('fall') for f in fs if not f.get('bestanden')]
    if erg.get('fehler') and 'Compiler' in erg['fehler']:
        out.append(uebersprungen('FW2', 'Hosttest Rechenlogik', erg['fehler'], Q))
    else:
        st = 'ok' if erg.get('ok') else 'fehler'
        out.append(ergebnis('FW2', 'Hosttest Rechenlogik', st, wert=len(fs) - len(schlecht), grenze=len(fs), quelle=Q,
                            hinweis=(f'{len(fs)} Faelle bestanden' if st == 'ok' else
                                     f'{erg.get("fehler") or ""} nicht bestanden: {schlecht[:5]}').strip()))
    erk = [f.get('fehler') for a in _j.load(open(os.path.join(pdir, 'anforderungen.json'), encoding='utf-8')).get(
        'anforderungen', []) for f in a.get('erkennung') or []] if os.path.exists(os.path.join(pdir, 'anforderungen.json')) else []
    if not erk:
        out.append(uebersprungen('FW3', 'Fehlerinjektion in Software', 'keine Anforderung mit erkennung', Q))
    else:
        gedeckt = {f.get('fehler') for f in fs if f.get('art') == 'fehlerinjektion' and f.get('bestanden')}
        fehlt = [e for e in erk if e not in gedeckt]
        fa = any(f.get('art') == 'fehlalarm' and f.get('bestanden') for f in fs)
        st = 'ok' if not fehlt and fa else 'fehler'
        out.append(ergebnis('FW3', 'Fehlerinjektion in Software', st, wert=len(erk) - len(fehlt), grenze=len(erk),
                            quelle=Q, hinweis=('jeder Fehler in Software eingespielt und erkannt, Fehlalarm-Fall bestanden'
                                               if st == 'ok' else f'ohne bestandenen Fall: {fehlt}' +
                                               ('' if fa else '; kein bestandener Fehlalarm-Fall'))))
    return out


def pruefe(pdir):
    pj = projekt_soll(pdir)
    fw = pj.get('firmware')
    if not fw:
        return [uebersprungen('FW1', T, 'soll.json _projekt.firmware fehlt (Pfad + Konstanten mit Pruefwirkung)', Q)]
    basis = fw.get('pfad', '')
    basis = basis if os.path.isabs(basis) else os.path.join(pdir, basis)
    out = []
    for name, k in (fw.get('konstanten') or {}).items():
        datei = os.path.join(basis, k.get('datei', ''))
        if not os.path.exists(datei):
            out.append(uebersprungen('FW1', f'{T} {name}', f'Datei fehlt: {datei}', Q))
            continue
        ist = _wert_aus_datei(open(datei, encoding='utf-8', errors='replace').read(), name)
        soll = k.get('soll', _feld(pj, k['soll_aus']) if k.get('soll_aus') else None)
        if isinstance(soll, bool):
            soll = int(soll)
        if k.get('soll_aus') and isinstance(soll, (int, float)) and soll:
            soll = float(k.get('faktor', 1.0)) / soll if k.get('kehrwert') else soll * float(k.get('faktor', 1.0))
        if ist is None:
            out.append(ergebnis('FW1', f'{T} {name}', 'fehler', quelle=Q, hinweis=f'{name} nicht in {datei} gefunden'))
        elif soll is None:
            out.append(uebersprungen('FW1', f'{T} {name}', f'kein soll-Wert ({k.get("soll_aus") or "soll"} fehlt)', Q))
        elif abs(float(ist) - float(soll)) > 1e-9 * max(1.0, abs(float(soll))):
            out.append(ergebnis('FW1', f'{T} {name}', 'fehler', wert=ist, grenze=soll, quelle=Q,
                                hinweis=f'Firmware {name} = {ist}, Pruefungen rechnen mit {soll} '
                                        f'({k.get("soll_aus") or "soll"}) - angleichen'))
        else:
            out.append(ergebnis('FW1', f'{T} {name}', 'ok', wert=ist, grenze=soll, quelle=Q,
                                hinweis=f'{name} = {ist} wie {k.get("soll_aus") or "soll"}'))
    return (out or [uebersprungen('FW1', T, 'firmware.konstanten leer', Q)]) + _hosttest(pdir, pj)
