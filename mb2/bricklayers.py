"""Bricklayers: versetzte Innenwaende fuer mehr Haftung quer zu den Schichten und dichtere Waende.

Nachbearbeitung von PrusaSlicer-ASCII-G-Code (MK4 IS, relative E). Fuer ausgewaehlte Objekte (M486-Index =
Reihenfolge in print/platte.json) wird jede zweite INNERE Wandlinie um eine halbe Schichthoehe angehoben, so dass
sich die Linien wie Mauersteine verzahnen. Die Aussenwand bleibt unveraendert (Oberflaeche, Masse).

Regeln je Wandblock (zusammenhaengende ;TYPE:Perimeter-Linien eines Objekts vor seiner Aussenwand):
- PrusaSlicer druckt Innenwaende von innen nach aussen, die Aussenwand zuletzt. Linie j von k hat den Abstand
  k - j zur Aussenwand; ungerader Abstand -> angehoben (die Linie direkt an der Aussenwand immer).
- Erste Schicht: angehobene Linie bei z + h/2 mit 1,5-facher Extrusion (fuellt 0 .. 1,5 h).
- Letzte Schicht des Objekts: angehobene Linie NICHT anheben, 0,5-fache Extrusion (sonst Ueberstand h/2).
- Dazwischen: z + h/2, Extrusion unveraendert.
Grenzen (bewusst einfach, im Bericht ausgewiesen): an Zwischen-Deckflaechen (Absaetze) steht die angehobene Linie
h/2 ueber; Ueberhang-Wandlinien werden nicht angefasst; nur relative E (M83) und nur ASCII-G-Code.
Quelle des Verfahrens: CNC Kitchen „Brick Layers“ (+14 % PLA / +10 % PETG Z-Festigkeit), GeekDetour/BrickLayers.
"""
import math
import re

_ZAHL = r'(-?\d+(?:\.\d*)?|-?\.\d+)'
_E = re.compile(r'E' + _ZAHL)
_Z = re.compile(r'Z' + _ZAHL)
_XY = re.compile(r'[XYIJ]' + _ZAHL)


def _ist_extrusion(z):
    if not (z.startswith('G1 ') or z.startswith('G2 ') or z.startswith('G3 ')):
        return False
    m = _E.search(z.split(';')[0])
    return bool(m and float(m.group(1)) > 0 and _XY.search(z.split(';')[0]))


def _e_skalieren(z, f):
    teil, rest = (z.split(';', 1) + [''])[:2]
    teil = _E.sub(lambda m: f'E{float(m.group(1)) * f:.5f}', teil)
    return teil + (';' + rest if rest else '')


