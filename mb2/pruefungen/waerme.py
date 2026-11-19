"""Waerme-Pruefungen W1-W10 (OCW_PRUEFKATALOG.md 3.3). Einheiten: mm, W, K, W/(m2 K) - intern SI.

Liest je Waerme-Lastfall fem/<fall>.json + fem/<fall>.erg.json (Zusatzdaten schreibt fem.waerme: randbedingungen,
energiebilanz, koerper_info, flaechen_mm2, geometrie) und dazu cad/soll.json, out/*.pruefung.json, print/slice.json.
  W1  h freie Konvektion   h = 1,42 (dT/L)^1/4, Ra = gbetadT L^3/(nualpha); Festwert gegen Korrelation (> 30 % -> warnung)
  W2  Strahlung            h_r = epssigma(T_s + Tinf)(T_s^2 + Tinf^2); fehlt sie im Modell -> info (Ergebnis zu warm)
  W3  Energiebilanz        Sum  Quellen (+ Sonne) = Konvektion + Strahlung + feste Temperaturen; < 2 %
  W4  Waermewiderstands-Netz  Quelle auf Wand: R_frei || (t/(2kA) + R_Platte || 1/(hA)), Platte als Kreisrippe
                           R = 1/(2pi k t * m a * K1(ma)/K0(ma)), m = sqrt(2h/(kt)); Elmer-dT_mittel +-25 %
  W5  Innenluft            k = k_Luft*Nu + 4eps_eff sigma T_m^3 delta, eps_eff = 1/(1/eps1 + 1/eps2 - 1); geschlossene Innenflaechen
                           ohne Innenluft konvektieren gegen Tinf (zu kalt) -> warnung
  W6  Sonne                Q = alpha G A_proj, dT = Q/((h_c + h_r) A_ges); T = max(T + dT_Sonne + dT_intern,
                           realterme.teil_temperatur wie D1); Regel wie D1: Tg - T >= 30 ok, >= 20 warnung, sonst fehler
  W7  Biot, Zeitkonstante  Bi = h L_c/k < 1/6 (L_c = V/A), tau = Sum rhoc V/(h A); Lastdauer > 3tau -> stationaer erreicht
  W8  Quelle im Koerper    dT = q''' L^2/(8k) (Platte beidseitig gekuehlt; einseitig 4x) - Groessenordnung, info
  W9  Rippen-Wirkungsgrad  m = sqrt(hP/(kA)), eta = tanh(mL)/(mL); eta < 0,5 -> Rippe lohnt nicht
  W10 Abkuehlung beim Druck  Schicht als konzentrierte Masse (Bi < 1/6): t = rho c h_s/h * ln((T_D - Tinf)/(Tg - Tinf)),
                           Fo = alpha t/h_s^2; Schichtzeit (Slicer-Mindestzeit) >= t. Braucht h des Bauteil-Luefters.
Optionale Eingaben (alle fehlen duerfen): Lastfall 'lastdauer_h', 'rippen' [{"name","L_mm","t_mm","b_mm"}],
'wand_mm' (Wanddicke fuer W4); soll.json _projekt: aussen, farbe | absorption, T_max_C, material, lastdauer_h,
h_luefter_W_m2K; je Teil 'rippen'.
"""
import glob
import json
import math
import os
import re

from . import ergebnis, projekt_soll, soll, uebersprungen
from ..fem import C_FREI, K0, K_LUFT, SIGMA, h_frei
from ..material import DRUCKSTOFFE, MATERIAL

Q_W1 = '3.185 Par. 5.4, 4.42J Gl. 3.13 (MIT OCW): Nu = 0,56 Ra^1/4 laminar, Luft h = 1,42 (dT/L)^1/4'
Q_W2 = '4.42J Gl. 4.5-4.7, 16.050 Par. 9 (MIT OCW): h_r = eps sigma (Ts + Too)(Ts^2 + Too^2)'
Q_W3 = '2.092 L11 (MIT OCW): Energiebilanz des FE-Modells'
Q_W4 = ('4.42J Par. 2, 16.050 Par. 2 (MIT OCW): R = t/(kA), 1/(hA); Platte als Kreisrippe 16.050 Par. 5 '
        '(Besselloesung K0/K1, Lienhard-Lehrbuch, extern)')
Q_W5 = '4.42J Gl. 3.15, 16.050 Par. 9.3 (MIT OCW): Spalt Nu = 1, eps_eff = 1/(1/e1 + 1/e2 - 1)'
Q_W6 = ('2.997 L8 (MIT OCW, G = 1000 W/m2); Solar-Absorptionsgrad je Farbe: Richtwerte Lackflaechen '
        '(Incropera Tab. A.12 / ASHRAE, extern, am Teil nicht gemessen)')
Q_W7 = '4.42J, 16.050 Par. 3.3/Par. 6, 3.044 L4 (MIT OCW): Bi = hL/k, tau = rho c V/(hA)'
Q_W8 = '16.050 Par. 4 (MIT OCW): Platte mit Quelle dT = q L^2/(8k)'
Q_W9 = '16.050 Par. 5 (MIT OCW): Rippe eta = tanh(mL)/(mL), m = sqrt(hP/(kA))'
Q_W10 = '3.064 lec_33, 3.044 L4 (MIT OCW): Fo = a t/L^2, konzentrierte Masse bei Bi < 1/6'

G_SONNE = 1000.0                 # W/m2, Katalog W6
EPS_STANDARD = 0.9               # Katalog W2
RA_LAMINAR = (1e4, 1e9)
# Solar-Absorptionsgrad alpha_s (Richtwerte, extern - siehe Q_W6); unbekannt -> 0,95 (schwarz, konservativ)
from mb2.realterme import ALPHA_FARBE as ABSORPTION  # noqa: E402 - eine Tabelle (realterme)


# ---------------------------------------------------------------- Formeln

