"""Toleranz, Montage, Druckgenauigkeit (OCW_PRUEFKATALOG.md Abschnitt 3.5, T1-T6).

Prozessmodell des MK4 je Merkmalart ('aussen', 'aussen_bett' = Aussenmass in den ersten Schichten (Elefantenfuss),
'bohrung' = stehende Bohrung, 'bohrung_liegend', 'z'):
    gedruckt = k * CAD + b,  Streuung sigma
aus projects/kalibrierkoerper/messung.json (lineare Ausgleichsrechnung ueber alle Messwerte der Merkmalart), falls
ausgefuellt. Sonst vorlaeufige Standardwerte (STANDARD), sigma mal realterme.abminderung('streuung') (0,05 -> 0,10 mm)
- jede Pruefung weist das aus und meldet dann hoechstens 'warnung' (realterme.deckel), ausser der Mittelwert liegt schon
ausserhalb (fehler). Jede Kette (T2) bekommt automatisch ein Waermeglied alpha L dT (dT aus _projekt.T_min_C/T_max_C
gegen 23 C, sonst +/-20 K angenommen).

Eingaben (alle optional):
- je Teil (soll.json) bzw. _projekt:
  toleranzen [{"name", "nenn_mm", "tol_mm" | "plus_mm"/"minus_mm", "art", "cad_mm"}]   - T1, T4
  toleranzketten [{"name", "glieder": [{"name", "nenn_mm" (mit Vorzeichen), "tol_mm", "art", "cad_mm"}],
                   "spalt_min_mm", "spalt_max_mm"}]                                         - T2
  steckungen [{"name", "D_mm" (Loch), "d_mm" (Zapfen), "fase_mm", "tiefe_mm", "mu", "versatz_mm"}] - T3
  wand_gleichmaessig: true | {"raster_mm": 2}  (Strahltest am STEP, kostet Sekunden)       - T5
  fehlerbudget {"ziel_mm", "posten": [{"name", "fehler_mm"} | {"winkel_mrad"|"winkel_grad", "abstand_mm"} |
                {"L_mm", "dT_K", "material"|"alpha_1_K"} | {"druck": "<art>", "nenn_mm", "kompensiert"}]} - T6
- 'cad_mm' = Mass im CAD, wenn es vom Funktionsmass 'nenn_mm' abweicht (Vorhalt schon eingebaut).
"""
import math
import os

from .. import kennwerte as kw
from .. import realterme as rt
from . import ergebnis, soll as lade_soll, uebersprungen
from .dauer import kennwert, material_von, teile, temperatur, T_MONTAGE_C

MB2_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MESSUNG = os.path.join(MB2_ROOT, 'projects', 'kalibrierkoerper', 'messung.json')
ARTEN = ('aussen', 'aussen_bett', 'bohrung', 'bohrung_liegend', 'z')

# Vorlaeufig, NICHT gemessen: uebliche FDM-Werte 0,4-mm-Duese (Aussenmasse leicht zu gross durch Linienbreite,
# Bohrungen zu klein durch Polygon/Nachfliessen, liegende Bohrungen zusaetzlich oben durchhaengend);
# z: Schichtquantisierung 0,2 mm -> sigma = 0,2/sqrt(12) = 0,058.
STANDARD = {
    'aussen': {'k': 1.0, 'b': 0.05, 'sigma': 0.05},
    # erste Schichten: Elefantenfuss +0,25 mm aussen trotz Slicer-Kompensation (Audit Scheinsicherheit 15.11.2026)
    'aussen_bett': {'k': 1.0, 'b': 0.05 + 0.25, 'sigma': 0.05},
    'bohrung': {'k': 1.0, 'b': -0.15, 'sigma': 0.05},
    'bohrung_liegend': {'k': 1.0, 'b': -0.20, 'sigma': 0.07},
    'z': {'k': 1.0, 'b': 0.0, 'sigma': 0.058},
}
Q_STANDARD = 'vorlaeufige MK4-Standardstreuung (Annahme, nicht gemessen - Kalibrierkoerper drucken und messen)'
ALPHA_UNBEKANNT = 1e-4      # 1/K, groesstes der Druckstoffe (ASA), wenn kennwerte.py nichts hat
DT_ANNAHME_K = 20.0         # Waermeglied ohne T_min_C/T_max_C: +/-20 K um 23 C
Q_CPK = '2.830J L8 (OCW)'
Q_KETTE = '2.875 cls8/9 (OCW)'
Q_FASE = '2.875 cls3 (OCW; Grenze abgeleitet)'
Q_SCHWIND = '2.008 L03 (OCW, Spritzguss-Werte) + MK4-Messung'
Q_WAND = '2.008 L03 (OCW)'
Q_BUDGET = '2.75 Topic 4, 2.76 L10 (OCW)'
CPK_ZIEL = 1.33


