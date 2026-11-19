"""FEM-Plausibilitaet und Werkstoff-Richtung (OCW_PRUEFKATALOG.md 3.2 und M7-M9).

Liest je Mechanik-Lastfall fem/<fall>.json + fem/<fall>.erg.json (+ fem/<fall>/<lastfall>.spannung.npz) und meldet:
  F20 Netzkonvergenz      Energie monoton, beobachtete Ordnung (Tet10: u ~ h^3, sigma ~ h^2, Energie ~ h^4)
  F21 Richardson          p = ln((f3-f2)/(f2-f1))/ln r, f_inf = f1 + (f1-f2)/(r^p-1), Fehlerband (GCI)
  F22 Singularitaet       sigma_max waechst bei jeder Verfeinerung, Energie konvergiert -> Kerbsingularitaet
  F23 Gleichgewicht       Summe Reaktionen + Summe Lasten = 0 (Kraft und Moment), < 0,5 %
      Energiebilanz      linear: 1/2 Int(eps C eps dV) = 1/2 F u (Clapeyron), < 0,5 %
  F24 Newton/Kontakt      Zeit 1,0 erreicht, Residuen, Durchdringung < 1 % Element und < 0,05 mm
  F25 Locking             nu > 0,45 -> Warnung
  M7  Tsai-Hill           transversal-isotrop mit Druckrichtung (Lastfall, Koerper, soll.json oder cad druck_drehung)
  M8  orthotrope Steifigkeit (nur Bericht, gerechnet wird in fem.py mit "orthotrop")
  M9  Infill              Kern unter den Perimetern: E*/E = rho^2, sigma*/sigma = 0,3 rho^1,5 (Gibson-Ashby);
                          ungesliced: Standardprofil 0.20mm SPEED @MK4IS 0.4 angenommen (hoechstens warnung), S < 1 fehler
Die FEM-Felder dafuer schreibt fem.mechanik (Gleichgewicht, Energie, Spannungsfeld, Newton, Kontakt, Konvergenz).
Aeltere Ergebnisse ohne diese Felder -> 'uebersprungen' mit Hinweis "fem_mech neu=true".
"""
import glob
import json
import math
import os
import re

import numpy as np

from . import ergebnis, soll, uebersprungen
from .. import realterme
from ..material import DRUCKSTOFFE, MATERIAL

Q_F20 = '2.094 L8 (MIT OCW): Konvergenzordnung, Energie monoton'
Q_F21 = '2.29 L10 (MIT OCW-Thema): Richardson; Fehlerband GCI nach Roache/Celik (extern)'
Q_F22 = 'abgeleitet aus 2.094 L8 (MIT OCW): Kerbsingularitaet'
Q_F23 = '2.092 (MIT OCW-Thema): Gleichgewicht der Reaktionen'
Q_F23_E = '2.092 (MIT OCW-Thema): Satz von Clapeyron, U = 1/2 F u (linear elastisch)'
Q_F24 = '2.094 L10 (MIT OCW): Newton-Abbruch; Penalty-Kontakt extern'
Q_F25 = '2.094 L8/L9 (MIT OCW): volumetrisches Locking'
Q_M7 = '16.20 Unit 4/5, 2.002 L7 (MIT OCW-Thema); Tsai-Hill/Hill 1948 (extern)'
Q_M8 = '16.20 Unit 4/5 (MIT OCW-Thema): transversal-isotrope Elastizitaet'
Q_M9 = '3.054 L4/5/7/17 (MIT OCW-Thema): Gibson-Ashby, Sandwich'
S_ZIEL = 2.0                                     # wie fem.mechanik-Bewertung
STANDARD_DRUCK = '0.20mm SPEED @MK4IS 0.4'       # Standard von slice_plate (befehle.py)
# Rueckfall, falls das Prusa-Bundle nicht lesbar ist: Werte dieses Profils (PrusaResearch.ini, aufgeloest 15.11.2026)
STANDARD_WERTE = {'fill': 15.0, 'perimeter': 2, 'breite_mm': 0.45, 'schicht_mm': 0.2, 'decklagen': 3}


# ---------------------------------------------------------------- Formeln (auch von fem.py genutzt)

def festigkeiten(mat):
    """X (XY), Z, Schub XY, Schub Z in MPa + Liste geschaetzter Werte. Schub fehlt -> sigma/sqrt(3) (Katalog M7)."""
    from .. import kennwerte
    m = MATERIAL[mat]
    X, Z = m['festigkeit_xy_MPa'], m['festigkeit_z_MPa']
    geschaetzt = []
    sxy = kennwerte.wert(mat, 'schub_xy_MPa')
    if sxy is None:
        sxy = X / math.sqrt(3)
        geschaetzt.append('Schub XY = X/sqrt(3)')
    sz = kennwerte.wert(mat, 'schub_z_MPa')
    if sz is None:
        sz = Z / math.sqrt(3)
        geschaetzt.append('Schub Z = Z/sqrt(3)')
    return X, Z, sxy, sz, geschaetzt