def bearbeiten(zeilen, objekte):
    """zeilen: Liste von G-Code-Zeilen (ohne \\n); objekte: Menge der M486-Indizes. -> (neue_zeilen, bericht)."""
    if not objekte:
        return zeilen, {'aktiv': False}
    if not any(z.startswith('M83') for z in zeilen[:400]):
        raise RuntimeError('Bricklayers braucht relative Extrusion (M83) - im G-Code nicht gefunden.')
    # 1. Durchlauf: je Objekt die hoechste Schicht mit Wandlinien (fuer die Regel "letzte Schicht")
    obj, z_schicht, letzte = -1, 0.0, {}
    for z in zeilen:
        if z.startswith(';Z:'):
            z_schicht = float(z[3:])
        elif z.startswith('M486 S'):
            obj = int(z.split()[1][1:])
        elif z.startswith(';TYPE:Perimeter') and obj in objekte:
            letzte[obj] = max(letzte.get(obj, 0.0), z_schicht)
    # Wandbloecke finden: Indexbereiche der Linien je Block, zuerst sammeln, dann umschreiben
    aus, obj, typ, z_schicht, h, z_akt = [], -1, '', 0.0, 0.2, 0.0
    schicht_nr = 0
    block = []          # Liste der Linien [(start, ende)] im aktuellen Perimeter-Block
    linie = None        # [start] Index der laufenden Linie im Ausgabe-Puffer
    stat = {'angehoben': 0, 'erste_schicht': 0, 'letzte_schicht': 0, 'bloecke': 0}

    def block_abschliessen():
        nonlocal block
        if not block:
            return
        stat['bloecke'] += 1
        k = len(block)
        erste = schicht_nr == 1
        letzte_s = abs(z_schicht - letzte.get(obj_block, -1)) < 1e-6
        for j, (a, b) in enumerate(block):
            if (k - j) % 2 == 0:
                continue
            if letzte_s:
                for i in range(a, b):
                    if _ist_extrusion(aus[i]):
                        aus[i] = _e_skalieren(aus[i], 0.5)
                stat['letzte_schicht'] += 1
                continue
            f = 1.5 if erste else 1.0
            if f != 1.0:
                for i in range(a, b):
                    if _ist_extrusion(aus[i]):
                        aus[i] = _e_skalieren(aus[i], f)
                stat['erste_schicht'] += 1
            aus[a] = f'G1 Z{z_schicht + h / 2:.3f} ; bricklayers\n' + aus[a]
            aus[b - 1] = aus[b - 1] + f'\nG1 Z{z_akt_block:.3f} ; bricklayers zurueck'
            stat['angehoben'] += 1
        block = []

    obj_block, z_akt_block = -1, 0.0
    for z in zeilen:
        if z.startswith(';LAYER_CHANGE'):
            schicht_nr += 1
        if z.startswith(';Z:'):
            z_schicht = float(z[3:])
        elif z.startswith(';HEIGHT:'):
            h = float(z[8:])
        elif z.startswith('M486 S'):
            obj = int(z.split()[1][1:])
        neue_typ = z[6:].strip() if z.startswith(';TYPE:') else None
        ext = _ist_extrusion(z)
        mz = _Z.search(z.split(';')[0]) if z.startswith(('G0 ', 'G1 ')) else None
        # Linie beenden bei Nicht-Extrusion (Fahrt, Wipe, Typwechsel, Objektwechsel)
        if linie is not None and (not ext or neue_typ is not None or z.startswith('M486')):
            if not z.startswith((';WIDTH', 'G1 F')) or neue_typ is not None:
                block.append((linie, len(aus)))
                linie = None
        if neue_typ is not None:
            if typ == 'Perimeter' and neue_typ != 'Perimeter':
                block_abschliessen()
            typ = neue_typ
        if z.startswith('M486 S') and block:
            block_abschliessen()
        if mz:
            z_akt = float(mz.group(1))
        aus.append(z)
        if ext and typ == 'Perimeter' and obj in objekte and linie is None:
            linie = len(aus) - 1
            obj_block, z_akt_block = obj, z_akt
    if linie is not None:
        block.append((linie, len(aus)))
    block_abschliessen()
    neu = '\n'.join(aus).split('\n')
    stat['aktiv'] = True
    stat['objekte'] = sorted(objekte)
    return neu, stat


def pruefen(alt, neu, objekte):
    """G-Code-Gegenpruefung nach der Bearbeitung."""
    def summe_e(zz):
        return sum(float(m.group(1)) for z in zz if z.startswith(('G1', 'G2', 'G3'))
                   for m in [_E.search(z.split(';')[0])] if m)

    def max_z(zz):
        return max((float(m.group(1)) for z in zz if z.startswith(('G0', 'G1'))
                    for m in [_Z.search(z.split(';')[0])] if m), default=0.0)
    e_alt, e_neu = summe_e(alt), summe_e(neu)
    fehler = []
    rel = (e_neu - e_alt) / e_alt if e_alt else 0.0
    if abs(rel) > 0.02:
        fehler.append(f'Extrusion veraendert um {rel * 100:.1f} % (> 2 %)')
    if max_z(neu) > max_z(alt) + 1e-6:
        fehler.append(f'hoechstes Z steigt ({max_z(alt):.2f} -> {max_z(neu):.2f})')
    n_hoch = sum(1 for z in neu if z.endswith('; bricklayers'))
    n_zur = sum(1 for z in neu if z.endswith('; bricklayers zurueck'))
    if n_hoch != n_zur:
        fehler.append(f'{n_hoch} Anhebungen, aber {n_zur} Rueckstellungen')
    if objekte and n_hoch == 0:
        fehler.append('keine Linie angehoben - Objektzuordnung pruefen')
    return {'ok': not fehler, 'fehler': fehler, 'extrusion_aenderung_pct': round(rel * 100, 2),
            'anhebungen': n_hoch}