# ---------------------------------------------------------------- Messung und Prozessmodell

def _json(p):
    import json
    try:
        return json.load(open(p, encoding='utf-8'))
    except (OSError, ValueError):
        return None


def messung_material(material, pfad=None):
    """Messblock eines Materials aus messung.json (None, wenn fehlt)."""
    m = _json(pfad or MESSUNG) or {}
    b = m.get(material)
    return b if isinstance(b, dict) else None


def _werte(liste):
    """[(nenn, ist)] aus [{"nenn_mm", "ist_mm": [..]}]."""
    pkt = []
    for e in liste or []:
        if not isinstance(e, dict) or e.get('nenn_mm') is None:
            continue
        ist = e.get('ist_mm')
        ist = ist if isinstance(ist, list) else ([] if ist is None else [ist])
        pkt += [(float(e['nenn_mm']), float(x)) for x in ist if x is not None]
    return pkt


def ausgleich(pkt):
    """Lineare Ausgleichsrechnung ist = k nenn + b. Gibt {'k', 'b', 'sigma', 'n', 'sigma_gemessen'} oder None.
    Nur ein Nennmass -> k = 1, b = Mittelwert. sigma nur bei mindestens 2 Freiheitsgraden."""
    n = len(pkt)
    if n == 0:
        return None
    xs = sorted({x for x, _ in pkt})
    if len(xs) >= 2 and n >= 3:
        mx = sum(x for x, _ in pkt) / n
        my = sum(y for _, y in pkt) / n
        sxx = sum((x - mx) ** 2 for x, _ in pkt)
        k = sum((x - mx) * (y - my) for x, y in pkt) / sxx
        b = my - k * mx
        p = 2
    else:
        k = 1.0
        b = sum(y - x for x, y in pkt) / n
        p = 1
    dof = n - p
    sig = math.sqrt(sum((y - (k * x + b)) ** 2 for x, y in pkt) / dof) if dof >= 2 else None
    return {'k': k, 'b': b, 'sigma': sig, 'n': n, 'sigma_gemessen': sig is not None}


def modell(material, art, pfad=None):
    """Prozessmodell {'k', 'b', 'sigma', 'quelle', 'vorlaeufig'} fuer eine Merkmalart."""
    if art not in STANDARD:
        return None
    std = dict(STANDARD[art])
    if art != 'z':      # z ist Schichtquantisierung (h/sqrt 12), kein Streuungsmodell
        f, terme, _ = rt.abminderung('streuung', {})
        std['sigma'] = STANDARD[art]['sigma'] * f
        std['_streuung'] = f'sigma {STANDARD[art]["sigma"]} x {f:g} = {std["sigma"]:.3f} ({"; ".join(terme)})'
    else:
        std['_streuung'] = ''
    mb = messung_material(material, pfad) if material else None
    a = ausgleich(_werte((mb or {}).get(art)))
    if a is None:
        # Schwindung nur in der Schichtebene; Z wird schichtweise angefahren (Quantisierung, kein Faktor)
        sw = kw.wert(material, 'schwindung') if material in kw.KENNWERTE and art != 'z' else None
        q = Q_STANDARD + (f'; {std["_streuung"]}' if std['_streuung'] else '')
        std.pop('_streuung')
        if sw is not None:
            return {**std, 'k': 1.0 - sw, 'quelle': f'{q}; Schwindung {sw} aus kennwerte.py', 'vorlaeufig': True}
        return {**std, 'quelle': q, 'vorlaeufig': True}
    q = f'messung.json {material}.{art} ({a["n"]} Werte)'
    if not a['sigma_gemessen']:
        q += ', sigma aus Standard (zu wenige Werte)' + (f'; {std["_streuung"]}' if std['_streuung'] else '')
    return {'k': a['k'], 'b': a['b'], 'sigma': a['sigma'] if a['sigma_gemessen'] else std['sigma'], 'quelle': q,
            'vorlaeufig': not a['sigma_gemessen']}


