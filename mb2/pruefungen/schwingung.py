"""Katalog 3.6 Schwingung, Stoss, Akustik (OCW_PRUEFKATALOG.md, S1-S8) - analytisch, keine Modalanalyse.

S1 Eigenfrequenz aus statischer Durchbiegung  f1 = (1/2pi)*sqrt(g/delta_st) = 15,76/sqrt(delta_st/mm) Hz
   Quellen der Durchbiegung (je Teil, alle werden gemeldet, S2 nimmt die kleinste Frequenz):
   a) FEM-Lastfall mit Eigengewicht ("schwerkraft": true, fem/<fall>.json) -> max_verschiebung_mm aus <fall>.erg.json
   b) analytisch aus soll-Feld 'kragarm' (wie S3): delta = q*L^4/(8EI) + P*L^3/(3EI)  (Hinweis: Naeherung)
   c) Einmassenschwinger aus einer FEM-Federrate: delta = m*g/k, ganze Teilmasse am Lastpunkt (Untergrenze)
S2 Resonanzabstand: f1 >= 3*f_max ok, 2..3 warnung, f1 im Band [f_min/sqrt2, 2*f_max] fehler (bei Quelle c warnung,
   weil c nur eine Untergrenze ist); f1 < f_min/sqrt2 = Isolation (info).
S3 Kragarm: f = (1,875^2/2pi)*sqrt(EI/(rho*A*L^4)); mit Spitzenmasse f = (1/2pi)*sqrt(k/(m + 0,2357*m_balken)),
   k = 3EI/L^3. Gegenprobe zu S1a (+-30 %).
S4 Fallstoss: F_max = m*g*(1 + sqrt(1 + 2h/delta_st)), delta_st = m*g/k -> statischer Ersatzlastfall: sigma skaliert
   linear vom FEM-Lastfall, Sicherheit gegen Festigkeit in Z >= 1,5 (>= 2 bei T_min_C < 5 C bzw. aussen ohne T_min_C).
   Je Lastfall die Hauptachse der Kraft; fehlt eine der Achsen x/y/z -> eine 'warnung' (Ecke/Kante ungeprueft).
   Ohne fallhoehe_m 'uebersprungen' (Ausloeser 'handgeraet' stuft hoch).
S5 Helmholtz Vorkammer/Gitter: f_H = (c/2pi)*sqrt(sum(S_i/l_eff,i)/V), l_eff = l + 1,6*a_eq, a_eq = sqrt(S_i/pi)
   (bei Schlitzen ist das eine zu grosse Muendungskorrektur -> f_H zu klein = konservativ). Gueltig bei Massen < 0,1*lambda.
S6 Luftpolster geschlossene Box: C = V/(rho*c^2); f_c = f_s*sqrt(1 + V_as/V); Kriterium f_c/f_s < 1,5.
S7 Stehwellen: f1 = c/(2*L_innen) je Achse; im Sprach-/Anregungsband -> warnung (Daemmung).
S8 Gitterloch vs. viskose Grenzschicht: delta_v = sqrt(mu/(rho*omega)) bei der tiefsten Bandfrequenz;
   kleinste halbe Lochabmessung a < 10*delta_v -> warnung (Gitter daempft).

Eingaben (alle optional, siehe FELDER.md): soll.json je Teil oder unter '_projekt':
  'anregung_Hz' (Zahl oder [f_min, f_max]), 'zusatzmasse_g', 'fallhoehe_m', 'masse_g' (Geraet gesamt, fuer S4),
  'material', 'kragarm': [{'name', 'L_mm', 'b_mm', 't_mm'} oder {'L_mm', 'I_mm4', 'A_mm2'}, optional 'masse_spitze_g'],
  'schnapper' (L_mm, b_mm, t_mm -> S3),
  'lautsprecher': {
     'vorkammer_mm3' | 'vorkammer': {'d_mm', 'h_mm'},
     'loecher': {'anzahl', 'd_mm'} | {'anzahl', 'breite_mm', 'laenge_mm'} | {'liste': [...]} | 'auto' (aus STEP),
     'mitte_mm': [x, y(, z)], 'r_mm', 'achse': 'z', 'teil' (fuer 'auto', Standard: Teil des Eintrags),
     'wand_mm' (Halslaenge; bei 'auto' aus der Geometrie),
     'f_s_Hz', 'V_as_l', 'geschlossen' (bool), 'innenvolumen_mm3', 'einbauten_mm3', 'innen_mm': [Lx, Ly, Lz],
     'gehaeuse_teile': [..] (Standard: alle out/*.step), 'band_Hz': [f_min, f_max] (Standard Sprachband 300-3400),
     'f_H_min_Hz' (Standard 4000)}
Einheiten intern: mm, N, MPa, kg, s, Hz.
"""
import glob
import json
import math
import os
import re

from mb2.material import DRUCKSTOFFE, MATERIAL
from mb2.pruefungen import ergebnis, soll, uebersprungen

G_MM_S2 = 9810.0                     # Erdbeschleunigung in mm/s^2
K_S1 = math.sqrt(G_MM_S2) / (2 * math.pi)  # 15,76 Hz*sqrt(mm)
BETA1 = 1.8751040687                 # erste Nullstelle cos*cosh = -1 (Kragarm)
SPRACHBAND = (300.0, 3400.0)         # Telefonband, Standard wenn ein Lautsprecher da ist und nichts angegeben ist
F_H_MIN = 4000.0
S4_S_ZIEL = 1.5                      # Fallstoss, Sicherheit gegen Festigkeit Z
S4_S_ZIEL_KALT = 2.0                 # unter S4_T_KALT_C (Versproedung)
S4_T_KALT_C = 5.0