def rayleigh(dT, L_m, T_film_K, nu=1.589e-5, a=2.25e-5, g=9.81):
    """Ra = g beta dT L^3/(nu alpha), Luft ~300 K (Incropera Tab. A.4), beta = 1/T_film."""
    return g / T_film_K * max(dT, 0.0) * L_m ** 3 / (nu * a)


def h_strahlung(eps, Ts_C, Tinf_C):
    """W2: linearisierter Strahlungs-Waermeuebergang (exakt fuer die Temperaturen Ts, Tinf)."""
    Ts, Ti = Ts_C + K0, Tinf_C + K0
    return eps * SIGMA * (Ts + Ti) * (Ts ** 2 + Ti ** 2)


def eps_eff(e1, e2):
    """W5: zwei parallele graue Flaechen."""
    return 1.0 / (1.0 / e1 + 1.0 / e2 - 1.0)


def k_spalt(delta_m, T_m_K, e_eff, Nu=1.0):
    """W5: Ersatzleitfaehigkeit einer Luftschicht (Leitung + Strahlung als h_r*delta)."""
    return K_LUFT * Nu + 4 * e_eff * SIGMA * T_m_K ** 3 * delta_m


def _bessel_k0_k1(x):
    from scipy.special import k0, k1
    return float(k0(x)), float(k1(x))


def r_platte(k, t_m, h, a_m):
    """W4: unendliche Platte (Dicke t, beidseitig h) als Kreisrippe ab Radius a: R = 1/(2pi k t * ma * K1/K0)."""
    m = math.sqrt(2 * h / (k * t_m))
    k0, k1 = _bessel_k0_k1(m * a_m)
    return 1.0 / (2 * math.pi * k * t_m * m * a_m * k1 / k0)


def netz_quelle(P, h_frei_ges, A_frei_m2, k_wand, t_m, A_kontakt_m2, h_platte):
    """W4: dT einer Quelle, die frei abgibt und ueber die Kontaktflaeche in eine Wand (Platte) leitet."""
    leit = []
    if A_frei_m2 > 0 and h_frei_ges > 0:
        leit.append(h_frei_ges * A_frei_m2)
    if A_kontakt_m2 > 0:
        a = math.sqrt(A_kontakt_m2 / math.pi)
        R_pfad = t_m / (2 * k_wand * A_kontakt_m2) + 1.0 / (1.0 / r_platte(k_wand, t_m, h_platte, a)
                                                              + h_platte * A_kontakt_m2)
        leit.append(1.0 / R_pfad)
    return P / sum(leit) if leit else float('inf')


def dT_sonne(alpha, G, A_proj_m2, h_ges, A_ges_m2):
    """W6: Uebertemperatur durch Sonne, konzentriert."""
    return alpha * G * A_proj_m2 / (h_ges * A_ges_m2)


def biot(h, L_m, k):
    return h * L_m / k


def zeitkonstante(rho_c_V, h, A_m2):
    """W7: tau = rho c V/(h A) in s."""
    return rho_c_V / (h * A_m2)


def dT_quelle(q3, L_m, k):
    """W8: Platte der Dicke L mit Quelle q''', beide Seiten auf gleicher Temperatur."""
    return q3 * L_m ** 2 / (8 * k)


def rippe_eta(h, k, t_m, b_m, L_m):
    """W9: gerade Rippe, Rechteckquerschnitt b x t, adiabate Spitze."""
    P, A = 2 * (b_m + t_m), b_m * t_m
    mL = math.sqrt(h * P / (k * A)) * L_m
    return math.tanh(mL) / mL if mL > 0 else 1.0


def abkuehlzeit_schicht(rho, c, h_s_m, h, T_duese, T_bau, Tg):
    """W10: frische Schicht als konzentrierte Masse, nur oben gekuehlt (konservativ, ohne Leitung nach unten)."""
    return rho * c * h_s_m / h * math.log((T_duese - T_bau) / (Tg - T_bau))


def h_frei_strahlung(dT, L_m, eps, T_inf_C):
    """h_c (W1) + h_r (W2) bei Uebertemperatur dT."""
    return h_frei(dT, L_m) + h_strahlung(eps, T_inf_C + dT, T_inf_C)


# ---------------------------------------------------------------- Eingaben

def _json(p):
    try:
        return json.load(open(p, encoding='utf-8'))
    except (OSError, ValueError):
        return None


def waerme_faelle(pdir):
    """[(fall, spec, erg|None)] aller Waerme-Lastfaelle (fem/<fall>.json ohne 'lagerung')."""
    out = []
    for p in sorted(glob.glob(os.path.join(pdir, 'fem', '*.json'))):
        if p.endswith('.erg.json'):
            continue
        spec = _json(p)
        if not isinstance(spec, dict) or 'koerper' not in spec or 'lagerung' in spec:
            continue
        fall = os.path.basename(p)[:-5]
        out.append((fall, spec, _json(os.path.join(pdir, 'fem', fall + '.erg.json'))))
    return out


def _pruefung(pdir, teil):
    return _json(os.path.join(pdir, 'out', teil + '.pruefung.json'))


def _druck_koerper(erg):
    return {n: i for n, i in erg.get('koerper_info', {}).items() if i['material'] in DRUCKSTOFFE}


def _eps(erg):
    st = erg.get('randbedingungen', {}).get('strahlung')
    return (st['emission'], True) if st else (EPS_STANDARD, False)


def _h_ges(erg, T_s_C=None):
    """Im Modell wirksamer Uebergang an den Konvektionsflaechen: h (+ h_r, falls Strahlung modelliert)."""
    rb = erg['randbedingungen']
    h = rb['h_W_m2K']
    eps, mit = _eps(erg)
    if mit:
        Ts = erg['T_mittel_konvektion_C'] if T_s_C is None else T_s_C
        h += h_strahlung(eps * rb['strahlung'].get('himmel_anteil_mittel', 1.0), Ts, rb['T_umgebung_C'])
    return h


def _L_m(spec, erg):
    rb = erg.get('randbedingungen', {})
    if rb.get('konvektion_auto'):
        return rb['konvektion_auto']['L_mm'] * 1e-3
    L = (spec.get('konvektion') or {}).get('L_mm')
    if L:
        return L * 1e-3
    bb = erg.get('geometrie', {}).get('bbox_mm')
    return (bb[2] or max(bb)) * 1e-3 if bb else None


