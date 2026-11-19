"""Sensorprofil ``wandler`` (seit 19.11.2026): selbst gebaute Messprinzipien als Modellgleichung - Messgroesse aus
Signal und Parametern. GUM linear (numerische Sensitivitaeten, ``budget_aus_modell``) und, wenn die lineare
Naeherung nicht traegt, Monte-Carlo nach GUM-Ergaenzung 1 (JCGM 101:2008, Prinzip: Verteilungen fortpflanzen).

Prinzipien (Formeln aus Lehrbuechern, alle Parameter mit Unsicherheit und Herkunft aus dem Projekt):
  beer_lambert              c = -lg(I/I0) / (eps l)                       optisch, Absorption (c in mol/L)
  amperometrisch_grenzstrom c = I delta / (n F A D)                       Elektrochemie, diffusionsbegrenzter
                                                                          Grenzstrom (Nernst-Schicht delta), mol/m3
  differenzdruck_laminar    Q = dp pi d^4 / (128 mu L)                    Durchfluss aus Druckabfall (laminar!), m3/s
  linear_tk                 y = (s - s0) / (S (1 + alpha (T - T0)))       kalibrierte lineare Kennlinie mit Temperatur-
                                                                          gang (z. B. thermisch-kalorimetrisch)
  kings_law                 v = ((E^2 - A) / B)^(1/n)                     Hitzdraht/Heissfilm (King), Anemometrie
F = 96485.33212 C/mol (Faraday-Konstante, exakt seit SI 2019: e N_A).

soll.json ``_projekt.messkette``:
    {"profil": "wandler", "prinzip": "beer_lambert", "einheit": "mol/L", "faktor": 1.0,   # Ausgabe = faktor x Modell
     "ziel_U": .., "k": 2,
     "eingaben": {"I": {"wert": 0.5, "u": {"wert": 0.002, "verteilung": "normal", "k": 2}}, "I0": {...},
                  "eps": {...}, "l": {...}},
     "arbeitspunkte": [{"I": 0.9}, {"I": 0.1}]}            # je Punkt ueberschriebene Eingabewerte
MK1 = schlechtester Arbeitspunkt (groesseres U aus linear und Monte-Carlo). Herkunft schwach -> hoechstens warnung.
Monte-Carlo laeuft, wenn nichtlinear_max > 0,05 (Vorwaerts-/Rueckwaertsdifferenz weichen ab): U = halbe Breite des
symmetrischen 95,45-%-Intervalls aus 200 000 Ziehungen (fester Startwert, reproduzierbar).
"""
import math

import numpy as np

from ..pruefungen import ergebnis, uebersprungen
from ..pruefungen.messkette import TEILER, budget_aus_modell

Q = 'mb2/sensorprofile/wandler.py (Modellgleichung, GUM + Monte-Carlo JCGM 101)'
F_FARADAY = 96485.33212
N_MC = 200_000


def _np(x):
    return np.asarray(x, float)


MODELLE = {
    'beer_lambert': (('I', 'I0', 'eps', 'l'), lambda x: -np.log10(_np(x['I']) / x['I0']) / (_np(x['eps']) * x['l'])),
    'amperometrisch_grenzstrom': (('I', 'delta', 'n', 'A', 'D'),
                                  lambda x: _np(x['I']) * x['delta'] / (_np(x['n']) * F_FARADAY * x['A'] * x['D'])),
    'differenzdruck_laminar': (('dp', 'd', 'L', 'mu'),
                               lambda x: _np(x['dp']) * math.pi * _np(x['d']) ** 4 / (128 * _np(x['mu']) * x['L'])),
    'linear_tk': (('s', 's0', 'S', 'alpha', 'T', 'T0'),
                  lambda x: (_np(x['s']) - x['s0']) / (_np(x['S']) * (1 + _np(x['alpha']) * (_np(x['T']) - x['T0'])))),
    'kings_law': (('E', 'A', 'B', 'n'),
                  lambda x: np.maximum((_np(x['E']) ** 2 - x['A']) / x['B'], 0) ** (1 / _np(x['n']))),
}


def _modell(mk):
    p = mk.get('prinzip')
    if p not in MODELLE:
        raise ValueError(f'messkette.prinzip {p!r} unbekannt ({", ".join(MODELLE)})')
    namen, f = MODELLE[p]
    fak = float(mk.get('faktor', 1.0))
    return namen, (lambda x: float(fak * f(x))), (lambda x: fak * f(x))


def _punkte(mk):
    return [{}] + list(mk.get('arbeitspunkte') or [])


