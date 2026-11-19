"""Register der Realterme (Audit Scheinsicherheit 15.11.2026, Muster B).

Idealformeln (Kurzzeitfestigkeit bei 23 C, Nennkapazitaet, R_int neu bei 25 C, Freiraum, sigma 0,05 mm) versprechen
mehr, als im Feld ankommt. Jede Pruefung holt ihre Abminderung HIER statt Kennwerte roh zu nutzen:

    f, terme, angenommen = abminderung('festigkeit', kontext)

- ``f``          Faktor, durch den die Idealgroesse geteilt (Festigkeit, Kapazitaet) bzw. mit dem sie multipliziert wird
                 (R_int, Streuung) – Richtung steht je Groesse unten.
- ``terme``      Liste lesbarer Texte "A_T 1,5 (PLA, 17 K unter Tg)" fuer den Hinweis des Ergebnisses.
- ``angenommen`` True, wenn eine Bedingung unbekannt war und der UNGUENSTIGE Standard angewandt wurde. Dann darf das
                 Ergebnis hoechstens 'warnung' sein (nie 'ok' auf Annahmen).

``kontext(pdir)`` baut den gemeinsamen Kontext aus soll.json + Projektmerkmalen, darunter die EINE Teiltemperatur
``T_teil_C`` fuer D*, M*, E4 und W6 (Luft + Sonne + Eigenerwaermung), damit Sonne nicht in einem Modul fehlt und im
anderen steht.

Rueckkopplung: ``projects/<p>/feld.json`` (optional) haelt Feldmessungen fest; ``FELDBEFUNDE`` unten dokumentiert, welche
Standardwerte daraus kalibriert wurden.
"""
import os

from . import kennwerte as kw

FELDBEFUNDE = {
    'funk_dorf_n': 'Bodenklima 15.11.2026: 868 MHz, 830 m durchs Dorf, Basis unter Dachziegeln, Magnetfuss ohne Blech, '
                   '3 m RG174, 14 dBm -> ~ -134 dBm (SNR -17 dB). Freiraum versprach -103 dBm. n = 3,5 trifft es.',
}

# Glastemperaturen (C): EINE Quelle, mb2/material.py (glasuebergang_C); nur fehlende Stoffe hier
def _tg_tabelle():
    t = {'ABS': 100.0, 'TPU': -30.0, 'PC': 140.0}
    try:
        from .material import MATERIAL
        t.update({k.upper(): v['glasuebergang_C'] for k, v in MATERIAL.items() if v.get('glasuebergang_C') is not None})
    except Exception:  # noqa: BLE001
        t.update({'PLA': 57.0, 'PETG': 80.0, 'ASA': 100.0})
    return t


TG_C = _tg_tabelle()

# Sonne: dT = alpha * G / h_ges, G = 1000 W/m2, h_ges = Konvektion + Strahlung ~ 25 W/m2K (kleines Gehaeuse, Wind schwach)
SONNE_G_W_M2 = 1000.0
SONNE_H_W_M2K = 25.0
# Solarer Absorptionsgrad je Farbe – EINE Tabelle fuer realterme und waerme.W6
ALPHA_FARBE = {'weiss': 0.25, 'natur': 0.4, 'transparent': 0.4, 'silber': 0.4, 'hell': 0.4, 'gelb': 0.45,
               'hellgrau': 0.5, 'orange': 0.55, 'grau': 0.65, 'rot': 0.65, 'gruen': 0.75, 'blau': 0.8, 'braun': 0.8,
               'dunkelgrau': 0.85, 'schwarz': 0.95}
ALPHA_UNBEKANNT = 0.95          # unguenstig

# Akku: Kapazitaetsfaktor bei Kaelte je Chemie (T in C -> Faktor), linear interpoliert; Datenblaetter (Panasonic NCR,
# Energizer L91, Duracell MN1500) gerundet
KAELTE_KAPAZITAET = {
    'lipo': [(-20, 0.5), (-10, 0.65), (0, 0.8), (20, 1.0)],
    'li_fes2': [(-20, 0.85), (0, 0.95), (20, 1.0)],          # L91
    'alkali': [(-20, 0.3), (-10, 0.45), (0, 0.65), (20, 1.0)],
    'lifepo4': [(-20, 0.6), (0, 0.85), (20, 1.0)],
    'nimh': [(-20, 0.5), (0, 0.8), (20, 1.0)],
}
SELBSTENTLADUNG_PRO_MONAT = {'lipo': 0.03, 'li_fes2': 0.001, 'alkali': 0.003, 'lifepo4': 0.03, 'nimh': 0.15}
# R_int: Faktor bei Kaelte (T -> Faktor) und Alterung
KAELTE_RINT = [(-20, 4.0), (-10, 3.0), (0, 2.0), (25, 1.0)]
RINT_ALTERUNG = 1.5


