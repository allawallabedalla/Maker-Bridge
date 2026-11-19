"""Stroemung in Kanaelen und Leitungen, analytisch (FL1-FL4, seit 19.11.2026). Fluessigkeiten und Gase (inkompressibel
gerechnet, bei Gasen nur bis ~5 % Druckaenderung sinnvoll).

Warum analytisch: In duennen Kanaelen (Mikrofluidik, Schlaeuche, Duesen) ist die Stroemung fast immer laminar. Dann
gilt Hagen-Poiseuille exakt - eine CFD-Rechnung bringt keinen Gewinn. FL1 prueft genau diese Voraussetzung; ist sie
verletzt, rechnet FL2 nicht weiter (statt falsch weiter).

soll.json ``_projekt.stroemung`` (oder je Teil):
    {"medium": {"name": "Wasser 20 C", "viskositaet_Pa_s": .., "dichte_kg_m3": ..},   # mit _herkunft belegen
     "kanaele": [{"name": "Messkanal", "d_mm": 1.0, "L_mm": 20,                     # rund; rechteckig: b_mm + h_mm
                  "Q_min_ml_min": 0.5, "Q_max_ml_min": 40,
                  "dp_max_Pa": 5000,                                               # zulaessiger Druckverlust
                  "einlauf_vor_sensor_mm": 15,                                    # gerade Strecke vor dem Sensor
                  "dp_sensor_aufloesung_Pa": 2}]}                                  # nur bei Differenzdruck-Messung
FL1 Stroemungsform: Re = rho v d_h / mu. Re < 2000 laminar (ok), 2000-4000 Uebergang (warnung), > 4000 turbulent
    (warnung: FL2-Formel gilt nicht). Grenzen: uebliche Lehrbuchwerte fuer Rohrstroemung (Re_krit ~ 2300).
FL2 Druckverlust laminar: rund dp = 128 mu L Q / (pi d^4); rechteckig dp = 12 mu L Q / (w h^3 (1 - 0,63 h/w)), h <= w
    (Naeherung fuer flache Kanaele, Fehler wenige %). Gegen dp_max_Pa.
FL3 Einlauflaenge laminar: L_e ~ 0,06 Re d_h (Lehrbuch-Naeherung, z. B. White, Fluid Mechanics). Gerade Strecke vor dem
    Sensor kuerzer -> warnung (Profil noch nicht ausgebildet, Kalibrierung gilt nur fuer genau diesen Einbau).
FL4 Messbarkeit Differenzdruck: dp bei Q_min >= 10 x Aufloesung des Drucksensors, sonst warnung (kleinster Durchfluss
    geht im Rauschen unter -> anderes Messprinzip, z. B. thermisch, oder laengere Messstrecke).
Stoffwerte nie aus dem Code: fehlen sie, ist alles 'uebersprungen'. Geschaetzte Herkunft -> hoechstens warnung.
"""
import math

from . import ergebnis, projekt_soll, soll as lade_soll, uebersprungen

Q = 'mb2/pruefungen/stroemung.py (Hagen-Poiseuille, laminare Rohrstroemung, Lehrbuch)'
T = {'FL1': 'Stroemungsform (Reynolds)', 'FL2': 'Druckverlust laminar', 'FL3': 'Einlauflaenge vor dem Sensor',
     'FL4': 'Messbarkeit Differenzdruck'}
RE_LAMINAR, RE_TURBULENT = 2000.0, 4000.0
SCHWACH = ('geschaetzt', 'angenommen', None)


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0


def geometrie(k):
    """(Querschnitt m^2, hydraulischer Durchmesser m, Art) oder None."""
    if _num(k.get('d_mm')):
        d = k['d_mm'] * 1e-3
        return math.pi * d * d / 4, d, 'rund'
    if _num(k.get('b_mm')) and _num(k.get('h_mm')):
        w, h = max(k['b_mm'], k['h_mm']) * 1e-3, min(k['b_mm'], k['h_mm']) * 1e-3
        return w * h, 2 * w * h / (w + h), 'rechteckig'
    return None


def druckverlust(k, mu, Q_m3_s):
    L = k['L_mm'] * 1e-3
    if _num(k.get('d_mm')):
        d = k['d_mm'] * 1e-3
        return 128 * mu * L * Q_m3_s / (math.pi * d ** 4)
    w, h = max(k['b_mm'], k['h_mm']) * 1e-3, min(k['b_mm'], k['h_mm']) * 1e-3
    return 12 * mu * L * Q_m3_s / (w * h ** 3 * (1 - 0.63 * h / w))


def reynolds(k, rho, mu, Q_m3_s):
    A, dh, _ = geometrie(k)
    return rho * (Q_m3_s / A) * dh / mu


def _ml_min(q):
    return q * 1e-6 / 60.0


def _bloecke(pdir):
    pj = projekt_soll(pdir)
    if pj.get('stroemung'):
        yield None, pj['stroemung'], 'stroemung'
    for teil, ts in (lade_soll(pdir) or {}).items():
        if teil != '_projekt' and isinstance(ts, dict) and ts.get('stroemung'):
            yield teil, ts['stroemung'], f'{teil}.stroemung'