# ---------------------------------------------------------------- Einzelpruefungen je Lastfall

def _w1(fall, spec, erg):
    rb = erg['randbedingungen']
    T_inf, h = rb['T_umgebung_C'], rb['h_W_m2K']
    dT = erg['T_mittel_konvektion_C'] - T_inf
    L = _L_m(spec, erg)
    if L is None:
        return uebersprungen('W1', 'h freie Konvektion', 'Hoehe L unbekannt (konvektion.L_mm)', Q_W1, fall)
    h_k = h_frei(dT, L)
    Ra = rayleigh(dT, L, T_inf + K0 + dT / 2)
    daten = {'dT_mittel_K': round(dT, 3), 'L_mm': round(L * 1e3, 2), 'Ra': round(Ra, 1),
             'h_korrelation_W_m2K': round(h_k, 3), 'h_modell_W_m2K': h}
    zusatz = ''
    if Ra > RA_LAMINAR[1]:
        zusatz = f' Ra = {Ra:.2g} > 1e9: turbulent, laminare Korrelation ungueltig.'
    elif Ra < RA_LAMINAR[0]:
        zusatz = f' Ra = {Ra:.2g} < 1e4: Korrelation unterschaetzt h eher (konservativ).'
    if rb.get('konvektion_auto'):
        v = rb['konvektion_auto']['verlauf'][-1]
        ok = abs(v['h_korrelation_W_m2K'] - v['h_W_m2K']) <= 0.02 * v['h_W_m2K']
        stufe = 'warnung' if (not ok or Ra > RA_LAMINAR[1]) else 'ok'
        return ergebnis('W1', 'h freie Konvektion', stufe, wert=round(h, 3), grenze=round(h_k, 3), einheit='W/m2K',
                        quelle=Q_W1, teil=fall, daten=daten,
                        hinweis=f'h automatisch aus W1 ({len(rb["konvektion_auto"]["verlauf"])} Laeufe)'
                                + ('' if ok else ', Fixpunkt nicht konvergiert') + '.' + zusatz)
    eps, mit = _eps(erg)
    h_r = 0.0 if mit else h_strahlung(eps, T_inf + dT, T_inf)
    unten, oben = h_k, h_k + h_r          # ohne Strahlung im Modell darf ein Festwert h_c + h_r enthalten
    daten['h_r_W_m2K'] = round(h_r, 3)
    if h == 0:
        return ergebnis('W1', 'h freie Konvektion', 'info', wert=0.0, grenze=round(h_k, 3), einheit='W/m2K',
                        quelle=Q_W1, teil=fall, daten=daten,
                        hinweis=f'h = 0: Konvektionsflaechen adiabat (Gegencheck/Isolation gewollt?); frei waere '
                                f'h_c = {h_k:.2f} W/m2K')
    if h > 1.3 * oben:
        stufe, txt = 'warnung', (f'Festwert {h} > 1,3 x {"h_c + h_r" if h_r else "h_c"} = {oben:.2f}: zu optimistisch, '
                                 'T zu niedrig' + (' (Strahlung doppelt?)' if mit else '') + ' - konvektion.auto nutzen')
    elif h < unten / 1.3:
        stufe, txt = 'warnung', (f'Festwert {h} < h_c/1,3 = {unten / 1.3:.2f}: konservativ, aber > 30 % daneben - '
                                 'neu rechnen mit konvektion.auto')
    else:
        stufe, txt = 'ok', f'Festwert {h} im Band h_c = {unten:.2f} .. h_c + h_r = {oben:.2f} (+-30 %)'
    if Ra > RA_LAMINAR[1]:
        stufe = 'warnung'
    return ergebnis('W1', 'h freie Konvektion', stufe, wert=h, grenze=round(h_k, 3), einheit='W/m2K', quelle=Q_W1,
                    teil=fall, hinweis=txt + '.' + zusatz, daten=daten)


def _w2(fall, spec, erg):
    rb = erg['randbedingungen']
    T_inf = rb['T_umgebung_C']
    Ts = erg['T_mittel_konvektion_C']
    eps, mit = _eps(erg)
    h_r = h_strahlung(eps, Ts, T_inf)
    h_lin = 4 * eps * SIGMA * (0.5 * (Ts + T_inf) + K0) ** 3
    daten = {'emission': eps, 'T_s_C': Ts, 'h_r_W_m2K': round(h_r, 3), 'h_r_4epsT3_W_m2K': round(h_lin, 3),
             'dT_max_K': round(erg['T_max_C'] - T_inf, 2)}
    if mit:
        st = rb['strahlung']
        daten.update({'himmel_anteil_mittel': st.get('himmel_anteil_mittel'),
                      'Q_strahlung_W': erg['energiebilanz']['Q_strahlung_W']})
        return ergebnis('W2', 'Strahlung', 'ok', wert=round(h_r, 3), einheit='W/m2K', quelle=Q_W2, teil=fall,
                        daten=daten, hinweis=f'Strahlung modelliert (eps = {eps}, T^4 in Elmer, Himmelsanteil '
                                             f'{st.get("himmel_anteil_mittel")}); Anteil an der Abgabe '
                                             f'{erg["energiebilanz"]["Q_strahlung_W"]:.4g} W')
    anteil = h_r / (rb['h_W_m2K'] + h_r) if rb['h_W_m2K'] + h_r > 0 else 0
    return ergebnis('W2', 'Strahlung', 'info', wert=round(h_r, 3), einheit='W/m2K', quelle=Q_W2, teil=fall,
                    daten=daten, hinweis=f'Strahlung nicht modelliert: h_r = {h_r:.2f} W/m2K (~{anteil:.0%} der '
                                         'Abgabe) fehlt -> Ergebnis zu warm (konservativ), sofern h sie nicht schon '
                                         'enthaelt. Lastfall "strahlung": {"emission": 0.9}')