def tsai_hill_index(sig_lokal, X, Z, S_xy, S_z):
    """Versagensindex (>= 1 = Versagen) fuer lokale Voigt-Spannungen (..., 6) mit 3 = Druckrichtung.
    Groesserer Wert aus (a) Katalogform (s1^2 + s2^2 - s1 s2)/X^2 + s3^2/Z^2 + (t13^2 + t23^2)/S_z^2 + t12^2/S_xy^2
    und (b) vollem Hill-Kriterium mit X = Y (mit den Kreuztermen zu s3), beide in der Schichtebene drehinvariant:
    a = (s1+s2)/2, R^2 = ((s1-s2)/2)^2 + t12^2.
      (a) = a^2/X^2 + R^2 max(3/X^2, 1/S_xy^2) + s3^2/Z^2 + (t13^2+t23^2)/S_z^2
          (ungunstigste Lage in der Ebene; bei S_xy = X/sqrt(3) genau die Katalogform, bei S_xy < X/sqrt(3)
          konservativer als X fuer Zug in der Ebene, z. B. S_xy = X/2 -> Versagen bei 0,89 X)
      (b) = (a - s3)^2/Z^2 + R^2 (4/X^2 - 1/Z^2) + (t13^2+t23^2)/S_z^2   (Hill 1948, transversal-isotrop)"""
    s = np.asarray(sig_lokal, float)
    s1, s2, s3, t12, t13, t23 = np.moveaxis(s, -1, 0)
    a = 0.5 * (s1 + s2)
    R2 = (0.5 * (s1 - s2)) ** 2 + t12 ** 2
    aus = (t13 ** 2 + t23 ** 2) / S_z ** 2
    kat = a ** 2 / X ** 2 + R2 * max(3 / X ** 2, 1 / S_xy ** 2) + s3 ** 2 / Z ** 2 + aus
    hill = (a - s3) ** 2 / Z ** 2 + R2 * max(4 / X ** 2 - 1 / Z ** 2, 0.0) + aus
    return np.maximum(kat, hill)


def _basis(d):
    d = np.asarray(d, float) / np.linalg.norm(d)
    h = np.array([1.0, 0, 0]) if abs(d[0]) < 0.9 else np.array([0, 1.0, 0])
    e1 = np.cross(h, d)
    e1 /= np.linalg.norm(e1)
    return np.array([e1, np.cross(d, e1), d]).T


def drehe_voigt(s, d):
    """Globale Voigt-Spannungen (xx yy zz xy xz yz) in das lokale System mit 3 = d."""
    s = np.asarray(s, float)
    Q = _basis(d)
    T = np.empty(s.shape[:-1] + (3, 3))
    for I, (i, j) in enumerate([(0, 0), (1, 1), (2, 2), (0, 1), (0, 2), (1, 2)]):
        T[..., i, j] = T[..., j, i] = s[..., I]
    L = np.einsum('ai,...ab,bj->...ij', Q, T, Q)
    return np.stack([L[..., 0, 0], L[..., 1, 1], L[..., 2, 2], L[..., 0, 1], L[..., 0, 2], L[..., 1, 2]], -1)


def tsai_hill_sicherheit(tensor, mat, d):
    """tensor (M, P, 6) global -> (Sicherheit 1/sqrt(Index_max), Element, Punkt, info). Kein Druckstoff -> None."""
    if mat not in DRUCKSTOFFE or not len(tensor):
        return None, None, None, {}
    X, Z, sxy, sz, gesch = festigkeiten(mat)
    idx = tsai_hill_index(drehe_voigt(tensor, d), X, Z, sxy, sz)
    e, p = np.unravel_index(int(np.argmax(idx)), idx.shape)
    imax = float(idx[e, p])
    S = 1 / math.sqrt(imax) if imax > 0 else float('inf')
    return S, int(e), int(p), {'index_max': round(imax, 5), 'X_MPa': X, 'Z_MPa': Z, 'schub_xy_MPa': round(sxy, 2),
                               'schub_z_MPa': round(sz, 2), 'geschaetzt': gesch}


def richardson(h, f):
    """Richardson-Extrapolation fuer 2 oder 3 Netze (h gross -> klein egal, wird sortiert). Ungleiche Verhaeltnisse
    nach Celik (2008): p = |ln|e32/e21| + q(p)| / ln r21, q = ln((r21^p - s)/(r32^p - s)), s = sign(e32/e21).
    Rueckgabe dict: p, f_inf, gci_fein, monoton, oder None bei zu wenig/ungueltigen Werten."""
    pts = sorted((float(a), float(b)) for a, b in zip(h, f) if a is not None and b is not None)
    if len(pts) < 3:
        return None
    (h1, f1), (h2, f2), (h3, f3) = pts[:3]                  # 1 = feinstes Netz
    r21, r32 = h2 / h1, h3 / h2
    e21, e32 = f2 - f1, f3 - f2
    if e21 == 0 or e32 == 0:
        return {'p': None, 'f_inf': f1, 'gci_fein': 0.0, 'monoton': True, 'r21': r21, 'r32': r32,
                'hinweis': 'Werte gleich - konvergiert (oder Netz nicht veraendert)'}
    s = math.copysign(1.0, e32 / e21)
    p = abs(math.log(abs(e32 / e21))) / math.log(r21)
    for _ in range(100):
        try:
            q = math.log((r21 ** p - s) / (r32 ** p - s))
        except (ValueError, ZeroDivisionError):
            break
        p_neu = abs(math.log(abs(e32 / e21)) + q) / math.log(r21)
        if abs(p_neu - p) < 1e-10:
            p = p_neu
            break
        p = p_neu
    # Richtung: |e21| < |e32| -> konvergent (p > 0); sonst divergent (p < 0 markieren)
    if abs(e21) > abs(e32) and s > 0:
        p = -p
    monoton = s > 0
    if p > 0:
        f_inf = f1 + (f1 - f2) / (r21 ** p - 1)
        gci = 1.25 * abs((f1 - f2) / f1) / (r21 ** p - 1) if f1 else None
    else:
        f_inf, gci = None, None
    return {'p': p, 'f_inf': f_inf, 'gci_fein': gci, 'monoton': monoton, 'r21': r21, 'r32': r32}


# ---------------------------------------------------------------- Pruefungen