Q = {
    'S1': 'OCW 2.003SC L21, Rezitation 10: f = (1/2pi)*sqrt(g/delta_st)',
    'S2': 'OCW 16.20 Unit 19, 2.003SC L21: Vergroesserungsfunktion, Isolation ab f/f1 > sqrt(2)',
    'S3': 'OCW 2.002 L2, 2.003SC L27: Euler-Bernoulli-Kragarm, beta1*L = 1,875',
    'S4': 'extern: Energieerhaltung Feder-Masse (Fallhoehe h auf Feder k), OCW 16.20 Unit 19 qualitativ',
    'S5': 'OCW 6.551J L7/L10: Helmholtz, akustische Masse rho*l_eff/S, Nachgiebigkeit V/(rho c^2)',
    'S6': 'OCW 6.551J L7 (akustische Nachgiebigkeit); Thiele-Small f_c = f_s*sqrt(1+V_as/V) extern',
    'S7': 'OCW 2.003SC L27, 6.551J L15: Rohr/Raum beidseitig schallhart f_n = n*c/(2L)',
    'S8': 'OCW 6.551J L7: viskose Grenzschicht delta_v = sqrt(mu/(rho*omega))',
}
T = {
    'S1': 'Eigenfrequenz aus statischer Durchbiegung', 'S2': 'Resonanzabstand', 'S3': 'Kragarm-Frequenz',
    'S4': 'Fallstoss-Ersatzlast', 'S5': 'Helmholtz Vorkammer/Gitter', 'S6': 'Luftpolster geschlossene Box',
    'S7': 'Stehwellen im Gehaeuse', 'S8': 'Gitterloch vs. viskose Grenzschicht',
}


# ------------------------------------------------------------------ Formeln (einzeln testbar)
def luft(T_C=20.0):
    """Schallgeschwindigkeit (mm/s), Dichte (kg/m^3), dynamische Zaehigkeit (Pa s, Sutherland)."""
    Tk = T_C + 273.15
    c = 331.3 * math.sqrt(Tk / 273.15) * 1000.0
    rho = 101325.0 / (287.05 * Tk)
    mu = 1.716e-5 * (Tk / 273.15) ** 1.5 * (273.15 + 110.4) / (Tk + 110.4)
    return c, rho, mu


def f_aus_durchbiegung(delta_mm):
    """S1: f1 = (1/2pi)*sqrt(g/delta)."""
    return K_S1 / math.sqrt(delta_mm)


def f_einmassen(k_N_mm, m_kg):
    """f = (1/2pi)*sqrt(k/m), k in N/mm -> N/m."""
    return math.sqrt(k_N_mm * 1000.0 / m_kg) / (2 * math.pi)


def kragarm_f(E_MPa, rho_kg_m3, L_mm, I_mm4, A_mm2, m_spitze_kg=0.0):
    """S3 (Hz). Ohne Spitzenmasse exakt (erste Mode), mit Spitzenmasse Rayleigh (0,2357 der Balkenmasse)."""
    EI = E_MPa * 1e6 * I_mm4 * 1e-12          # N m^2
    L = L_mm * 1e-3
    rA = rho_kg_m3 * A_mm2 * 1e-6             # kg/m
    if not m_spitze_kg:
        return BETA1 ** 2 / (2 * math.pi) * math.sqrt(EI / (rA * L ** 4))
    k = 3 * EI / L ** 3
    return math.sqrt(k / (m_spitze_kg + 0.2357 * rA * L)) / (2 * math.pi)


def kragarm_durchbiegung(E_MPa, rho_kg_m3, L_mm, I_mm4, A_mm2, m_spitze_kg=0.0):
    """S1b: Spitzendurchbiegung unter 1 g (mm): q L^4/(8EI) + P L^3/(3EI)."""
    q = rho_kg_m3 * A_mm2 * 1e-9 * G_MM_S2 * 1e-3      # N/mm (kg/mm * m/s^2)
    P = m_spitze_kg * G_MM_S2 * 1e-3                  # N
    EI = E_MPa * I_mm4                                # N mm^2
    return q * L_mm ** 4 / (8 * EI) + P * L_mm ** 3 / (3 * EI)


def fallstoss(m_kg, k_N_mm, h_mm):
    """S4: (F_max in N, delta_st in mm). F = m g (1 + sqrt(1 + 2h/delta_st))."""
    mg = m_kg * G_MM_S2 * 1e-3
    d = mg / k_N_mm
    return mg * (1 + math.sqrt(1 + 2 * h_mm / d)), d


def helmholtz(V_mm3, loecher, l_mm, c_mm_s):
    """S5: f_H (Hz). loecher = [(S_mm2, a_eq_mm), ...]; l_eff = l + 1,6 a_eq; parallele Haelse addieren S/l_eff."""
    summe = sum(S / (l_mm + 1.6 * a) for S, a in loecher)
    return c_mm_s / (2 * math.pi) * math.sqrt(summe / V_mm3)


def box_fc(f_s, V_as_mm3, V_mm3):
    """S6: Einbau-Resonanz der geschlossenen Box."""
    return f_s * math.sqrt(1 + V_as_mm3 / V_mm3)


def nachgiebigkeit(V_mm3, rho, c_mm_s):
    """S6: akustische Nachgiebigkeit C = V/(rho c^2) in m^3/Pa."""
    c = c_mm_s * 1e-3
    return V_mm3 * 1e-9 / (rho * c * c)


def stehwelle(L_mm, c_mm_s):
    """S7: f1 = c/(2L)."""
    return c_mm_s / (2 * L_mm)


def grenzschicht_mm(f_Hz, rho, mu):
    """S8: delta_v = sqrt(mu/(rho omega)) in mm."""
    return math.sqrt(mu / (rho * 2 * math.pi * f_Hz)) * 1000.0


def lochform(A, P):
    """Aus Flaeche und Umfang: ('rund', Radius) oder ('schlitz', Breite, Laenge) als Rechteck-Ersatz."""
    rund = P * P / (4 * math.pi * A)
    disk = P * P / 4 - 4 * A
    if rund < 1.05 or disk <= 0:
        return ('rund', 2 * A / P)
    w = (P / 2 - math.sqrt(disk)) / 2
    return ('schlitz', w, A / w)


def halbe_kleinste(form):
    return form[1] if form[0] == 'rund' else form[1] / 2


# ------------------------------------------------------------------ Eingaben lesen
def _band(wert):
    if wert is None:
        return None
    if isinstance(wert, (int, float)):
        return (float(wert), float(wert))
    w = [float(x) for x in wert]
    return (min(w), max(w)) if w else None


def _lies_json(p):
    try:
        return json.load(open(p, encoding='utf-8'))
    except Exception:  # noqa: BLE001 - kaputte Datei = keine Eingabe
        return None