def _w3(fall, spec, erg):
    eb = erg['energiebilanz']
    a = eb.get('abweichung')
    if a is None:
        return uebersprungen('W3', 'Energiebilanz', 'keine Waermequelle und keine Sonne im Lastfall', Q_W3, fall)
    stufe = 'ok' if abs(a) < 0.02 else ('warnung' if abs(a) < 0.05 else 'fehler')
    txt = (f'ein {eb["P_netz_W"] + eb["Q_sonne_W"]:.4g} W, aus {eb["Q_aus_W"]:.4g} W (Konvektion '
           f'{eb["Q_konvektion_W"]:.4g}, Strahlung {eb["Q_strahlung_W"]:.4g}, feste T {eb["Q_feste_temperatur_W"]:.4g})')
    if eb['P_nenn_W'] > 0 and abs(eb['P_netz_W'] - eb['P_nenn_W']) > 0.02 * eb['P_nenn_W']:
        stufe = 'fehler' if stufe == 'fehler' else 'warnung'
        txt += (f'; eingespeist {eb["P_netz_W"]:.4g} W statt {eb["P_nenn_W"]:.4g} W (Netzvolumen <> CAD-Volumen '
                'der Quelle > 2 %)')
    return ergebnis('W3', 'Energiebilanz', stufe, wert=round(100 * a, 3), grenze=2.0, einheit='%', quelle=Q_W3,
                    teil=fall, hinweis=txt, daten=eb)


def _wanddicke(pdir, spec, name):
    if spec.get('wand_mm'):
        return float(spec['wand_mm']), 'Lastfall wand_mm'
    for k in spec['koerper']:
        nm = k.get('name') or os.path.splitext(os.path.basename(k.get('step', '')))[0]
        if nm == name and 'step' in k:
            pr = _pruefung(pdir, os.path.splitext(os.path.basename(k['step']))[0])
            if pr and pr.get('wand_min_mm'):
                return float(pr['wand_min_mm']), 'out/*.pruefung.json wand_min_mm (duennste Stelle, konservativ)'
    return None, None


def _w4(pdir, fall, spec, erg):
    titel = 'Waermewiderstands-Netz'
    if spec.get('flaechen'):
        return uebersprungen('W4', titel, 'feste Temperaturflaechen: Netz nicht eindeutig (Waerme geht teils dorthin)',
                             Q_W4, fall)
    if erg['randbedingungen'].get('innenluft'):
        return uebersprungen('W4', titel, 'Innenluft modelliert: Netz Quelle-Luft-Wand nicht abgebildet', Q_W4, fall)
    ki = erg['koerper_info']
    quellen = [n for n, i in ki.items() if i['waerme_W'] > 0]
    if not quellen:
        return uebersprungen('W4', titel, 'keine Waermequelle', Q_W4, fall)
    n = max(quellen, key=lambda q: ki[q]['waerme_W'])
    q = ki[n]
    if q['material'] in DRUCKSTOFFE:
        return uebersprungen('W4', titel, f'Quelle {n} ist selbst Druckteil -> W8', Q_W4, fall)
    T_inf = erg['randbedingungen']['T_umgebung_C']
    P = sum(ki[x]['waerme_W'] for x in quellen)
    if not q['kontakt_mm2']:
        wand, A_c, t, k_w, tq = None, 0.0, 1e-3, 1.0, ''
    else:
        wand = max(q['kontakt_mm2'], key=q['kontakt_mm2'].get)
        A_c = q['kontakt_mm2'][wand] * 1e-6
        t_mm, tq = _wanddicke(pdir, spec, wand)
        if t_mm is None:
            return uebersprungen('W4', titel, f'Wanddicke von {wand} unbekannt (out/{wand}.pruefung.json oder '
                                              'Lastfall wand_mm)', Q_W4, fall)
        t = t_mm * 1e-3
        mat_w = ki[wand]['material']
        k_w = MATERIAL[mat_w]['waermeleitung_W_mK'] if mat_w in MATERIAL else None
        if k_w is None:
            return uebersprungen('W4', titel, f'Waermeleitung von {mat_w} unbekannt', Q_W4, fall)
    # h_r haengt von der Temperatur ab -> Fixpunkt (5 Schritte reichen, h_r aendert sich langsam)
    dT = q['T_mittel_C'] - T_inf
    h_pl = _h_ges(erg)
    for _ in range(6):
        h_q = _h_ges(erg, T_inf + dT) if erg['randbedingungen'].get('strahlung') else erg['randbedingungen']['h_W_m2K']
        dT = netz_quelle(P, h_q, q['A_konvektion_mm2'] * 1e-6, k_w, t, A_c, h_pl)
    dT_fem = q['T_mittel_C'] - T_inf
    abw = dT / dT_fem - 1 if dT_fem > 0 else None
    daten = {'quelle': n, 'P_W': P, 'wand': wand, 'wand_mm': round(t * 1e3, 3), 'wand_quelle': tq,
             'A_kontakt_mm2': round(A_c * 1e6, 1), 'A_frei_mm2': q['A_konvektion_mm2'], 'h_platte_W_m2K': round(h_pl, 3),
             'dT_netz_K': round(dT, 2), 'dT_elmer_mittel_K': round(dT_fem, 2)}
    if abw is None:
        return uebersprungen('W4', titel, 'Quelle nicht waermer als Umgebung', Q_W4, fall)
    stufe = 'ok' if abs(abw) <= 0.25 else 'warnung'
    hinw = f'Netz {dT:.1f} K vs. Elmer {dT_fem:.1f} K (mittlere Quellentemperatur), Abweichung {abw:+.0%}'
    if len(quellen) > 1:
        hinw += f'; {len(quellen)} Quellen als eine an {n} zusammengefasst'
    if stufe == 'warnung':
        hinw += ' -> Randbedingungen/Kontakt/Netz pruefen (Platte endlich? Waende nahe der Quelle?)'
    return ergebnis('W4', titel, stufe, wert=round(100 * abw, 1), grenze=25.0, einheit='%', quelle=Q_W4, teil=fall,
                    hinweis=hinw, daten=daten)