def _faelle(pdir):
    for sp in sorted(glob.glob(os.path.join(pdir, 'fem', '*.json'))):
        if sp.endswith('.erg.json'):
            continue
        fall = os.path.basename(sp)[:-5]
        try:
            spec = json.load(open(sp, encoding='utf-8'))
        except ValueError:
            continue
        ep = os.path.join(pdir, 'fem', fall + '.erg.json')
        erg = None
        if os.path.exists(ep):
            try:
                erg = json.load(open(ep, encoding='utf-8'))
            except ValueError:
                erg = None
        if erg is not None and 'lastfaelle' not in erg:
            continue                                   # Waerme-Fall
        if erg is None and not spec.get('lagerung'):
            continue                                   # nicht gerechneter Waerme-Fall
        yield fall, spec, erg


NEU = 'Ergebnis ohne die neuen Felder (vor der Erweiterung gerechnet) - fem_mech mit neu=true rechnen'


def pruefe(pdir):
    out = []
    so = soll(pdir)
    slicer = _slicer(pdir)
    faelle = list(_faelle(pdir))
    if not faelle:
        return [uebersprungen('F23', 'FEM-Plausibilitaet', 'keine Mechanik-Lastfaelle in fem/', Q_F23)]
    for fall, spec, erg in faelle:
        out += _f25(fall, spec)
        if erg is None:
            out.append(uebersprungen('F23', 'Gleichgewicht', 'Lastfall noch nicht gerechnet (fem_mech)', Q_F23, fall))
            continue
        nl = 'nichtlinear' in erg.get('loeser', '')
        for lf, r in erg['lastfaelle'].items():
            t = f'{fall}/{lf}'
            out.append(_f23(t, r))
            if not nl:
                out.append(_f23_energie(t, r))
            if nl:
                out += _f24(t, r, spec)
            fr = _realfaktor(pdir, so, spec, fall, lf)
            out.append(_m7(pdir, t, r, spec, so, fr))
            out.append(_m9(t, r, slicer or _standardprofil(), fr))
        if not nl:
            out.append(uebersprungen('F24', 'Newton/Kontakt-Konvergenz', 'linearer Lastfall - kein Newton', Q_F24, fall))
        out += _f20_22(fall, erg)
        out.append(_m8(fall, spec, erg))
    return out


def _f23(t, r):
    g = r.get('gleichgewicht')
    if not g:
        return uebersprungen('F23', 'Gleichgewicht', NEU, Q_F23, t)
    R, F = np.array(g['reaktion_N']), np.array(g['last_N'])
    MR, MF = np.array(g['reaktion_moment_Nmm']), np.array(g['last_moment_Nmm'])
    je = [np.linalg.norm(v) for v in g.get('reaktion_je_lager_N', [])]
    skala = max(np.linalg.norm(F), max(je, default=0.0), np.linalg.norm(R))
    if skala < 1e-12:
        return ergebnis('F23', 'Gleichgewicht', 'info', wert=0.0, grenze=0.5, einheit='%', quelle=Q_F23, teil=t,
                        hinweis='keine Last und keine Reaktion')
    fk = float(np.linalg.norm(R + F) / skala * 100)
    fm = float(np.linalg.norm(MR + MF) / (skala * g['laenge_mm']) * 100)
    w = max(fk, fm)
    stufe = 'ok' if w < 0.5 else ('warnung' if w < 5 else 'fehler')
    lost = np.linalg.norm(g.get('last_auf_lager_N', [0, 0, 0]))
    h = f'Kraft {fk:.3f} %, Moment {fm:.3f} % (bezogen auf {skala:.4g} N bzw. x Laenge {g["laenge_mm"]} mm)'
    if lost > 1e-9:
        h += f'; {lost:.4g} N der Last sitzen auf gesperrten Freiheitsgraden (gehen direkt ins Lager)'
    if stufe != 'ok':
        h += ' - Lasten/Lager/Auswahl pruefen'
    return ergebnis('F23', 'Gleichgewicht', stufe, wert=round(w, 4), grenze=0.5, einheit='%', quelle=Q_F23, teil=t,
                    hinweis=h, daten={'kraft_prozent': round(fk, 5), 'moment_prozent': round(fm, 5)})


def _f23_energie(t, r):
    """Clapeyron (linear): 1/2 Int(eps C eps) = 1/2 F u. Ein falsches oertliches Feld e kostet e^T K e > 0 ->
    erkennt Loeserfehler, die das Gleichgewicht der Reaktionen nicht zeigt (Befund I2)."""
    titel = 'Energiebilanz (Clapeyron)'
    eb = r.get('energiebilanz')
    if not eb:
        return uebersprungen('F23', titel, NEU, Q_F23_E, t)
    ab = abs(float(eb['abweichung'])) * 100
    gr = float(eb.get('grenze', 0.005)) * 100
    stufe = 'ok' if ab <= gr else 'fehler'
    h = (f'U_innen {eb["innen_Nmm"]:.6g} Nmm gegen F u/2 {eb["aussen_Nmm"]:.6g} Nmm'
         + (f' (nach {eb["neu_gerechnet"]}em Neulauf)' if eb.get('neu_gerechnet') else ''))
    if stufe != 'ok':
        h += ' - Verschiebungsfeld ist keine FE-Loesung: Loeserfehler, Ergebnis NICHT verwenden, neu rechnen'
    return ergebnis('F23', titel, stufe, wert=round(ab, 5), grenze=gr, einheit='%', quelle=Q_F23_E, teil=t,
                    hinweis=h)