def objekt_boxen(zeilen):
    """XY-Bereich und hoechstes Z der Extrusionen je M486-Objekt -> {idx: [xmin, ymin, xmax, ymax, zmax]}."""
    obj, x, y, z, boxen = -1, 0.0, 0.0, 0.0, {}
    zahl = re.compile(r'([XYZ])' + _ZAHL)
    for l in zeilen:
        if l.startswith('M486 S'):
            obj = int(l.split()[1][1:])
            continue
        if not l.startswith(('G0 ', 'G1 ', 'G2 ', 'G3 ')):
            continue
        teil = l.split(';')[0]
        x0, y0 = x, y                                  # Startpunkt der Bewegung gehoert mit zur Box
        for a, v in zahl.findall(teil):
            if a == 'X':
                x = float(v)
            elif a == 'Y':
                y = float(v)
            else:
                z = float(v)
        if obj >= 0 and _ist_extrusion(l):
            b = boxen.setdefault(obj, [x0, y0, x0, y0, z])
            b[0], b[1] = min(b[0], x0, x), min(b[1], y0, y)
            b[2], b[3], b[4] = max(b[2], x0, x), max(b[3], y0, y), max(b[4], z)
    return boxen


def objekt_zuordnung(zeilen, teile_bbox):
    """Teilname -> M486-Index ueber Groesse und relative Lage (der Slicer verschiebt die ganze Platte per --center).
    Wirft, wenn die Zuordnung nicht eindeutig ist (lieber kein Bricklayers als am falschen Teil)."""
    import itertools
    boxen = objekt_boxen(zeilen)
    namen, idx = list(teile_bbox), sorted(boxen)
    if len(namen) != len(idx):
        raise RuntimeError(f'{len(namen)} Teile auf der Platte, aber {len(idx)} Objekte im G-Code')
    # gemeinsame Verschiebung: Mitte aller Teile gegen Mitte aller Objekte
    tm = [sum((b[0] + b[3]) / 2 for b in teile_bbox.values()) / len(namen),
          sum((b[1] + b[4]) / 2 for b in teile_bbox.values()) / len(namen)]
    gm = [sum((b[0] + b[2]) / 2 for b in boxen.values()) / len(idx),
          sum((b[1] + b[3]) / 2 for b in boxen.values()) / len(idx)]

    def kosten(n, i):
        t, g = teile_bbox[n], boxen[i]
        dx = ((t[0] + t[3]) / 2 - tm[0]) - ((g[0] + g[2]) / 2 - gm[0])
        dy = ((t[1] + t[4]) / 2 - tm[1]) - ((g[1] + g[3]) / 2 - gm[1])
        dh = t[5] - g[4]
        return math.hypot(dx, dy) + abs(dh)
    if len(namen) > 7:
        raise RuntimeError('zu viele Teile fuer die Zuordnung (max. 7)')
    best = min(itertools.permutations(idx), key=lambda p: sum(kosten(n, i) for n, i in zip(namen, p)))
    zu = dict(zip(namen, best))
    schlecht = {n: round(kosten(n, i), 2) for n, i in zu.items() if kosten(n, i) > 3.0}
    if schlecht:
        raise RuntimeError(f'Objektzuordnung unsicher (Abweichung mm): {schlecht}')
    return zu


def meta_ascii(zeilen):
    """'; key = value'-Block am Ende eines ASCII-G-Codes -> dict (wie slicer.summarize fuer .bgcode)."""
    d = {}
    for z in zeilen[-1500:]:
        if z.startswith('; ') and ' = ' in z:
            k, v = z[2:].split(' = ', 1)
            d[k.strip()] = v.strip()
    return d
