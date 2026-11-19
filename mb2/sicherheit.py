"""Ein Sicherheitsziel fuer alle Festigkeitspruefungen (seit 19.11.2026, Entscheidung Nutzer).

Vorher galt das Ziel aus soll.json und M26 nur in mechanik.py; FEM-Bewertung, M7, M9 rechneten fest mit 2,0,
M1 mit 1,5, M4 mit 3, D9/D11 nur mit dem Teilwert. Ein Projekt mit Ziel 2,5 bekam so "gruen" bei 2,0.

ziel(projekt, teil_soll, material, richtung, minimum):
    S = max(minimum der Pruefung, ausdrueckliches Ziel (Teil vor Projekt), M26 aus Streuung und Lastfaktor)
Das Minimum ist der bisherige feste Wert der Pruefung (FEM/M7/M9/D9/D11 2,0, M1 1,5, M4 3,0): eine Pruefung wird
dadurch nie lascher, nur strenger, wenn das Projekt es verlangt.
"""
import statistics

from . import kennwerte

S_STANDARD = 2.0


def m26_ke(s_rel, R):
    """k_e = 1 - s z (z = Quantil der Normalverteilung zur Zuverlaessigkeit R; s = 0,08: Katalogwert 2.72)."""
    z = statistics.NormalDist().inv_cdf(R)
    return 1 - s_rel * z, z


def streuung(projekt, mat, richtung):
    feld = 'streuung_xy' if richtung == 'xy' else 'streuung_z'
    if (projekt or {}).get(feld) is not None:
        return float(projekt[feld]), 'soll.json _projekt'
    v = kennwerte.wert(mat, feld) if mat else None
    return (v, 'kennwerte.py') if v is not None else (None, None)


def m26_sicherheit(projekt, mat, richtung):
    projekt = projekt or {}
    s, _ = streuung(projekt, mat, richtung)
    if s is None:
        return None
    ke, _ = m26_ke(s, float(projekt.get('zuverlaessigkeit') or 0.99))
    return float(projekt.get('lastfaktor') or 1.0) / ke if ke > 0 else None


def ziel(projekt=None, teil_soll=None, material=None, richtung='z', minimum=S_STANDARD):
    """(S_ziel, Text). projekt = soll._projekt, teil_soll = soll[teil]."""
    projekt, teil_soll = projekt or {}, teil_soll or {}
    teile = [(float(minimum), f'Minimum der Pruefung {minimum:g}')]
    if teil_soll.get('sicherheit') is not None:
        teile.append((float(teil_soll['sicherheit']), f'Teil sicherheit {teil_soll["sicherheit"]}'))
    elif projekt.get('sicherheit') is not None:
        teile.append((float(projekt['sicherheit']), f'Projekt sicherheit {projekt["sicherheit"]}'))
    s26 = m26_sicherheit(projekt, material, richtung) if material else None
    if s26 and s26 > 0:
        teile.append((s26, f'M26 {material} {richtung}: {s26:.2f}'))
    S, txt = max(teile)
    return S, txt