def cp_cpk(usl, lsl, mu, sigma):
    """C_p = (USL - LSL)/(6 sigma); C_pk = min(USL - mu, mu - LSL)/(3 sigma)."""
    return (usl - lsl) / (6 * sigma), min(usl - mu, mu - lsl) / (3 * sigma)


def kette(glieder):
    """glieder: [(nenn mit Vorzeichen, T (+/-), versatz mit Vorzeichen)] -> dict mit WC/RSS min/max.
    Systematischer Versatz geht linear ein, die Toleranzen als Summe (WC) bzw. Wurzel der Quadratsumme (RSS)."""
    nenn = sum(g[0] for g in glieder)
    vers = sum(g[2] for g in glieder)
    wc = sum(abs(g[1]) for g in glieder)
    rss = math.sqrt(sum(g[1] ** 2 for g in glieder))
    m = nenn + vers
    return {'nenn': nenn, 'versatz': vers, 'wc_min': m - wc, 'wc_max': m + wc, 'rss_min': m - rss, 'rss_max': m + rss}


# ---------------------------------------------------------------- Pruefungen

def _grenzen(t):
    n = float(t['nenn_mm'])
    if 'tol_mm' in t:
        return n + abs(t['tol_mm']), n - abs(t['tol_mm'])
    if 'plus_mm' in t or 'minus_mm' in t:
        return n + float(t.get('plus_mm', 0)), n - abs(float(t.get('minus_mm', 0)))
    return None


def _t1_t4(teil, material, t):
    """Prozessfaehigkeit (T1) und Schwindungsvorhalt (T4) eines Toleranzmasses."""
    name = t.get('name', '?')
    art = t.get('art')
    md = modell(material, art)
    if md is None:
        return [uebersprungen('T1', f'Prozessfaehigkeit {name}', f'art {art!r} unbekannt ({", ".join(ARTEN)})', Q_CPK, teil)]
    gr = _grenzen(t)
    if gr is None:
        return [uebersprungen('T1', f'Prozessfaehigkeit {name}', 'keine Toleranz (tol_mm oder plus_mm/minus_mm)', Q_CPK, teil)]
    usl, lsl = gr
    nenn = float(t['nenn_mm'])
    cad = float(t.get('cad_mm', nenn))
    mu = md['k'] * cad + md['b']
    cp, cpk = cp_cpk(usl, lsl, mu, md['sigma'])
    vorl = ' VORLAEUFIG' if md['vorlaeufig'] else ''
    if cpk >= CPK_ZIEL:
        st = 'ok'
    elif cpk < 0:
        # erwarteter Mittelwert liegt schon ausserhalb der Toleranz: auch mit vorlaeufigem Modell ein Fehler
        # (Befund T1-vorlaeufig-deckel)
        st = 'fehler'
    elif md['vorlaeufig'] or cpk >= 1.0:
        st = 'warnung'
    else:
        st = 'fehler'
    st = rt.deckel(st, md['vorlaeufig'])
    out = [ergebnis('T1', f'Prozessfaehigkeit {name}', st, wert=round(cpk, 2), grenze=CPK_ZIEL, einheit='C_pk',
                    quelle=Q_CPK, teil=teil,
                    hinweis=f'{art}: CAD {cad} -> erwartet {mu:.3f} +/- {md["sigma"]:.3f} (1 sigma), Grenzen '
                            f'{lsl:.3f}..{usl:.3f}; C_p {cp:.2f}. Modell aus {md["quelle"]}{vorl}. '
                            f'Unter 1,33 Toleranz aufweiten oder Vorhalt (T4)')]
    # T4: Vorhalt, damit der Mittelwert auf dem Nennmass liegt
    soll_cad = (nenn - md['b']) / md['k']
    abw = mu - nenn
    tol = (usl - lsl) / 2
    st4 = 'ok' if abs(abw) <= 0.5 * tol else 'warnung'
    out.append(ergebnis('T4', f'Schwindungsvorhalt {name}', st4, wert=round(abw, 3), grenze=round(0.5 * tol, 3),
                        einheit='mm', quelle=Q_SCHWIND, teil=teil,
                        hinweis=f'gedruckt = {md["k"]:.4f} CAD {md["b"]:+.3f}; erwartete Abweichung {abw:+.3f} mm. '
                                f'Fuer Nennmass {nenn} im CAD {soll_cad:.3f} mm zeichnen (Vorhalt {soll_cad - nenn:+.3f}).'
                                f'{vorl}'))
    return out


