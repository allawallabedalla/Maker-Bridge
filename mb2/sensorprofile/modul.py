"""Sensorprofil ``modul_digital`` (seit 19.11.2026): gekauftes, digital auslesbares Messmodul (I2C/SPI/UART) fuer eine
beliebige Messgroesse - Durchfluss, Druck, Feuchte, Gas, Beschleunigung ...

Warum ein eigenes Profil: Bei einem Modul steckt die ganze analoge Kette im Bauteil. Pruefbar ist dann, ob die
Datenblattangaben des Moduls plus Einbau, Temperatur und Mittelung das Ziel erreichen - nicht ADC und Referenz.
Alle Zahlen kommen aus dem Projekt (Datenblatt mit Seite/Tabelle in ``_herkunft``), nie aus diesem Profil.

soll.json ``_projekt.messkette``:
    {"profil": "modul_digital", "einheit": "ml/min", "messbereich": {"min": 0, "max": 40},
     "ziel_U": 1.0, "ziel_aufloesung": 0.1, "k": 2, "dT_K": 10, "messrate_Hz": 2, "mittelung": 4,
     "arbeitspunkte": [5, 20],                                    # optional, zusaetzlich zu min/Mitte/max
     "modul": {"name": "...", "bereich_min": 0, "bereich_max": 80,
               "genauigkeit": {"abs": 0.2, "rel_messwert": 0.05, "rel_endwert": 0.0, "kombination": "summe|max",
                               "verteilung": "rechteck"},           # Datenblatt-Grenzwert -> Rechteck (u = G/sqrt3)
               "wiederholbarkeit": 0.05,                            # 1 sigma, Messgroesse
               "rauschen": 0.03,                                    # RMS je Einzelmessung (sonst wiederholbarkeit)
               "aufloesung": 0.01,                                  # kleinster Schritt (LSB)
               "tk_rel_je_K": 0.001,                                # relativ zum Messwert je K Abweichung von T_kal
               "messzeit_s": 0.1},                                  # Dauer einer Einzelmessung
     "modus": "ab_werk|kalibriert", "kalibrierung": {"u_kal": 0.1},  # kalibriert: ersetzt die Datenblatt-Genauigkeit
     "zusatz": [{"name": "Einbau/Medium", "wert": 0.1, "verteilung": "rechteck"}]}
Pruefungen: MK1 Budget (schlechtester Arbeitspunkt), MK2 Aufloesung, MK3 Messbereich im Modulbereich, MK5 Zeitbudget.
Herkunft je Feld ``messkette.modul.<feld>``: schwach/offen -> hoechstens warnung (wie rtd).
"""
import math

from ..pruefungen import ergebnis, uebersprungen
from ..pruefungen.messkette import budget

Q = 'mb2/sensorprofile/modul.py (gekauftes Messmodul, GUM-Budget aus Datenblattangaben)'
T = {'MK1': 'Unsicherheitsbudget Messkette', 'MK2': 'Rauschbegrenzte Aufloesung', 'MK3': 'Messbereich im Modulbereich',
     'MK5': 'Zeitbudget Messrate'}


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _punkte(mk):
    mb = mk.get('messbereich') or {}
    lo, hi = mb.get('min'), mb.get('max')
    if not (_num(lo) and _num(hi)):
        return []
    p = {float(lo), float(hi), (float(lo) + float(hi)) / 2}
    p |= {float(x) for x in mk.get('arbeitspunkte') or [] if _num(x)}
    return sorted(p)