def _ziehen(u, n, rng):
    if u is None:
        return 0.0
    v = u.get('verteilung', 'u')
    w = float(u['wert'])
    if v == 'normal':
        return rng.normal(0, w / float(u.get('k', 2.0)), n)
    if v == 'rechteck':
        return rng.uniform(-w, w, n)
    if v == 'dreieck':
        return rng.triangular(-w, 0, w, n)
    if v == 'u':
        return rng.normal(0, w, n)
    s = w / TEILER.get(v, 1.0)
    return rng.normal(0, s, n)


def monte_carlo(mk, eing, p=0.9545, n=N_MC, seed=1):
    """(y_mittel, U) - halbe Breite des symmetrischen p-Intervalls um den Mittelwert."""
    _, _, f = _modell(mk)
    rng = np.random.default_rng(seed)
    x = {k: e['wert'] + _ziehen(e.get('u'), n, rng) for k, e in eing.items()}
    y = np.asarray(f(x), float)
    y = y[np.isfinite(y)]
    m = float(np.mean(y))
    U = float(np.quantile(np.abs(y - m), p))
    return m, U


def budget_bei(mk, punkt, hk=lambda f: None):
    namen, f_skalar, _ = _modell(mk)
    eing = {}
    for n in namen:
        e = dict((mk.get('eingaben') or {}).get(n) or {})
        if n in punkt:
            e['wert'] = punkt[n]
        e.setdefault('wert', None)
        e['herkunft'] = hk(f'eingaben.{n}')
        eing[n] = e
    b = budget_aus_modell(f_skalar, eing, k=float(mk.get('k', 2.0)), einheit=mk.get('einheit', ''))
    b['eingaben'] = eing
    if b['U'] is not None and b.get('nichtlinear_max', 0) > 0.05:
        ym, Umc = monte_carlo(mk, eing)
        b['monte_carlo'] = {'y_mittel': ym, 'U': Umc, 'n': N_MC}
        b['U_lin'] = b['U']
        b['U'] = max(b['U'], Umc)
    return b


def pruefe(mk, herkunft_klasse):
    e = mk.get('einheit', '')
    try:
        namen, _, _ = _modell(mk)
    except ValueError as ex:
        return [uebersprungen('MK1', 'Unsicherheitsbudget Messkette', str(ex), Q)]
    tab = [(pk, budget_bei(mk, pk, herkunft_klasse)) for pk in _punkte(mk)]
    fehlt = sorted({x for _, b in tab for x in b['fehlt']})
    out = []
    if fehlt:
        out.append(uebersprungen('MK1', 'Unsicherheitsbudget Messkette', f'Profil wandler/{mk["prinzip"]}: Wert oder '
                                 f'Unsicherheit fehlt fuer {", ".join(fehlt)} (Datenblatt/Messung, keine Annahme)', Q))
    else:
        pk, b = max(tab, key=lambda t: t[1]['U'])
        schwach = sorted(n for n, x in b['eingaben'].items() if x.get('u') is not None and
                         (x.get('herkunft') or 'offen') in ('offen', 'geschaetzt', 'angenommen'))
        mc = b.get('monte_carlo')
        txt = (f'{mk["prinzip"]}: y = {b["y"]:.5g} {e}, U = {b["U"]:.4g} {e} (k {b["k"]:g}) am Punkt {pk or "Nennwert"}; '
               + ', '.join(f'{z["name"]} {z["beitrag"]:.3g}' for z in sorted(b['beitraege'], key=lambda z: -z['beitrag'])))
        if mc:
            txt += (f'; nichtlinear ({b["nichtlinear_max"]:.2f}): Monte-Carlo U {mc["U"]:.4g} gegen linear '
                    f'{b["U_lin"]:.4g}, groesseres gilt')
        if schwach:
            txt += f'; Herkunft schwach/offen: {", ".join(schwach)} (angenommen)'
        ziel = mk.get('ziel_U')
        daten = {'y': b['y'], 'U': b['U'], 'beitraege': b['beitraege'], 'monte_carlo': mc,
                 'je_punkt': [{'punkt': p, 'y': x['y'], 'U': x['U']} for p, x in tab]}
        if ziel is None:
            out.append(uebersprungen('MK1', 'Unsicherheitsbudget Messkette', 'messkette.ziel_U fehlt; ' + txt, Q))
        else:
            st = 'fehler' if b['U'] > ziel else ('warnung' if schwach else 'ok')
            out.append(ergebnis('MK1', 'Unsicherheitsbudget Messkette', st, wert=b['U'], grenze=ziel, einheit=e,
                                quelle=Q, hinweis=txt, daten=daten))
    out.append(ergebnis('MK2', 'Rauschbegrenzte Aufloesung', 'info', quelle=Q,
                        hinweis='Profil wandler: Rauschen steckt als Unsicherheit des Signals im Budget (MK1)'))
    return out