def waermeglied(glieder_alpha, T_min, T_max):
    """Waermeglied einer Kette: [(nenn mit Vorzeichen, alpha)] -> (T_waerme (+/-), dT_warm, dT_kalt, angenommen).
    Spaltaenderung je Kelvin = Sum nenn_i alpha_i; als symmetrische Toleranz der groessere Betrag aus warm und kalt
    gegen Montage 23 C. Fehlt eine Seite, gilt 23 +/- 20 K fuer diese Seite (angenommen)."""
    ang = T_min is None or T_max is None
    dT_w = (T_max - T_MONTAGE_C) if T_max is not None else DT_ANNAHME_K
    dT_k = (T_min - T_MONTAGE_C) if T_min is not None else -DT_ANNAHME_K
    je_K = sum(n * a for n, a in glieder_alpha)
    return max(abs(je_K * dT_w), abs(je_K * dT_k)), dT_w, dT_k, ang


def _alpha(pdir, s, material):
    """(alpha, text) - kennwerte (Projekt-Ueberschreibung zuerst), sonst ALPHA_UNBEKANNT angenommen."""
    a, q = kennwert(pdir, material, 'alpha_1_K', s) if material else (None, None)
    if a is None:
        return ALPHA_UNBEKANNT, f'alpha {material or "?"} unbekannt -> {ALPHA_UNBEKANNT:g} angenommen'
    return a, f'alpha {material} {a:g}'


def _t2(teil, material, k, pdir=None, s=None):
    name = k.get('name', '?')
    titel = f'Toleranzkette {name}'
    s = s if s is not None else {}
    pj = s.get('_projekt', {})
    gl, txt, vorl = [], [], False
    ga, atxt = [], set()
    for g in k.get('glieder') or []:
        n = float(g['nenn_mm'])
        art = g.get('art', 'fremd')
        sgn = 1.0 if n >= 0 else -1.0
        if art in STANDARD:
            md = modell(material, art)
            vorl |= md['vorlaeufig']
            cad = abs(float(g.get('cad_mm', abs(n))))
            vers = sgn * (md['k'] * cad + md['b'] - abs(n))
            T = max(abs(g['tol_mm']), 3 * md['sigma']) if g.get('tol_mm') is not None else 3 * md['sigma']
            a, at = (float(g['alpha_1_K']), f'alpha {g.get("name", "?")} {g["alpha_1_K"]:g}')                 if g.get('alpha_1_K') is not None else _alpha(pdir, s, g.get('material', material))
        elif g.get('tol_mm') is not None:
            vers, T = 0.0, abs(g['tol_mm'])
            # Fremdteil: alpha aus dem Glied, sonst aus kennwerte (material, z. B. FR4), sonst 0 (dehnt nicht mit -
            # fuer Kunststoff gegen Platine/Metall die unguenstige Seite)
            if g.get('alpha_1_K') is not None:
                a, at = float(g['alpha_1_K']), f'alpha {g.get("name", "?")} {g["alpha_1_K"]:g}'
            elif g.get('material') and kw.wert(str(g['material']).upper(), 'alpha_1_K') is not None:
                a = kw.wert(str(g['material']).upper(), 'alpha_1_K')
                at = f'alpha {g["material"]} {a:g}'
            else:
                a, at = 0.0, f'{g.get("name", "?")} ohne alpha -> 0'
        else:
            return uebersprungen('T2', titel, f'Glied {g.get("name")}: art {art!r} ohne tol_mm', Q_KETTE, teil)
        ga.append((n, a))
        atxt.add(at)
        gl.append((n, T, vers))
        txt.append(f'{g.get("name", "?")} {n:+.2f} +/-{T:.3f} Versatz {vers:+.3f}')
    if not gl:
        return uebersprungen('T2', titel, 'keine glieder', Q_KETTE, teil)
    # Waermeglied automatisch (Befund Scheinsicherheit 15.11.2026: Waermedehnung stand nur in D8)
    Tw, dT_w, dT_k, w_ang = waermeglied(ga, pj.get('T_min_C'), pj.get('T_max_C'))
    if Tw > 0:
        gl.append((0.0, Tw, 0.0))
        txt.append(f'Waerme +/-{Tw:.3f} (Sum nenn alpha, dT {dT_w:+.0f}/{dT_k:+.0f} K'
                   + (' angenommen, T_min_C/T_max_C fehlt' if w_ang else '') + f'; {", ".join(sorted(atxt))})')
    vorl |= w_ang or any('angenommen' in x for x in atxt)
    r = kette(gl)
    smin = k.get('spalt_min_mm', 0.4)
    smax = k.get('spalt_max_mm')
    if r['rss_min'] < smin or (smax is not None and r['rss_max'] > smax):
        st = 'fehler'
    elif r['wc_min'] < smin or (smax is not None and r['wc_max'] > smax):
        st = 'warnung'
    else:
        st = 'ok'
    st = rt.deckel(st, vorl)
    return ergebnis('T2', titel, st, wert=round(r['rss_min'], 4), grenze=smin, einheit='mm', quelle=Q_KETTE, teil=teil,
                    daten={k2: round(v, 4) for k2, v in r.items()},
                    hinweis=f'Nenn {r["nenn"]:.3f}, systematischer Versatz {r["versatz"]:+.3f} (linear); min WC '
                            f'{r["wc_min"]:.3f} / RSS {r["rss_min"]:.3f}, max WC {r["wc_max"]:.3f} / RSS '
                            f'{r["rss_max"]:.3f}. Gedruckte Glieder: T = max(tol, 3 sigma). ' + '; '.join(txt)
                            + (' VORLAEUFIG (MK4 nicht gemessen bzw. Temperatur angenommen) - hoechstens warnung'
                               if vorl else ''))