def _w5(fall, spec, erg):
    titel = 'Innenluft'
    il = erg['randbedingungen'].get('innenluft')
    fl = erg.get('flaechen_mm2', {})
    zu = fl.get('konvektion_ohne_sicht_nach_aussen')
    offen = zu is not None and zu > 0.05 * max(fl.get('konvektion', 0), 1e-9)
    if il and offen:
        # Hohlraum nur teilweise erfasst (z. B. Lueftungsschlitze): der Rest konvektiert weiter gegen T_umgebung
        return ergebnis('W5', titel, 'warnung', wert=zu, einheit='mm2', quelle=Q_W5, teil=fall, daten=il,
                        hinweis=f'Innenluft nur {il["V_mm3"]:.0f} mm3 erfasst, {zu:.0f} mm2 Innenflaechen ohne Sicht '
                                f'nach aussen konvektieren weiter gegen T_umgebung = '
                                f'{erg["randbedingungen"]["T_umgebung_C"]} C - Hohlraum offen? "innenluft.box" angeben')
    if il:
        e = il['eps_eff']
        k_chk = k_spalt(il['spalt_mm'] * 1e-3, il['T_mittel_C'] + K0, e, il['Nu'])
        zus = []
        if il['Ra_spalt'] > 1708:
            zus.append(f'Ra_delta = {il["Ra_spalt"]:.0f} > 1708: Zellkonvektion moeglich, Nu = 1 konservativ')
        if il['spalt_mm'] > 10:
            zus.append('Spalt > 10 mm: Nu = 1 konservativ')
        stufe = 'ok' if abs(k_chk - il['k_W_mK']) <= 0.02 * il['k_W_mK'] else 'warnung'
        return ergebnis('W5', titel, stufe, wert=il['k_W_mK'], grenze=round(k_chk, 5), einheit='W/mK', quelle=Q_W5,
                        teil=fall, daten=il,
                        hinweis=(f'Luft als Ersatzleiter: delta = {il["spalt_mm"]} mm ({il["spalt_quelle"]}), '
                                 f'eps_eff = {e}, T_m = {il["T_mittel_C"]} C' + ('; ' + '; '.join(zus) if zus else '')
                                 + ('' if stufe == 'ok' else '; k passt nicht zu T_m (Fixpunkt?)')))
    if zu is None:
        return uebersprungen('W5', titel, 'Ergebnis ohne Sichtpruefung - fem_waerme neu=true', Q_W5, fall)
    if offen:
        return ergebnis('W5', titel, 'warnung', wert=zu, einheit='mm2', quelle=Q_W5, teil=fall,
                        hinweis=f'{zu:.0f} mm2 Innenflaechen ohne Sicht nach aussen konvektieren gegen T_umgebung = '
                                f'{erg["randbedingungen"]["T_umgebung_C"]} C - ist das die Innenlufttemperatur? Sonst '
                                'ist die Innenluft waermer und das Ergebnis zu kalt. Lastfall "innenluft": true')
    return ergebnis('W5', titel, 'ok', wert=zu, einheit='mm2', quelle=Q_W5, teil=fall,
                    hinweis='kein geschlossener Hohlraum an Konvektionsflaechen (Innenflaechen sehen nach aussen)')


def _w7(pdir, fall, spec, erg):
    from .. import kennwerte
    out = []
    ki = erg['koerper_info']
    h = _h_ges(erg)
    for n, i in _druck_koerper(erg).items():
        A = i['A_konvektion_mm2'] + i['A_fest_mm2'] + sum(i['kontakt_mm2'].values())
        L_c = i['volumen_mm3'] / A * 1e-3 if A else None
        if not L_c:
            continue
        k = MATERIAL[i['material']]['waermeleitung_W_mK']
        Bi = biot(h, L_c, k)
        out.append(ergebnis('W7', f'Biot {n}', 'ok' if Bi < 1 / 6 else 'info', wert=round(Bi, 4), grenze=round(1 / 6, 4),
                            quelle=Q_W7, teil=fall,
                            hinweis=f'L_c = V/A = {L_c * 1e3:.2f} mm' + ('' if Bi < 1 / 6 else
                                    ': Temperatur im Teil ungleich - nur FEM, keine Einzelwert-Abschaetzung')))
    rcv, fehlt = 0.0, []
    for n, i in ki.items():
        if i['material'] == 'LUFT':
            rcv += 1.2 * 1005 * i['volumen_mm3'] * 1e-9
            continue
        c = kennwerte.wert(i['material'], 'cp_J_kgK')
        rho = MATERIAL.get(i['material'], {}).get('dichte_kg_m3')
        if c is None or rho is None:
            fehlt.append(n)
            continue
        rcv += rho * c * i['volumen_mm3'] * 1e-9
    A_k = erg['flaechen_mm2']['konvektion'] * 1e-6
    if rcv <= 0 or A_k <= 0 or h <= 0:
        out.append(uebersprungen('W7', 'Zeitkonstante', 'c_p fehlt fuer alle Koerper oder keine Konvektionsflaeche',
                                 Q_W7, fall))
        return out
    tau = zeitkonstante(rcv, h, A_k)
    t_last = spec.get('lastdauer_h') or projekt_soll(pdir).get('lastdauer_h')
    daten = {'tau_s': round(tau, 1), 'h_W_m2K': round(h, 3), 'rho_c_V_J_K': round(rcv, 3), 'ohne_c_p': fehlt}
    hinw = f'tau = {tau / 60:.1f} min, 3tau = {3 * tau / 60:.1f} min'
    if fehlt:
        hinw += f' (ohne {", ".join(fehlt)}: c_p unbekannt -> tau eher zu klein)'
    if t_last is None:
        out.append(ergebnis('W7', 'Zeitkonstante', 'info', wert=round(tau, 1), einheit='s', quelle=Q_W7, teil=fall,
                            daten=daten, hinweis=hinw + '; Lastdauer unbekannt (lastdauer_h) - stationaer ist die '
                                                        'obere Grenze (konservativ)'))
    else:
        ok = t_last * 3600 > 3 * tau
        out.append(ergebnis('W7', 'Zeitkonstante', 'ok' if ok else 'info', wert=round(tau, 1), grenze=round(t_last * 3600 / 3, 1),
                            einheit='s', quelle=Q_W7, teil=fall, daten=daten,
                            hinweis=hinw + (f'; Lastdauer {t_last} h > 3tau: stationaer wird erreicht' if ok else
                                            f'; Lastdauer {t_last} h < 3tau: stationaer ueberschaetzt (konservativ)')))
    return out