def _f24(t, r, spec):
    out = []
    nw = r.get('newton')
    if not nw:
        out.append(uebersprungen('F24', 'Newton-Konvergenz', NEU, Q_F24, t))
    else:
        zeit = nw.get('zeit_erreicht')
        li = nw.get('letzte_iteration') or {}
        if zeit is None or zeit < 1 - 1e-6:
            stufe, h = 'fehler', f'Lastschritt nur bis Zeit {zeit} - Newton nicht konvergiert'
        elif nw.get('abbrueche', 0) > 0 or nw.get('iterationen_max', 0) > 12:
            stufe, h = 'info', 'konvergiert, aber mit Abbruechen/vielen Iterationen'
        else:
            stufe, h = 'ok', 'konvergiert'
        h += (f"; {nw.get('inkremente')} Inkremente, max {nw.get('iterationen_max')} Iterationen, letzte Korrektur "
              f"Weg {li.get('korrektur_weg_prozent')} %, Residuum Kraft {li.get('residuum_kraft_prozent')} %")
        if li.get('korrektur_weg_prozent') is not None and li['korrektur_weg_prozent'] > 1.0 and stufe == 'ok':
            stufe = 'warnung'
            h += ' (letzte Wegkorrektur > 1 %)'
        out.append(ergebnis('F24', 'Newton-Konvergenz', stufe, wert=zeit, grenze=1.0, quelle=Q_F24, teil=t,
                            hinweis=h, daten=nw))
    if spec.get('kontakt'):
        kt = r.get('kontakt')
        if not kt:
            out.append(uebersprungen('F24', 'Kontakt-Durchdringung', NEU, Q_F24, t))
        for i, k in enumerate(kt or []):
            d, h_el = k['durchdringung_max_mm'], k['element_mm']
            grenze = min(0.01 * h_el, 0.05)
            stufe = 'ok' if d <= grenze else 'warnung'
            h = (f'Durchdringung {d:.4g} mm, Element {h_el:.3g} mm, Grenze {grenze:.3g} mm '
                 f'({k["knoten_durchdrungen"]} von {k["slave_knoten"]} Slave-Knoten)')
            if stufe != 'ok':
                h += f' - Kontaktsteifigkeit ({k["steifigkeit_N_mm3"]} N/mm3) erhoehen, Kraft sonst zu klein'
            out.append(ergebnis('F24', f'Kontakt-Durchdringung Paar {i}', stufe, wert=d, grenze=grenze, einheit='mm',
                                quelle=Q_F24, teil=t, hinweis=h))
    return out


def _f25(fall, spec):
    nus = {k.get('material', '?').upper(): MATERIAL.get(k.get('material', '').upper(), {}).get('nu')
           for k in spec.get('koerper', [])}
    nus = {m: v for m, v in nus.items() if v is not None}
    if not nus:
        return [uebersprungen('F25', 'Locking', 'kein bekanntes Material', Q_F25, fall)]
    m, v = max(nus.items(), key=lambda x: x[1])
    stufe = 'warnung' if v > 0.45 else 'ok'
    h = f'groesstes nu = {v} ({m}); Tet10 (C3D10)'
    if stufe != 'ok':
        h += ' - fast inkompressibel (z. B. TPU): Locking, Spannungen unzuverlaessig; hybride Elemente/feiner'
    return [ergebnis('F25', 'Locking', stufe, wert=v, grenze=0.45, quelle=Q_F25, teil=fall, hinweis=h)]


def _f20_22(fall, erg):
    k = erg.get('konvergenz')
    if not k:
        g = 'keine Netzstudie - im Lastfall "konvergenz": {"faktoren": [1.0, 0.7, 0.5]} setzen'
        return [uebersprungen('F20', 'Netzkonvergenz', g, Q_F20, fall),
                uebersprungen('F21', 'Richardson-Fehlerband', g, Q_F21, fall),
                uebersprungen('F22', 'Singularitaet', g, Q_F22, fall)]
    out = []
    h = k['faktoren']
    i1 = h.index(1.0) if 1.0 in h else None
    for lf, d in k['lastfaelle'].items():
        res = bewerte_konvergenz(f'{fall}/{lf}', h, d, i1)
        if ((erg['lastfaelle'].get(lf) or {}).get('spannung_max') or {}).get('am_lager'):
            for x in res:
                if x['id'] == 'F22' and x['stufe'] in ('warnung', 'info'):
                    x['hinweis'] += ('; Spitze beruehrt eine Lagerflaeche - Lagerkante/Randbedingung, Lagerung '
                                     'realistischer (Flaeche, Nachgiebigkeit) modellieren')
        out += res
    return out