def _fem_faelle(pdir):
    """[(fall, spec, erg)] - nur Faelle mit Ergebnis."""
    out = []
    for p in sorted(glob.glob(os.path.join(pdir, 'fem', '*.json'))):
        if p.endswith('.erg.json'):
            continue
        fall = os.path.basename(p)[:-5]
        spec, erg = _lies_json(p), _lies_json(os.path.join(pdir, 'fem', fall + '.erg.json'))
        if spec and erg and isinstance(erg.get('lastfaelle'), dict):
            out.append((fall, spec, erg))
    return out


def _schwer_lastfaelle(spec, erg):
    """[(name, delta_mm, ueberlagert)] - Eigengewichts-Lastfaelle eines FEM-Falls."""
    lf = erg['lastfaelle']
    namen = [l.get('name') for l in spec.get('lasten', []) if l.get('schwerkraft')]
    namen = [n for n in namen if n in lf]
    if not namen:
        namen = [n for n in lf if re.search(r'schwer|eigengew|gravit', n, re.I)]
    ueber = False
    if not namen and spec.get('schwerkraft'):
        namen = list(lf)
        ueber = bool(spec.get('lasten'))           # Eigengewicht mit anderen Lasten ueberlagert
    out = [(n, lf[n].get('max_verschiebung_mm'), ueber) for n in namen]
    sk = erg.get('schwerkraft')
    if isinstance(sk, dict) and sk.get('max_verschiebung_mm'):
        out.append(('schwerkraft', sk['max_verschiebung_mm'], False))
    return [(n, d, u) for n, d, u in out if d]


def _koerper(spec, erg):
    namen = erg.get('koerper') or [k.get('name') for k in spec.get('koerper', [])]
    mats = {k.get('name'): (k.get('material') or '').upper() for k in spec.get('koerper', [])}
    return [n for n in namen if n], mats


class Projekt:
    def __init__(self, pdir, soll_daten=None):
        self.pdir = pdir
        self.soll = soll(pdir) if soll_daten is None else soll_daten
        self.proj = self.soll.get('_projekt', {})
        self.faelle = _fem_faelle(pdir)
        self._steps = {}
        self.T_C = float(self.proj.get('T_mittel_C', 20.0))
        self.c, self.rho, self.mu = luft(self.T_C)

    def teile(self):
        t = [k for k in self.soll if not k.startswith('_')]
        for _, spec, erg in self.faelle:
            for n in _koerper(spec, erg)[0]:
                if n not in t and os.path.exists(os.path.join(self.pdir, 'out', n + '.step')):
                    t.append(n)
        return t

    def feld(self, teil, name, standard=None):
        s = self.soll.get(teil, {}) if teil else {}
        return s[name] if isinstance(s, dict) and name in s else self.proj.get(name, standard)

    def material(self, teil):
        m = self.feld(teil, 'material')
        if m:
            return m.upper()
        for _, spec, erg in self.faelle:
            namen, mats = _koerper(spec, erg)
            if teil in mats and mats[teil]:
                return mats[teil]
        return None

    def masse_kg(self, teil):
        """Teilmasse aus out/<teil>.pruefung.json (Volumen) und Dichte, sonst None."""
        pr = _lies_json(os.path.join(self.pdir, 'out', teil + '.pruefung.json'))
        mat = self.material(teil)
        if not pr or not pr.get('volumen_mm3') or mat not in MATERIAL:
            return None
        return pr['volumen_mm3'] * 1e-9 * MATERIAL[mat]['dichte_kg_m3']

    def step(self, teil):
        if teil not in self._steps:
            p = os.path.join(self.pdir, 'out', teil + '.step')
            if os.path.exists(p):
                from build123d import import_step
                self._steps[teil] = import_step(p)
            else:
                self._steps[teil] = None
        return self._steps[teil]

    def alle_steps(self):
        return sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(self.pdir, 'out', '*.step')))


# ------------------------------------------------------------------ Geometrie aus STEP
def loecher_auto(shape, mitte, r, achse='z'):
    """Durchbrueche eines Gitters: die zwei gegenueberliegenden ebenen Flaechen (Normale +-achse) mit den meisten
    Innenkonturen im Kreis (mitte, r). Je Loch die kleinere Kontur (engster Querschnitt). -> (liste[(A, P)], l_mm)."""
    from build123d import Face, GeomType
    ai = 'xyz'.index(achse)
    oi = [i for i in range(3) if i != ai]
    kand = []
    for f in shape.faces():
        if f.geom_type != GeomType.PLANE:
            continue
        n = f.normal_at(f.center())
        nv = (n.X, n.Y, n.Z)
        if abs(abs(nv[ai]) - 1) > 1e-3:
            continue
        loecher = []
        for w in f.inner_wires():
            fw = Face(w)
            c = fw.center()
            cv = (c.X, c.Y, c.Z)
            if math.hypot(cv[oi[0]] - mitte[0], cv[oi[1]] - mitte[1]) <= r:
                loecher.append((cv[oi[0]], cv[oi[1]], fw.area, w.length))
        if loecher:
            kand.append((len(loecher), nv[ai], (f.center().X, f.center().Y, f.center().Z)[ai], loecher))
    if not kand:
        return [], None
    kand.sort(key=lambda k: -k[0])
    a = kand[0]
    gegen = [k for k in kand if k[1] * a[1] < 0 and k[0] == a[0]]
    if not gegen:
        return [(A, P) for _, _, A, P in a[3]], None
    b = min(gegen, key=lambda k: abs(k[2] - a[2]))
    l = abs(a[2] - b[2])
    paar = []
    for x, y, A, P in a[3]:
        g = min(b[3], key=lambda h: (h[0] - x) ** 2 + (h[1] - y) ** 2)
        paar.append((A, P) if A <= g[2] else (g[2], g[3]))
    return paar, l


