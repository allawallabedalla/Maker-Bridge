"""Druck-Nachbearbeitung (Bricklayers) im Katalog sichtbar machen. Kein Festigkeitsbonus: Die Literatur nennt
+14 % (PLA) / +10 % (PETG) Z-Festigkeit (CNC Kitchen), am MK4 ist das nicht gemessen -> M7/M22 rechnen ohne."""
import json
import os

from . import ergebnis, soll

Q = 'CNC Kitchen „Brick Layers“; mb2/bricklayers.py'


def pruefe(pdir):
    s = soll(pdir)
    teile = [t for t, v in s.items() if isinstance(v, dict) and v.get('bricklayers')]
    if not teile:
        return []
    sl = os.path.join(pdir, 'print', 'slice.json')
    slicen = json.load(open(sl, encoding='utf-8')) if os.path.exists(sl) else {}
    bl = slicen.get('bricklayers')
    erg = []
    for t in teile:
        if not bl:
            erg.append(ergebnis('BL', 'Bricklayers', 'warnung', teil=t, quelle=Q,
                                hinweis='in soll.json gesetzt, aber noch nicht gesliced (slice_plate)'))
        elif t not in slicen.get('bricklayers_teile', []):
            erg.append(ergebnis('BL', 'Bricklayers', 'fehler', teil=t, quelle=Q,
                                hinweis='gesetzt, aber im G-Code nicht bearbeitet - cad_plate + slice_plate neu'))
        elif not bl.get('pruefung', {}).get('ok'):
            erg.append(ergebnis('BL', 'Bricklayers', 'fehler', teil=t, quelle=Q,
                                hinweis=f'G-Code-Gegenpruefung: {bl.get("pruefung", {}).get("fehler")}'))
        else:
            erg.append(ergebnis('BL', 'Bricklayers', 'info', teil=t, quelle=Q,
                                wert=bl['pruefung'].get('anhebungen'), einheit='Linien angehoben',
                                hinweis='aktiv; nicht als Festigkeitsbonus angerechnet (am MK4 nicht gemessen). '
                                        'Grenze: an Zwischen-Deckflaechen steht die angehobene Linie h/2 ueber.'))
    return erg