def _t3(pdir, teil, material, st_, s):
    name = st_.get('name', '?')
    titel = f'Verkeilen/Fase {name}'
    D, d = st_.get('D_mm'), st_.get('d_mm')
    if D is None or d is None:
        return [uebersprungen('T3', titel, 'D_mm und d_mm noetig', Q_FASE, teil)]
    out = []
    c = (D - d) / D
    mb, md_ = modell(material, 'bohrung'), modell(material, 'aussen')
    spiel_druck = (mb['k'] * D + mb['b']) - (md_['k'] * d + md_['b'])
    vorl = ' VORLAEUFIG' if mb['vorlaeufig'] or md_['vorlaeufig'] else ''
    if D - d <= 0 or spiel_druck <= 0:
        out.append(ergebnis('T3', titel + ' Spiel', 'fehler', wert=round(spiel_druck, 3), grenze=0.0, einheit='mm',
                            quelle=Q_FASE, teil=teil,
                            hinweis=f'Spiel CAD {D - d:.3f}, nach Druck erwartet {spiel_druck:.3f} mm -> klemmt '
                                    f'(Pressitz: M14).{vorl}'))
    fmin = max(D - d, 0.4, st_.get('versatz_mm', 0.0))
    f = st_.get('fase_mm')
    if f is None:
        out.append(ergebnis('T3', titel + ' Fase', 'warnung', wert=None, grenze=round(fmin, 3), einheit='mm',
                            quelle=Q_FASE, teil=teil, hinweis=f'keine fase_mm angegeben; mindestens {fmin:.2f} mm '
                                                               '(c D, 0,4 mm, Versatz)'))
    else:
        out.append(ergebnis('T3', titel + ' Fase', 'ok' if f >= fmin else 'warnung', wert=f, grenze=round(fmin, 3),
                            einheit='mm', quelle=Q_FASE, teil=teil,
                            hinweis=f'c = (D - d)/D = {c:.4f}; Fase >= max(c D, 0,4 mm, Versatz)'))
    mu = st_.get('mu')
    q = 'soll.json'
    if mu is None:
        mu, q = kennwert(pdir, material, 'mu', s)
    if mu is None:
        out.append(uebersprungen('T3', titel + ' Verkeilen', f'Reibwert mu fuer {material} fehlt', Q_FASE, teil))
    else:
        grenze = mu * D
        tiefe = st_.get('tiefe_mm')
        if tiefe is None:
            out.append(ergebnis('T3', titel + ' Verkeilen', 'info', grenze=round(grenze, 3), einheit='mm',
                                quelle=Q_FASE, teil=teil, hinweis=f'Verkeilgefahr bei Einstecktiefe < mu D = '
                                                                   f'{grenze:.2f} mm (mu {mu} aus {q})'))
        else:
            out.append(ergebnis('T3', titel + ' Verkeilen', 'ok' if tiefe >= grenze else 'warnung', wert=tiefe,
                                grenze=round(grenze, 3), einheit='mm', quelle=Q_FASE, teil=teil,
                                hinweis=f'Zweipunktkontakt kann verkeilen, solange Einstecktiefe < mu D (mu {mu} aus '
                                        f'{q}); bis dahin gerade fuehren'))
    return out


