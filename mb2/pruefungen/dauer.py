"""Werkstoff, Dauerlast, Temperatur (OCW_PRUEFKATALOG.md Abschnitt 3.4, D1-D12).

Alle Pruefungen sind analytisch (keine FEM-Laeufe). Einheiten: mm, N, MPa, K bzw. C, h.

Eingaben (alle optional, fehlt etwas -> 'uebersprungen' mit Grund):
- Temperatur je Teil: aus fem/*.erg.json (Waerme, T_max_je_koerper_C). Zuordnung Koerper -> Teil ueber den
  STEP-Namen in fem/<fall>.json (out/<teil>.step) oder den Koerpernamen; sonst Maximum aller gedruckten Koerper
  (konservativ). Liegt soll._projekt.T_max_C ueber der Umgebung der FEM, wird die Eigenerwaermung darauf addiert
  (lineare Waermeleitung: Temperaturhub unabhaengig von der Umgebung). Ohne Waerme-FEM: soll._projekt.T_max_C.
  Daraus macht realterme.teil_temperatur die EINE Teiltemperatur (plus Sonne bei aussen; ohne Luftangabe 40 C mit
  Elektronik bzw. 30 C angenommen -> D1/D4 hoechstens 'warnung', ein 'fehler' bleibt 'fehler').
- D4 ohne Kriechkennwerte (PLA/PETG): Restvorspannung 0,5 F0 / A_T angenommen, hoechstens 'warnung'.
- Ohne dauerlast/schrauben in irgendeinem Teil: je ein projektweites 'uebersprungen' D2/D3/D7/D12 bzw. D4.
- soll._projekt: material, T_max_C, T_min_C, T_mittel_C, T_tagesgang_K (Spanne Spitze-Spitze), lebensdauer_h,
  T_bauraum_C (Druckraum, Standard 25), platine_spalt_mm (Spalt je Seite Platine <-> Wand bei 23 C),
  platine_schraube_d_mm, kennwerte (Projekt-Ueberschreibung {"PETG": {"kriech_tau_h": [1000, "Quelle"]}}),
  kriechbruch ({"PETG": {"eps0_1_h", "s_MPa", "n", "Q_kJ_mol", "C_MG"}}).
- je Teil: material, druckrichtung, dauerlast {"dauer_h", "durchbiegung_mm" | "fem": "fall[/lastfall]",
  "sigma_MPa", "dehnung", "durchbiegung_zul_mm", "richtung": "xy"|"z", "geschichte": [{"t_h", "sigma_MPa"}]},
  schrauben [{"vorspannung_N", "klemmkraft_min_N"}], zwang {"partner": "FR4"|"ALU"|"STARR", "alpha_partner_1_K",
  "dT_K", "art": "voll"|"bimetall", "t_mm", "t_partner_mm", "L_mm", "E_partner_MPa", "durchbiegung_zul_mm"},
  zyklen, wechsellast {"sigma_max_MPa" | "fem": "fall[/lastfall]", "sigma_min_MPa" | "R", "k_faktor",
  "zuverlaessigkeit", "richtung"}, kriechbruch (wie oben, je Teil), sicherheit (Standard 2).
"""
import glob
import json
import math
import os
import statistics

from .. import kennwerte as kw
from .. import material as mat
from .. import realterme as rt
from . import ergebnis, soll as lade_soll, uebersprungen

R_GAS = 8.314          # J/(mol K)
T_REF_C = 23.0         # Bezugstemperatur der Kennwerte
T_MONTAGE_C = 23.0     # Montage-/Raumtemperatur
T_BAURAUM_C = 25.0     # offener MK4, Raumluft am Teil
K0 = 273.15
S_STANDARD = 2.0
# D4 ohne Kriechkennwerte: Restvorspannung am Lebensende 0,5 F0 (ASA gemessen: Kriechmodul 1000 h / E0 = 900/2000 =
# 0,45..0,48; PLA/PETG kriechen eher staerker), zusaetzlich durch A_T aus realterme geteilt (Audit 15.11.2026, M12/D4)
D4_REST_ANNAHME = 0.5

Q_LABOR = '2.002 Labor 2 Polymer-Viskoelastik (OCW)'
Q_SLS = '2.002 Labor 2, 3.064 lec_8/10-12 (OCW)'
Q_WLF = '3.064 lec_14 (OCW)'
Q_BOLTZ = '3.064 lec_16 (OCW)'
Q_DEHN = '2.75 Topic 4, 2.001 L14 (OCW)'
Q_ERM = '2.72 L04, 2.002 L20-22 (OCW)'
Q_KRIECH = '2.002 L14a/b/15 (OCW, Metalle)'


# ---------------------------------------------------------------- gemeinsame Helfer (auch fuer toleranz.py)

def _json(p):
    try:
        return json.load(open(p, encoding='utf-8'))
    except (OSError, ValueError):
        return None


def teile(pdir):
    """Teilname -> {'soll': dict, 'pruefung': dict|None}. Aus soll.json (ohne _projekt) und out/*.pruefung.json."""
    s = lade_soll(pdir)
    t = {k: {'soll': v if isinstance(v, dict) else {}, 'pruefung': None} for k, v in s.items() if not k.startswith('_')}
    for p in glob.glob(os.path.join(pdir, 'out', '*.pruefung.json')):
        name = os.path.basename(p)[:-len('.pruefung.json')]
        t.setdefault(name, {'soll': {}, 'pruefung': None})['pruefung'] = _json(p)
    if not t:       # reines FEM-Projekt: gedruckte FEM-Koerper als Teile
        for _, ein, _ in fem_faelle(pdir):
            for k in ein.get('koerper', []):
                if k.get('material') in mat.DRUCKSTOFFE:
                    t.setdefault(_koerper_teil(k), {'soll': {}, 'pruefung': None})
    return dict(sorted(t.items()))


def fem_faelle(pdir):
    """[(fall, eingabe, ergebnis)] aller fem/*.erg.json (nur oberste Ebene, 'veraltet/' nicht)."""
    out = []
    for p in sorted(glob.glob(os.path.join(pdir, 'fem', '*.erg.json'))):
        fall = os.path.basename(p)[:-len('.erg.json')]
        erg = _json(p)
        if erg is None:
            continue
        out.append((fall, _json(os.path.join(pdir, 'fem', fall + '.json')) or {}, erg))
    return out


def _koerper_teil(k):
    """Teilname eines FEM-Koerpers: Name der STEP-Datei, sonst Koerpername."""
    st = k.get('step')
    return os.path.splitext(os.path.basename(st))[0] if st else k.get('name')


