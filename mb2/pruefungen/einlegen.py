"""Einlegeteile: Magnete, Muttern, Lager, NFC-Tags, Gewichte ... eingedruckt (Druckpause) oder nachher eingesetzt
(EL1-EL5, seit 20.11.2026).

Belegt am PrusaSlicer-Quellcode 2.9.7 (github.com/prusa3d/PrusaSlicer, Tag version_2.9.7):
- Pause je Hoehe steht im 3MF unter ``Metadata/Prusa_Slicer_custom_gcode_per_print_z.xml``
  (<custom_gcodes_per_print_z bed_idx="0"><code print_z=".." type="1" extruder="1" color="" extra="Text"
  gcode="M601"/><mode value="SingleExtruder"/></custom_gcodes_per_print_z>), type 1 = PausePrint
  (src/libslic3r/CustomGCode.hpp, Format/3mf.cpp).
- Im G-Code: ``;PAUSE_PRINT``, optional ``M117 <Text>``, dann ``pause_print_gcode`` (Voreinstellung M601,
  PrintConfig.cpp; das MK4-Profil ueberschreibt sie nicht). Schichtbeginn ``;Z:<print_z>`` (GCode.cpp).
- Restzeit ``M73 P<Prozent> R<Minuten>`` (GCodeProcessor.cpp).
Die Pause wird vor der Schicht mit dieser print_z ausgefuehrt; PrusaSlicer schneidet jede Schicht in ihrer Mitte.

soll.json je Teil:
    "einlegeteile": [{"name": "Magnet_1",            # Platzhalter im CAD-Skript (Koerper mit Quelle, z. B. Datenblatt)
                      "art": "magnet|mutter|lager|sonstiges", "einlegen": "eingedruckt|nachher",
                      "T_max_C": 80,                 # Magnet: zulaessige Betriebstemperatur laut Datenblatt
                      "polung": "Nordpol nach oben (rote Markierung)", "anzahl": 1}]
cad_build schreibt je Einlegeteil die Lage in Drucklage (out/<teil>.pruefung.json "einlegeteile": z_unten, z_oben,
decke = Unterkante des Materials ueber dem Teil, offen = nichts darueber).
Schichtraster: aus dem aufgeloesten Slicer-Profil (print/slice.json -> config) oder _projekt.druck
{erste_schicht_mm, schicht_mm, bett_C}.

EL1 Pausenschicht: deckende Schicht n = erste Schicht, deren Mitte ueber der Decke liegt; Pause bei print_z = t_n.
    Teil-Oberkante <= t_(n-1) (sonst faehrt die Duese dagegen) -> ok; Abstand < 0,05 mm oder Decke nicht auf einer
    Schichtgrenze (> 0,02 mm daneben) -> warnung.
    Boden unter dem Teil mindestens eine Schicht. 'nachher': Tasche muss nach oben offen sein.
EL2 Ueberbrueckung: die deckende Schicht ueberspannt die Tasche (kleinere Seite der Grundflaeche) -> info mit Laenge.
EL3 Temperatur (nur Magnet): Bett-Temperatur < T_max_C, sonst fehler (Entmagnetisierung); ohne T_max uebersprungen.
EL4 Pause im G-Code: ;PAUSE_PRINT + M601 genau vor ;Z:<print_z> jeder geplanten Pause (ASCII-G-Code).
EL5 Zeitpunkt: Slicer-Schaetzung bis zur Pause aus M73 (R gesamt - R an der Pause) - damit der Nutzer weiss, wann er
    am Drucker sein muss.
"""
import json
import os
import re

from . import ergebnis, projekt_soll, soll as lade_soll, uebersprungen

Q = 'mb2/pruefungen/einlegen.py (Einlegeteile, Druckpause; PrusaSlicer 2.9.7 Quellcode)'
T = {'EL1': 'Pausenschicht', 'EL2': 'Ueberbrueckung der Tasche', 'EL3': 'Temperatur am Magneten',
     'EL4': 'Pause im G-Code', 'EL5': 'Zeitpunkt der Pause'}
ABSTAND_MIN = 0.05