def innenraum(shapes):
    """Lichte Innenmasse per Strahl-Test (OCCT): je Achse 5x5 parallele Strahlen ab Bbox-Mitte; ein Strahl zaehlt nur,
    wenn er in beiden Richtungen auf eine Wand trifft, in die er eintritt (also im Hohlraum startet). Je Achse gilt
    die groesste lichte Weite. -> ([Lx, Ly, Lz], [(lo, hi)] je Achse) oder None."""
    from build123d import Compound, Face, Vector
    from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
    from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
    comp = Compound(list(shapes))
    bb = comp.bounding_box()
    lo, hi = (bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z)
    si = IntCurvesFace_ShapeIntersector()
    si.Load(comp.wrapped, 1e-6)

    def erster(p, d):
        si.Perform(gp_Lin(gp_Pnt(*p), gp_Dir(*d)), 0.0, 1e6)
        best = None
        for i in range(1, si.NbPnt() + 1):
            w = si.WParameter(i)
            if w > 1e-6 and (best is None or w < best[0]):
                best = (w, i)
        if best is None:
            return None
        w, i = best
        hp = si.Pnt(i)
        try:
            n = Face(si.Face(i)).normal_at(Vector(hp.X(), hp.Y(), hp.Z()))
        except Exception:  # noqa: BLE001
            return None
        if n.X * d[0] + n.Y * d[1] + n.Z * d[2] >= 0:     # Austritt aus Material: Start lag im Material
            return None
        return w

    masse, grenzen = [], []
    for ai in range(3):
        oi = [i for i in range(3) if i != ai]
        best = None
        for fu in (0.3, 0.4, 0.5, 0.6, 0.7):
            for fv in (0.3, 0.4, 0.5, 0.6, 0.7):
                p = [0.0, 0.0, 0.0]
                p[ai] = (lo[ai] + hi[ai]) / 2
                p[oi[0]] = lo[oi[0]] + fu * (hi[oi[0]] - lo[oi[0]])
                p[oi[1]] = lo[oi[1]] + fv * (hi[oi[1]] - lo[oi[1]])
                d = [0.0, 0.0, 0.0]
                d[ai] = 1.0
                wp = erster(p, d)
                d[ai] = -1.0
                wm = erster(p, d)
                if wp is None or wm is None:
                    continue
                if best is None or wp + wm > best[0]:
                    best = (wp + wm, p[ai] - wm, p[ai] + wp)
        if best is None:
            return None
        masse.append(best[0])
        grenzen.append((best[1], best[2]))
    return masse, grenzen


def innenvolumen(shapes, grenzen):
    """Quader der lichten Masse minus alles Teilematerial darin (Dome, Ringe, Rundungen) in mm^3."""
    from build123d import Box, Pos
    (x0, x1), (y0, y1), (z0, z1) = grenzen
    q = Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * Box(x1 - x0, y1 - y0, z1 - z0)
    V = q.volume
    belegt = 0.0
    for s in shapes:
        try:
            belegt += (s & q).volume
        except Exception:  # noqa: BLE001 - Boolesche Operation gescheitert -> nicht abziehen, Hinweis
            return V, None
    return V, V - belegt