def _w8(fall, spec, erg):
    out = []
    for n, i in erg['koerper_info'].items():
        if i['waerme_W'] <= 0:
            continue
        k = MATERIAL.get(i['material'], {}).get('waermeleitung_W_mK')
        if not k or i['volumen_mm3'] <= 0:
            out.append(uebersprungen('W8', f'Quelle im Koerper {n}', 'Waermeleitung unbekannt', Q_W8, fall))
            continue
        q3 = i['waerme_W'] / (i['volumen_mm3'] * 1e-9)
        L = min(i['bbox_mm']) * 1e-3
        dT = dT_quelle(q3, L, k)
        dT_fem = i['T_max_C'] - i['T_min_C']
        out.append(ergebnis('W8', f'Quelle im Koerper {n}', 'info', wert=round(dT, 3), einheit='K', quelle=Q_W8,
                            teil=fall, daten={'q3_W_m3': round(q3, 1), 'L_mm': round(L * 1e3, 3),
                                              'dT_elmer_K': round(dT_fem, 3), 'verhaeltnis': round(dT_fem / dT, 2)
                                              if dT > 0 else None},
                            hinweis=f'q*L^2/8k = {dT:.3g} K (beidseitig gekuehlt; einseitig 4x = {4 * dT:.3g} K), '
                                    f'Elmer T_max - T_min im Koerper {dT_fem:.3g} K'))
    return out


def _w6(pdir, faelle):
    titel = 'Sonne'
    pj = projekt_soll(pdir)
    sonnen = [(f, s, e) for f, s, e in faelle if s.get('sonne') and e]
    out = []
    for f, s, e in sonnen:
        so = e['randbedingungen'].get('sonne', {})
        out.append(ergebnis('W6', 'Sonne im FEM', 'info', wert=so.get('P_W'), einheit='W', quelle=Q_W6, teil=f,
                            daten=so, hinweis=f'Elmer mit Sonne: T_max {e["T_max_C"]} C, absorbiert {so.get("P_W")} W '
                                              f'auf {so.get("A_proj_mm2")} mm2 Projektion (mit Abschattung)'))
    from .. import realterme as rt
    k = rt.kontext(pdir, soll=soll(pdir))
    if not k.get('aussen'):
        # aussen nur aus Merkmalen (Stichwort, T_min < 5, Funkstrecke) setzt kontext() schon; sonst wirklich innen
        out.append(uebersprungen('W6', titel, 'Teil nicht aussen (soll.json _projekt.aussen)', Q_W6))
        return out
    aussen_ang = pj.get('aussen') is None          # nur aus Projektmerkmalen erkannt
    # Geometrie: erster Waerme-Lastfall, sonst groesstes Teil aus out/*.pruefung.json
    bb, A_mod = None, None
    for f, s, e in faelle:
        if e and e.get('geometrie'):
            bb = e['geometrie']['bbox_mm']
            break
    if bb is None:
        prs = [p for p in (_json(x) for x in glob.glob(os.path.join(pdir, 'out', '*.pruefung.json'))) if p]
        if prs:
            bb = max((p['bbox_mm'] for p in prs if p.get('bbox_mm')), key=lambda b: b[0] * b[1] * b[2], default=None)
    if bb is None:
        out.append(uebersprungen('W6', titel, 'keine Geometrie (kein Waerme-Lastfall, kein Pruefbericht)', Q_W6))
        return out
    x, y, z = (v * 1e-3 for v in bb)
    A_proj = math.sqrt((x * y) ** 2 + (y * z) ** 2 + (x * z) ** 2)     # unguenstigste Sonnenrichtung auf die Box
    A_ges = 2 * (x * y + y * z + x * z)
    stufe_min = 'warnung' if aussen_ang else 'ok'
    if pj.get('absorption') is not None:
        alpha, aq = float(pj['absorption']), 'soll.json absorption'
    else:
        farbe = str(pj.get('farbe', '')).lower()
        for u, a in (('\u00e4', 'ae'), ('\u00f6', 'oe'), ('\u00fc', 'ue'), ('\u00df', 'ss')):
            farbe = farbe.replace(u, a)
        # zuerst dieselbe Tabelle wie D1 (realterme), dann die feinere hier
        alpha = rt.ALPHA_FARBE.get(farbe) or next((v for k_, v in ABSORPTION.items() if k_ == farbe), None)
        if alpha is None:
            alpha = next((v for k_, v in ABSORPTION.items() if k_ in farbe), None)
        aq = f'Farbe {farbe}'
        if alpha is None:
            alpha, aq, stufe_min = rt.ALPHA_UNBEKANNT, f'Farbe "{farbe}" unbekannt -> {rt.ALPHA_UNBEKANNT} angenommen', \
                'warnung'
    T_umg = pj.get('T_max_C')
    tq = 'soll T_max_C'
    if T_umg is None:
        T_umg = max((e['randbedingungen']['T_umgebung_C'] for f, s, e in faelle if e and e.get('randbedingungen')),
                    default=None)
        tq = 'T_umgebung aus FEM'
        stufe_min = 'warnung'
    if T_umg is None:
        T_umg = rt.teil_temperatur(dict(k, aussen=False))[0]       # Luft allein: 40 C mit Elektronik, sonst 30 C
        tq = 'Luft angenommen (realterme, T_max_C fehlt)'
        stufe_min = 'warnung'
    L = z or max(x, y)
    dT = 10.0
    for _ in range(30):                                   # dT = Q/((h_c(dT) + h_r(dT)) A)
        h = h_frei_strahlung(dT, L, EPS_STANDARD, T_umg)
        dT = dT_sonne(alpha, G_SONNE, A_proj, h, A_ges)
    dT_int = max((e['T_max_C'] - e['randbedingungen']['T_umgebung_C'] for f, s, e in faelle
                  if e and e.get('randbedingungen') and not s.get('sonne')), default=0.0)
    mat = pj.get('material') or next((i['material'] for f, s, e in faelle if e for i in
                                      _druck_koerper(e).values()), None)
    if mat not in MATERIAL:
        # wie D1: Material je Teil (soll/FEM/Slice), das mit der niedrigsten Tg zaehlt
        from .dauer import material_von, teile as _teile
        ms = [m_ for m_ in (material_von(pdir, t)[0] for t in _teile(pdir)) if m_ in MATERIAL]
        mat = min(ms, key=lambda m_: MATERIAL[m_].get('glasuebergang_C', 1e9), default=mat)
    if mat not in MATERIAL or 'glasuebergang_C' not in MATERIAL[mat]:
        out.append(uebersprungen('W6', titel, 'Druckstoff unbekannt (soll.json _projekt.material)', Q_W6))
        return out
    from .dauer import d1_stufe
    Tg = MATERIAL[mat]['glasuebergang_C']
    T_geo = T_umg + dT + dT_int
    # Dieselbe Teiltemperatur wie D1 (realterme: Luft + alpha G / 25 W/m2K + intern); es gilt die waermere
    T_rt, terme_rt, _ = rt.teil_temperatur(dict(k, T_max_C=T_umg), dT_eigen_K=dT_int)
    T_ges = max(T_geo, T_rt)
    dT_rt = rt.sonne_dT(k)[0]
    # Grenze wie D1 (Befund Scheinsicherheit 15.11.2026: W6 meldete fehler erst ab Tg - 10, D1 schon ab Tg - 20;
    # unter Dauerlast liegt die HDT von PLA bei ~55 C)
    grenze = Tg - 20
    stufe = d1_stufe(Tg - T_ges)
    if stufe == 'ok' and stufe_min == 'warnung':
        stufe = 'warnung'
    out.append(ergebnis('W6', titel, stufe, wert=round(T_ges, 1), grenze=grenze, einheit='C', quelle=Q_W6,
                        daten={'alpha': alpha, 'alpha_quelle': aq, 'A_proj_mm2': round(A_proj * 1e6, 1),
                               'A_ges_mm2': round(A_ges * 1e6, 1), 'h_ges_W_m2K': round(h, 3),
                               'dT_sonne_K': round(dT, 2), 'dT_sonne_realterme_K': round(dT_rt, 2),
                               'T_geometrie_C': round(T_geo, 2), 'T_realterme_C': round(T_rt, 2),
                               'dT_intern_K': round(dT_int, 2), 'T_umgebung_C': T_umg,
                               'T_umgebung_quelle': tq, 'material': mat, 'Tg_C': Tg},
                        hinweis=f'{T_umg} C ({tq}) + Sonne {dT:.1f} K (alpha = {alpha}, {aq}, unguenstigste Richtung '
                                f'auf die Bounding Box) + intern {dT_int:.1f} K = {T_geo:.1f} C; D1-Teiltemperatur '
                                f'{T_rt:.1f} C ({rt.hinweis(terme_rt)}); es gilt {T_ges:.1f} C. Regel wie D1: Tg - T '
                                f'>= 30 K ok, >= 20 K warnung, sonst fehler (Grenze {grenze} C)'
                                + ('; aussen nur aus Projektmerkmalen erkannt' if aussen_ang else '')))
    return out