def material_von(pdir, teil, s=None):
    """(Material, Herkunft) oder (None, Grund)."""
    s = s if s is not None else lade_soll(pdir)
    ts = s.get(teil, {}) if isinstance(s.get(teil), dict) else {}
    if ts.get('material'):
        return str(ts['material']).upper(), f'soll.json {teil}.material'
    if s.get('_projekt', {}).get('material'):
        return str(s['_projekt']['material']).upper(), 'soll.json _projekt.material'
    for fall, ein, _ in fem_faelle(pdir):
        for k in ein.get('koerper', []):
            if teil in (_koerper_teil(k), k.get('name')) and k.get('material') in mat.DRUCKSTOFFE:
                return k['material'], f'fem/{fall}.json'
    sl = _json(os.path.join(pdir, 'print', 'slice.json')) or {}
    ft = (sl.get('stats') or {}).get('filament_type')
    if ft in mat.DRUCKSTOFFE:
        return ft, 'print/slice.json filament_type'
    return None, 'kein Material (soll.json material, FEM-Koerper oder print/slice.json)'


def kennwert(pdir, material, feld, s=None):
    """(wert, quelle) - Projekt-Ueberschreibung in soll._projekt.kennwerte vor mb2/kennwerte.py; (None, None)."""
    s = s if s is not None else lade_soll(pdir)
    ub = (s.get('_projekt', {}).get('kennwerte') or {}).get(material, {})
    if feld in ub:
        v = ub[feld]
        if isinstance(v, (list, tuple)):
            return float(v[0]), f'soll.json _projekt.kennwerte ({v[1] if len(v) > 1 else "ohne Quelle"})'
        return float(v), 'soll.json _projekt.kennwerte (ohne Quelle)'
    if feld in kw.FELDER:
        w = kw.wert(material, feld)
        if w is not None:
            return w, f'kennwerte.py: {kw.quelle(material, feld)}'
    return None, None


def temperatur(pdir, teil, s=None):
    """{'T_max_C', 'dT_eigen_K', 'herkunft'} oder None. Siehe Modulkopf."""
    s = s if s is not None else lade_soll(pdir)
    pj = s.get('_projekt', {})
    T_proj = pj.get('T_max_C')
    best = None
    for fall, ein, erg in fem_faelle(pdir):
        je = erg.get('T_max_je_koerper_C')
        if not je:
            continue
        T_umg = (ein.get('konvektion') or {}).get('T_umgebung_C', erg.get('T_min_C', 25.0))
        kandid, eigen = [], False
        for k in ein.get('koerper', []):
            if k.get('name') not in je:
                continue
            if teil in (_koerper_teil(k), k.get('name')):
                kandid.append(je[k['name']])
                eigen = True
        if not eigen:   # Teil nicht im Fall: alle gedruckten Koerper (konservativ, gleiches Gehaeuse angenommen)
            kandid = [je[k['name']] for k in ein.get('koerper', [])
                      if k.get('name') in je and k.get('material') in mat.DRUCKSTOFFE]
        if not kandid:
            continue
        T = max(kandid)
        dT = T - T_umg
        if T_proj is not None:
            T = max(T, T_proj + dT)
        h = f'fem/{fall}.erg.json ({"Koerper " + teil if eigen else "max. gedruckter Koerper"}, Eigenerwaermung ' \
            f'{dT:.1f} K' + (f', auf T_max_C {T_proj} C umgerechnet' if T_proj is not None else '') + ')'
        if best is None or T > best['T_max_C'] or (eigen and not best['_eigen'] and T >= best['T_max_C']):
            best = {'T_max_C': round(T, 2), 'dT_eigen_K': round(dT, 2), 'herkunft': h, '_eigen': eigen}
    if best:
        best.pop('_eigen')
        return best
    if T_proj is not None:
        return {'T_max_C': float(T_proj), 'dT_eigen_K': 0.0, 'herkunft': 'soll.json _projekt.T_max_C (ohne Eigenerwaermung)'}
    return None


def fem_lastfall(pdir, ref):
    """'fall' oder 'fall/lastfall' -> (lastfall-dict, text) oder (None, Grund). Ohne Lastfall: der ungguenstigste."""
    fall, _, last = str(ref).partition('/')
    erg = _json(os.path.join(pdir, 'fem', fall + '.erg.json'))
    if not erg or not erg.get('lastfaelle'):
        return None, f'fem/{fall}.erg.json fehlt oder hat keine Lastfaelle'
    lf = erg['lastfaelle']
    if last:
        return (lf[last], f'fem/{fall}/{last}') if last in lf else (None, f'Lastfall {last} nicht in fem/{fall}')
    k = max(lf, key=lambda n: lf[n].get('max_vonMises_MPa', 0))
    return lf[k], f'fem/{fall}/{k} (ungguenstigster von {len(lf)})'