# ------------------------------------------------------------------ S1-S4
def _s1_s4(P):
    erg = []
    f1 = {}     # teil -> [(f, quelle, unterschranke)]

    def merke(teil, f, art, unter):
        f1.setdefault(teil, []).append((f, art, unter))

    # S1a FEM-Eigengewicht
    gefunden = set()
    for fall, spec, e in P.faelle:
        namen, _ = _koerper(spec, e)
        teil = '+'.join(namen)
        for lf, d, ueber in _schwer_lastfaelle(spec, e):
            f = f_aus_durchbiegung(d)
            hinweis = f'FEM-Fall {fall}/{lf}: delta_st = {d:.4g} mm (Eigengewicht 1 g)'
            stufe = 'info'
            if ueber:
                hinweis += '; Eigengewicht mit weiteren Lasten ueberlagert -> delta zu gross, f1 zu klein'
                stufe = 'warnung'
            zm = P.feld(namen[0] if len(namen) == 1 else None, 'zusatzmasse_g')
            if zm:
                ks = [l.get('federrate_N_mm') for l in e['lastfaelle'].values() if (l.get('federrate_N_mm') or 0) > 0]
                if ks:
                    fz = f_einmassen(min(ks), zm / 1000.0)
                    f = 1 / math.sqrt(1 / f ** 2 + 1 / fz ** 2)
                    hinweis += f'; Zusatzmasse {zm} g per Dunkerley mit k = {min(ks):.4g} N/mm (f_zus {fz:.0f} Hz)'
                else:
                    stufe = 'warnung'
                    hinweis += f'; Zusatzmasse {zm} g NICHT erfasst (keine Federrate) -> f1 zu hoch'
            erg.append(ergebnis('S1', T['S1'] + ' (FEM)', stufe, wert=round(f, 1), einheit='Hz', quelle=Q['S1'],
                                hinweis=hinweis, teil=teil, daten={'fall': fall, 'lastfall': lf, 'delta_mm': d}))
            merke(teil, f, 'FEM-Eigengewicht', stufe == 'warnung' and ueber)
            gefunden.add(teil)

    teile = P.teile()
    for teil in teile:
        mat = P.material(teil)
        km = (P.soll.get(teil) or {}).get('kragarm')
        # S1b + S3 analytisch aus Kragarm/Schnapper
        balken = []
        for k in (km or []):
            balken.append(('kragarm', k))
        for k in (P.soll.get(teil, {}).get('schnapper') or []):
            balken.append(('schnapper', k))
        for art, k in balken:
            name = k.get('name', art)
            if mat not in MATERIAL:
                erg.append(uebersprungen('S3', T['S3'], f'{name}: Material unbekannt (soll material)', Q['S3'], teil))
                continue
            try:
                L = float(k['L_mm'])
                if 'I_mm4' in k:
                    I, A = float(k['I_mm4']), float(k['A_mm2'])
                else:
                    b, t = float(k['b_mm']), float(k['t_mm'])
                    I, A = b * t ** 3 / 12, b * t
            except (KeyError, TypeError, ValueError):
                erg.append(uebersprungen('S3', T['S3'], f'{name}: L_mm + (b_mm, t_mm) oder (I_mm4, A_mm2) fehlt',
                                         Q['S3'], teil))
                continue
            E, rho = MATERIAL[mat]['E_MPa'], MATERIAL[mat]['dichte_kg_m3']
            ms = float(k.get('masse_spitze_g', 0) or 0) / 1000.0
            f3 = kragarm_f(E, rho, L, I, A, ms)
            hin = (f'{name}: L {L:g}, I {I:.4g} mm4, A {A:.4g} mm2, {mat} E {E:g} MPa'
                   + (f', Spitzenmasse {ms * 1000:g} g (Rayleigh)' if ms else ''))
            stufe, gegen = 'info', None
            fem = [x for x in f1.get(teil, []) if x[1] == 'FEM-Eigengewicht']
            if fem:
                gegen = fem[0][0] / f3 - 1
                stufe = 'ok' if abs(gegen) <= 0.30 else 'warnung'
                hin += f'; Gegenprobe S1-FEM {fem[0][0]:.0f} Hz: {gegen * 100:+.0f} % (Grenze +-30 %)'
            erg.append(ergebnis('S3', T['S3'], stufe, wert=round(f3, 1), grenze=0.30 if fem else None, einheit='Hz',
                                quelle=Q['S3'], hinweis=hin, teil=teil, daten={'abweichung_S1': gegen}))
            merke(teil, f3, 'S3', False)
            if teil not in gefunden:
                d = kragarm_durchbiegung(E, rho, L, I, A, ms)
                f = f_aus_durchbiegung(d)
                erg.append(ergebnis('S1', T['S1'] + ' (analytisch)', 'info', wert=round(f, 1), einheit='Hz',
                                    quelle=Q['S1'], teil=teil,
                                    hinweis=f'{name}: kein FEM-Eigengewicht -> delta_st = qL^4/8EI + PL^3/3EI = '
                                            f'{d:.4g} mm aus Kragarm-Geometrie (Naeherung, ~20 % unter S3)',
                                    daten={'delta_mm': d}))
                merke(teil, f, 'Kragarm', False)
        # S1c Einmassenschwinger aus FEM-Federrate
        if teil not in gefunden and not balken:
            ks = []
            for fall, spec, e in P.faelle:
                namen, _ = _koerper(spec, e)
                if namen == [teil]:
                    for lf, l in e['lastfaelle'].items():
                        if (l.get('federrate_N_mm') or 0) > 0:
                            ks.append((l['federrate_N_mm'], f'{fall}/{lf}'))
            m = P.masse_kg(teil)
            if ks and m:
                zm = float(P.feld(teil, 'zusatzmasse_g', 0) or 0) / 1000.0
                k, wo = min(ks)
                f = f_einmassen(k, m + zm)
                erg.append(ergebnis('S1', T['S1'] + ' (Federrate)', 'info', wert=round(f, 1), einheit='Hz',
                                    quelle=Q['S1'], teil=teil,
                                    hinweis=f'kein FEM-Eigengewicht, kein Kragarm: Einmassenschwinger k = {k:.4g} N/mm '
                                            f'({wo}, weichster Lastfall), m = {(m + zm) * 1000:.1f} g ganze Teilmasse'
                                            f'{" + Zusatzmasse" if zm else ""} am Lastpunkt -> Untergrenze, nur fuer '
                                            'diese Lastrichtung; andere Moden (Platte) koennen tiefer liegen',
                                    daten={'k_N_mm': k, 'm_kg': m + zm, 'delta_mm': (m + zm) * G_MM_S2 * 1e-3 / k}))
                merke(teil, f, 'Federrate', True)
        if teil not in f1:
            erg.append(uebersprungen('S1', T['S1'], 'kein FEM-Lastfall mit "schwerkraft": true, kein soll-Feld '
                                     '"kragarm" und keine FEM-Federrate mit Teilmasse', Q['S1'], teil))

    # S2 Resonanzabstand
    for teil in sorted(f1):
        einzel = teil.split('+')[0]
        band = _band(P.feld(einzel, 'anregung_Hz'))
        angenommen = False
        if band is None and _lautsprecher(P):
            band, angenommen = SPRACHBAND, True
        if band is None:
            erg.append(uebersprungen('S2', T['S2'], 'soll-Feld anregung_Hz fehlt', Q['S2'], teil))
            continue
        fmin, fmax = band
        if fmax <= 0 or fmin < 0:       # 0 Hz = keine Anregung; negative Werte sind ein Eingabefehler (19.11.2026: Absturz)
            erg.append(uebersprungen('S2', T['S2'], f'anregung_Hz {band} ungueltig - ohne Anregung Feld weglassen, '
                                     'sonst f > 0 angeben', Q['S2'], teil))
            continue
        # Jede f1-Schaetzung einzeln bewerten, die schaerfste Stufe gilt (Befund S2-min-untergrenze):
        # die tiefste Schaetzung ist fuer die Isolationsaussage NICHT konservativ (S1b ~20 % unter S3,
        # S1c Untergrenze) - ein Resonanzalarm einer anderen Schaetzung darf nicht verloren gehen.
        rang = {'ok': 0, 'info': 1, 'warnung': 2, 'fehler': 3}
        bew = []
        for f, art, unter in sorted(f1[teil]):
            r = f / fmax
            zus = ''
            if f < fmin / math.sqrt(2):
                st = 'info'
                zus = '; ueberkritisch (Isolation, f/f1 > sqrt2) - Anlauf durch die Resonanz beachten'
            elif r >= 3:
                st = 'ok'
            elif r >= 2:
                st = 'warnung'
                zus = '; Abstand nur 2-3fach'
            else:
                st = 'warnung' if unter else 'fehler'
                zus = '; f1 im/nahe am Anregungsband -> Resonanz' + (
                    ' (f1 ist eine Untergrenze aus Einmassenschwinger: Resonanz nicht ausgeschlossen, FEM-Lastfall '
                    'schwerkraft rechnen)' if unter else '')
            bew.append((rang[st], -f, st, f, art, r, zus))
        _, _, stufe, f, art, r, zus = max(bew)
        hin = (f'f1 = {f:.0f} Hz ({art}), Anregung {fmin:g}-{fmax:g} Hz'
               + (' (Sprachband angenommen: Lautsprecher im Projekt, anregung_Hz fehlt)' if angenommen else '')
               + zus)
        if len(bew) > 1:
            hin += '; bewertet: schaerfste von ' + ', '.join(f'{b[4]} {b[3]:.0f} Hz ({b[2]})' for b in bew)
        erg.append(ergebnis('S2', T['S2'], stufe, wert=round(r, 2), grenze=3.0, einheit='f1/f_max', quelle=Q['S2'],
                            hinweis=hin, teil=teil, daten={'f1_Hz': f, 'band_Hz': list(band),
                                                           'schaetzungen': [[b[4], b[3], b[2]] for b in bew]}))

    # S4 Fallstoss
    h_m = P.proj.get('fallhoehe_m')
    if not h_m:
        erg.append(uebersprungen('S4', T['S4'], 'soll-Feld fallhoehe_m fehlt', Q['S4']))
        return erg, f1
    m_ges = P.proj.get('masse_g')
    if m_ges:
        m_ges = float(m_ges) / 1000.0
        m_hin = f'Geraetemasse {m_ges * 1000:g} g (soll masse_g)'
    else:
        ms = [P.masse_kg(t) for t in P.alle_steps()]
        if not ms or any(m is None for m in ms):
            erg.append(uebersprungen('S4', T['S4'], 'Geraetemasse unbekannt (soll masse_g oder Volumen+Material)',
                                     Q['S4']))
            return erg, f1
        zm = float(P.proj.get('zusatzmasse_g', 0) or 0) / 1000.0
        m_ges = sum(ms) + zm
        m_hin = f'Masse aller Teile {sum(ms) * 1000:.1f} g + Zusatzmasse {zm * 1000:g} g'
        if not zm:
            m_hin += ' (Einbauten ohne zusatzmasse_g nicht erfasst -> F zu klein)'
    # Kaelte versproedet (Befund Scheinsicherheit 15.11.2026): S >= 2 unter 5 C; T_min unbekannt + aussen -> kalt annehmen
    S_ziel, s_hin = S4_S_ZIEL, ''
    T_min = P.proj.get('T_min_C')
    from mb2 import realterme as rt
    if T_min is None and rt.kontext(P.pdir).get('aussen'):   # aussen auch aus den Projektmerkmalen
        S_ziel, s_hin = S4_S_ZIEL_KALT, '; T_min_C fehlt bei aussen -> kalt angenommen, S >= 2'
    elif T_min is not None and T_min < S4_T_KALT_C:
        S_ziel, s_hin = S4_S_ZIEL_KALT, f'; T_min {T_min:g} C < {S4_T_KALT_C:g} C (versproedet) -> S >= 2'
    n, achsen = 0, set()
    for fall, spec, e in P.faelle:
        namen, mats = _koerper(spec, e)
        stoffe = [mats.get(nm) for nm in namen if mats.get(nm) in DRUCKSTOFFE]
        if not stoffe:
            continue
        fz = min(MATERIAL[s]['festigkeit_z_MPa'] for s in stoffe)
        for lf, l in e['lastfaelle'].items():
            k, F = l.get('federrate_N_mm'), l.get('kraft_N')
            if not k or k <= 0 or not F or not l.get('max_vonMises_MPa'):
                continue
            Fn = math.sqrt(sum(x * x for x in F))
            if not Fn:
                continue
            achse = 'xyz'[max(range(3), key=lambda i: abs(F[i]))]
            achsen.add(achse)
            Fmax, d = fallstoss(m_ges, k, h_m * 1000.0)
            sig = l['max_vonMises_MPa'] * Fmax / Fn
            S = fz / sig
            stufe = 'ok' if S >= S_ziel else 'fehler'
            erg.append(ergebnis('S4', T['S4'], stufe, wert=round(S, 2), grenze=S_ziel, einheit='S_z', quelle=Q['S4'],
                                teil='+'.join(namen),
                                hinweis=f'{fall}/{lf} (Achse {achse}): h {h_m:g} m, {m_hin}, k {k:.4g} N/mm -> delta_st '
                                        f'{d:.3g} mm, F_max {Fmax:.0f} N (Ersatzlast), sigma {sig:.1f} MPa (linear aus '
                                        f'{l["max_vonMises_MPa"]:g} MPa bei {Fn:g} N), Festigkeit Z {fz:g} MPa; Boden '
                                        f'starr, Aufprall in Lastrichtung angenommen{s_hin}',
                                daten={'F_max_N': Fmax, 'delta_st_mm': d, 'sigma_MPa': sig, 'achse': achse,
                                       'S_ziel': S_ziel}))
            n += 1
    if not n:
        erg.append(uebersprungen('S4', T['S4'], 'kein FEM-Lastfall mit Federrate (k) und Spannung', Q['S4']))
    elif len(achsen) < 3:
        fehlt = sorted(set('xyz') - achsen)
        erg.append(ergebnis('S4', T['S4'] + ' (Achsen)', 'warnung', wert=len(achsen), grenze=3, einheit='Achsen',
                            quelle=Q['S4'],
                            hinweis=f'Fall nur in Achse {", ".join(sorted(achsen))} gerechnet (Federrate aus FEM-Lastfall); '
                                    f'Achse {", ".join(fehlt)} fehlt - Aufprall auf Seite/Ecke/Kante nicht geprueft. '
                                    'FEM-Lastfall mit Kraft in dieser Richtung (federrate_N_mm) ergaenzen',
                            daten={'achsen': sorted(achsen), 'fehlt': fehlt}))
    return erg, f1