def budget_bei(mk, x, hk=lambda f: None):
    """Budget beim Messwert x. Fehlt ein Pflichtwert, steht er in 'fehlt' und U ist None."""
    m = mk.get('modul') or {}
    g = m.get('genauigkeit') or {}
    zeilen, fehlt = [], []
    if mk.get('modus') == 'kalibriert':
        u = (mk.get('kalibrierung') or {}).get('u_kal')
        if _num(u):
            zeilen.append({'name': 'Kalibrierung (u_kal)', 'wert': float(u), 'verteilung': 'u',
                           'herkunft': hk('kalibrierung.u_kal')})
        else:
            fehlt.append('kalibrierung.u_kal')
    else:
        teile = [(g.get('abs'), 1.0), (g.get('rel_messwert'), abs(x)),
                 (g.get('rel_endwert'), abs(float(m.get('bereich_max') or 0)))]
        if not any(_num(v) for v, _ in teile):
            fehlt.append('modul.genauigkeit')
        else:
            werte = [float(v) * f for v, f in teile if _num(v)]
            G = max(werte) if g.get('kombination') == 'max' else sum(werte)
            zeilen.append({'name': 'Modul-Genauigkeit (Datenblatt)', 'wert': G, 'verteilung': g.get('verteilung', 'rechteck'),
                           'herkunft': hk('modul.genauigkeit'), **({'k': g['k']} if _num(g.get('k')) else {})})
    n = max(1, int(mk.get('mittelung') or 1))
    s = m.get('wiederholbarkeit')
    if _num(s):
        zeilen.append({'name': f'Wiederholbarkeit / sqrt({n})', 'wert': float(s) / math.sqrt(n), 'verteilung': 'u',
                       'herkunft': hk('modul.wiederholbarkeit')})
    else:
        fehlt.append('modul.wiederholbarkeit')
    q = m.get('aufloesung')
    if _num(q):
        zeilen.append({'name': 'Aufloesung q/sqrt12', 'wert': float(q) / 2, 'verteilung': 'rechteck',
                       'herkunft': hk('modul.aufloesung')})
    else:
        fehlt.append('modul.aufloesung')
    tk, dT = m.get('tk_rel_je_K'), mk.get('dT_K')
    if _num(tk) and _num(dT):
        zeilen.append({'name': 'Temperaturgang', 'wert': float(tk) * abs(x) * abs(float(dT)), 'verteilung': 'rechteck',
                       'herkunft': hk('modul.tk_rel_je_K')})
    else:                          # auch kalibriert: Abweichung von der Kalibriertemperatur bleibt
        fehlt.append('modul.tk_rel_je_K' if not _num(tk) else 'dT_K')
    for z in mk.get('zusatz') or []:
        zeilen.append(dict(z, herkunft=hk(f'zusatz.{z.get("name")}')))
    b = budget(zeilen, k=float(mk.get('k', 2.0)), einheit=mk.get('einheit', ''))
    b['fehlt'] = sorted(set(b['fehlt']) | set(fehlt))
    if b['fehlt']:
        b['U'] = b['u_c'] = None
    for z in b['beitraege']:
        z['herkunft'] = next((y.get('herkunft') for y in zeilen if y['name'] == z['name']), None)
    return b


def _schwach(b):
    return sorted({z['name'] for z in b['beitraege'] if (z.get('herkunft') or 'offen')
                   in ('offen', 'geschaetzt', 'angenommen', None)})