def _w9(pdir, faelle):
    s = soll(pdir)
    rippen = [(t, r) for t, v in s.items() if t != '_projekt' and isinstance(v, dict) for r in v.get('rippen', [])]
    rippen += [(f, r) for f, sp, e in faelle for r in sp.get('rippen', [])]
    if not rippen:
        return [uebersprungen('W9', 'Rippen-Wirkungsgrad', 'keine Rippen angegeben (soll.json/Lastfall "rippen")', Q_W9)]
    h_fem = next((_h_ges(e) for f, sp, e in faelle if e and e.get('randbedingungen')), None)
    mat_p = projekt_soll(pdir).get('material')
    out = []
    for teil, r in rippen:
        mat = r.get('material') or (s.get(teil, {}) if isinstance(s.get(teil), dict) else {}).get('material') or mat_p
        k = MATERIAL.get(str(mat).upper(), {}).get('waermeleitung_W_mK') if mat else None
        if k is None or not all(r.get(x) for x in ('L_mm', 't_mm', 'b_mm')):
            out.append(uebersprungen('W9', f'Rippe {r.get("name", "")}', 'L_mm/t_mm/b_mm oder Material fehlt', Q_W9,
                                     teil))
            continue
        h, hq = (r['h_W_m2K'], 'Rippe') if r.get('h_W_m2K') else ((h_fem, 'FEM') if h_fem else
                                                                    (h_frei_strahlung(20, r['L_mm'] * 1e-3, 0.9, 25),
                                                                     'W1+W2 bei 20 K'))
        eta = rippe_eta(h, k, r['t_mm'] * 1e-3, r['b_mm'] * 1e-3, r['L_mm'] * 1e-3)
        out.append(ergebnis('W9', f'Rippe {r.get("name", "")}', 'ok' if eta >= 0.5 else 'warnung', wert=round(eta, 3),
                            grenze=0.5, quelle=Q_W9, teil=teil,
                            hinweis=f'h = {h:.2f} W/m2K ({hq}), k = {k}' + ('' if eta >= 0.5 else
                                    ': Rippe lohnt nicht - kuerzer/dicker oder Flaeche anders vergroessern')))
    return out