def pruefe(pdir):
    from ..anforderungen import herkunft_von
    soll = lade_soll(pdir) or {}
    out = []
    bloecke = list(_bloecke(pdir))
    if not bloecke:
        return [uebersprungen(i, T[i], 'kein soll-Feld stroemung {medium, kanaele}', Q) for i in ('FL1', 'FL2')]
    for teil, st, wo in bloecke:
        med = st.get('medium') or {}
        mu, rho = med.get('viskositaet_Pa_s'), med.get('dichte_kg_m3')
        herk = herkunft_von(soll, f'{teil}:stroemung.medium' if teil else 'stroemung.medium')[0]
        schwach = herk in SCHWACH
        for k in st.get('kanaele') or []:
            n = k.get('name', 'Kanal')
            geo = geometrie(k)
            fehlt = [f for f, ok in (('viskositaet_Pa_s', _num(mu)), ('dichte_kg_m3', _num(rho)),
                                     ('d_mm oder b_mm+h_mm', geo is not None), ('L_mm', _num(k.get('L_mm'))),
                                     ('Q_max_ml_min', _num(k.get('Q_max_ml_min')))) if not ok]
            if fehlt:
                for i in ('FL1', 'FL2'):
                    out.append(uebersprungen(i, f'{T[i]} {n}', f'fehlt: {", ".join(fehlt)} (Stoffwerte mit Quelle)', Q, teil))
                continue
            A, dh, art = geo
            Qmax = _ml_min(k['Q_max_ml_min'])
            Re = reynolds(k, rho, mu, Qmax)
            v = Qmax / A
            ann = f'; Stoffwerte {herk or "ohne Herkunft"} (angenommen)' if schwach else ''
            st1 = 'ok' if Re < RE_LAMINAR else 'warnung'
            if st1 == 'ok' and schwach:
                st1 = 'warnung'
            out.append(ergebnis('FL1', f'{T["FL1"]} {n}', st1, wert=round(Re, 1), grenze=RE_LAMINAR, quelle=Q, teil=teil,
                                daten={'v_m_s': v, 'd_h_mm': dh * 1e3, 'art': art},
                                hinweis=f'Re = rho v d_h / mu = {rho:g}*{v:.4g}*{dh * 1e3:g}e-3/{mu:g} = {Re:.0f} bei '
                                        f'Q_max {k["Q_max_ml_min"]:g} ml/min' +
                                        (' - laminar' if Re < RE_LAMINAR else ' - Uebergang' if Re < RE_TURBULENT
                                         else ' - turbulent: Hagen-Poiseuille gilt nicht') + ann))
            if Re >= RE_LAMINAR:
                out.append(uebersprungen('FL2', f'{T["FL2"]} {n}', f'Re {Re:.0f} nicht laminar - Formel gilt nicht '
                                         '(Rohrreibungszahl/Moody-Diagramm oder CFD)', Q, teil))
            else:
                dp = druckverlust(k, mu, Qmax)
                g = k.get('dp_max_Pa')
                txt = (f'dp = {dp:.4g} Pa bei Q_max ({art}, L {k["L_mm"]:g} mm){ann}')
                if not _num(g):
                    out.append(uebersprungen('FL2', f'{T["FL2"]} {n}', f'dp_max_Pa fehlt ({txt})', Q, teil))
                else:
                    s2 = 'fehler' if dp > g else ('warnung' if schwach else 'ok')
                    out.append(ergebnis('FL2', f'{T["FL2"]} {n}', s2, wert=round(dp, 4), grenze=g, einheit='Pa',
                                        quelle=Q, teil=teil, hinweis=txt, daten={'dp_Pa': dp}))
            # FL3
            ein = k.get('einlauf_vor_sensor_mm')
            Le = 0.06 * Re * dh * 1e3
            if ein is None:
                out.append(uebersprungen('FL3', f'{T["FL3"]} {n}', f'einlauf_vor_sensor_mm fehlt (noetig ~{Le:.1f} mm)', Q, teil))
            else:
                s3 = 'ok' if ein >= Le and not schwach else 'warnung'
                out.append(ergebnis('FL3', f'{T["FL3"]} {n}', s3, wert=ein, grenze=round(Le, 2), einheit='mm', quelle=Q,
                                    teil=teil, hinweis=f'L_e ~ 0,06 Re d_h = {Le:.2f} mm (Re {Re:.0f}); vorhanden {ein} mm'
                                                       + ('' if ein >= Le else ' - Profil am Sensor nicht ausgebildet') + ann))
            # FL4
            res = k.get('dp_sensor_aufloesung_Pa')
            if res is not None and _num(k.get('Q_min_ml_min')) and Re < RE_LAMINAR:
                dpmin = druckverlust(k, mu, _ml_min(k['Q_min_ml_min']))
                s4 = 'ok' if dpmin >= 10 * res else 'warnung'
                out.append(ergebnis('FL4', f'{T["FL4"]} {n}', s4, wert=round(dpmin, 4), grenze=10 * res, einheit='Pa',
                                    quelle=Q, teil=teil,
                                    hinweis=f'dp bei Q_min {k["Q_min_ml_min"]:g} ml/min = {dpmin:.3g} Pa gegen 10 x '
                                            f'Aufloesung {res:g} Pa' + ('' if s4 == 'ok' else
                                                                       ' - geht im Rauschen unter: thermisches Prinzip '
                                                                       'oder laengere Messstrecke')))
    return out