# ------------------------------------------------------------------ S5-S8
def _lautsprecher(P):
    """[(teil oder None, eintrag)]"""
    out = []
    if isinstance(P.proj.get('lautsprecher'), dict):
        out.append((None, P.proj['lautsprecher']))
    for k, v in P.soll.items():
        if not k.startswith('_') and isinstance(v, dict) and isinstance(v.get('lautsprecher'), dict):
            out.append((k, v['lautsprecher']))
    return out


def _loecher(P, teil, ls):
    """-> (liste[(A, P, form)], l_mm, herkunft) oder (None, None, grund)."""
    lo = ls.get('loecher', 'auto' if ls.get('mitte_mm') else None)
    l = ls.get('wand_mm')
    if lo is None:
        return None, None, 'soll lautsprecher.loecher fehlt (oder mitte_mm + r_mm fuer "auto")'
    if lo == 'auto' or (isinstance(lo, dict) and lo.get('auto')):
        quelle = ls.get('teil') or teil
        if not quelle or not ls.get('mitte_mm') or not ls.get('r_mm'):
            return None, None, 'loecher "auto" braucht teil, mitte_mm und r_mm'
        s = P.step(quelle)
        if s is None:
            return None, None, f'out/{quelle}.step fehlt'
        paar, l_geo = loecher_auto(s, ls['mitte_mm'], float(ls['r_mm']), ls.get('achse', 'z'))
        if not paar:
            return None, None, f'keine Durchbrueche im Kreis r {ls["r_mm"]} um {ls["mitte_mm"]} gefunden'
        if l is None:
            l = l_geo
        if l is None:
            return None, None, 'Halslaenge nicht bestimmbar (wand_mm angeben)'
        return [(A, Pu, lochform(A, Pu)) for A, Pu in paar], float(l), f'aus out/{quelle}.step'
    if l is None:
        return None, None, 'soll lautsprecher.wand_mm (Halslaenge) fehlt'
    liste = []
    eintraege = lo.get('liste') if isinstance(lo, dict) and 'liste' in lo else [lo]
    for h in eintraege:
        nz = int(h.get('anzahl', 1))
        if 'd_mm' in h:
            a = float(h['d_mm']) / 2
            A, Pu = math.pi * a * a, 2 * math.pi * a
        elif 'breite_mm' in h and 'laenge_mm' in h:
            w, L = float(h['breite_mm']), float(h['laenge_mm'])
            A, Pu = w * L, 2 * (w + L)
        else:
            return None, None, 'loecher: d_mm oder breite_mm + laenge_mm fehlt'
        liste += [(A, Pu, lochform(A, Pu) if 'd_mm' not in h else ('rund', float(h['d_mm']) / 2))] * nz
    return liste, float(l), 'aus soll.json'