def _ini(pfad):
    werte = {}
    try:
        for z in open(pfad, encoding='utf-8', errors='replace'):
            m = re.match(r'\s*([a-z_0-9]+)\s*=\s*(.*)$', z)
            if m:
                werte[m.group(1)] = m.group(2).strip()
    except OSError:
        pass
    return werte


def _zahl(s):
    try:
        return float(str(s).split(',')[0].split(';')[0].replace('%', ''))
    except (TypeError, ValueError):
        return None


def _w10(pdir):
    from .. import kennwerte
    titel = 'Abkuehlung beim Druck'
    sl = _json(os.path.join(pdir, 'print', 'slice.json'))
    if not sl:
        return [uebersprungen('W10', titel, 'nicht gesliced (print/slice.json fehlt)', Q_W10)]
    pj = projekt_soll(pdir)
    h = pj.get('h_luefter_W_m2K')
    if not h:
        return [uebersprungen('W10', titel, 'h des Bauteil-Luefters unbekannt (soll.json _projekt.h_luefter_W_m2K, '
                                            'am MK4 zu messen) - ohne ihn keine belastbare Abkuehlzeit', Q_W10)]
    cfg = _ini(sl.get('config', '')) if sl.get('config') else {}
    st = sl.get('stats', {})
    t_min = _zahl(cfg.get('slowdown_below_layer_time'))
    v_min = _zahl(cfg.get('min_print_speed'))
    T_d = _zahl(cfg.get('temperature'))
    h_s = _zahl(st.get('layer_height') or cfg.get('layer_height'))
    mat = str(st.get('filament_type') or pj.get('material') or '').upper()
    if None in (t_min, T_d, h_s) or mat not in MATERIAL:
        return [uebersprungen('W10', titel, 'Slicer-Werte (slowdown_below_layer_time, temperature, layer_height) '
                                            'oder Material fehlen', Q_W10)]
    m = MATERIAL[mat]
    c = kennwerte.wert(mat, 'cp_J_kgK')
    if c is None:
        return [uebersprungen('W10', titel, f'c_p von {mat} unbekannt', Q_W10)]
    T_bau = pj.get('T_bauraum_C', 25.0)
    Tg = m['glasuebergang_C']
    t_ab = abkuehlzeit_schicht(m['dichte_kg_m3'], c, h_s * 1e-3, h, T_d, T_bau, Tg)
    a = m['waermeleitung_W_mK'] / (m['dichte_kg_m3'] * c)
    Bi = biot(h, h_s * 1e-3, m['waermeleitung_W_mK'])
    out = []
    for p in sorted(glob.glob(os.path.join(pdir, 'out', '*.pruefung.json'))):
        pr = _json(p)
        if not pr or not pr.get('bbox_mm') or not pr.get('volumen_mm3'):
            continue
        teil = os.path.basename(p).split('.')[0]
        H = pr['bbox_mm'][2]
        A_schicht = pr['volumen_mm3'] / H if H else 0             # mittlerer Querschnitt
        weg = A_schicht / (1.125 * 0.4)                           # Linienbreite 0,45 mm
        t_s = min(t_min, weg / v_min) if v_min else t_min         # Slicer bremst nicht unter min_print_speed
        Fo = a * t_s / (h_s * 1e-3) ** 2
        stufe = 'ok' if t_s >= t_ab else 'warnung'
        out.append(ergebnis('W10', titel, stufe, wert=round(t_s, 2), grenze=round(t_ab, 2), einheit='s', quelle=Q_W10,
                            teil=teil, daten={'Bi_schicht': round(Bi, 3), 'Fo': round(Fo, 2), 'A_schicht_mm2':
                                              round(A_schicht, 1), 'h_W_m2K': h, 'T_duese_C': T_d, 'Tg_C': Tg},
                            hinweis=f'Schichtzeit >= {t_s:.1f} s (Mindestzeit {t_min} s, min. {v_min} mm/s), '
                                    f'Abkuehlung bis Tg {t_ab:.1f} s (Bi = {Bi:.2f}'
                                    + (', > 1/6: Schicht nicht isotherm' if Bi > 1 / 6 else '') + ')'))
    return out or [uebersprungen('W10', titel, 'keine Pruefberichte out/*.pruefung.json', Q_W10)]


# ---------------------------------------------------------------- Einstieg

def pruefe(pdir):
    faelle = waerme_faelle(pdir)
    out = []
    if not faelle:
        for i, t in (('W1', 'h freie Konvektion'), ('W2', 'Strahlung'), ('W3', 'Energiebilanz'),
                     ('W4', 'Waermewiderstands-Netz'), ('W5', 'Innenluft'), ('W7', 'Biot, Zeitkonstante'),
                     ('W8', 'Quelle im Koerper')):
            out.append(uebersprungen(i, t, 'kein Waerme-Lastfall (fem/*.json mit Waerme)', globals()['Q_' + i]))
    for fall, spec, erg in faelle:
        if not erg or 'energiebilanz' not in erg or 'koerper_info' not in erg:
            grund = 'nicht gerechnet' if not erg else 'Ergebnis aelter als die Pruefung - fem_waerme neu=true'
            for i, t in (('W1', 'h freie Konvektion'), ('W2', 'Strahlung'), ('W3', 'Energiebilanz'),
                         ('W4', 'Waermewiderstands-Netz'), ('W5', 'Innenluft'), ('W7', 'Biot, Zeitkonstante'),
                         ('W8', 'Quelle im Koerper')):
                out.append(uebersprungen(i, t, grund, globals()['Q_' + i], fall))
            continue
        for f in (_w1, _w2, _w3, _w5, _w8):
            r = f(fall, spec, erg)
            out += r if isinstance(r, list) else [r]
        out.append(_w4(pdir, fall, spec, erg))
        out += _w7(pdir, fall, spec, erg)
    gueltig = [(f, s, e) for f, s, e in faelle if e and 'energiebilanz' in e]
    out += _w6(pdir, gueltig)
    out += _w9(pdir, gueltig)
    out += _w10(pdir)
    return out