def bewerte_konvergenz(t, h, d, i_basis=None):
    """F20-F22 aus Reihen je Netz (h = Elementgroessen-Faktor). d: energie_Nmm, max_vonMises_MPa,
    verschiebung_lastrichtung_mm, kraft_weg_N (optional), max_verschiebung_mm, ort_max_mm.
    F21 nimmt die Verschiebung an der Lastflaeche, sonst die Kraft an der Wegvorgabe, sonst die max. Verschiebung."""
    out = []
    o = np.argsort(h)[::-1]                                 # grob -> fein
    hs = [h[i] for i in o]
    E = [d['energie_Nmm'][i] for i in o]
    S = [d['max_vonMises_MPa'][i] for i in o]
    ul = [d['verschiebung_lastrichtung_mm'][i] for i in o]
    kw = [(d.get('kraft_weg_N') or [None] * len(h))[i] for i in o]
    if all(v is not None for v in ul):
        groesse, u = 'Verschiebung', ul
        hin_u = ('Mittel der Lastflaeche; gleich verteilte Knotenlasten wirken wie Punktlasten (3D: Weg darunter '
                 'singulaer) - divergiert er, Federrate/Weg an der Lastflaeche als netzabhaengig ansehen')
    elif all(v is not None for v in kw):
        groesse, u, hin_u = 'Kraft', kw, 'Reaktion an der Wegvorgabe'
    else:
        groesse, u, hin_u = 'Verschiebung', [d['max_verschiebung_mm'][i] for i in o], 'max. Verschiebung'
    ib = None if i_basis is None else list(o).index(i_basis)
    n = len(hs)
    # F20: Energie monoton, beobachtete Ordnung
    if n < 2 or any(v is None for v in E):
        out.append(uebersprungen('F20', 'Netzkonvergenz', 'weniger als 2 Netze oder keine Energie (NLGEOM)',
                                 Q_F20, t))
        rE = None
    else:
        dE = np.diff(E)
        mono = bool(np.all(dE >= -1e-12 * abs(E[-1]))) or bool(np.all(dE <= 1e-12 * abs(E[-1])))
        rE = richardson(hs, E)
        aend = abs(E[-1] - E[-2]) / abs(E[-1]) * 100 if E[-1] else 0.0
        if not mono and aend >= 1.0:
            stufe, hin = 'warnung', 'Energie nicht monoton - Netze nicht verschachtelt oder Modellfehler'
        elif not mono:
            stufe, hin = 'info', 'Energie nicht monoton, aber Aenderung < 1 % (Netzrauschen, Netze nicht verschachtelt)'
        elif rE and rE['p'] is not None and rE['p'] < 1.0 and aend > 1.0:
            stufe, hin = 'warnung', f'beobachtete Ordnung Energie p = {rE["p"]:.2f} (erwartet ~4) - nicht asymptotisch'
        else:
            stufe, hin = 'ok', 'Energie monoton'
        hin += f'; Aenderung letzte Verfeinerung {aend:.3f} %'
        if rE and rE['p'] is not None:
            hin += f', p_E = {rE["p"]:.2f}'
        out.append(ergebnis('F20', 'Netzkonvergenz', stufe, wert=round(aend, 4), grenze=1.0, einheit='%',
                            quelle=Q_F20, teil=t, hinweis=hin, daten={'h': hs, 'energie_Nmm': E}))
    # F21: Richardson fuer Verschiebung (5 %) und Spannung (10 %); Fehler des Hauptergebnisses (Faktor 1)
    for name, reihe, grenze in ((groesse, u, 5.0), ('Spannung', S, 10.0)):
        zus = ('; ' + hin_u) if name == groesse else ''
        rr = richardson(hs, reihe)
        if rr is None:
            out.append(uebersprungen('F21', f'Richardson {name}', 'mindestens 3 Netze noetig', Q_F21, t))
            continue
        if rr['f_inf'] is None or not rr['monoton']:
            f1, f2 = reihe[-1], reihe[-2]
            rel = abs(f1 - f2) / abs(f1) * 100 if f1 else 0.0
            if rel < grenze / 10:                      # Netzrauschen: Ordnung nicht bestimmbar, Aenderung klein
                fehler = rel / (math.sqrt(hs[-2] / hs[-1]) - 1)   # konservativ mit p = 0,5
                out.append(ergebnis('F21', f'Richardson {name}', 'info' if fehler < grenze else 'warnung',
                                    wert=round(fehler, 3), grenze=grenze, einheit='%', quelle=Q_F21, teil=t,
                                    hinweis=('nicht monoton' if not rr['monoton'] else f'kein asymptotischer Verlauf '
                                             f'(p = {rr["p"]:.2f})') + f', letzte Aenderung nur {rel:.3f} % '
                                             '(Netzrauschen); Fehler mit p = 0,5 abgeschaetzt' + zus,
                                    daten={'h': hs, 'werte': reihe}))
                continue
            out.append(ergebnis('F21', f'Richardson {name}', 'warnung', quelle=Q_F21, teil=t,
                                hinweis=('nicht monoton (oszillierend)' if not rr['monoton'] else
                                         f'divergiert (p = {rr["p"]:.2f})') + ' - kein Fehlerband moeglich' + zus,
                                daten={'h': hs, 'werte': reihe}))
            continue
        fb = reihe[ib] if ib is not None else reihe[-1]
        fehler = abs(fb - rr['f_inf']) / abs(rr['f_inf']) * 100 if rr['f_inf'] else 0.0
        stufe = 'ok' if fehler < grenze else 'warnung'
        out.append(ergebnis('F21', f'Richardson {name}', stufe, wert=round(fehler, 3), grenze=grenze, einheit='%',
                            quelle=Q_F21, teil=t,
                            hinweis=(f'p = {rr["p"]:.2f}, ' if rr['p'] is not None else 'Werte gleich, ') +
                                    f'extrapoliert {rr["f_inf"]:.5g}, Hauptnetz {fb:.5g}, '
                                    f'GCI fein {100 * (rr["gci_fein"] or 0):.2f} %' + zus,
                            daten={'h': hs, 'werte': reihe, 'p': rr['p'], 'f_inf': rr['f_inf']}))
    # F22: sigma waechst bei jeder Verfeinerung, Energie konvergiert
    if n < 2:
        out.append(uebersprungen('F22', 'Singularitaet', 'weniger als 2 Netze', Q_F22, t))
        return out
    waechst = all(b > a * 1.001 for a, b in zip(S, S[1:]))
    rs = richardson(hs, S)
    e_konv = rE is not None and rE['p'] is not None and rE['p'] > 0 or (
        E[-1] is not None and E[-2] is not None and E[-1] and abs(E[-1] - E[-2]) / abs(E[-1]) < 0.02)
    zuwachs = (S[-1] / S[-2] - 1) * 100 if S[-2] else 0.0
    singulaer = waechst and e_konv and ((rs is not None and (rs['p'] is None or rs['p'] < 0.5)) or
                                        (rs is None and zuwachs > 10))
    ort = d['ort_max_mm'][o[-1]] if d.get('ort_max_mm') else None
    if singulaer:
        out.append(ergebnis('F22', 'Singularitaet', 'warnung', wert=round(zuwachs, 2), grenze=10, einheit='%',
                            quelle=Q_F22, teil=t,
                            hinweis=f'sigma_max waechst mit jeder Verfeinerung (+{zuwachs:.1f} % zuletzt), Energie '
                                    f'konvergiert -> Kerbsingularitaet bei {ort}: dieser Wert gilt nicht fuer die '
                                    'Sicherheit; Innenradius >= 1 mm vorsehen und neu rechnen',
                            daten={'h': hs, 'sigma_MPa': S, 'ort_mm': ort}))
    elif waechst:
        out.append(ergebnis('F22', 'Singularitaet', 'info', wert=round(zuwachs, 2), grenze=10, einheit='%',
                            quelle=Q_F22, teil=t,
                            hinweis=f'sigma_max steigt noch (+{zuwachs:.1f} %), konvergiert aber (p_sigma = '
                                    f'{rs["p"]:.2f})' if rs and rs['p'] is not None else
                                    f'sigma_max steigt noch (+{zuwachs:.1f} %)',
                            daten={'h': hs, 'sigma_MPa': S, 'ort_mm': ort}))
    else:
        out.append(ergebnis('F22', 'Singularitaet', 'ok', wert=round(zuwachs, 2), grenze=10, einheit='%',
                            quelle=Q_F22, teil=t, hinweis='sigma_max waechst nicht unbegrenzt',
                            daten={'h': hs, 'sigma_MPa': S}))
    return out