def pruefe(mk, herkunft_klasse):
    e = mk.get('einheit', '')
    hk = lambda f: herkunft_klasse(f)  # noqa: E731
    pk = _punkte(mk)
    if not pk:
        g = 'messkette.messbereich {min, max} fehlt'
        return [uebersprungen(i, T[i], g, Q) for i in ('MK1', 'MK2', 'MK3')]
    out = []
    # MK1
    tab = [(x, budget_bei(mk, x, hk)) for x in pk]
    fehlt = sorted({f for _, b in tab for f in b['fehlt']})
    ziel = mk.get('ziel_U')
    if fehlt:
        out.append(uebersprungen('MK1', T['MK1'], f'Profil modul_digital: Werte fehlen fuer {", ".join(fehlt)} '
                                 '(Datenblatt mit Seite/Tabelle eintragen, keine Annahme)', Q))
    else:
        x_w, b_w = max(tab, key=lambda t: t[1]['U'])
        schwach = _schwach(b_w)
        txt = (f'U = {b_w["k"]:g}*{b_w["u_c"]:.4g} = {b_w["U"]:.4g} {e} bei {x_w:g} {e} (schlechtester Punkt); '
               + ', '.join(f'{z["name"]} {z["beitrag"]:.3g}' for z in sorted(b_w['beitraege'], key=lambda z: -z['beitrag']))
               + f'. {b_w["korrelationen_hinweis"]}')
        if schwach:
            txt += f'; Herkunft schwach/offen: {", ".join(schwach)} (angenommen)'
        daten = {'schlechtester_punkt': x_w, 'beitraege': b_w['beitraege'], 'u_c': b_w['u_c'], 'k': b_w['k'],
                 'U': b_w['U'], 'je_punkt': [{'x': x, 'U': b['U']} for x, b in tab]}
        if not _num(ziel):
            out.append(uebersprungen('MK1', T['MK1'], 'messkette.ziel_U fehlt; ' + txt, Q))
        else:
            st = 'fehler' if b_w['U'] > ziel else ('warnung' if schwach else 'ok')
            out.append(ergebnis('MK1', T['MK1'], st, wert=b_w['U'], grenze=ziel, einheit=e, quelle=Q, hinweis=txt,
                                daten=daten))
    # MK2
    m = mk.get('modul') or {}
    n = max(1, int(mk.get('mittelung') or 1))
    sig = m.get('rauschen') if _num(m.get('rauschen')) else m.get('wiederholbarkeit')
    q = m.get('aufloesung')
    za = mk.get('ziel_aufloesung')
    if not (_num(sig) and _num(q)):
        out.append(uebersprungen('MK2', T['MK2'], 'modul.rauschen/wiederholbarkeit oder modul.aufloesung fehlt', Q))
    else:
        w = max(float(q), 6.6 * float(sig) / math.sqrt(n))
        txt = f'max(q {q:g}, 6,6 sigma/sqrt({n}) = {6.6 * float(sig) / math.sqrt(n):.4g}) = {w:.4g} {e}'
        if not _num(za):
            out.append(uebersprungen('MK2', T['MK2'], f'messkette.ziel_aufloesung fehlt ({txt})', Q))
        else:
            schw = [f for f in ('modul.aufloesung', 'modul.rauschen' if _num(m.get('rauschen')) else 'modul.wiederholbarkeit')
                    if (hk(f) or 'offen') in ('offen', 'geschaetzt', 'angenommen')]
            st = 'fehler' if w > za else ('warnung' if schw else 'ok')
            out.append(ergebnis('MK2', T['MK2'], st, wert=round(w, 6), grenze=za, einheit=e, quelle=Q,
                                hinweis=txt + (f'; Herkunft schwach/offen: {", ".join(schw)}' if schw else '')))
    # MK3
    lo, hi = m.get('bereich_min'), m.get('bereich_max')
    mb = mk['messbereich']
    if not (_num(lo) and _num(hi)):
        out.append(uebersprungen('MK3', T['MK3'], 'modul.bereich_min/bereich_max fehlt (Datenblatt)', Q))
    else:
        ok = lo <= mb['min'] and mb['max'] <= hi
        out.append(ergebnis('MK3', T['MK3'], 'ok' if ok else 'fehler', wert=[mb['min'], mb['max']], grenze=[lo, hi],
                            einheit=e, quelle=Q, hinweis=f'Messbereich {mb["min"]} ... {mb["max"]} {e} gegen Modul '
                                                         f'{lo} ... {hi} {e}' + ('' if ok else ' - ausserhalb: Modul passt nicht')))
    # MK5
    tm, rate = m.get('messzeit_s'), mk.get('messrate_Hz')
    if _num(tm) and _num(rate) and rate > 0:
        t = n * float(tm)
        out.append(ergebnis('MK5', T['MK5'], 'ok' if t <= 1 / rate else 'fehler', wert=round(t, 6),
                            grenze=round(1 / rate, 6), einheit='s', quelle=Q,
                            hinweis=f'{n} x {tm} s = {t:.3g} s je Wert gegen 1/{rate} Hz'))
    else:
        out.append(uebersprungen('MK5', T['MK5'], 'modul.messzeit_s oder messrate_Hz fehlt', Q))
    return out