def drucker_bbox(pruefung):
    """Bounding Box in Druckrichtung (Drehung aus pruefung.json, Grad um X, Y, Z) -> (x, y, z)."""
    if not pruefung or 'bbox_mm' not in pruefung:
        return None
    bx = pruefung['bbox_mm']
    rx, ry, rz = (math.radians(a) for a in (pruefung.get('druck_drehung') or (0, 0, 0)))

    def rot(p):
        x, y, z = p
        y, z = y * math.cos(rx) - z * math.sin(rx), y * math.sin(rx) + z * math.cos(rx)
        x, z = x * math.cos(ry) + z * math.sin(ry), -x * math.sin(ry) + z * math.cos(ry)
        x, y = x * math.cos(rz) - y * math.sin(rz), x * math.sin(rz) + y * math.cos(rz)
        return x, y, z
    ecken = [rot((sx * bx[0] / 2, sy * bx[1] / 2, sz * bx[2] / 2)) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    return tuple(round(max(e[i] for e in ecken) - min(e[i] for e in ecken), 3) for i in range(3))


# ---------------------------------------------------------------- Formeln (rein, ohne Dateien; fuer Gegentests)

def sls_verhaeltnis(t_h, r_inf, tau_h):
    """Standard Linear Solid: E_r(t)/E_0 = r + (1 - r) e^(-t/tau)."""
    return r_inf + (1.0 - r_inf) * math.exp(-t_h / tau_h)


def sls_nachgiebigkeit(t_h, E0, r_inf, tau_h):
    """Kriechnachgiebigkeit J(t) des SLS [1/MPa]; Retardationszeit tau_c = tau * E0/E_inf."""
    E_inf = r_inf * E0
    tau_c = tau_h / r_inf
    return 1.0 / E_inf - (1.0 / E_inf - 1.0 / E0) * math.exp(-t_h / tau_c)


def log10_aT(T_C, Tg_C, U_kJ_mol=None, T_ref_C=T_REF_C):
    """Verschiebungsfaktor log10 a_T gegen T_ref (a_T < 1 = schneller). Unter Tg Arrhenius, ueber Tg Arrhenius bis
    Tg + WLF ab Tg (C1 = 17,44, C2 = 51,6 K). None, wenn U fehlt (und T > T_ref)."""
    def arr(T):
        return U_kJ_mol * 1e3 / (R_GAS * math.log(10)) * (1 / (T + K0) - 1 / (T_ref_C + K0))
    if U_kJ_mol is None:
        return None
    if T_C <= Tg_C:
        return arr(T_C)
    return arr(Tg_C) + (-17.44 * (T_C - Tg_C) / (51.6 + T_C - Tg_C))


def effektive_zeit(t_h, T_avg_C, spanne_K, Tg_C, U_kJ_mol, n=720):
    """t' = Int dxi / a_T(T(xi)) ueber ganze Tage; T(xi) = T_avg + spanne/2 * sin(2 pi xi / 24 h).
    Ueber eine Periode gemittelt (Mittelpunktsregel, n Stuetzstellen), dann mal t."""
    if spanne_K == 0:
        return t_h / 10 ** log10_aT(T_avg_C, Tg_C, U_kJ_mol)
    m = sum(1.0 / 10 ** log10_aT(T_avg_C + spanne_K / 2 * math.sin(2 * math.pi * (i + 0.5) / n), Tg_C, U_kJ_mol)
            for i in range(n)) / n
    return t_h * m


def boltzmann_dehnung(geschichte, t_h, J):
    """eps(t) = Sum dsigma_i J(t - t_i) fuer Spannungsstufen [(t_i, sigma_i)]."""
    eps, vor = 0.0, 0.0
    for ti, si in sorted(geschichte):
        if ti > t_h:
            break
        eps += (si - vor) * J(t_h - ti)
        vor = si
    return eps


def bimetall_kruemmung(d_alpha, dT, t1, t2, E1, E2):
    """Timoshenko: kappa = 6 da dT (1+m)^2 / (h (3(1+m)^2 + (1+mn)(m^2 + 1/(mn)))), m = t1/t2, n = E1/E2 [1/mm]."""
    m, n, h = t1 / t2, E1 / E2, t1 + t2
    return 6 * d_alpha * dT * (1 + m) ** 2 / (h * (3 * (1 + m) ** 2 + (1 + m * n) * (m * m + 1 / (m * n))))


def wechselfestigkeit(N, S_ut, S_e):
    """S_f(N): N <= 1e3 -> 0,9 S_ut; 1e3..1e6 Basquin log-log zwischen (1e3, 0,9 S_ut) und (1e6, S_e); darueber S_e."""
    if N <= 1e3:
        return 0.9 * S_ut
    if N >= 1e6:
        return S_e
    b = -math.log10(0.9 * S_ut / S_e) / 3.0
    return 0.9 * S_ut * (N / 1e3) ** b


def goodman_n(sa, sm, S_f, S_ut):
    """1/n = sigma_a/S_f + sigma_m/S_ut."""
    d = sa / S_f + max(sm, 0.0) / S_ut
    return math.inf if d <= 0 else 1.0 / d


# ---------------------------------------------------------------- Bausteine je Teil

def _stufe_n(n, grenze=S_STANDARD):
    return 'ok' if n >= grenze else ('warnung' if n >= 1.0 else 'fehler')


def _schlechter(a, b):
    rang = {'ok': 0, 'info': 0, 'uebersprungen': 0, 'warnung': 1, 'fehler': 2}
    return a if rang[a] >= rang[b] else b


def _richtungs_stufe(n_xy, n_z, richtung, grenze):
    """Stufe nach Lastrichtung; ohne Angabe gilt XY, aber Z unter der Grenze -> mindestens 'warnung'."""
    if richtung == 'z':
        return _stufe_n(n_z, grenze)
    st = _stufe_n(n_xy, grenze)
    if richtung != 'xy' and n_z < grenze:
        st = _schlechter(st, 'warnung')
    return st


class _Kriechen:
    """Kriechverhalten eines Materials am Teil: E0, Verhaeltnis E_r(t')/E0, effektive Zeit."""

    def __init__(self, pdir, s, material, temp):
        self.material, self.temp = material, temp
        self.E0 = mat.MATERIAL[material]['E_MPa']
        self.Tg = mat.MATERIAL[material]['glasuebergang_C']
        g = lambda f: kennwert(pdir, material, f, s)  # noqa: E731
        self.r, self.q_r = g('kriech_E_inf_zu_E0')
        self.tau, self.q_tau = g('kriech_tau_h')
        self.E1000, self.q_1000 = g('kriechmodul_1000h_MPa')
        self.U, self.q_U = g('aktivierung_U_kJ_mol')
        pj = s.get('_projekt', {})
        self.T_mittel, self.spanne = pj.get('T_mittel_C'), pj.get('T_tagesgang_K')

    def zeit(self, t_h):
        """(t', text, nicht_konservativ). Temperaturprofil: T_mittel + Eigenerwaermung mit Tagesgang (D6), sonst
        dauernd T_max (konservativ)."""
        T_max = self.temp['T_max_C'] if self.temp else None
        if T_max is None:
            return t_h, f'keine Temperatur bekannt, t bei {T_REF_C:.0f} C', True
        if self.U is None:
            if T_max <= T_REF_C:
                return t_h, f'T_max {T_max} C <= {T_REF_C:.0f} C, ohne Verschiebung (konservativ)', False
            if T_max > self.Tg:
                return t_h, 'ueber Tg, aber U fehlt', True
            return t_h, f'U fehlt: T_max {T_max} C nicht verschoben (nicht konservativ)', True
        if self.T_mittel is not None and self.spanne is not None:
            Tm = self.T_mittel + self.temp['dT_eigen_K']
            tp = effektive_zeit(t_h, Tm, float(self.spanne), self.Tg, self.U)
            return tp, f"t' {tp:.0f} h aus Tagesgang {Tm:.1f} +/- {self.spanne / 2:.1f} C (D6)", False
        aT = 10 ** log10_aT(T_max, self.Tg, self.U)
        return t_h / aT, f"t' = t/a_T bei dauernd T_max {T_max} C, a_T = {aT:.3g}", False

    def verhaeltnis(self, t_eff):
        """(E_r/E0, text, extrapoliert) oder (None, Grund, False)."""
        if self.r is not None and self.tau is not None:
            return sls_verhaeltnis(t_eff, self.r, self.tau), f'SLS E_inf/E0 {self.r}, tau {self.tau} h', False
        if self.E1000 is not None:
            v = min(1.0, self.E1000 / self.E0)
            return v, f'Kriechmodul 1000 h {self.E1000} MPa', t_eff > 1000
        return None, f'Kriechkennwerte fuer {self.material} fehlen (kriech_E_inf_zu_E0 + kriech_tau_h oder ' \
                     'kriechmodul_1000h_MPa in kennwerte.py)', False


def _dauer_h(ts, pj):
    return (ts.get('dauerlast') or {}).get('dauer_h') or pj.get('lebensdauer_h')


def _dauerlast_werte(pdir, dl, E0):
    """(dehnung, sigma_MPa, durchbiegung_mm, text) aus direkter Angabe oder FEM."""
    eps, sig, d, txt = dl.get('dehnung'), dl.get('sigma_MPa'), dl.get('durchbiegung_mm'), []
    if dl.get('fem'):
        lf, t = fem_lastfall(pdir, dl['fem'])
        if lf is None:
            txt.append(t)
        else:
            txt.append(t)
            sig = sig if sig is not None else lf.get('max_vonMises_MPa')
            d = d if d is not None else lf.get('max_verschiebung_mm')
    if eps is None and sig is not None:
        eps = sig / E0
        txt.append(f'eps = sigma/E0 = {sig}/{E0:.0f}')
    return eps, sig, d, '; '.join(txt)


# ---------------------------------------------------------------- Pruefungen

def teil_temp(k, temp):
    """EINE Teiltemperatur (realterme.teil_temperatur) aus dem FEM-/soll-Ergebnis ``temperatur()``: Luft (oder 40/30 C
    angenommen) + Sonne + Eigenerwaermung. -> {'T_max_C', 'dT_eigen_K', 'herkunft', 'angenommen', 'terme'}."""
    T, terme, ang = rt.teil_temperatur(k, T_fem_C=temp['T_max_C'] if temp else None,
                                       dT_eigen_K=temp['dT_eigen_K'] if temp else 0.0)
    h = (temp['herkunft'] + '; ' if temp else 'keine Waerme-FEM, kein T_max_C; ') + rt.hinweis(terme)
    return {'T_max_C': round(T, 2), 'dT_eigen_K': temp['dT_eigen_K'] if temp else 0.0, 'herkunft': h,
            'angenommen': ang, 'terme': terme}


def d1_stufe(ab_K):
    """Gemeinsame Regel D1/W6 (Abstand Tg - T_Teil): >= 30 K ok, >= 20 K warnung, darunter fehler."""
    return 'ok' if ab_K >= 30 else ('warnung' if ab_K >= 20 else 'fehler')


def _d1(teil, material, tt):
    titel = 'Abstand zur Glasuebergangstemperatur'
    Tg = mat.MATERIAL[material]['glasuebergang_C']
    T = tt['T_max_C']
    ab = Tg - T
    st = rt.deckel(d1_stufe(ab), tt['angenommen'])
    h = (f'{material}: Tg {Tg} C, T_Teil {T} C aus {tt["herkunft"]}. Steifigkeit faellt um Tg innerhalb 10-20 K um '
         '~Faktor 1000; >= 20 K Abstand Pflicht, Warnung unter 30 K')
    if tt['angenommen']:
        h += ('. ANGENOMMEN (Luft und/oder Farbe unbekannt) - soll._projekt.T_max_C, aussen, farbe eintragen; '
              + ('auch mit Annahme schon zu warm' if st == 'fehler' else 'hoechstens warnung'))
    return ergebnis('D1', titel, st, wert=round(ab, 1), grenze=20.0, einheit='K', quelle=Q_LABOR, teil=teil, hinweis=h,
                    daten={'T_teil_C': T, 'angenommen': tt['angenommen']})


def _d2(pdir, teil, ts, material, kr, s):
    titel = 'Grenze lineare Viskoelastik (Dauerdehnung)'
    dl = ts.get('dauerlast')
    if not dl:
        return None
    E0 = mat.MATERIAL[material]['E_MPa']
    eps, sig, _, txt = _dauerlast_werte(pdir, dl, E0)
    if eps is None:
        return uebersprungen('D2', titel, 'dauerlast ohne dehnung, sigma_MPa oder fem ' + txt, Q_LABOR, teil)
    lim, q = kennwert(pdir, material, 'eps_dauer', s)
    if lim is None:
        lim, q = (0.005 if material == 'PLA' else 0.01), 'Katalog D2: linear bis ~1 % (PLA eher 0,5 %)'
    eps_t, zus = eps, ''
    t = _dauer_h(ts, s.get('_projekt', {}))
    if t:
        tp, _, _ = kr.zeit(t)
        v, vt, _ = kr.verhaeltnis(tp)
        if v:
            eps_t = eps / v
            zus = f', nach {t} h Kriechen {eps_t:.4%} ({vt})'
    st = 'fehler' if eps_t > lim else ('warnung' if eps_t > 0.8 * lim else 'ok')
    return ergebnis('D2', titel, st, wert=round(eps_t, 5), grenze=lim, einheit='-', quelle=Q_LABOR, teil=teil,
                    hinweis=f'eps0 {eps:.4%}{zus}; Grenze aus {q}. {txt}. Darueber gelten D3/D4 nicht (nichtlinear)')


def _d3(pdir, teil, ts, material, kr, s):
    titel = 'Kriechdurchbiegung (Korrespondenzprinzip)'
    dl = ts.get('dauerlast')
    if not dl:
        return None
    t = _dauer_h(ts, s.get('_projekt', {}))
    E0 = mat.MATERIAL[material]['E_MPa']
    _, _, d0, txt = _dauerlast_werte(pdir, dl, E0)
    if d0 is None:
        return uebersprungen('D3', titel, 'dauerlast ohne durchbiegung_mm bzw. fem. ' + txt, Q_SLS, teil)
    if not t:
        return uebersprungen('D3', titel, 'keine Dauer (dauerlast.dauer_h oder _projekt.lebensdauer_h)', Q_SLS, teil)
    tp, zt, nk = kr.zeit(t)
    v, vt, extra = kr.verhaeltnis(tp)
    if v is None:
        return uebersprungen('D3', titel, vt, Q_SLS, teil)
    d = d0 / v
    zul = dl.get('durchbiegung_zul_mm')
    h = (f'delta(t) = delta0 E0/E_r(t\') = {d0} / {v:.3f}; {zt}; {vt}. E0/E_r ist >= E0*J(t), also konservativ. '
         f'{txt}')
    if zul is None:
        st = 'info'
        h += '; keine durchbiegung_zul_mm'
    else:
        st = 'ok' if d <= zul else 'fehler'
    if (nk or extra) and st == 'ok':
        st = 'warnung'
        h += '; Ergebnis evtl. zu klein (Temperaturverschiebung fehlt oder Kriechmodul ueber 1000 h extrapoliert)'
    return ergebnis('D3', titel, st, wert=round(d, 4), grenze=zul, einheit='mm', quelle=Q_SLS, teil=teil, hinweis=h,
                    daten={'t_h': t, 't_eff_h': round(tp, 1), 'E_r_zu_E0': round(v, 4), 'delta0_mm': d0})


def d4_rest_annahme(k, material, T_C):
    """(F_Ende/F0, text) ohne Kriechkennwerte: 0,5 / A_T(T_Teil) - A_T allein aus realterme ('festigkeit' ohne
    Dauerlast- und Aussenterm)."""
    A_T, terme, _ = rt.abminderung('festigkeit', dict(k, material=material, T_teil_C=T_C, dauerlast=False,
                                                      aussen=False))
    v = 0.0 if math.isinf(A_T) else D4_REST_ANNAHME / A_T
    return v, (f'F(Ende) = {D4_REST_ANNAHME} F0 angenommen (Kriechkennwerte fehlen; ASA gemessen 0,48, PLA/PETG eher '
               f'schlechter) / A_T {A_T:.2f} bei T_Teil {T_C:.1f} C = {v:.3f} F0'
               + (f' ({"; ".join(terme)})' if terme else ''))


def _d4(pdir, teil, ts, material, kr, s, tt=None, k=None):
    titel = 'Vorspannungsverlust Schrauben (Relaxation)'
    q = '3.064 lec_8, 2.72 L10 (OCW)'
    out = []
    for i, sc in enumerate(ts.get('schrauben') or []):
        F0 = sc.get('vorspannung_N')
        mn = sc.get('klemmkraft_min_N')
        t = sc.get('dauer_h') or s.get('_projekt', {}).get('lebensdauer_h')
        v, nk, extra, ang = None, False, False, False
        if t:
            tp, zt, nk = kr.zeit(t)
            v, vt, extra = kr.verhaeltnis(tp)
            h = f'F(t) = F0 E_r(t\')/E0 = {F0} * {v:.3f}; {zt}; {vt}' if v is not None else vt
        else:
            vt = 'keine _projekt.lebensdauer_h'
        if v is None:
            # Befund Scheinsicherheit D4: fuer PLA/PETG fehlen Kriechwerte -> frueher immer uebersprungen
            T_C = (tt or {}).get('T_max_C', rt.teil_temperatur(k or {})[0])
            v, h = d4_rest_annahme(k or {}, material, T_C)
            h = f'{vt}. {h}'
            ang = True
            if (tt or {}).get('angenommen'):
                h += '; T_Teil selbst angenommen'
        name = titel + f' M{sc.get("d_mm", "?")} x{sc.get("anzahl", 1)}'
        if F0 is None:
            # ohne Vorspannung nur der Restanteil: Schraube ist da, Bewertung offen -> warnung (nie stilles skip)
            out.append(ergebnis('D4', name, 'warnung', wert=round(v, 3), einheit='F/F0', quelle=q, teil=teil,
                                hinweis=f'Schraube {i + 1}: keine vorspannung_N/klemmkraft_min_N - Restvorspannung '
                                        f'{v:.0%} von F0. {h}'))
            continue
        F = F0 * v
        if mn is None:
            st = 'warnung' if ang else 'info'
            h += '; keine klemmkraft_min_N'
        else:
            st = 'ok' if F >= mn else 'fehler'
        if (nk or extra) and st == 'ok':
            st, h = 'warnung', h + '; evtl. zu guenstig (Verschiebung fehlt/extrapoliert)'
        st = rt.deckel(st, ang)
        out.append(ergebnis('D4', name, st, wert=round(F, 1), grenze=mn, einheit='N', quelle=q, teil=teil, hinweis=h,
                            daten={'F0_N': F0, 'rest': round(v, 4), 'angenommen': ang}))
    return out


def _d5_d6(teil, kr, s):
    """Verschiebungsfaktor (D5) und effektive Zeit im Tagesgang (D6) - nur Info, die Werte gehen in D3/D4 ein."""
    out = []
    t1, t2 = 'Zeit-Temperatur-Verschiebung (WLF/Arrhenius)', 'Effektive Zeit im Tagesgang'
    if not kr.temp:
        return [uebersprungen('D5', t1, 'keine Temperatur', Q_WLF, teil)]
    T = kr.temp['T_max_C']
    lg = log10_aT(T, kr.Tg, kr.U)
    if lg is None:
        out.append(uebersprungen('D5', t1, f'aktivierung_U_kJ_mol fuer {kr.material} fehlt (unter Tg Arrhenius)',
                                 Q_WLF, teil))
    else:
        out.append(ergebnis('D5', t1, 'info', wert=round(10 ** lg, 5), einheit='a_T', quelle=Q_WLF, teil=teil,
                            hinweis=f'a_T bei {T} C gegen {T_REF_C:.0f} C (Tg {kr.Tg} C, U {kr.U} kJ/mol): Zeit laeuft '
                                    f'{10 ** -lg:.3g}-mal schneller'))
    if kr.T_mittel is None or kr.spanne is None:
        out.append(uebersprungen('D6', t2, 'soll._projekt.T_mittel_C und T_tagesgang_K fehlen', Q_WLF, teil))
    elif kr.U is None:
        out.append(uebersprungen('D6', t2, 'aktivierung_U_kJ_mol fehlt', Q_WLF, teil))
    else:
        Tm = kr.T_mittel + kr.temp['dT_eigen_K']
        f = effektive_zeit(1.0, Tm, float(kr.spanne), kr.Tg, kr.U)
        f0 = effektive_zeit(1.0, Tm, 0.0, kr.Tg, kr.U)
        out.append(ergebnis('D6', t2, 'info', wert=round(f, 4), einheit="t'/t", quelle=Q_WLF, teil=teil,
                            hinweis=f'Tagesgang {Tm:.1f} C +/- {kr.spanne / 2:.1f} K: t\'/t {f:.3g} '
                                    f'(ohne Tagesgang {f0:.3g})'))
    return out


def _d7(pdir, teil, ts, material, kr, s):
    titel = 'Boltzmann-Superposition (Lastgeschichte)'
    if not ts.get('dauerlast'):
        return None
    g = ts['dauerlast'].get('geschichte')
    if not g:
        return uebersprungen('D7', titel, 'dauerlast ohne geschichte [{t_h, sigma_MPa}] - D2/D3 rechnen mit konstanter '
                             'Last', Q_BOLTZ, teil)
    if kr.r is None or kr.tau is None:
        return uebersprungen('D7', titel, f'SLS-Kennwerte fuer {material} fehlen (kriech_E_inf_zu_E0, kriech_tau_h)',
                             Q_BOLTZ, teil)
    stufen = [(float(x['t_h']), float(x['sigma_MPa'])) for x in g]
    t = _dauer_h(ts, s.get('_projekt', {})) or max(x[0] for x in stufen)
    tp, zt, nk = kr.zeit(t)
    f = tp / t if t else 1.0     # gleichmaessige Verschiebung der Zeitachse
    eps = boltzmann_dehnung([(ti * f, si) for ti, si in stufen], tp,
                            lambda x: sls_nachgiebigkeit(x, kr.E0, kr.r, kr.tau))
    lim, q = kennwert(pdir, material, 'eps_dauer', s)
    if lim is None:
        lim, q = (0.005 if material == 'PLA' else 0.01), 'Katalog D2'
    st = 'fehler' if eps > lim else ('warnung' if eps > 0.8 * lim or nk else 'ok')
    return ergebnis('D7', titel, st, wert=round(eps, 5), grenze=lim, einheit='-', quelle=Q_BOLTZ, teil=teil,
                    hinweis=f'eps(t) = Sum dsigma_i J(t - t_i), J aus SLS; {zt}; Grenze {q}')


def _d9(pdir, teil, ts, material, temp, s):
    titel = 'Waermedehnung unter Zwang'
    z = ts.get('zwang')
    if not z:
        return None
    a_k, qa = kennwert(pdir, material, 'alpha_1_K', s)
    partner = z.get('partner', 'FR4')
    a_p = z.get('alpha_partner_1_K')
    if a_p is None:
        a_p = {'STARR': 12e-6, 'ALU': 23e-6}.get(partner) if partner in ('STARR', 'ALU') else kw.wert(partner, 'alpha_1_K')
    if a_k is None or a_p is None:
        return uebersprungen('D9', titel, f'alpha_1_K fehlt ({material if a_k is None else partner})', Q_DEHN, teil)
    dT = z.get('dT_K')
    if dT is None:
        if not temp:
            return uebersprungen('D9', titel, 'kein dT_K und keine Temperatur', Q_DEHN, teil)
        dT = temp['T_max_C'] - T_MONTAGE_C
    m = mat.MATERIAL[material]
    da = a_k - a_p
    if z.get('art') == 'bimetall':
        need = [k for k in ('t_mm', 't_partner_mm', 'L_mm') if z.get(k) is None]
        if need:
            return uebersprungen('D9', titel, f'bimetall: {need} fehlt', Q_DEHN, teil)
        Ep = z.get('E_partner_MPa') or mat.MATERIAL.get(partner, {}).get('E_MPa')
        if Ep is None:
            return uebersprungen('D9', titel, 'E_partner_MPa fehlt', Q_DEHN, teil)
        kap = bimetall_kruemmung(da, dT, z['t_mm'], z['t_partner_mm'], m['E_MPa'], Ep)
        w = abs(kap) * z['L_mm'] ** 2 / 8
        zul = z.get('durchbiegung_zul_mm')
        st = 'info' if zul is None else ('ok' if w <= zul else 'warnung')
        return ergebnis('D9', titel + ' (Bimetall)', st, wert=round(w, 4), grenze=zul, einheit='mm', quelle=Q_DEHN,
                        teil=teil, hinweis=f'Timoshenko kappa {kap:.3e} 1/mm, w = kappa L^2/8 ueber {z["L_mm"]} mm; '
                                           f'da {da:.2e} 1/K, dT {dT:.1f} K; alpha aus {qa}')
    sig = abs(m['E_MPa'] * da * dT)
    S = ts.get('sicherheit', S_STANDARD)
    n_xy = m['festigkeit_xy_MPa'] / sig if sig else math.inf
    n_z = m['festigkeit_z_MPa'] / sig if sig else math.inf
    st = _richtungs_stufe(n_xy, n_z, z.get('richtung'), S)
    return ergebnis('D9', titel + ' (voll eingespannt)', st, wert=round(sig, 2),
                    grenze=round(m['festigkeit_xy_MPa'] / S, 2), einheit='MPa', quelle=Q_DEHN, teil=teil,
                    hinweis=f'sigma = E da dT = {m["E_MPa"]:.0f} * {da:.2e} * {dT:.1f}; S_xy {n_xy:.2f}, S_z {n_z:.2f} '
                            f'(Ziel {S}); E0 bei 23 C (konservativ); alpha aus {qa}')


def _d10(pdir, teil, info, material, s):
    titel = 'Verzug-Indikator (Schwindung auf dem Bett)'
    q = '2.75 Topic 4, 2.008 L23 (OCW qualitativ)'
    bb = drucker_bbox(info.get('pruefung'))
    if bb is None:
        return uebersprungen('D10', titel, 'keine out/<teil>.pruefung.json (cad_build)', q, teil)
    pj = s.get('_projekt', {})
    T_bau = pj.get('T_bauraum_C', T_BAURAUM_C)
    Tg = mat.MATERIAL[material]['glasuebergang_C']
    dT = Tg - T_bau
    L = math.hypot(bb[0], bb[1])
    h = max(bb[2], 0.2)
    a, qa = kennwert(pdir, material, 'alpha_1_K', s)
    from .toleranz import messung_material   # Kalibrierung am MK4-Verzugsstreifen
    kal = (messung_material(material) or {}).get('verzug_asa') or {}
    if kal.get('abheben_mm') is not None and kal.get('laenge_mm') and kal.get('dicke_mm'):
        Tb_k = kal.get('T_bauraum_C') or T_BAURAUM_C
        a_eff = a if a is not None else 1.0         # ohne alpha steckt es im Kalibrierfaktor
        c = kal['abheben_mm'] / (a_eff * (Tg - Tb_k) * kal['laenge_mm'] ** 2 / kal['dicke_mm'])
        lift = c * a_eff * dT * L * L / h
        st = 'ok' if lift <= 0.1 else ('warnung' if lift <= 0.3 else 'fehler')
        return ergebnis('D10', titel, st, wert=round(lift, 3), grenze=0.1, einheit='mm', quelle=q, teil=teil,
                        hinweis=f'Abheben ~ c alpha dT L^2/h, kalibriert am Verzugsstreifen ({kal["abheben_mm"]} mm bei '
                                f'{kal["laenge_mm"]} x {kal["dicke_mm"]} mm): L {L:.0f} mm (Diagonale), h {h:.1f} mm, '
                                f'dT {dT:.0f} K. Ab 0,1 mm Brim/Ecken-Ohren empfohlen, ab 0,3 mm Fehler')
    if a is None:
        return uebersprungen('D10', titel, f'alpha_1_K fuer {material} fehlt und Verzugsstreifen nicht gemessen '
                             '(projects/kalibrierkoerper/messung.json)', q, teil)
    eps = a * dT
    return ergebnis('D10', titel, 'info', wert=round(eps * L, 3), einheit='mm', quelle=q, teil=teil,
                    hinweis=f'Schwindung alpha (Tg - T_Bauraum) L = {a:.1e} * {dT:.0f} * {L:.0f} mm, kappa = '
                            f'alpha dT/h = {eps / h:.2e} 1/mm. Nur Rangfolge - Schwelle am MK4-Verzugsstreifen '
                            'kalibrieren (messung.json verzug_asa)')


def _d11(pdir, teil, ts, material, s):
    titel = 'Ermuedung (Goodman)'
    N = ts.get('zyklen')
    wl = ts.get('wechsellast')
    if not N and not wl:
        return None
    if not N or not wl:
        return uebersprungen('D11', titel, 'zyklen und wechsellast noetig (beide)', Q_ERM, teil)
    smax, txt = wl.get('sigma_max_MPa'), ''
    if smax is None and wl.get('fem'):
        lf, txt = fem_lastfall(pdir, wl['fem'])
        smax = lf.get('max_vonMises_MPa') if lf else None
    if smax is None:
        return uebersprungen('D11', titel, 'wechsellast ohne sigma_max_MPa bzw. fem ' + txt, Q_ERM, teil)
    if wl.get('sigma_min_MPa') is not None:
        smin = wl['sigma_min_MPa']
    elif wl.get('R') is not None:
        smin = smax * wl['R']
    else:
        # weder sigma_min noch R: wechselnd (R = -1) annehmen - schaerfster Fall fuer Goodman, ein FEM-von-Mises
        # hat kein Vorzeichen (Befund D11-R0-still)
        smin = -smax
        txt = ('R = -1 angenommen (wechselnd; sigma_min_MPa bzw. R fehlt - schwellend R = 0 waere milder). '
               + txt).strip()
    sa, sm = abs(smax - smin) / 2, (smax + smin) / 2
    m = mat.MATERIAL[material]
    Se, qs = kennwert(pdir, material, 'S_e_MPa', s)
    if Se is None:
        return uebersprungen('D11', titel, f'S_e_MPa fuer {material} fehlt (kennwerte.py)', Q_ERM, teil)
    rel = wl.get('zuverlaessigkeit', 0.99)
    z = statistics.NormalDist().inv_cdf(rel) if 0.5 < rel < 1 else 0.0
    k = wl.get('k_faktor', 1.0) * max(0.0, 1 - 0.08 * z)
    Sut_xy, Sut_z = m['festigkeit_xy_MPa'], m['festigkeit_z_MPa']
    Sf_xy = wechselfestigkeit(N, Sut_xy, Se) * k
    Sf_z = Sf_xy * Sut_z / Sut_xy
    n_xy, n_z = goodman_n(sa, sm, Sf_xy, Sut_xy), goodman_n(sa, sm, Sf_z, Sut_z)
    S = ts.get('sicherheit', S_STANDARD)
    st = _richtungs_stufe(n_xy, n_z, wl.get('richtung'), S)
    return ergebnis('D11', titel, st, wert=round(n_xy if wl.get('richtung') != 'z' else n_z, 2), grenze=S,
                    einheit='n', quelle=Q_ERM, teil=teil,
                    hinweis=f'sigma_a {sa:.2f}, sigma_m {sm:.2f} MPa, N {N:g}: S_f {Sf_xy:.2f} MPa (k {k:.3f}, '
                            f'Zuverlaessigkeit {rel}); n_xy {n_xy:.2f}, n_z {n_z:.2f}; S_e aus {qs}. {txt}')


def _d12(pdir, teil, ts, material, temp, s):
    titel = 'Kriechbruch (Norton + Monkman-Grant)'
    dl = ts.get('dauerlast')
    if not dl:
        return None
    p = ts.get('kriechbruch') or (s.get('_projekt', {}).get('kriechbruch') or {}).get(material)
    if not p:
        return uebersprungen('D12', titel, f'Kriechbruch-Kennwerte fuer {material} fehlen (soll kriechbruch: eps0_1_h, '
                             's_MPa, n, Q_kJ_mol, C_MG) - fuer Kunststoffe kaum veroeffentlicht', Q_KRIECH, teil)
    _, sig, _, txt = _dauerlast_werte(pdir, dl, mat.MATERIAL[material]['E_MPa'])
    t = _dauer_h(ts, s.get('_projekt', {}))
    if sig is None or not t or not temp:
        return uebersprungen('D12', titel, 'sigma, Dauer oder Temperatur fehlt', Q_KRIECH, teil)
    T = temp['T_max_C'] + K0
    rate = p['eps0_1_h'] * (sig / p['s_MPa']) ** p['n'] * math.exp(-p['Q_kJ_mol'] * 1e3 / (R_GAS * T))
    tf = p['C_MG'] / rate if rate > 0 else math.inf
    st = 'fehler' if tf < t else ('warnung' if tf < 10 * t else 'ok')
    return ergebnis('D12', titel, st, wert=round(tf, 1), grenze=t, einheit='h', quelle=Q_KRIECH, teil=teil,
                    hinweis=f'eps_punkt {rate:.3e} 1/h bei {sig} MPa, {temp["T_max_C"]} C; t_f = C_MG/eps_punkt; '
                            f'Faktor 10 Reserve fuer Streuung. {txt}')


def _d8(pdir, s, temps, mats):
    """Waermedehnung Gehaeuse gegen Platine (board_info.json)."""
    titel = 'Waermedehnung gegen Platine'
    bi = _json(os.path.join(pdir, 'electronics', 'board_info.json'))
    if not bi:
        return [uebersprungen('D8', titel, 'keine electronics/board_info.json', Q_DEHN)]
    pj = s.get('_projekt', {})
    material = pj.get('material') or next((m for m in mats.values() if m), None)
    if not material:
        return [uebersprungen('D8', titel, 'kein Gehaeusematerial', Q_DEHN)]
    a_k, qa = kennwert(pdir, material, 'alpha_1_K', s)
    a_p = kw.wert('FR4', 'alpha_1_K')
    if a_k is None:
        return [uebersprungen('D8', titel, f'alpha_1_K fuer {material} fehlt (kennwerte.py)', Q_DEHN)]
    T_warm = max((t['T_max_C'] for t in temps.values() if t), default=None)
    Ts = [('warm', T_warm), ('kalt', pj.get('T_min_C'))]
    Ts = [(n, T) for n, T in Ts if T is not None]
    if not Ts:
        return [uebersprungen('D8', titel, 'keine Temperatur (FEM, T_max_C oder T_min_C)', Q_DEHN)]
    L = max(bi.get('board_size_mm') or [0])
    da = a_k - a_p
    out = []
    s0 = pj.get('platine_spalt_mm')
    if s0 is None:
        out.append(uebersprungen('D8', titel + ' (Rand)', 'soll._projekt.platine_spalt_mm fehlt (Spalt je Seite)', Q_DEHN))
    else:
        for n, T in Ts:
            d = da * L * (T - T_MONTAGE_C)          # > 0: Tasche waechst gegen die Platine
            rest = s0 - max(0.0, -d)
            st = 'ok' if rest >= 0.1 else 'fehler'
            out.append(ergebnis('D8', f'{titel} (Rand, {n})', st, wert=round(rest, 4), grenze=0.1, einheit='mm',
                                quelle=Q_DEHN, hinweis=f'dd = (a_K - a_FR4) L dT = {da:.2e} * {L} * {T - T_MONTAGE_C:+.1f}'
                                f' = {d:+.3f} mm; Restspalt = Spalt {s0} - schliessender Anteil (ganz auf eine Seite '
                                f'angenommen); alpha aus {qa}'))
    loecher = bi.get('mounting_holes') or []
    d_s = pj.get('platine_schraube_d_mm')
    if len(loecher) >= 2:
        La = max(math.dist(a['pos'], b['pos']) for a in loecher for b in loecher)
        if d_s is None:
            out.append(uebersprungen('D8', titel + ' (Befestigungsloecher)', 'soll._projekt.platine_schraube_d_mm fehlt',
                                     Q_DEHN))
        else:
            spiel = min(h['drill_mm'] for h in loecher) - d_s      # Gesamtspiel, Platine kann voll ausweichen
            for n, T in Ts:
                d = abs(da) * La * abs(T - T_MONTAGE_C)
                st = 'ok' if d <= spiel else 'warnung'
                h = (f'Lochabstand {La:.1f} mm: Versatz Dom <-> Loch {d:.3f} mm gegen Spiel {spiel:.2f} mm '
                     f'(Bohrung - Schraube)')
                if d > spiel:
                    sig = mat.MATERIAL[material]['E_MPa'] * abs(da) * abs(T - T_MONTAGE_C)
                    h += f'; Platine verspannt, Obergrenze sigma = E da dT = {sig:.1f} MPa (D9)'
                out.append(ergebnis('D8', f'{titel} (Befestigungsloecher, {n})', st, wert=round(d, 4),
                                    grenze=round(spiel, 3), einheit='mm', quelle=Q_DEHN, hinweis=h))
    return out


def pruefe(pdir):
    s = lade_soll(pdir)
    erg = []
    alle = teile(pdir)
    if not alle:
        return [uebersprungen('D1', 'Dauer/Temperatur', 'keine Teile (cad/soll.json, out/*.pruefung.json)', Q_LABOR)]
    temps, mats = {}, {}
    asa = False
    k0 = rt.kontext(pdir, soll=s)
    hat_dauerlast = hat_schrauben = False
    for teil, info in alle.items():
        ts = info['soll']
        material, mq = material_von(pdir, teil, s)
        mats[teil] = material
        if material not in mat.DRUCKSTOFFE:
            erg.append(uebersprungen('D1', 'Dauer/Temperatur', f'{mq}' if material is None else
                                     f'{material} ist kein Druckstoff', Q_LABOR, teil))
            continue
        k = dict(k0, material=material)
        temp = temperatur(pdir, teil, s)
        tt = teil_temp(k, temp)
        # Fuer D2-D12/D8 gilt die Teiltemperatur (mit Sonne), aber nur, wenn ueberhaupt eine Temperatur bekannt ist;
        # reine Annahme (Luft 40/30 C) nutzen nur D1 und D4, die sie als 'angenommen' deckeln.
        temp = tt if temp else None
        temps[teil] = temp
        kr = _Kriechen(pdir, s, material, temp)
        erg.append(_d1(teil, material, tt))
        hat_dauerlast |= bool(ts.get('dauerlast'))
        hat_schrauben |= bool(ts.get('schrauben'))
        if ts.get('dauerlast') or ts.get('schrauben'):
            erg += _d5_d6(teil, kr, s)
        for f in (_d2, _d3, _d7):
            r = f(pdir, teil, ts, material, kr, s)
            if r:
                erg.append(r)
        erg += _d4(pdir, teil, ts, material, kr, s, tt, k)
        for r in (_d9(pdir, teil, ts, material, temp, s), _d11(pdir, teil, ts, material, s),
                  _d12(pdir, teil, ts, material, temp, s)):
            if r:
                erg.append(r)
    # Soll-gesteuerte Pruefungen ohne Eintrag: ein sichtbares 'uebersprungen' statt nichts (Ausloeser stuft hoch)
    if not hat_dauerlast:
        for i, t, q in (('D2', 'Grenze lineare Viskoelastik (Dauerdehnung)', Q_LABOR),
                        ('D3', 'Kriechdurchbiegung (Korrespondenzprinzip)', Q_SLS),
                        ('D7', 'Boltzmann-Superposition (Lastgeschichte)', Q_BOLTZ),
                        ('D12', 'Kriechbruch (Norton + Monkman-Grant)', Q_KRIECH)):
            erg.append(uebersprungen(i, t, 'kein Teil mit soll.json dauerlast (ruhende Last: Eigengewicht, Klemmung, '
                                     'Pressitz, vorgespannter Schnapper?)', q))
    if not hat_schrauben:
        erg.append(uebersprungen('D4', 'Vorspannungsverlust Schrauben (Relaxation)',
                                 'kein Teil mit soll.json schrauben', '3.064 lec_8, 2.72 L10 (OCW)'))
        if material == 'ASA':
            asa = True
            erg.append(_d10(pdir, teil, info, material, s))
    if not asa:
        erg.append(uebersprungen('D10', 'Verzug-Indikator ASA', 'kein ASA-Teil im Projekt',
                                 '2.75 Topic 4, 2.008 L23 (OCW qualitativ)'))
    erg += _d8(pdir, s, temps, mats)
    return erg