def raster(erste, h, z_max):
    """Schichtoberkanten t_1..t_N (t_1 = erste Schicht)."""
    t, z = [], erste
    while z <= z_max + h:
        t.append(round(z, 6))
        z += h
    return t


def pausenschicht(decke, erste, h):
    """(n, t_(n-1), t_n): deckende Schicht = erste, deren Mitte ueber der Decke liegt."""
    t = raster(erste, h, decke + 2 * h)
    unten = 0.0
    for n, oben in enumerate(t, 1):
        if (unten + oben) / 2 > decke + 1e-9:
            return n, unten, oben
        unten = oben
    return None


def profil(pdir):
    """{erste, h, bett} aus print/slice.json -> config (aufgeloestes Profil) oder _projekt.druck; sonst None."""
    sj = os.path.join(pdir, 'print', 'slice.json')
    if os.path.exists(sj):
        cfg = json.load(open(sj, encoding='utf-8')).get('config')
        if cfg and os.path.exists(cfg):
            w = dict(z.split(' = ', 1) for z in open(cfg, encoding='utf-8').read().splitlines() if ' = ' in z)
            try:
                bett = max(float(w.get('bed_temperature', '0').split(',')[0]),
                           float(w.get('first_layer_bed_temperature', '0').split(',')[0]))
                h = float(w['layer_height'])
                erste = w.get('first_layer_height', str(h)).strip()
                erste = h * float(erste[:-1]) / 100 if erste.endswith('%') else float(erste)
                return {'erste': erste, 'h': h, 'bett': bett, 'quelle': os.path.basename(cfg)}
            except (KeyError, ValueError):
                pass
    d = projekt_soll(pdir).get('druck') or {}
    if all(isinstance(d.get(f), (int, float)) for f in ('erste_schicht_mm', 'schicht_mm')):
        return {'erste': d['erste_schicht_mm'], 'h': d['schicht_mm'], 'bett': d.get('bett_C'),
                'quelle': '_projekt.druck'}
    return None


def _lage(pdir, teil):
    p = os.path.join(pdir, 'out', teil + '.pruefung.json')
    return {e['name']: e for e in (json.load(open(p, encoding='utf-8')).get('einlegeteile') or [])} if os.path.exists(p) else None


def pausen(pdir, teile, pr=None):
    """Geplante Pausen fuer die Teile auf einer Platte: [{print_z, text, teile}] (gleiche Hoehe zusammengefasst)."""
    pr = pr or profil(pdir)
    s = lade_soll(pdir) or {}
    plan = {}
    for t in teile:
        lage = _lage(pdir, t) or {}
        for e in (s.get(t) or {}).get('einlegeteile') or []:
            g = lage.get(e.get('name'))
            if e.get('einlegen', 'eingedruckt') != 'eingedruckt' or not g or g.get('offen') or not pr or pr['erste'] is None:
                continue
            ps = pausenschicht(g['decke_mm'], pr['erste'], pr['h'])
            if not ps:
                continue
            z = round(ps[2], 4)
            txt = f'{e.get("anzahl", 1)}x {e["name"]} in {t}' + (f' ({e["polung"]})' if e.get('polung') else '')
            p = plan.setdefault(z, {'print_z': z, 'teile': [], 'text': []})
            p['teile'].append(t)
            p['text'].append(txt)
    return [dict(p, text='; '.join(p['text'])[:120]) for _, p in sorted(plan.items())]