def _lade_feld(r):
    p = r.get('spannungsfeld')
    if not p or not os.path.exists(p):
        return None
    try:
        return dict(np.load(p, allow_pickle=False))
    except (OSError, ValueError):
        return None


def _druck_drehung(pdir, teil):
    """Schichtnormale aus out/<teil>.pruefung.json "druck_drehung" (cad_build), wie mechanik.Kontext.druckrichtung."""
    pp = os.path.join(pdir or '', 'out', teil + '.pruefung.json')
    if not pdir or not os.path.exists(pp):
        return None
    try:
        d = json.load(open(pp, encoding='utf-8')).get('druck_drehung')
        if d is None:
            return None
        from .. import geometrie
        return [round(float(x), 6) for x in geometrie.baurichtung(tuple(d))], d
    except Exception:  # noqa: BLE001 - unlesbar -> wie fehlend
        return None


def _druckrichtung(spec, so, name, k, pdir=None):
    kp = spec.get('koerper', [])
    if k < len(kp) and kp[k].get('druckrichtung') is not None:
        return kp[k]['druckrichtung'], 'Lastfall-Koerper'
    if spec.get('druckrichtung') is not None:
        return spec['druckrichtung'], 'Lastfall'
    if k < len(kp) and 'step' in kp[k]:
        teil = os.path.splitext(os.path.basename(kp[k]['step']))[0]
        if (so.get(teil) or {}).get('druckrichtung') is not None:
            return so[teil]['druckrichtung'], f'soll.json[{teil}]'
    if (so.get(name) or {}).get('druckrichtung') is not None:
        return so[name]['druckrichtung'], f'soll.json[{name}]'
    kandidaten = [name]
    if k < len(kp) and 'step' in kp[k]:
        kandidaten.insert(0, os.path.splitext(os.path.basename(kp[k]['step']))[0])
    for teil in kandidaten:
        r = _druck_drehung(pdir, teil)
        if r is not None:
            return r[0], f'out/{teil}.pruefung.json druck_drehung {list(r[1])}'
    return None, None


def _vektor(d):
    if isinstance(d, str):
        v = np.zeros(3)
        v['xyz'.index(d.strip().lstrip('+-').lower())] = 1.0
        return v
    v = np.asarray(d, float).reshape(3)
    n = np.linalg.norm(v)
    if not n > 0:
        raise ValueError(d)
    return v / n


def _realfaktor(pdir, so, spec, fall, lf):
    """Abminderung und Sicherheitsziel je Lastfall wie fem.bewertung_mech (realterme + mb2/sicherheit.py):
    -> funktion(material) = (f, S_ziel, angenommen, text)."""
    from .. import fem, realterme, sicherheit
    try:
        k0 = realterme.kontext(pdir, soll=so)
    except Exception:  # noqa: BLE001
        k0 = realterme.kontext(None)
    dl = fem.dauerlast_je_lastfall(spec, [lf], so, fall).get(lf)
    pj = (so or {}).get('_projekt', {})

    def je(mat):
        kk = {**k0, 'material': mat, 'dauerlast': dl}
        tt, a_t = [], False
        if kk.get('T_teil_C') is None:
            kk['T_teil_C'], tt, a_t = realterme.teil_temperatur(kk)
        f, terme, ang = realterme.abminderung('festigkeit', kk)
        S, st = sicherheit.ziel(pj, None, mat, 'z')
        return f, S, ang or a_t, realterme.hinweis(tt + terme) + f'; Ziel {st}'
    return je