def _band_ls(P, teil, ls):
    b = _band(ls.get('band_Hz')) or _band(P.feld(teil, 'anregung_Hz'))
    return (b, False) if b else (SPRACHBAND, True)


def _akustik(P):
    erg = []
    eintr = _lautsprecher(P)
    if not eintr:
        for i in ('S5', 'S6', 'S7', 'S8'):
            erg.append(uebersprungen(i, T[i], 'kein soll-Feld lautsprecher', Q[i]))
        return erg
    for teil, ls in eintr:
        band, angen = _band_ls(P, teil, ls)
        b_hin = f'Band {band[0]:g}-{band[1]:g} Hz' + (' (Sprachband angenommen)' if angen else '')
        luft_hin = f'Luft {P.T_C:g} C: c {P.c / 1000:.1f} m/s, rho {P.rho:.3f} kg/m3'
        loecher, l, herkunft = _loecher(P, teil, ls)

        # S5 Helmholtz
        V = ls.get('vorkammer_mm3')
        vk = ls.get('vorkammer')
        D_v = None
        if V is None and isinstance(vk, dict) and vk.get('d_mm') and vk.get('h_mm'):
            V = math.pi * float(vk['d_mm']) ** 2 / 4 * float(vk['h_mm'])
            D_v = float(vk['d_mm'])
        if D_v is None:
            D_v = 2 * float(ls['r_mm']) if ls.get('r_mm') else (V ** (1 / 3) if V else None)
        if loecher is None:
            erg.append(uebersprungen('S5', T['S5'], herkunft, Q['S5'], teil))
        elif not V:
            erg.append(uebersprungen('S5', T['S5'], 'soll lautsprecher.vorkammer_mm3 (oder vorkammer d_mm/h_mm) '
                                     'fehlt - Volumen zwischen Membran und Gitter', Q['S5'], teil))
        else:
            V = float(V)
            hl = [(A, math.sqrt(A / math.pi)) for A, _, _ in loecher]
            fH = helmholtz(V, hl, l, P.c)
            lam = P.c / fH
            fmin_soll = float(ls.get('f_H_min_Hz', F_H_MIN))
            S_ges = sum(A for A, _, _ in loecher)
            gross = max(D_v or 0, l)
            gueltig = gross < 0.1 * lam
            if fH < band[1]:
                stufe = 'fehler'
            elif fH < fmin_soll or not gueltig:
                stufe = 'warnung'
            else:
                stufe = 'ok'
            hin = (f'{len(loecher)} Loecher {herkunft}, S = {S_ges:.1f} mm2, Hals l = {l:.2f} mm, V = {V:.0f} mm3; '
                   f'l_eff = l + 1,6 sqrt(S_i/pi) (bei Schlitzen konservativ); {luft_hin}; {b_hin}')
            if not gueltig:
                hin += (f'; Gueltigkeit verletzt: groesstes Mass {gross:.1f} mm >= 0,1 lambda = {0.1 * lam:.1f} mm '
                        '-> Vorkammer wirkt als Wellenleiter, f_H nur Richtwert')
            erg.append(ergebnis('S5', T['S5'], stufe, wert=round(fH), grenze=fmin_soll, einheit='Hz', quelle=Q['S5'],
                                hinweis=hin, teil=teil,
                                daten={'V_mm3': V, 'S_mm2': S_ges, 'l_mm': l, 'n_loecher': len(loecher),
                                       'lambda_mm': lam, 'gueltig': gueltig}))

        # S8 Grenzschicht
        if loecher is None:
            erg.append(uebersprungen('S8', T['S8'], herkunft, Q['S8'], teil))
        else:
            dv = grenzschicht_mm(band[0], P.rho, P.mu)
            amin = min(halbe_kleinste(f) for _, _, f in loecher)
            form = min((f for _, _, f in loecher), key=halbe_kleinste)
            stufe = 'ok' if amin >= 10 * dv else 'warnung'
            hin = (f'kleinste halbe Lochweite a = {amin:.3f} mm ({form[0]}, {herkunft}), delta_v({band[0]:g} Hz) = '
                   f'{dv:.4f} mm, Grenze 10 delta_v = {10 * dv:.3f} mm; {b_hin}')
            if stufe == 'warnung':
                hin += ' -> viskose Verluste im Gitter (daempft/filtert), Loecher groesser oder weniger lang'
            erg.append(ergebnis('S8', T['S8'], stufe, wert=round(amin / dv, 2), grenze=10.0, einheit='a/delta_v',
                                quelle=Q['S8'], hinweis=hin, teil=teil, daten={'a_mm': amin, 'delta_v_mm': dv}))

        # S7 + S6: Innenraum
        innen = ls.get('innen_mm')
        grenzen = None
        g_hin = 'aus soll innen_mm'
        shapes = None
        if not innen:
            namen = ls.get('gehaeuse_teile') or P.alle_steps()
            shapes = [P.step(n) for n in namen]
            shapes = [s for s in shapes if s is not None]
            if shapes:
                try:
                    r = innenraum(shapes)
                except Exception as ex:  # noqa: BLE001 - Geometriefehler sichtbar machen, nicht abstuerzen
                    r = None
                    g_hin = f'Strahl-Test gescheitert: {type(ex).__name__}: {ex}'
                if r:
                    innen, grenzen = r
                    g_hin = f'lichte Masse per Strahl-Test aus {", ".join(namen)} (Teile im Zusammenbau-Rahmen)'
        if not innen:
            for i in ('S7', 'S6'):
                erg.append(uebersprungen(i, T[i], 'Innenmasse unbekannt (soll lautsprecher.innen_mm oder '
                                         'out/*.step im gemeinsamen Rahmen) ' + ('' if g_hin.startswith('aus') else g_hin),
                                         Q[i], teil))
        else:
            innen = [float(x) for x in innen]
            fs = [stehwelle(L, P.c) for L in innen]
            im_band = [(a, f) for a, f in zip('xyz', fs) if f <= band[1]]
            moden = sum(int(band[1] // f) - max(0, math.ceil(band[0] / f) - 1) for f in fs)
            stufe = 'warnung' if im_band else 'ok'
            hin = (f'L = {" x ".join(f"{L:.1f}" for L in innen)} mm ({g_hin}) -> f1 = '
                   f'{", ".join(f"{a}: {f:.0f}" for a, f in zip("xyz", fs))} Hz; {b_hin}')
            if im_band:
                hin += (f'; {moden} axiale Moden im Band -> Daemmung (Vlies/Schaum an den grossen Waenden) '
                        'gegen Droehnen/Kammfilter')
            erg.append(ergebnis('S7', T['S7'], stufe, wert=round(min(fs)), grenze=band[1], einheit='Hz',
                                quelle=Q['S7'], hinweis=hin, teil=teil,
                                daten={'innen_mm': innen, 'f1_Hz': fs, 'moden_im_band': moden}))

            # S6 Luftpolster
            V_i = ls.get('innenvolumen_mm3')
            v_hin = 'aus soll innenvolumen_mm3'
            if V_i is None:
                V_brutto, V_netto = innen[0] * innen[1] * innen[2], None
                if grenzen and shapes:
                    V_brutto, V_netto = innenvolumen(shapes, grenzen)
                V_i = V_netto if V_netto is not None else V_brutto
                v_hin = (f'Quader {V_brutto / 1000:.1f} cm3' + (f' minus Teilematerial = {V_i / 1000:.1f} cm3'
                                                                  if V_netto is not None else ' (Teilematerial nicht abgezogen)'))
            V_i = float(V_i)
            ein = ls.get('einbauten_mm3')
            if ein:
                V_i -= float(ein)
                v_hin += f' minus Einbauten {float(ein) / 1000:.1f} cm3'
            if V_i <= 0:
                erg.append(ergebnis('S6', T['S6'], 'fehler', wert=V_i, einheit='mm3', quelle=Q['S6'], teil=teil,
                                    hinweis='Innenvolumen <= 0 nach Abzug der Einbauten - Eingaben pruefen'))
                continue
            C = nachgiebigkeit(V_i, P.rho, P.c)
            if not ls.get('f_s_Hz') or not ls.get('V_as_l'):
                erg.append(ergebnis('S6', T['S6'], 'uebersprungen', wert=None, quelle=Q['S6'], teil=teil,
                                    hinweis=f'Datenblatt f_s_Hz und V_as_l fehlen; Innenvolumen V = {V_i / 1000:.1f} cm3 '
                                            f'({v_hin}), C = V/(rho c^2) = {C:.3g} m3/Pa',
                                    daten={'V_mm3': V_i, 'C_m3_Pa': C}))
                continue
            f_s, V_as = float(ls['f_s_Hz']), float(ls['V_as_l']) * 1e6
            fc = box_fc(f_s, V_as, V_i)
            q = fc / f_s
            stufe = 'ok' if q < 1.5 else 'warnung'
            hin = (f'f_s {f_s:g} Hz, V_as {V_as / 1e6:g} l, V {V_i / 1000:.1f} cm3 ({v_hin}) -> f_c {fc:.0f} Hz, '
                   f'C = {C:.3g} m3/Pa')
            if not ein:
                stufe = 'warnung' if stufe == 'ok' else stufe
                hin += '; Einbauten (Platine, Lautsprecherkorb) nicht abgezogen (einbauten_mm3) -> V zu gross, f_c zu klein'
            if ls.get('geschlossen') is False:
                stufe = 'info'
                hin += '; Gehaeuse offen (Lueftung): Luftpolster wirkt nur teilweise, f_c ist Obergrenze'
            elif 'geschlossen' not in ls:
                hin += '; Dichtheit nicht angegeben (geschlossen), als geschlossen gerechnet'
            erg.append(ergebnis('S6', T['S6'], stufe, wert=round(q, 3), grenze=1.5, einheit='f_c/f_s', quelle=Q['S6'],
                                hinweis=hin, teil=teil, daten={'f_c_Hz': fc, 'V_mm3': V_i, 'C_m3_Pa': C}))

    return erg


def pruefe(pdir, soll_daten=None):
    """Alle S-Pruefungen. soll_daten ersetzt cad/soll.json (fuer Vorschlaege/Tests), Standard: aus dem Projekt."""
    P = Projekt(pdir, soll_daten)
    erg, _ = _s1_s4(P)
    erg += _akustik(P)
    return erg