def _t5(pdir, teil, opt):
    titel = 'Gleichmaessige Wand'
    step = os.path.join(pdir, 'out', teil + '.step')
    if not os.path.exists(step):
        return uebersprungen('T5', titel, f'out/{teil}.step fehlt (cad_build)', Q_WAND, teil)
    from build123d import import_step
    from .. import cad
    raster = opt.get('raster_mm', 2.0) if isinstance(opt, dict) else 2.0
    d = cad.wand_und_spalt(import_step(step), raster=raster)
    alle = sorted(p[3] for p in d['wand'])
    if len(alle) < 10:
        return uebersprungen('T5', titel, 'zu wenige Wandmesspunkte', Q_WAND, teil)
    # Strahlen laengs durch eine Wand (Stirnflaeche -> Boden) messen die Wandhoehe, nicht die Dicke: nur Treffer bis
    # 3 x P10 zaehlen (dickste Wand darf das Dreifache der duennen sein, sonst ist es ohnehin ungleichmaessig)
    w = [x for x in alle if x <= 3 * alle[len(alle) // 10]]
    p10, p50, p90 = w[len(w) // 10], w[len(w) // 2], w[(9 * len(w)) // 10]
    streu = max(p50 - p10, p90 - p50) / p50
    st = 'ok' if streu <= 0.10 else 'info'
    return ergebnis('T5', titel, st, wert=round(streu, 3), grenze=0.10, einheit='-', quelle=Q_WAND, teil=teil,
                    hinweis=f'Wand P10/P50/P90 {p10:.2f}/{p50:.2f}/{p90:.2f} mm ({len(w)} von {len(alle)} Strahlen <= 3 x P10, Raster {raster} mm); '
                            'Hinweis ab +/-10-20 % (Schwindungsunterschiede, Verzug)')


def _t6(pdir, teil, material, fb, s):
    titel = 'Fehlerbudget'
    ziel = fb.get('ziel_mm')
    if not ziel:
        return uebersprungen('T6', titel, 'fehlerbudget.ziel_mm fehlt', Q_BUDGET, teil)
    zuf, sys_, txt, fehlt, vorl_b = [], 0.0, [], [], False
    for p in fb.get('posten') or []:
        n = p.get('name', '?')
        if 'fehler_mm' in p:
            e = abs(p['fehler_mm'])
        elif 'abstand_mm' in p and ('winkel_mrad' in p or 'winkel_grad' in p):
            th = p['winkel_mrad'] * 1e-3 if 'winkel_mrad' in p else math.radians(p['winkel_grad'])
            e = abs(th * p['abstand_mm'])
            n += ' (Abbe)'
        elif 'L_mm' in p:
            a = p.get('alpha_1_K')
            if a is None:
                a, _ = kennwert(pdir, p.get('material', material), 'alpha_1_K', s) if (p.get('material') or material) \
                    else (None, None)
            dT = p.get('dT_K')
            if dT is None:
                t = temperatur(pdir, teil, s)
                dT = (t['T_max_C'] - T_MONTAGE_C) if t else None
            if a is None or dT is None:
                fehlt.append(n)
                continue
            e = abs(a * p['L_mm'] * dT)
            n += ' (Waerme)'
        elif 'druck' in p:
            md = modell(material, p['druck'])
            if md is None:
                fehlt.append(n)
                continue
            e = 3 * md['sigma']
            vorl_b |= md['vorlaeufig']
            if not p.get('kompensiert'):
                L = float(p.get('nenn_mm', 0.0))
                sys_ += abs(md['k'] * L + md['b'] - L)
            n += ' (Druck 3 sigma)'
        else:
            fehlt.append(n)
            continue
        zuf.append(e)
        txt.append(f'{n} {e:.4f}')
    if not zuf and not sys_:
        return uebersprungen('T6', titel, 'keine auswertbaren posten', Q_BUDGET, teil)
    rss = sys_ + math.sqrt(sum(e * e for e in zuf))
    wc = sys_ + sum(zuf)
    st = 'ok' if rss <= ziel / 4 else ('warnung' if rss <= ziel else 'fehler')
    if fehlt and st == 'ok':
        st = 'warnung'
    st = rt.deckel(st, vorl_b)
    return ergebnis('T6', titel, st, wert=round(rss, 5), grenze=round(ziel / 4, 4), einheit='mm', quelle=Q_BUDGET,
                    teil=teil, hinweis=f'RSS {rss:.4f} (WC {wc:.4f}, systematisch {sys_:.4f}) gegen Ziel {ziel} - '
                                       f'Konzept soll 4x besser sein. ' + '; '.join(txt)
                                       + (f'; NICHT bewertet: {fehlt}' if fehlt else '')
                                       + ('; Druckstreuung VORLAEUFIG (nicht gemessen)' if vorl_b else ''))


def _ueberhang_bruecke(material):
    """Info: am MK4 gemessene Grenzen fuer Ueberhang und Bruecke (Katalog 3.5, nicht OCW)."""
    mb = messung_material(material) if material else None
    titel = 'MK4-Grenzen Ueberhang/Bruecke'
    q = 'Kalibrierkoerper MK4 (extern, nicht OCW)'
    if not mb:
        return uebersprungen('T-UB', titel, f'messung.json ohne {material}', q)
    ue = [e for e in mb.get('ueberhang') or [] if e.get('ok') is not None]
    br = [e for e in mb.get('bruecke') or [] if e.get('ok') is not None]
    if not ue and not br:
        return uebersprungen('T-UB', titel, 'Ueberhang/Bruecke noch nicht bewertet (messung.json)', q)
    u = max((e['winkel_grad'] for e in ue if e['ok']), default=None)
    b = max((e['spannweite_mm'] for e in br if e['ok']), default=None)
    return ergebnis('T-UB', titel, 'info', quelle=q, hinweis=f'{material}: Ueberhang ok bis {u} Grad (von senkrecht), '
                                                             f'Bruecke ok bis {b} mm - Sichtkontrolle danach richten')


def pruefe(pdir):
    s = lade_soll(pdir)
    pj = s.get('_projekt', {})
    erg = []
    alle = teile(pdir)
    mat_proj = pj.get('material')
    if not mat_proj:
        ms = [material_von(pdir, t, s)[0] for t in alle]
        mat_proj = next((m for m in ms if m), None)
    gefunden = False
    quellen = [('_projekt', pj, mat_proj)] + [(t, i['soll'], material_von(pdir, t, s)[0]) for t, i in alle.items()]
    for teil, ts, material in quellen:
        tn = None if teil == '_projekt' else teil
        for t in ts.get('toleranzen') or []:
            gefunden = True
            erg += _t1_t4(tn, material, t)
        for k in ts.get('toleranzketten') or []:
            gefunden = True
            erg.append(_t2(tn, material, k, pdir, s))
            for g in k.get('glieder') or []:      # gedruckte Kettenglieder mit Toleranz auch einzeln (T1)
                if g.get('art') in STANDARD and g.get('tol_mm') is not None:
                    erg += _t1_t4(tn, material, {**g, 'nenn_mm': abs(float(g['nenn_mm'])),
                                                 'name': f'{k.get("name", "?")}: {g.get("name", "?")}'})
        for st_ in ts.get('steckungen') or []:
            gefunden = True
            erg += _t3(pdir, tn, material, st_, s)
        if ts.get('wand_gleichmaessig') and tn:
            gefunden = True
            erg.append(_t5(pdir, tn, ts['wand_gleichmaessig']))
        if ts.get('fehlerbudget'):
            gefunden = True
            erg.append(_t6(pdir, tn, material, ts['fehlerbudget'], s))
    if not gefunden:
        erg.append(uebersprungen('T1', 'Toleranzen', 'keine toleranzen/toleranzketten/steckungen/fehlerbudget in '
                                 'soll.json', Q_CPK))
    if mat_proj:
        mb = modell(mat_proj, 'aussen')
        gem = not mb['quelle'].startswith(Q_STANDARD)
        erg.append(ergebnis('T4', f'Schwindung {mat_proj} (MK4)', 'info',
                            wert=round(1 - mb['k'], 5) if gem or mb['k'] != 1.0 else None, einheit='-',
                            quelle=Q_SCHWIND, hinweis=f'gedruckt = {mb["k"]:.4f} CAD {mb["b"]:+.3f} mm (Aussenmasse) '
                                                      f'aus {mb["quelle"]}'))
        erg.append(_ueberhang_bruecke(mat_proj))
    return erg