def _m7(pdir, t, r, spec, so, fr=None):
    f = _lade_feld(r)
    if f is None:
        return uebersprungen('M7', 'Tsai-Hill (Druckrichtung)', 'kein Spannungsfeld (.npz) - ' + NEU, Q_M7, t)
    namen, mats = [str(x) for x in f['namen']], [str(x) for x in f['mats']]
    best, fehlend = None, []
    for k in np.unique(f['koerper']):
        k = int(k)
        dr, woher = _druckrichtung(spec, so, namen[k], k, pdir)
        if dr is None:
            fehlend.append(namen[k])
            continue
        sel = f['koerper'] == k
        try:
            v = _vektor(dr)
        except (ValueError, IndexError, TypeError, ZeroDivisionError):
            fehlend.append(f'{namen[k]} (Druckrichtung {dr!r} ungueltig)')
            continue
        S, e, p, info = tsai_hill_sicherheit(f['tensor'][sel], mats[k], v)
        if S is not None and (best is None or S < best[0]):
            am = bool(f['am_lager'][sel][e]) if 'am_lager' in f else None
            best = (S, namen[k], mats[k], dr, woher, info, f['schwerpunkt'][sel][e].tolist(), am)
    if best is None:
        return uebersprungen('M7', 'Tsai-Hill (Druckrichtung)',
                             f'Druckrichtung unbekannt fuer {fehlend} (Lastfall "druckrichtung", soll.json oder '
                             'cad_build mit druck -> out/<teil>.pruefung.json druck_drehung)', Q_M7, t)
    S, name, mat, dr, woher, info, ort, am = best
    f_r, S_Z, ang_r, txt_r = fr(mat) if fr else (1.0, S_ZIEL, True, 'ohne Realterme (angenommen)')
    S_roh, S = S, S / f_r
    stufe = realterme.deckel('ok' if S >= S_Z else ('warnung' if S >= 1.0 else 'fehler'), ang_r)
    h = (f'{name} ({mat}), Druckrichtung {dr} aus {woher}, Ort ~{[round(v, 2) for v in ort]}; '
         f'X {info["X_MPa"]}, Z {info["Z_MPa"]}, Schub XY {info["schub_xy_MPa"]}, Z {info["schub_z_MPa"]} MPa')
    if info['geschaetzt']:
        h += ' (geschaetzt: ' + ', '.join(info['geschaetzt']) + ')'
    if am:
        h += '; Ort beruehrt eine Lagerflaeche - kann Randbedingungs-Artefakt sein, Lagerung pruefen (Wert gilt trotzdem)'
    if fehlend:
        h += f'; ohne Druckrichtung nicht bewertet: {fehlend}'
    h += f'; roh {S_roh:.3g} / f {f_r:.2f} = wirksam {S:.3g}; {txt_r}'
    return ergebnis('M7', 'Tsai-Hill (Druckrichtung)', stufe, wert=round(S, 3), grenze=round(S_Z, 3), quelle=Q_M7, teil=t,
                    hinweis=h, daten={'index_max': info['index_max'], 'S_roh': round(S_roh, 4), 'f': round(f_r, 4),
                                      'S_ziel': round(S_Z, 3), 'angenommen': bool(ang_r)})


def _m8(fall, spec, erg):
    if not spec.get('orthotrop'):
        return uebersprungen('M8', 'Orthotrope Steifigkeit', 'nicht angefordert (Lastfall "orthotrop": true + '
                             '"druckrichtung") - isotrop gerechnet', Q_M8, fall)
    o = erg.get('orthotrop')
    if o:
        return ergebnis('M8', 'Orthotrope Steifigkeit', 'info', quelle=Q_M8, teil=fall,
                        hinweis='transversal-isotrop gerechnet (CalculiX ENGINEERING CONSTANTS + ORIENTATION)',
                        daten=o)
    hin = '; '.join(h for h in erg.get('hinweise', []) if 'orthotrop' in h) or NEU
    return ergebnis('M8', 'Orthotrope Steifigkeit', 'warnung', quelle=Q_M8, teil=fall,
                    hinweis='angefordert, aber isotrop gerechnet: ' + hin)


def _slicer(pdir):
    """Fuellgrad, Perimeter, Linienbreite, Decklagen aus print/slice.json (+ aufgeloeste Konfiguration)."""
    p = os.path.join(pdir, 'print', 'slice.json')
    if not os.path.exists(p):
        return None
    try:
        s = json.load(open(p, encoding='utf-8'))
    except ValueError:
        return None
    st = s.get('stats', {})
    cfg = {}
    if s.get('config') and os.path.exists(s['config']):
        for line in open(s['config'], encoding='utf-8', errors='replace'):
            m = re.match(r'\s*([a-z_]+)\s*=\s*(.*?)\s*$', line)
            if m:
                cfg[m.group(1)] = m.group(2)

    def zahl(v, d=None):
        try:
            return float(str(v).rstrip('%'))
        except (TypeError, ValueError):
            return d
    fill = zahl(st.get('fill_density', cfg.get('fill_density')))
    duese = zahl(st.get('nozzle_diameter', cfg.get('nozzle_diameter')), 0.4) or 0.4
    w = cfg.get('perimeter_extrusion_width') or cfg.get('extrusion_width') or '0'
    breite = duese * zahl(w, 0) / 100 if str(w).endswith('%') else zahl(w, 0)
    if not breite:
        breite = 1.125 * duese                        # PrusaSlicer-Automatik fuer Perimeter
    schicht = zahl(st.get('layer_height', cfg.get('layer_height')), 0.2) or 0.2
    perim = int(zahl(s.get('perimeter') or cfg.get('perimeters'), 2) or 2)
    oben = int(zahl(cfg.get('top_solid_layers'), 0) or 0)
    unten = int(zahl(cfg.get('bottom_solid_layers'), 0) or 0)
    return {'fill': fill, 'perimeter': perim, 'breite_mm': breite, 'schicht_mm': schicht,
            'decklagen': min([x for x in (oben, unten) if x] or [0]), 'quelle': p}


_STD = []