def _interp(tab, x):
    tab = sorted(tab)
    if x <= tab[0][0]:
        return tab[0][1]
    if x >= tab[-1][0]:
        return tab[-1][1]
    for (x0, y0), (x1, y1) in zip(tab, tab[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return tab[-1][1]


def kontext(pdir=None, soll=None, merkmale=None, **extra):
    """Gemeinsamer Kontext fuer alle Abminderungen. Fehlendes bleibt None (-> unguenstiger Standard, angenommen)."""
    if soll is None and pdir:
        from .pruefungen import soll as _s
        soll = _s(pdir)
    soll = soll or {}
    pj = soll.get('_projekt', {})
    if merkmale is None and pdir:
        try:
            from .pruefungen.merkmale import merkmale as _m
            merkmale = _m(pdir)
        except Exception:  # noqa: BLE001
            merkmale = {}
    merkmale = merkmale or {}
    aussen = pj.get('aussen')
    if aussen is None and merkmale.get('aussen', {}).get('aktiv'):
        aussen = True
    k = {
        'material': pj.get('material'),
        'T_max_C': pj.get('T_max_C'),
        'T_min_C': pj.get('T_min_C'),
        'aussen': aussen,
        'farbe': pj.get('farbe'),
        'absorption': pj.get('absorption'),
        'elektronik': merkmale.get('elektronik', {}).get('aktiv', False),
        'lebensdauer_h': pj.get('lebensdauer_h'),
        'akku_chemie': pj.get('akku_chemie'),
        'laufzeit_ziel_h': pj.get('laufzeit_ziel_h'),
    }
    k.update(extra)
    return k


def sonne_dT(k):
    """(dT_K, text, angenommen) fuer ein Teil in der Sonne; 0 wenn sicher innen."""
    if k.get('aussen') is False:
        return 0.0, 'innen (soll aussen=false)', False
    if not k.get('aussen'):
        return 0.0, 'keine Sonne (nicht aussen)', False
    a = k.get('absorption')
    ang = False
    if a is None:
        a = ALPHA_FARBE.get(str(k.get('farbe') or '').lower())
    if a is None:
        a, ang = ALPHA_UNBEKANNT, True
    dT = a * SONNE_G_W_M2 / SONNE_H_W_M2K
    return dT, f'Sonne +{dT:.0f} K (alpha {a:.2f}{", Farbe unbekannt" if ang else ""})', ang


def teil_temperatur(k, T_fem_C=None, dT_eigen_K=0.0):
    """EINE Teiltemperatur fuer D*, M*, E4, W6: max(FEM, Luft) + Sonne + Eigenerwaermung.
    Luft unbekannt: 40 C mit Elektronik im Gehaeuse, sonst 30 C (beides angenommen)."""
    terme, ang = [], False
    T_luft = k.get('T_max_C')
    if T_luft is None and T_fem_C is not None:
        T_luft = 0.0          # FEM traegt die Temperatur (unten), keine Annahme noetig
    elif T_luft is None:
        T_luft = 40.0 if k.get('elektronik') else 30.0
        terme.append(f'Luft {T_luft:.0f} C angenommen (T_max_C fehlt)')
        ang = True
    else:
        terme.append(f'Luft {T_luft:.0f} C')
    dS, tS, aS = sonne_dT(k)
    if dS:
        terme.append(tS)
    if dT_eigen_K:
        terme.append(f'Eigenerwaermung +{dT_eigen_K:.1f} K')
    T = T_luft + dS + (dT_eigen_K or 0.0)
    if T_fem_C is not None and T_fem_C + dS > T:
        T = T_fem_C + dS
        terme.append(f'FEM {T_fem_C:.1f} C')
    return T, terme, ang or aS


def _festigkeit(k):
    terme, ang, f = [], False, 1.0
    mat_ = (k.get('material') or '').upper()
    if not mat_:
        mat_, ang = 'PLA', True
        terme.append('Material unbekannt -> PLA')
    Tg = TG_C.get(mat_)
    T = k.get('T_teil_C')
    if T is None:
        T, tt, a2 = teil_temperatur(k)
        terme += tt
        ang = ang or a2
    if Tg is not None:
        dT = Tg - T
        if dT <= 5:
            A_T = float('inf')
        else:
            A_T = 1.0 + max(0.0, 30.0 - dT) * 0.04
        if A_T > 1:
            terme.append(f'A_T {A_T:.2f} ({mat_}, {dT:.0f} K unter Tg {Tg:.0f} C)')
        f *= A_T
    dauer = k.get('dauerlast')
    if dauer is None:
        dauer = True if k.get('dauerlast_unbekannt_unguenstig', True) else False
        if dauer:
            ang = True
    if dauer:
        f *= 1.7
        terme.append('A_K 1,70 (Dauerlast, Kriechbruch ~0,6 sigma_Z)' + (' – angenommen' if k.get('dauerlast') is None else ''))
    if k.get('aussen'):
        A_A = 1.1 if mat_ == 'ASA' else 1.3
        f *= A_A
        terme.append(f'A_A {A_A:.1f} (aussen: UV/Feuchte)')
    return f, terme, ang


def _kapazitaet(k):
    terme, ang = [], False
    chem = (k.get('akku_chemie') or '').lower()
    if chem not in KAELTE_KAPAZITAET:
        chem, ang = 'lipo', True
        terme.append('Chemie unbekannt -> LiPo')
    f = 1 / 0.85
    terme.append('nutzbar 0,85 bis Abschaltspannung')
    Tmin = k.get('T_min_C')
    if Tmin is None:
        Tmin = -10.0 if k.get('aussen') else 15.0
        ang = True
        terme.append(f'T_min {Tmin:.0f} C angenommen')
    kT = _interp(KAELTE_KAPAZITAET[chem], Tmin)
    if kT < 1:
        f /= kT
        terme.append(f'Kaelte x{kT:.2f} bei {Tmin:.0f} C')
    if chem in ('lipo', 'lifepo4', 'nimh'):
        f /= 0.8
        terme.append('Alterung x0,80 (Lebensende)')
    t_h = k.get('laufzeit_ziel_h')
    if t_h:
        sd = SELBSTENTLADUNG_PRO_MONAT[chem] * t_h / 730.0
        if sd > 0.01:
            f /= max(0.05, 1 - sd)
            terme.append(f'Selbstentladung {sd * 100:.0f} % ueber die Laufzeit')
    return f, terme, ang


def _rint(k):
    terme, ang = [], False
    Tmin = k.get('T_min_C')
    if Tmin is None:
        Tmin = -10.0 if k.get('aussen') else 15.0
        ang = True
        terme.append(f'T_min {Tmin:.0f} C angenommen')
    kT = _interp(KAELTE_RINT, Tmin)
    f = kT * RINT_ALTERUNG
    terme.append(f'R_int x{kT:.1f} bei {Tmin:.0f} C, x{RINT_ALTERUNG} Alterung/Kontakte')
    return f, terme, ang


def _eps_zul(k):
    """Teiler fuer die zulaessige Dehnung von Schnappern."""
    terme, ang, f = [], False, 1.0
    z = k.get('zyklen')
    if z is None:
        z, ang = 10, True
        terme.append('Zyklen unbekannt -> haeufig')
    if z > 1:
        f /= 0.6
        terme.append('haeufiges Fuegen x0,6 (Bayer Snap-Fit)')
    Tmin = k.get('T_min_C')
    if Tmin is None and k.get('aussen'):
        Tmin, ang = -10.0, True
    if Tmin is not None and Tmin < 5:
        f /= 0.7
        terme.append(f'Kaelte x0,7 ({Tmin:.0f} C)')
    return f, terme, ang


def _streuung(k):
    """Faktor auf die Mass-Streuung sigma des Toleranzmodells (Standard 0,05 mm -> 0,10 mm)."""
    return 2.0, ['sigma x2 (Elefantenfuss, Lochschrumpf je Durchmesser, Nachfluss – bis Kalibrierkoerper gemessen)'], True


def _rthja(k):
    if k.get('kuehlflaeche'):
        return 1.0, [], False
    return 1.5, ['RthJA x1,5 (kleine 2-Lagen-Platine statt JEDEC-Testboard)'], k.get('kuehlflaeche') is None


GROESSEN = {
    'festigkeit': _festigkeit,   # sigma_zul = sigma_Z / (S * f)
    'temperatur_festigkeit': lambda k: _festigkeit(dict(k, dauerlast=False, aussen=False)),   # nur A_T
    'kapazitaet': _kapazitaet,   # C_eff = C_nenn / f
    'rint': _rint,               # R_eff = R_int * f
    'eps_zul': _eps_zul,         # eps_zul_eff = eps_zul / f
    'streuung': _streuung,       # sigma_eff = sigma * f
    'rthja': _rthja,             # RthJA_eff = RthJA * f
}


def abminderung(groesse, k):
    """(faktor, terme, angenommen) – siehe Modulkopf."""
    return GROESSEN[groesse](dict(k or {}))


def hinweis(terme):
    return ('Realterme: ' + '; '.join(terme)) if terme else ''


def deckel(stufe, angenommen):
    """Annahmen erlauben hoechstens 'warnung'."""
    return 'warnung' if angenommen and stufe == 'ok' else stufe


def feld(pdir):
    """Feldmessungen projects/<p>/feld.json oder {}."""
    import json
    p = os.path.join(pdir, 'feld.json')
    return json.load(open(p, encoding='utf-8')) if pdir and os.path.exists(p) else {}


_ = kw  # Kennwerte bleiben Quelle der Rohwerte; dieses Modul liefert nur die Abschlaege