def pausen_xml(plan):
    """Metadata/Prusa_Slicer_custom_gcode_per_print_z.xml (Format aus PrusaSlicer 3mf.cpp, type 1 = PausePrint)."""
    def esc(x):
        return (str(x).replace('&', '&amp;').replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;'))
    z = ['<?xml version="1.0" encoding="utf-8"?>', '<custom_gcodes_per_print_z bed_idx="0">']
    z += [f'<code print_z="{p["print_z"]:.4f}" type="1" extruder="1" color="" extra="{esc(p["text"])}" gcode="M601"/>'
          for p in plan]
    z += ['<mode value="SingleExtruder"/>', '</custom_gcodes_per_print_z>']
    return '\n'.join(z) + '\n'


def gcode_pausen(text):
    """[(print_z der folgenden Schicht, Minuten seit Start laut M73, Restminuten)] fuer jedes ;PAUSE_PRINT."""
    out, z_akt, r_start, r_akt = [], None, None, None
    zeilen = text.splitlines()
    for i, l in enumerate(zeilen):
        if l.startswith(';Z:'):
            z_akt = float(l[3:])
        m = re.match(r'M73 P[\d.]+ R(\d+)', l)
        if m:
            r_akt = int(m.group(1))
            r_start = r_akt if r_start is None else r_start
        if l.startswith(';PAUSE_PRINT'):
            folgt = next((float(x[3:]) for x in zeilen[i + 1:i + 400] if x.startswith(';Z:')), None)
            m601 = any(x.strip().startswith('M601') for x in zeilen[i + 1:i + 6])
            out.append({'z_vorher': z_akt, 'z_folgt': folgt, 'm601': m601,
                        'minuten': (r_start - r_akt) if r_start is not None and r_akt is not None else None,
                        'rest_min': r_akt})
    return out


def _gcode(pdir):
    pd = os.path.join(pdir, 'print')
    g = sorted(f for f in os.listdir(pd) if f.endswith('.gcode')) if os.path.isdir(pd) else []
    b = sorted(f for f in os.listdir(pd) if f.endswith('.bgcode')) if os.path.isdir(pd) else []
    return (os.path.join(pd, g[-1]) if g else None), bool(b)


def pruefe(pdir):
    s = lade_soll(pdir) or {}
    teile = {t: v for t, v in s.items() if t != '_projekt' and isinstance(v, dict) and v.get('einlegeteile')}
    if not teile:
        return [uebersprungen(i, T[i], 'kein soll-Feld einlegeteile', Q) for i in ('EL1', 'EL4')]
    pr = profil(pdir)
    out, geplant = [], False
    for t, ts in teile.items():
        lage = _lage(pdir, t)
        for e in ts['einlegeteile']:
            n = e.get('name', '?')
            tit = lambda i: f'{T[i]} {n}'  # noqa: E731
            g = (lage or {}).get(n)
            if lage is None or g is None:
                out.append(uebersprungen('EL1', tit('EL1'), f'keine Lage aus cad_build ({n} als Platzhalter im Skript '
                                         'anlegen, dann cad_build)', Q, t))
                continue
            if e.get('einlegen', 'eingedruckt') == 'nachher':
                out.append(ergebnis('EL1', tit('EL1'), 'ok' if g['offen'] else 'fehler', quelle=Q, teil=t,
                                    hinweis='nachher einsetzen: Tasche nach oben offen' if g['offen'] else
                                    'nachher einsetzen geht nicht: Material ueber dem Teil - Tasche oeffnen oder eindrucken'))
                continue
            if g['offen']:
                out.append(ergebnis('EL1', tit('EL1'), 'warnung', quelle=Q, teil=t,
                                    hinweis='eingedruckt, aber nichts ueber dem Teil - Pause unnoetig, nachher einsetzen'))
                continue
            if not pr or pr['erste'] is None:
                out.append(uebersprungen('EL1', tit('EL1'), 'Schichtraster unbekannt (erst slicen oder _projekt.druck '
                                         '{erste_schicht_mm, schicht_mm})', Q, t))
                continue
            geplant = True
            nr, unten, oben = pausenschicht(g['decke_mm'], pr['erste'], pr['h'])
            luft = unten - g['z_oben_mm']
            boden_ok = g['z_unten_mm'] >= pr['erste'] - 1e-6
            schief = abs(unten - g['decke_mm']) > 0.02     # Decke nicht auf einer Schichtgrenze
            st = 'fehler' if luft < -1e-6 or not boden_ok else ('warnung' if luft < ABSTAND_MIN or schief else 'ok')
            out.append(ergebnis('EL1', tit('EL1'), st, wert=round(luft, 4), grenze=ABSTAND_MIN, einheit='mm', quelle=Q,
                                teil=t, daten={'schicht': nr, 'print_z': round(oben, 4), 'z_pause_mm': round(unten, 4)},
                                hinweis=f'Pause vor Schicht {nr} (print_z {oben:.3f} mm): gedruckt bis {unten:.3f} mm, '
                                        f'Teil-Oberkante {g["z_oben_mm"]:.3f} mm -> Luft {luft:+.3f} mm'
                                        + ('' if boden_ok else f'; Boden {g["z_unten_mm"]:.3f} mm < eine Schicht')
                                        + ('; Teil ragt ueber die Pausenschicht - Duese faehrt dagegen' if luft < 0 else '')
                                        + (f'; Decke {g["decke_mm"]:.3f} mm liegt nicht auf einer Schichtgrenze - im CAD '
                                           f'auf {unten:.3f} mm legen' if schief else '')
                                        + f' (Raster {pr["quelle"]})'))
            out.append(ergebnis('EL2', tit('EL2'), 'info', wert=g.get('spannweite_mm'), einheit='mm', quelle=Q, teil=t,
                                hinweis=f'Schicht {nr} ueberbrueckt {g.get("spannweite_mm")} mm frei ueber dem Teil'))
            if e.get('art') == 'magnet':
                if not isinstance(e.get('T_max_C'), (int, float)):
                    out.append(uebersprungen('EL3', tit('EL3'), 'T_max_C des Magneten fehlt (Datenblatt)', Q, t))
                elif pr.get('bett') is None:
                    out.append(uebersprungen('EL3', tit('EL3'), 'Betttemperatur unbekannt (Slicer-Profil)', Q, t))
                else:
                    ok = pr['bett'] < e['T_max_C']
                    out.append(ergebnis('EL3', tit('EL3'), 'ok' if ok else 'fehler', wert=pr['bett'], grenze=e['T_max_C'],
                                        einheit='C', quelle=Q, teil=t,
                                        hinweis=f'Bett {pr["bett"]} C gegen Magnet T_max {e["T_max_C"]} C (Datenblatt)' +
                                                ('' if ok else ' - Magnet verliert Magnetisierung: anderes Material/Profil '
                                                               'oder nachher einsetzen')))
    # EL4/EL5 gegen den G-Code
    if not geplant:
        out.append(uebersprungen('EL4', T['EL4'], 'keine eingedruckten Teile mit berechneter Pause', Q))
        return out
    plan = pausen(pdir, list(teile), pr)
    pfad, nur_binaer = _gcode(pdir)
    if not pfad:
        out.append(uebersprungen('EL4', T['EL4'], 'noch nicht gesliced' + (' (nur .bgcode - mit Einlegeteilen slicet '
                                 'slice_plate ASCII)' if nur_binaer else ''), Q))
        return out
    gp = gcode_pausen(open(pfad, encoding='utf-8', errors='replace').read())
    for p in plan:
        treffer = [x for x in gp if x['z_folgt'] is not None and abs(x['z_folgt'] - p['print_z']) < 0.0011 and x['m601']]
        out.append(ergebnis('EL4', f'{T["EL4"]} {p["print_z"]:.3f} mm', 'ok' if treffer else 'fehler', quelle=Q,
                            hinweis=(f'PAUSE_PRINT + M601 vor ;Z:{p["print_z"]:.3f} ({p["text"]})' if treffer else
                                     f'keine Pause vor ;Z:{p["print_z"]:.3f} im G-Code - NICHT drucken ({p["text"]})')))
        if treffer and treffer[0]['minuten'] is not None:
            out.append(ergebnis('EL5', f'{T["EL5"]} {p["print_z"]:.3f} mm', 'info', wert=treffer[0]['minuten'],
                                einheit='min', quelle=Q,
                                hinweis=f'Slicer-Schaetzung: Pause nach ca. {treffer[0]["minuten"]} min, danach noch '
                                        f'{treffer[0]["rest_min"]} min - dann einlegen: {p["text"]}'))
    extra = [x for x in gp if not any(x['z_folgt'] is not None and abs(x['z_folgt'] - p['print_z']) < 0.0011 for p in plan)]
    if extra:
        out.append(ergebnis('EL4', f'{T["EL4"]} ungeplant', 'warnung', quelle=Q,
                            hinweis=f'{len(extra)} Pause(n) im G-Code ohne Einlegeteil: {[x["z_folgt"] for x in extra]}'))
    return out