def _standardprofil():
    """Noch nicht gesliced: Fuellgrad/Perimeter des Standardprofils annehmen (Audit 15.11.2026, M9) statt zu
    ueberspringen. Ergebnis traegt 'angenommen' -> hoechstens warnung."""
    if _STD:
        return dict(_STD[0])
    q = f'Standardprofil {STANDARD_DRUCK} (noch nicht gesliced, angenommen)'
    w = dict(STANDARD_WERTE)
    try:
        from .. import slicer
        c = slicer.resolve('print', STANDARD_DRUCK)

        def zahl(v, d):
            try:
                return float(str(v).rstrip('%'))
            except (TypeError, ValueError):
                return d
        breite = str(c.get('perimeter_extrusion_width') or c.get('extrusion_width') or '')
        w = {'fill': zahl(c.get('fill_density'), w['fill']), 'perimeter': int(zahl(c.get('perimeters'), 2)),
             'breite_mm': (0.4 * zahl(breite, 0) / 100 if breite.endswith('%') else zahl(breite, 0)) or 0.45,
             'schicht_mm': zahl(c.get('layer_height'), 0.2),
             'decklagen': int(min([x for x in (zahl(c.get('top_solid_layers'), 0), zahl(c.get('bottom_solid_layers'), 0))
                                   if x] or [0]))}
    except Exception:  # noqa: BLE001 - Bundle fehlt: dokumentierte Profilwerte
        q += ' - Werte aus STANDARD_WERTE (Bundle nicht lesbar)'
    w.update({'quelle': q, 'angenommen': True})
    _STD.append(w)
    return dict(w)


def _m9(t, r, sl, fr=None):
    if sl is None or sl.get('fill') is None:
        sl = _standardprofil()
    ang = bool(sl.get('angenommen'))
    vor = f'{sl["quelle"]}: ' if ang else ''
    rho = sl['fill'] / 100
    if rho >= 0.999:
        return ergebnis('M9', 'Infill-Abminderung', 'ok', wert=sl['fill'], einheit='%', quelle=Q_M9, teil=t,
                        hinweis='100 % Fuellung - Vollmaterial wie in der FEM')
    f = _lade_feld(r)
    if f is None:
        return ergebnis('M9', 'Infill-Abminderung', 'warnung', wert=sl['fill'], einheit='%', quelle=Q_M9, teil=t,
                        hinweis=vor + f'Fuellung {sl["fill"]:.0f} %, FEM rechnet Vollmaterial; Kern nicht pruefbar '
                                '(kein Spannungsfeld - ' + NEU + ')')
    schale = sl['perimeter'] * sl['breite_mm']
    if sl['decklagen']:
        schale = min(schale, sl['decklagen'] * sl['schicht_mm'])
    E_f, s_f = rho ** 2, 0.3 * rho ** 1.5
    from ..material import MATERIAL as M
    kern = f['tiefe'] > schale
    v = f['volumen']
    anteil = float(v[kern].sum() / v.sum()) if v.sum() > 0 else 0.0
    daten = {'fill_prozent': sl['fill'], 'schale_mm': round(schale, 3), 'E_faktor': round(E_f, 4),
             'festigkeit_faktor': round(s_f, 4), 'kern_volumenanteil': round(anteil, 4), 'profil_angenommen': ang}
    if not kern.any():
        return ergebnis('M9', 'Infill-Abminderung', realterme.deckel('ok', ang), wert=0.0, quelle=Q_M9, teil=t,
                        daten=daten, hinweis=vor + f'alle Elemente innerhalb der Schale {schale:.2f} mm '
                                                   '(Perimeter/Decklagen) - Vollmaterial gilt')
    vm = np.sqrt(0.5 * sum((f['tensor'][..., i] - f['tensor'][..., j]) ** 2 for i, j in ((0, 1), (1, 2), (2, 0)))
                 + 3 * (f['tensor'][..., 3] ** 2 + f['tensor'][..., 4] ** 2 + f['tensor'][..., 5] ** 2)).max(1)
    mats = [str(x) for x in f['mats']]
    S_min, wo = None, None
    for k in np.unique(f['koerper'][kern]):
        sel = kern & (f['koerper'] == k)
        sk = float(vm[sel].max())
        sig = s_f * M[mats[int(k)]]['festigkeit_z_MPa']
        S = sig / sk if sk > 0 else float('inf')
        if S_min is None or S < S_min:
            S_min, wo = S, (str(f['namen'][int(k)]), sk, sig, mats[int(k)])
    daten.update({'sigma_kern_max_MPa': round(wo[1], 4), 'festigkeit_kern_MPa': round(wo[2], 4)})
    m9_mat = wo[3]
    f_r, S_Z, ang_r, txt_r = fr(m9_mat) if (fr and m9_mat) else (1.0, S_ZIEL, True, 'ohne Realterme (angenommen)')
    daten.update({'S_roh': round(S_min, 4) if S_min != float('inf') else None, 'f': round(f_r, 4),
                  'S_ziel': round(S_Z, 3), 'angenommen': bool(ang or ang_r)})
    S_min = S_min / f_r if S_min != float('inf') else S_min
    stufe = realterme.deckel('ok' if S_min >= S_Z else 'warnung' if S_min >= 1.0 else 'fehler', ang or ang_r)
    h = vor + (f'Fuellung {sl["fill"]:.0f} %, Schale {schale:.2f} mm; Kern ({100 * anteil:.0f} % Volumen) traegt bis '
         f'{wo[1]:.3g} MPa gegen 0,3 rho^1,5 sigma_Z = {wo[2]:.3g} MPa ({wo[0]})')
    if anteil > 0.05:
        h += f'; Steifigkeit dort nur {E_f:.3g} x E -> Federrate/Verschiebung der FEM zu guenstig'
    h += f'; wirksam nach f {f_r:.2f}; {txt_r}'
    if S_min < S_Z:
        h += ' - voll drucken (Fuellung/Perimeter erhoehen) oder FEM-Kern abmindern'
    return ergebnis('M9', 'Infill-Abminderung', stufe, wert=round(S_min, 3) if S_min != float('inf') else None,
                    grenze=round(S_Z, 3), quelle=Q_M9, teil=t, hinweis=h, daten=daten)
