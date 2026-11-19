"""Mechanik am Teil (OCW_PRUEFKATALOG.md 3.1): M1-M6, M12-M16, M19, M21-M24, M26. M7-M9 liegen in einem anderen Modul.

Analytische Vorab-Schaetzung und Gegenprobe zur FEM. Einheiten: mm, N, MPa (= N/mm2), Grad bzw. rad.
Eingaben: cad/soll.json (je Teil, siehe unten), mb2/material.py (E, nu, Festigkeit XY/Z), mb2/kennwerte.py
(eps_zul, E_z, mu, K_IC, Streuung ...), fem/<fall>.json + .erg.json, out/<teil>.step und out/<teil>.pruefung.json.

Neue optionale soll.json-Felder je Teil (zusaetzlich zu FELDER.md):
  "material": "PETG"                          sonst _projekt.material, FEM-Koerper, print/slice.json
  "druckrichtung": "z" | "-y" | [x, y, z]     Schichtnormale im Teil-KS; sonst aus druck_drehung (cad_build)
  "sicherheit": 2.0                           Ziel-Sicherheit (Standard 2,0 wie fem.py; M26 kann sie nur erhoehen)
  "schnapper": [{.., "a_mm": Lastpunkt ab Wurzel (Std. L), "achse": Zungen-Laengsrichtung, "eps_zul": .., "mu": ..,
                 "rueck_winkel_grad": Haltewinkel, "anzahl": 1, "handkraft_N": 30}]
  "balken": [{"fall": "kraft", "last": "grat", "art": "kragarm"|"gelenkig"|"eingespannt", "L_mm", "b_mm", "h_mm",
              "a_mm": Lastpunkt (kragarm), "kraft_N": optional}]                          -> M3
  "knicken": [{"L_mm", "lagerung": "frei"|"gelenkig"|"eingespannt_gelenkig"|"eingespannt" oder "K",
               "b_mm"+"h_mm" | "d_mm" (+"d_innen_mm") | "I_mm4"+"A_mm2", "kraft_N", "achse"}]   -> M4
  "rippen": [{"h_mm", "t_mm", "a_mm", "rand": "frei"|"gelenkig", "druck_MPa", "schub_MPa"}]  -> M5 von Hand
  "rippen_drucklast": false                   erkannte Rippen tragen keine Drucklast in ihrer Ebene (M5 -> info)
  "schrauben": [{.., "last_N": Betriebslast je Schraube, "klemmlaenge_mm", "art": "direkt"|"insert"|"mutter"}]
  "inserts": [{.., "kraft_N" (sonst Schraubenkraft aus M12)}]
  "pressitze": [{.., "welle": "starr"|"gleich", "achse": Bohrungsachse, "mu"}]
  "scharniere": [{.., "achse": Dehnrichtung (quer zur Faltlinie), "eps_zul"}]
  "torsion": [{"art": "offen"|"rund"|"rohr"|"bredt", "T_Nmm", "b_mm", "t_mm", "d_mm", "d_innen_mm", "A_m_mm2"}]
  "deckelbiegung": [{"a_mm", "b_mm", "t_mm", "druck_MPa" | "last_N", "last_art": "flaeche"|"punkt",
                     "rand": "gelenkig"|"eingespannt", "abstand_mm"}]                     -> M19
  "zahnraeder": [{"m_mm", "z", "b_mm", "F_t_N" | "M_Nmm", "achse"}]                       -> M23
  "constraints": [{"name", "sperrt": ["x", "y", "rz", ..]} | {"name", "anzahl": n}], "fg_soll": 0   -> M24
Realterme (mb2/realterme.py, Audit 15.11.2026): Festigkeiten werden durch f = A_T * A_K * A_A geteilt, eps_zul der
  Schnapper durch f_eps (Zyklen, Kaelte) und S_eps 1,2; Annahmen -> hoechstens warnung. Je Eintrag optional:
  "dauerlast": true/false, "kurzzeit": true (Schnapper: Fuegen = kurzzeit, "vorgespannt": true = Dauerlast;
  Schrauben/Inserts/Pressitze = Dauerlast; Torsion/Zahnrad unbekannt -> unguenstig), Schnapper "zyklen",
  Schraube "rest_vorspannung" (F_rest/F0, sonst Kriechdaten aus kennwerte bzw. 0,5).
Ohne Eintrag in keinem Teil liefern M1, M2, M12-M16, M19, M23 je ein 'uebersprungen' (fuer AUSLOESER).
Projektweit (_projekt): "material", "sicherheit", "zuverlaessigkeit" (Std. 0,99), "lastfaktor" (Std. 1,0),
  "streuung_xy"/"streuung_z" (ueberschreiben kennwerte)                                    -> M26
"""
import glob
import json
import math
import os
import statistics

import numpy as np

from . import ergebnis, soll as _soll_lesen, uebersprungen
from .. import kennwerte, realterme
from ..material import DRUCKSTOFFE, MATERIAL

S_STANDARD = 2.0           # wie fem.py: Sicherheit >= 2
S_EPS = 1.2                # Reserve auf die (abgeminderte) zulaessige Dehnung der Schnapper (Audit 15.11.2026)
REST_VORSPANNUNG_STD = 0.5  # F(t_Ende)/F0 ohne Kriechdaten (ASA 0,48 aus kennwerte; PLA/PETG eher schlechter)
HANDKRAFT_N = 30.0         # Katalog M2
E_STAHL = 210000.0         # MPa, Schraube
COS_Z = math.cos(math.radians(45))    # Achse naeher als 45 Grad an der Schichtnormalen -> "quer zu den Schichten"
COS_XY = math.cos(math.radians(75))   # Achse mehr als 75 Grad von der Schichtnormalen -> "in der Schichtebene"
KOPF_ISO4762 = {2.0: 3.8, 2.5: 4.5, 3.0: 5.5, 4.0: 7.0, 5.0: 8.5, 6.0: 10.0}   # Zylinderkopf d_k (kleinster Kopf)
LINIENBREITE_STD = 0.45    # mm, PrusaSlicer-Automatik 1,125 * 0,4 mm

Q = {
    'M1': '3.064 latch_design, 2.001 L18-20, 2.72 L08 (OCW)',
    'M2': '2.001 L4 Reibung/Keil (OCW-Thema)',
    'M3': '2.001 L18-21, 2.080J L5 (OCW)',
    'M4': '2.002 L2, 2.080J L9/10 (OCW); Johnson-Parabel fuer gedrungene Staebe extern (Shigley)',
    'M5': '2.080J L11 Plattenbeulen (OCW)',
    'M6': '2.72 L04, 16.20 Unit 8 (OCW); K_t = 1 + 0,5*sqrt(t/rho) Naeherung an K_t(R/t)-Diagramme der '
          'Kunststoff-Konstruktionsleitfaeden (extern)',
    'M12': '2.72 L10 Schraubverbindungen (OCW); Kopf ISO 4762; Ersatzzylinder d_w + l/2 (Naeherung, extern)',
    'M13': '2.001 L17 Versagen/Schub (OCW-Thema)',
    'M14': '2.001 L14 duennwandig (OCW), Lame dickwandig (extern)',
    'M15': '2.72 L08 Biegegelenke (OCW)',
    'M16': '2.001 L22/23, 16.20 Unit 10-12 Torsion (OCW)',
    'M19': '2.080J L7 Platten (OCW-Thema); Beiwerte Timoshenko/Woinowsky-Krieger Tab. 8/23/26/35 (extern, nu=0,3)',
    'M21': '2.002, 2.080J L12 Plastizitaet (OCW)',
    'M22': '2.002 SES 23-26 Bruchmechanik (OCW)',
    'M23': '2.007 L13 Lewis (OCW); Formfaktor Y Shigley Tab. 14-2 (extern)',
    'M24': '2.72 L08 Constraints, 2.75 (OCW)',
    'M26': '2.72 L04 Zuverlaessigkeitsfaktor (OCW)',
}
RANG = {'ok': 0, 'uebersprungen': 0, 'info': 1, 'warnung': 2, 'fehler': 3}


# ================================================================ Hilfen

def _schlimmer(*stufen):
    return max(stufen, key=lambda s: RANG[s])


def _fehlt(item, keys):
    return [k for k in keys if item.get(k) is None]


def _liste(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def _r(x, n=3):
    return None if x is None else round(float(x), n)


def _achse(a):
    """'x', '-y', [x, y, z] -> Einheitsvektor oder None."""
    if a is None:
        return None
    if isinstance(a, str):
        s = a.strip().lower()
        sign = -1.0 if s.startswith('-') else 1.0
        s = s.lstrip('+-')
        if s not in ('x', 'y', 'z'):
            return None
        v = np.zeros(3)
        v['xyz'.index(s)] = sign
        return v
    v = np.asarray(a, float)
    n = np.linalg.norm(v)
    return v / n if v.shape == (3,) and n > 0 else None


def _lage(achse, dr):
    """Lage einer Spannungs-/Stabachse zu den Schichten: 'xy' (in der Ebene), 'z' (quer), 'schraeg' oder None."""
    a = _achse(achse)
    if a is None or dr is None:
        return None, None
    c = abs(float(a @ dr))
    return ('z' if c >= COS_Z else 'xy' if c <= COS_XY else 'schraeg'), c


class Kontext:
    """Alles, was die Pruefungen eines Projekts gemeinsam brauchen (einmal gelesen)."""

    def __init__(self, pdir):
        self.pdir = pdir
        self.soll = _soll_lesen(pdir)
        self.projekt = self.soll.get('_projekt', {})
        self.fem = self._fem()
        self._dr = {}
        self._geo = {}
        self._rk = None

    # ---- Dateien
    def _fem(self):
        out = []
        for p in sorted(glob.glob(os.path.join(self.pdir, 'fem', '*.json'))):
            if p.endswith('.erg.json'):
                continue
            ep = p[:-5] + '.erg.json'
            try:
                spec = json.load(open(p, encoding='utf-8'))
                erg = json.load(open(ep, encoding='utf-8')) if os.path.exists(ep) else None
            except Exception:  # noqa: BLE001 - kaputte Lastfall-Datei: nicht mitzaehlen, aber nicht abstuerzen
                continue
            out.append((os.path.basename(p)[:-5], spec, erg))
        return out

    def step_pfad(self, rel):
        p = rel if os.path.isabs(rel) else os.path.join(self.pdir, rel)
        return os.path.normcase(os.path.abspath(p))

    def teile(self):
        """Teilnamen aus soll.json, out/*.step und FEM-Koerpern (Name des Koerpers, falls STEP ausserhalb out/)."""
        namen = [k for k in self.soll if not k.startswith('_')]
        for p in sorted(glob.glob(os.path.join(self.pdir, 'out', '*.step'))):
            n = os.path.basename(p)[:-5]
            if n not in namen:
                namen.append(n)
        for n, _ in self.fem_steps().items():
            if n not in namen:
                namen.append(n)
        return namen

    def fem_steps(self):
        """FEM-Koerper mit eigener STEP-Datei ausserhalb out/ -> {name: pfad}."""
        out_dir = os.path.normcase(os.path.abspath(os.path.join(self.pdir, 'out')))
        r = {}
        for _, spec, _ in self.fem:
            for k in spec.get('koerper', []):
                if 'step' in k:
                    p = self.step_pfad(k['step'])
                    if os.path.dirname(p) != out_dir and os.path.exists(p):
                        r.setdefault(k.get('name') or os.path.basename(p)[:-5], p)
        return r

    def step(self, teil):
        p = os.path.join(self.pdir, 'out', teil + '.step')
        if os.path.exists(p):
            return p
        return self.fem_steps().get(teil)

    def ts(self, teil):
        return self.soll.get(teil, {}) if isinstance(self.soll.get(teil, {}), dict) else {}

    def faelle_zu(self, teil, mech=False):
        """FEM-Faelle, in denen das Teil vorkommt: [(fall, spec, erg, koerper-eintrag)]; mech=True nur Mechanik
        (Lastfall mit Lagerung)."""
        sp = self.step(teil)
        sp = os.path.normcase(os.path.abspath(sp)) if sp else None
        out = []
        for fall, spec, erg in self.fem:
            if mech and 'lagerung' not in spec:
                continue
            for k in spec.get('koerper', []):
                if 'step' in k and (self.step_pfad(k['step']) == sp or k.get('name') == teil):
                    out.append((fall, spec, erg, k))
                    break
        return out

    # ---- Material
    def material(self, teil):
        ts = self.ts(teil)
        for m, q in ((ts.get('material'), 'soll.json Teil'), (self.projekt.get('material'), 'soll.json _projekt')):
            if m:
                return str(m).upper(), q
        for fall, _, _, k in self.faelle_zu(teil):
            if str(k.get('material', '')).upper() in DRUCKSTOFFE:
                return k['material'].upper(), f'FEM-Fall {fall}'
        sp = os.path.join(self.pdir, 'print', 'slice.json')
        if os.path.exists(sp):
            try:
                ft = json.load(open(sp, encoding='utf-8')).get('stats', {}).get('filament_type', '')
                if str(ft).upper() in DRUCKSTOFFE:
                    return str(ft).upper(), 'print/slice.json'
            except Exception:  # noqa: BLE001
                pass
        return None, 'Material unbekannt (soll.json "material", FEM-Koerper oder print/slice.json)'

    # ---- Druckrichtung
    def druckrichtung(self, teil):
        """(Schichtnormale im Teil-KS oder None, Herkunft)."""
        if teil in self._dr:
            return self._dr[teil]
        ts = self.ts(teil)
        r = (None, 'Druckrichtung unbekannt (soll.json "druckrichtung" oder cad_build mit druck)')
        if ts.get('druckrichtung') is not None:
            v = _achse(ts['druckrichtung'])
            r = (v, 'soll.json druckrichtung') if v is not None else (None, 'soll.json druckrichtung unlesbar')
        else:
            pp = os.path.join(self.pdir, 'out', teil + '.pruefung.json')
            if os.path.exists(pp):
                try:
                    d = json.load(open(pp, encoding='utf-8')).get('druck_drehung')
                    if d is not None:
                        from .. import geometrie
                        r = (geometrie.baurichtung(tuple(d)), f'cad druck_drehung {list(d)}')
                except Exception:  # noqa: BLE001
                    pass
        self._dr[teil] = r
        return r

    # ---- Sicherheit
    def S(self, teil, richtung='z'):
        """Ziel-Sicherheit: soll.json (Teil, sonst _projekt, sonst 2,0), von M26 hoechstens erhoeht."""
        ts = self.ts(teil)
        basis = float(ts.get('sicherheit') or self.projekt.get('sicherheit') or S_STANDARD)
        mat, _ = self.material(teil)
        s26 = m26_sicherheit(self.projekt, mat, richtung) if mat else None
        return max(basis, s26) if s26 and s26 > 0 else basis

    def kw(self, mat, feld, item=None, key=None):
        if item is not None and item.get(key or feld) is not None:
            return float(item[key or feld]), 'soll.json'
        v = kennwerte.wert(mat, feld) if mat else None
        return (v, 'kennwerte.py') if v is not None else (None, None)

    # ---- Realterme (mb2/realterme.py, Audit Scheinsicherheit 15.11.2026)
    def realkontext(self, teil, **extra):
        """realterme.kontext fuer ein Teil: _projekt + Merkmale, Material des Teils, Teil-Felder T_max_C/T_min_C/aussen."""
        if self._rk is None:
            try:
                from .merkmale import merkmale as _m
                mk = _m(self.pdir)
            except Exception:  # noqa: BLE001 - ohne Merkmale gelten die unguenstigen Standards
                mk = {}
            self._rk = realterme.kontext(self.pdir, soll=self.soll, merkmale=mk)
        k = dict(self._rk)
        mat, _ = self.material(teil)
        if mat:
            k['material'] = mat
        ts = self.ts(teil)
        for f in ('T_max_C', 'T_min_C', 'aussen'):
            if ts.get(f) is not None:
                k[f] = ts[f]
        k.update(extra)
        return k

    def abm(self, teil, groesse='festigkeit', item=None, dauerlast=None, **extra):
        """(faktor, terme, angenommen). dauerlast: True/False/None (unbekannt -> unguenstig); ein Eintrag (item) kann
        es mit "dauerlast": true/false oder "kurzzeit": true festlegen."""
        dl = dauerlast
        if item is not None:
            if isinstance(item.get('dauerlast'), bool):
                dl = item['dauerlast']
            if item.get('kurzzeit') is True:
                dl = False
        kk = self.realkontext(teil, dauerlast=dl, **extra)
        tt, a_t = [], False
        if groesse == 'festigkeit' and kk.get('T_teil_C') is None:   # Teiltemperatur samt Herkunft in die Terme
            kk['T_teil_C'], tt, a_t = realterme.teil_temperatur(kk)
        f, terme, ang = realterme.abminderung(groesse, kk)
        return f, tt + terme, ang or a_t

    # ---- Geometrie (einmal je Teil)
    def geo(self, teil):
        if teil not in self._geo:
            sp = self.step(teil)
            if not sp:
                self._geo[teil] = None
            else:
                from .. import geometrie
                self._geo[teil] = geometrie.merkmale(sp)
        return self._geo[teil]


def _mat(mat):
    return MATERIAL.get(mat) if mat in DRUCKSTOFFE else None


def _fest(m, lage, abm=(1.0, [], False)):
    """Wirksame Festigkeit fuer eine Spannung laengs einer Achse: in der Schichtebene sigma_XY, sonst (quer, schraeg
    oder unbekannt) sigma_Z - im Zweifel der kleinere Wert -, geteilt durch die Abminderung aus realterme
    (abm = abminderung('festigkeit', k)). Rueckgabe (sigma_wirksam, Name, sigma_roh)."""
    roh, name = (m['festigkeit_xy_MPa'], 'sigma_XY') if lage == 'xy' else (m['festigkeit_z_MPa'], 'sigma_Z')
    return roh / abm[0], name, roh


def _rt(abm):
    """Hinweis-Anhang mit den Realtermen."""
    h = realterme.hinweis(abm[1])
    return (f'; {h} (f = {abm[0]:.2f})' if h else '') + ('; Annahmen -> hoechstens warnung' if abm[2] else '')


def _sicherheit_stufe(s_ist, s_ziel):
    return 'ok' if s_ist >= s_ziel else 'warnung' if s_ist >= 1.0 else 'fehler'


# ================================================================ M1, M2 Schnapphaken + Fuegekraft

def m1_schnapper(s):
    """Rechteck-Kragarm, Last am Punkt a (Haken-Nase), Auslenkung y dort.
    F = 3EIy/a^3 = E b t^3 y / (4 a^3), eps = 1,5 t y / a^2 (a = L: Katalogformel), Spitze: d = F a^2 (3L - a)/(6EI)."""
    L, b, t, y = (float(s[k]) for k in ('L_mm', 'b_mm', 't_mm', 'hinterschnitt_mm'))
    a = float(s.get('a_mm') or L)
    E = float(s['E_MPa'])
    eps = 1.5 * t * y / a ** 2
    F = E * b * t ** 3 * y / (4 * a ** 3)
    I = b * t ** 3 / 12
    d_spitze = F * a ** 2 * (3 * L - a) / (6 * E * I)
    return {'eps': eps, 'sigma_MPa': E * eps, 'F_N': F, 'd_spitze_mm': d_spitze, 'I_mm4': I}


def m2_fuegekraft(F, mu, winkel_grad):
    """W = F (mu + tan a) / (1 - mu tan a); None bei Selbsthemmung (Nenner <= 0)."""
    ta = math.tan(math.radians(winkel_grad))
    nenner = 1 - mu * ta
    return None if nenner <= 0 else F * (mu + ta) / nenner


def _pruefe_schnapper(k, teil, mat, dr, dr_q):
    out = []
    m = _mat(mat)
    for i, s in enumerate(_liste(k.ts(teil).get('schnapper'))):
        name = s.get('name') or f'schnapper{i + 1}'
        titel = f'Schnapphaken {name}'
        fehlt = _fehlt(s, ('L_mm', 'b_mm', 't_mm', 'hinterschnitt_mm'))
        if fehlt:
            out.append(uebersprungen('M1', titel, f'Felder fehlen: {fehlt}', Q['M1'], teil))
            continue
        lage, c = _lage(s.get('achse'), dr)
        # Druckrichtung
        if s.get('achse') is None:
            out.append(uebersprungen('M1', titel + ': Druckrichtung', '"achse" (Zungen-Laengsrichtung) fehlt',
                                     Q['M1'], teil))
        elif dr is None:
            out.append(uebersprungen('M1', titel + ': Druckrichtung', dr_q, Q['M1'], teil))
        else:
            st = {'z': 'fehler', 'schraeg': 'warnung', 'xy': 'ok'}[lage]
            out.append(ergebnis('M1', titel + ': Druckrichtung', st, wert=_r(math.degrees(math.acos(min(1, c))), 1),
                                grenze=75.0, einheit='Grad zur Schichtnormalen', quelle=Q['M1'], teil=teil,
                                hinweis={'z': 'Hakenachse parallel zur Druckrichtung: Biegung quer zu den Schichten '
                                              '- Haken bricht zwischen den Lagen. Teil drehen (Zunge liegend).',
                                         'schraeg': 'Hakenachse schraeg zu den Schichten - Festigkeit gegen sigma_Z.',
                                         'xy': 'Biegung in der Schichtebene.'}[lage] + f' ({dr_q})'))
        if m is None:
            out.append(uebersprungen('M1', titel, k.material(teil)[1], Q['M1'], teil))
            continue
        r = m1_schnapper({**s, 'E_MPa': m['E_MPa']})
        # Dehnung
        feld = 'eps_zul_xy' if lage == 'xy' else 'eps_zul_z'
        ez, ezq = k.kw(mat, feld, s, 'eps_zul')
        daten = {'F_auslenk_N': _r(r['F_N']), 'd_spitze_mm': _r(r['d_spitze_mm']), 'lage': lage}
        if ez is None:
            out.append(uebersprungen('M1', titel + ': Dehnung',
                                     f'eps = {r["eps"]:.4f}; eps_zul unbekannt ({feld} in kennwerte.py oder '
                                     f'"eps_zul" im Schnapper)', Q['M1'], teil))
        else:
            # Realterme: haeufiges Fuegen x0,6, Kaelte x0,7 (realterme 'eps_zul'), dazu Reserve S_eps 1,2
            ae = k.abm(teil, 'eps_zul', zyklen=s.get('zyklen'))
            ez_real = ez / ae[0]
            ez_eff = ez_real / S_EPS
            st = 'ok' if r['eps'] <= ez_eff else 'warnung' if r['eps'] <= ez_real else 'fehler'
            out.append(ergebnis('M1', titel + ': Dehnung', realterme.deckel(st, ae[2]),
                                wert=_r(r['eps'], 5), grenze=_r(ez_eff, 5), einheit='-', quelle=Q['M1'], teil=teil,
                                hinweis=f'eps = 1,5*t*y/a^2 gegen eps_zul {feld} {ez} ({ezq}) / {ae[0]:.2f} / S_eps '
                                        f'{S_EPS} = {ez_eff:.5f}; ueber {ez_real:.5f} fehler' + _rt(ae),
                                daten={**daten, 'eps_zul_roh': ez, 'eps_zul_real': _r(ez_real, 5),
                                       'abminderung': _r(ae[0], 3), 'realterme': ae[1]}))
        # Fuegen ist Kurzzeitlast; vorgespannt in Ruhelage ("vorgespannt": true) ist Dauerlast
        af = k.abm(teil, 'festigkeit', item=s, dauerlast=bool(s.get('vorgespannt')))
        sig_f, sig_n, sig_roh = _fest(m, lage, af)
        st = 'ok' if r['sigma_MPa'] <= sig_f / 1.5 else 'warnung' if r['sigma_MPa'] <= sig_f else 'fehler'
        out.append(ergebnis('M1', titel + ': Spannung', realterme.deckel(st, af[2]), wert=_r(r['sigma_MPa'], 2),
                            grenze=_r(sig_f / 1.5, 2), einheit='MPa', quelle=Q['M1'], teil=teil,
                            daten={**daten, 'festigkeit_roh_MPa': sig_roh, 'abminderung': _r(af[0], 3),
                                   'realterme': af[1]},
                            hinweis=f'sigma = E*eps linear (ueberschaetzt, Sekantenmodul kleiner) gegen '
                                    f'{sig_n} {sig_roh} / {af[0]:.2f} / 1,5'
                                    + ('' if lage else '; Lage unbekannt -> sigma_Z') + _rt(af)))
        # M2 Fuegekraft
        if s.get('winkel_grad') is None:
            out.append(uebersprungen('M2', f'Fuegekraft {name}', '"winkel_grad" (Einfuehrschraege) fehlt',
                                     Q['M2'], teil))
            continue
        mu, muq = k.kw(mat, 'mu', s)
        if mu is None:
            out.append(uebersprungen('M2', f'Fuegekraft {name}', 'Reibwert mu unbekannt (kennwerte.py "mu" oder '
                                     '"mu" im Schnapper)', Q['M2'], teil))
            continue
        n = int(s.get('anzahl') or 1)
        grenze = float(s.get('handkraft_N') or HANDKRAFT_N)
        W = m2_fuegekraft(r['F_N'], mu, float(s['winkel_grad']))
        if W is None:
            out.append(ergebnis('M2', f'Fuegekraft {name}', 'fehler', wert=None, grenze=grenze, einheit='N',
                                quelle=Q['M2'], teil=teil,
                                hinweis=f'Selbsthemmung: 1 - mu*tan(alpha) <= 0 (mu {mu}, alpha {s["winkel_grad"]} '
                                        'Grad) - Montage unmoeglich, Schraege flacher'))
        else:
            out.append(ergebnis('M2', f'Fuegekraft {name}', 'ok' if W * n <= grenze else 'warnung',
                                wert=_r(W * n, 2), grenze=grenze, einheit='N', quelle=Q['M2'], teil=teil,
                                hinweis=f'W = F(mu + tan a)/(1 - mu tan a), F = {r["F_N"]:.2f} N, mu {mu} ({muq}), '
                                        f'{n} Haken'))
        if s.get('rueck_winkel_grad') is not None:
            Wl = m2_fuegekraft(r['F_N'], mu, float(s['rueck_winkel_grad']))
            out.append(ergebnis('M2', f'Loesekraft {name}', 'info', wert=None if Wl is None else _r(Wl * n, 2),
                                einheit='N', quelle=Q['M2'], teil=teil,
                                hinweis='selbsthemmend: haelt formschluessig, nur durch Aufbiegen loesbar'
                                if Wl is None else 'Kraft zum Abziehen ueber die Haltekante'))
    return out


# ================================================================ M3 Balken-Gegenprobe

def m3_balken(art, F, L, E, I, c, a=None):
    """(Weg am Lastpunkt, Biegespannung max). kragarm: Last bei a (Std. L); gelenkig/eingespannt: Last mittig."""
    if art == 'kragarm':
        a = a or L
        return F * a ** 3 / (3 * E * I), F * a * c / I
    if art == 'gelenkig':
        return F * L ** 3 / (48 * E * I), F * L / 4 * c / I
    if art == 'eingespannt':
        return F * L ** 3 / (192 * E * I), F * L / 8 * c / I
    raise ValueError(f'art {art!r} unbekannt (kragarm, gelenkig, eingespannt)')


def _pruefe_balken(k, teil, mat):
    out = []
    faelle = {f: (spec, erg) for f, spec, erg in k.fem}
    for i, b in enumerate(_liste(k.ts(teil).get('balken'))):
        titel = f'Balken-Gegenprobe {b.get("name") or b.get("fall", "") + "/" + str(b.get("last", ""))}'
        fehlt = _fehlt(b, ('fall', 'last', 'art', 'L_mm', 'b_mm', 'h_mm'))
        if fehlt:
            out.append(uebersprungen('M3', titel, f'Felder fehlen: {fehlt}', Q['M3'], teil))
            continue
        spec, erg = faelle.get(b['fall'], (None, None))
        lf = (erg or {}).get('lastfaelle', {}).get(b['last'])
        if lf is None:
            out.append(uebersprungen('M3', titel, f'FEM-Ergebnis fem/{b["fall"]}.erg.json Lastfall {b["last"]} fehlt',
                                     Q['M3'], teil))
            continue
        fm = mat
        for kk in spec.get('koerper', []):
            if str(kk.get('material', '')).upper() in DRUCKSTOFFE:
                fm = kk['material'].upper()
                break
        m = _mat(fm)
        if m is None:
            out.append(uebersprungen('M3', titel, 'Material unbekannt', Q['M3'], teil))
            continue
        Fv = np.asarray(lf.get('kraft_N') or [0, 0, 0], float)
        F = float(b['kraft_N']) if b.get('kraft_N') is not None else float(np.linalg.norm(Fv))
        if F == 0 and lf.get('kraft_in_wegrichtung_N') is not None:
            F = abs(float(lf['kraft_in_wegrichtung_N']))
        if F <= 0:
            out.append(uebersprungen('M3', titel, 'keine Kraft im Lastfall und kein "kraft_N"', Q['M3'], teil))
            continue
        L, bb, h = float(b['L_mm']), float(b['b_mm']), float(b['h_mm'])
        I = bb * h ** 3 / 12
        d_an, s_an = m3_balken(b['art'], F, L, m['E_MPa'], I, h / 2, b.get('a_mm'))
        # FEM-Weg am Lastpunkt in Kraftrichtung
        if lf.get('verschiebung_lastflaeche_mm') and np.linalg.norm(Fv) > 0:
            d_fem = abs(float(np.asarray(lf['verschiebung_lastflaeche_mm']) @ Fv / np.linalg.norm(Fv)))
            dq = 'Lastflaeche in Kraftrichtung'
        else:
            d_fem = float(lf.get('max_verschiebung_mm') or 0)
            dq = 'max. Verschiebung (keine Lastflaeche)'
        dv = d_fem / d_an - 1
        st = 'ok' if abs(dv) <= 0.2 else 'info' if abs(dv) <= 0.3 else 'warnung'
        out.append(ergebnis('M3', titel + ': Weg', st, wert=_r(d_fem, 4), grenze=_r(d_an, 4), einheit='mm',
                            quelle=Q['M3'], teil=teil, daten={'abweichung': _r(dv, 3)},
                            hinweis=f'FEM ({dq}) {dv:+.0%} gegen Balken {b["art"]} (E {m["E_MPa"]:.0f}, F {F:.2f} N); '
                                    '+15..20 % durch nachgiebige Einspannung ist normal; > 30 % Netz/RB pruefen'))
        s_fem = lf.get('max_vonMises_integrationspunkte_MPa') or lf.get('max_vonMises_MPa')
        if s_fem:
            q = float(s_fem) / s_an
            if q > 1.3:
                st, hw = 'warnung', ('FEM-Spitze deutlich ueber Balkenwert: oertliche Kerbe oder Lasteinleitung '
                                     '(singulaer?) - siehe M6/F22, Spitzenwert nicht fuer die Sicherheit nehmen')
            elif q < 0.7:
                st, hw = 'warnung', 'FEM unter Balkenwert: Netz zu grob oder Lagerung/Last falsch gesetzt'
            else:
                st, hw = 'ok', 'Balken und FEM passen'
            out.append(ergebnis('M3', titel + ': Spannung', st, wert=_r(s_fem, 2), grenze=_r(s_an, 2), einheit='MPa',
                                quelle=Q['M3'], teil=teil, daten={'verhaeltnis': _r(q, 2)},
                                hinweis=f'sigma = M c / I = {s_an:.2f} MPa; ' + hw))
    return out


# ================================================================ M4 Knicken

K_LAGERUNG = {'frei': 2.0, 'gelenkig': 1.0, 'eingespannt_gelenkig': 0.7, 'eingespannt': 0.5}


def querschnitt(s):
    """(I_min, A) fuer Rechteck b x h, Rund d (+ d_innen) oder direkt I_mm4/A_mm2."""
    if s.get('I_mm4') is not None and s.get('A_mm2') is not None:
        return float(s['I_mm4']), float(s['A_mm2'])
    if s.get('b_mm') is not None and s.get('h_mm') is not None:
        b, h = float(s['b_mm']), float(s['h_mm'])
        return max(b, h) * min(b, h) ** 3 / 12, b * h
    if s.get('d_mm') is not None:
        d, di = float(s['d_mm']), float(s.get('d_innen_mm') or 0)
        return math.pi * (d ** 4 - di ** 4) / 64, math.pi * (d ** 2 - di ** 2) / 4
    return None, None


def m4_knicken(E, I, A, K, L, sigma_y):
    """Euler P = pi^2 E I/(K L)^2; gedrungen (lambda < pi*sqrt(2E/sigma_y)): Johnson P = A s_y (1 - s_y l^2/(4 pi^2 E))."""
    lam = K * L / math.sqrt(I / A)
    lam_c = math.pi * math.sqrt(2 * E / sigma_y)
    if lam >= lam_c:
        return math.pi ** 2 * E * I / (K * L) ** 2, lam, 'Euler'
    return A * sigma_y * (1 - sigma_y * lam ** 2 / (4 * math.pi ** 2 * E)), lam, 'Johnson'


def _pruefe_knicken(k, teil, mat, dr, dr_q):
    out = []
    m = _mat(mat)
    for i, s in enumerate(_liste(k.ts(teil).get('knicken'))):
        titel = f'Knicken {s.get("name") or i + 1}'
        I, A = querschnitt(s)
        fehlt = _fehlt(s, ('L_mm', 'kraft_N')) + ([] if I else ['Querschnitt (b_mm+h_mm, d_mm oder I_mm4+A_mm2)'])
        Kf = s.get('K') if s.get('K') is not None else K_LAGERUNG.get(s.get('lagerung'))
        if Kf is None:
            fehlt.append('lagerung/K')
        if fehlt:
            out.append(uebersprungen('M4', titel, f'Felder fehlen: {fehlt}', Q['M4'], teil))
            continue
        if m is None:
            out.append(uebersprungen('M4', titel, k.material(teil)[1], Q['M4'], teil))
            continue
        lage, _ = _lage(s.get('achse'), dr)
        E, hw, st_min = m['E_MPa'], [], 'ok'
        ez, _ = k.kw(mat, 'E_z_MPa')
        if lage in ('z', 'schraeg', None):
            if ez is not None:
                E = min(E, ez)
                hw.append(f'E_Z = {ez:.0f} MPa (Stab nicht sicher in der Schichtebene)')
            else:
                hw.append('E_Z unbekannt - mit E_XY gerechnet (nicht konservativ)')
                st_min = 'warnung'
        druck, dq = k.kw(mat, 'druck_MPa')
        if druck is None:
            druck, dq = m['festigkeit_xy_MPa'], 'Zugfestigkeit XY als Ersatz (Druck meist hoeher)'
        P = float(s['kraft_N'])
        Pcr, lam, art = m4_knicken(E, I, A, float(Kf), float(s['L_mm']), druck)
        q = Pcr / P if P > 0 else float('inf')
        st = 'ok' if q >= 3 else 'warnung' if q >= 1 else 'fehler'
        out.append(ergebnis('M4', titel, _schlimmer(st, st_min), wert=_r(q, 2), grenze=3.0, einheit='P_cr/P',
                            quelle=Q['M4'], teil=teil, daten={'P_cr_N': _r(Pcr, 2), 'schlankheit': _r(lam, 1),
                                                              'verfahren': art},
                            hinweis=f'{art}: P_cr = {Pcr:.1f} N bei K = {Kf}, lineare FEM sieht Knicken nicht; '
                                    + '; '.join(hw) + f'; Druckgrenze {druck:.0f} MPa ({dq})'))
    return out


# ================================================================ M5 Plattenbeulen / Rippen

def beul_faktor(E, nu):
    return math.pi ** 2 * E / (12 * (1 - nu ** 2))


def m5_k(h, a, rand):
    """k: 'gelenkig' (beide Laengsraender gestuetzt) 4; freier Rand 0,456 + (h/a)^2 (Enden gestuetzt) bzw. 0,425
    (Enden frei, langer Streifen)."""
    if rand == 'gelenkig':
        return 4.0
    if rand == 'frei_enden' or not a:
        return 0.425
    return 0.456 + (h / a) ** 2


def m5_grenze_ht(E, nu, sigma, k):
    """h/t, bei dem sigma_cr = sigma (Formregel: Rippe beult nicht vor dem Werkstoffversagen)."""
    return math.sqrt(k * beul_faktor(E, nu) / sigma)


def _pruefe_rippen(k, teil, mat, dr):
    out = []
    ts = k.ts(teil)
    m = _mat(mat)
    # ---- von Hand
    for i, s in enumerate(_liste(ts.get('rippen'))):
        titel = f'Beulen {s.get("name") or "Rippe " + str(i + 1)}'
        fehlt = _fehlt(s, ('h_mm', 't_mm'))
        if fehlt or m is None:
            out.append(uebersprungen('M5', titel, f'Felder fehlen: {fehlt}' if fehlt else k.material(teil)[1],
                                     Q['M5'], teil))
            continue
        h, t, a = float(s['h_mm']), float(s['t_mm']), s.get('a_mm')
        kk = m5_k(h, float(a) if a else None, s.get('rand', 'frei'))
        scr = kk * beul_faktor(m['E_MPa'], m['nu']) * (t / h) ** 2
        S = k.S(teil, 'xy')
        if s.get('druck_MPa') is not None:
            q = scr / float(s['druck_MPa'])
            out.append(ergebnis('M5', titel, _sicherheit_stufe(q, S), wert=_r(q, 2), grenze=_r(S, 2),
                                einheit='sigma_cr/sigma', quelle=Q['M5'], teil=teil,
                                hinweis=f'sigma_cr = k pi^2 E/(12(1-nu^2)) (t/h)^2 = {scr:.1f} MPa, k = {kk:.3f}'))
        else:
            st = 'ok' if scr >= m['festigkeit_xy_MPa'] else 'warnung'
            out.append(ergebnis('M5', titel, st, wert=_r(scr, 1), grenze=m['festigkeit_xy_MPa'], einheit='MPa',
                                quelle=Q['M5'], teil=teil,
                                hinweis=f'Formregel sigma_cr >= sigma_XY (k = {kk:.3f}); Druckspannung unbekannt'))
        if s.get('schub_MPa') is not None:
            bmin = min(h, float(a)) if a else h
            ks = 5.35 + (4 * (bmin / float(a)) ** 2 if a else 0)
            tcr = ks * beul_faktor(m['E_MPa'], m['nu']) * (t / bmin) ** 2
            q = tcr / float(s['schub_MPa'])
            out.append(ergebnis('M5', titel + ' (Schub)', _sicherheit_stufe(q, S), wert=_r(q, 2), grenze=_r(S, 2),
                                einheit='tau_cr/tau', quelle=Q['M5'], teil=teil,
                                hinweis=f'k_s = 5,35 + 4(b/a)^2 = {ks:.2f} (gelenkig), tau_cr = {tcr:.1f} MPa'))
    # ---- automatisch aus der Geometrie
    g = k.geo(teil)
    if g is None:
        return out
    titel = 'Rippen-Schlankheit h/t (aus STEP)'
    if not g['rippen']:
        out.append(ergebnis('M5', titel, 'ok', wert=0, einheit='Rippen', quelle=Q['M5'], teil=teil,
                            hinweis='keine duennen Rippen/Waende mit freiem Rand erkannt'))
        return out
    stoffe = [mat] if m else list(DRUCKSTOFFE)
    ez_alle = {s: kennwerte.wert(s, 'E_z_MPa') for s in stoffe}
    zu_schlank = []
    for r in g['rippen']:
        kk = m5_k(r['h_mm'], r['a_mm'], 'frei_enden' if r['freie_enden'] else 'frei')
        n = np.asarray(r['ebene_normale'])
        grenzen = []
        for s in stoffe:
            ms = MATERIAL[s]
            E = ms['E_MPa']
            # Rippenebene enthaelt die Druckrichtung (stehende Rippe): E_Z, falls bekannt
            if ez_alle[s] is not None and (dr is None or abs(float(n @ dr)) < COS_XY):
                E = min(E, ez_alle[s])
            grenzen.append(m5_grenze_ht(E, ms['nu'], ms['festigkeit_xy_MPa'], kk))
        gr = min(grenzen)
        ht = r['h_mm'] / r['t_mm']
        if ht > gr:
            zu_schlank.append({**r, 'h_t': _r(ht, 2), 'grenze_h_t': _r(gr, 2), 'k': _r(kk, 3)})
    zu_schlank.sort(key=lambda r: -r['h_t'] / r['grenze_h_t'])
    drucklast = ts.get('rippen_drucklast', True)
    mq = mat if m else 'unguenstigstes Druckmaterial (Material unbekannt)'
    if not zu_schlank:
        out.append(ergebnis('M5', titel, 'ok', wert=len(g['rippen']), einheit='Rippen', quelle=Q['M5'], teil=teil,
                            hinweis=f'alle {len(g["rippen"])} Rippen unter der Grenze h/t ({mq})'))
    else:
        w = zu_schlank[0]
        st = 'warnung' if drucklast is not False else 'info'
        out.append(ergebnis('M5', titel, st, wert=w['h_t'], grenze=w['grenze_h_t'], einheit='h/t', quelle=Q['M5'],
                            teil=teil, daten={'zu_schlank': zu_schlank[:10], 'anzahl': len(zu_schlank)},
                            hinweis=f'{len(zu_schlank)} Rippen/Waende beulen vor dem Werkstoffversagen, wenn sie in '
                                    f'ihrer Ebene auf Druck belastet werden (k = 0,456 + (h/a)^2, Enden frei 0,425; '
                                    f'{mq}); schlankste bei {w["kappe"]}: h {w["h_mm"]} / t {w["t_mm"]}. '
                                    + ('Ausnahme soll.json rippen_drucklast=false: keine Drucklast in Wandebene.'
                                       if drucklast is False else
                                       'Abhilfe: dicker, niedriger, Querrippe; ohne Drucklast in Wandebene '
                                       'soll.json "rippen_drucklast": false setzen.')))
    return out


# ================================================================ M6 Kerbwirkung

def m6_kt(rho, t):
    """K_t-Naeherung fuer Innenecken (Kehle rho an Wand t): 1 + 0,5*sqrt(t/rho); q ~ 1 -> K_f = K_t."""
    return 1 + 0.5 * math.sqrt(t / rho)


def _in_box(p, box, rand=0.0):
    return all(box[i] - rand <= p[i] <= box[i + 3] + rand for i in range(3))


def _pruefe_kerben(k, teil):
    out = []
    g = k.geo(teil)
    if g is None:
        return [uebersprungen('M6', 'Kerbwirkung Innenecken', 'kein STEP (out/<teil>.step)', Q['M6'], teil)]
    scharf = sorted(g['innenkanten'], key=lambda e: -(e['laenge_mm']))
    if scharf:
        out.append(ergebnis('M6', 'Scharfe Innenecken', 'warnung', wert=len(scharf), grenze=0, einheit='Kanten',
                            quelle=Q['M6'], teil=teil,
                            daten={'kanten': scharf[:15], 'laenge_summe_mm': _r(sum(e['laenge_mm'] for e in scharf), 1)},
                            hinweis='Innenecke ohne Rundung: K_t theoretisch unbegrenzt (FEM-Spitze dort singulaer). '
                                    f'Rundung rho >= 0,5 t vorsehen, laengste bei {scharf[0]["punkt"]} '
                                    f'({scharf[0]["laenge_mm"]} mm, t {scharf[0]["t_mm"]} mm). Unkritisch nur, '
                                    'wo keine Last durchgeht.'))
    else:
        out.append(ergebnis('M6', 'Scharfe Innenecken', 'ok', wert=0, einheit='Kanten', quelle=Q['M6'], teil=teil))
    kl = []
    for f in g['kehlen']:
        t = f['t_mm']
        if t is None:
            f = {**f, 'rho_t': None, 'K_t': None, 'ok': f['rho_mm'] >= 0.9}
        else:
            f = {**f, 'rho_t': _r(f['rho_mm'] / t, 3), 'K_t': _r(m6_kt(f['rho_mm'], t), 2),
                 'ok': f['rho_mm'] >= 0.5 * t}
        kl.append(f)
    schlecht = sorted([f for f in kl if not f['ok']], key=lambda f: f['rho_t'] if f['rho_t'] is not None else 0)
    if kl:
        out.append(ergebnis('M6', 'Kehlradien', 'warnung' if schlecht else 'ok',
                            wert=schlecht[0]['rho_t'] if schlecht else min(f['rho_t'] or 9 for f in kl), grenze=0.5,
                            einheit='rho/t', quelle=Q['M6'], teil=teil,
                            daten={'zu_klein': schlecht[:15], 'anzahl': len(kl)},
                            hinweis=(f'{len(schlecht)} von {len(kl)} Kehlen mit rho < 0,5 t (K_t > '
                                     f'{m6_kt(0.5, 1):.2f}); kleinste bei {schlecht[0]["punkt"]}' if schlecht else
                                     f'{len(kl)} Kehlen, alle rho >= 0,5 t') + '; K_f = 1 + q(K_t - 1), q ~ 1'))
    # Netz an der Kerbe (rho/3): oertliche Netzgroesse = kleinste Verfeinerungsbox um die Kehle, sonst die globale
    # Netzgroesse. Ein grobes Netz an einer ECHTEN Rundung unterschaetzt sigma (nicht konservativ, Audit 15.11.2026).
    for fall, spec, erg, _ in k.faelle_zu(teil, mech=True):
        n = spec.get('netz') or {}
        g_glob = float(n.get('groesse', 2.0))                      # Standard wie fem.netz
        felder = [f for f in n.get('felder', []) if 'box' in f and f.get('innen')]
        if not kl and not felder:
            continue
        zu_grob, singulaer = [], []
        for f in kl:
            h_ort, wo = g_glob, 'global'
            for fe in felder:
                if _in_box(f['punkt'], fe['box'], rand=float(fe.get('dicke') or 0)) and fe['innen'] < h_ort:
                    h_ort, wo = float(fe['innen']), 'Box'
            if h_ort > f['rho_mm'] / 3:
                zu_grob.append({'punkt': f['punkt'], 'rho_mm': f['rho_mm'], 'netz_mm': h_ort, 'netz': wo})
        for e in scharf:
            if any(_in_box(e['punkt'], fe['box']) for fe in felder):
                singulaer.append(e['punkt'])
        if not zu_grob and not singulaer:
            out.append(ergebnis('M6', f'Netz an Kerben ({fall})', 'ok', quelle=Q['M6'], teil=teil,
                                hinweis=f'alle {len(kl)} Kehlen mit oertlichem Netz <= rho/3 (global {g_glob} mm)'))
            continue
        zu_grob.sort(key=lambda z: z['rho_mm'])
        ohne_box = sum(1 for z in zu_grob if z['netz'] == 'global')
        out.append(ergebnis('M6', f'Netz an Kerben ({fall})', 'warnung', wert=len(zu_grob) + len(singulaer),
                            einheit='Stellen', quelle=Q['M6'], teil=teil,
                            daten={'netz_zu_grob': zu_grob[:10], 'scharfe_kanten_in_box': singulaer[:10],
                                   'netz_global_mm': g_glob},
                            hinweis=f'{len(zu_grob)} Kehlen mit Netz > rho/3 ({ohne_box} ohne Verfeinerungsbox, global '
                                    f'{g_glob} mm; kleinste rho {zu_grob[0]["rho_mm"] if zu_grob else "-"} mm): grobes '
                                    'Netz an einer echten Rundung UNTERSCHAETZT sigma - dort Box mit innen <= rho/3 '
                                    f'setzen, wo Last durchgeht; {len(singulaer)} scharfe Innenkanten in der '
                                    'Verfeinerung: sigma_max dort netzabhaengig (F22) - nicht fuer die Sicherheit'))
    return out


# ================================================================ M12 Schrauben, M13 Inserts

def m12_schraube(F_i, d, d_w, d_h, l, E_m, P=0.0, E_b=E_STAHL):
    """Verspannte Verbindung. k_b = E_b A/l, k_m = E_m pi/4 ((d_w + l/2)^2 - d_h^2)/l, C = k_b/(k_b + k_m).
    l None -> C = 0 fuer Klaffen (konservativ) und C = 1 fuer die Schraubenkraft (konservativ)."""
    p = F_i / (math.pi / 4 * (d_w ** 2 - d_h ** 2)) if d_w and d_h is not None and d_w > d_h else None
    if l:
        kb = E_b * math.pi / 4 * d ** 2 / l
        km = E_m * math.pi / 4 * ((d_w + l / 2) ** 2 - (d_h or d) ** 2) / l
        C = kb / (kb + km)
        C_kl, C_b = C, C
    else:
        C = None
        C_kl, C_b = 0.0, 1.0
    F_m = F_i - (1 - C_kl) * P
    F_b = F_i + C_b * P
    P_klaff = F_i / (1 - C_kl) if C_kl < 1 else float('inf')
    return {'pressung_MPa': p, 'C': C, 'F_klemm_N': F_m, 'F_schraube_N': F_b, 'P_klaffen_N': P_klaff}


def rest_vorspannung(k, mat, s=None):
    """(F_rest/F0, Quelle) nach Kriechen des Kunststoffs unter dem Kopf. Vorrang: Schraube "rest_vorspannung",
    kennwerte kriech_E_inf_zu_E0, kriechmodul_1000h/E0 (ASA 900/1870 = 0,48), sonst 0,5 angenommen (PLA/PETG ohne
    Kriechdaten; eher schlechter). Bei Metall unter dem Kopf (art insert/mutter) kriecht trotzdem der Flansch."""
    if s and s.get('rest_vorspannung') is not None:
        return float(s['rest_vorspannung']), 'soll.json rest_vorspannung'
    if mat:
        v = kennwerte.wert(mat, 'kriech_E_inf_zu_E0')
        if v is not None:
            return float(v), f'kennwerte {mat} kriech_E_inf_zu_E0'
        e1000 = kennwerte.wert(mat, 'kriechmodul_1000h_MPa')
        m = _mat(mat)
        if e1000 is not None and m:
            return float(e1000) / m['E_MPa'], f'kennwerte {mat} Kriechmodul 1000 h / E0 ({e1000:.0f}/{m["E_MPa"]:.0f})'
    return REST_VORSPANNUNG_STD, f'keine Kriechdaten fuer {mat or "Material"} -> {REST_VORSPANNUNG_STD} angenommen'


def _loch_aus_geometrie(k, teil, d):
    g = k.geo(teil)
    if not g:
        return None
    kand = [b['d_mm'] for b in g['bohrungen'] if d < b['d_mm'] <= d + 1.0]
    return max(kand) if kand else None


def _pruefe_schrauben(k, teil, mat, dr):
    out, kraefte = [], []
    m = _mat(mat)
    for i, s in enumerate(_liste(k.ts(teil).get('schrauben'))):
        name = s.get('name') or f'M{s.get("d_mm")} #{i + 1}'
        titel = f'Schraube {name}'
        fehlt = _fehlt(s, ('d_mm', 'vorspannung_N'))
        if fehlt or m is None:
            out.append(uebersprungen('M12', titel, f'Felder fehlen: {fehlt}' if fehlt else k.material(teil)[1],
                                     Q['M12'], teil))
            continue
        d, F_i = float(s['d_mm']), float(s['vorspannung_N'])
        d_w = s.get('kopf_d_mm') or KOPF_ISO4762.get(d)
        if d_w is None:
            out.append(uebersprungen('M12', f'Schrauben M{d:g}', f'Kopfdurchmesser fuer M{d:g} nicht in der Tabelle '
                                     f'(ISO 4762) - kopf_d_mm in soll.json eintragen', Q['M12'], teil))
            continue
        d_h, dhq = s.get('loch_d_mm'), 'soll.json'
        if d_h is None:
            d_h, dhq = _loch_aus_geometrie(k, teil, d), 'groesste passende Bohrung im STEP'
        lage, _ = _lage(s.get('achse'), dr)
        E_m = m['E_MPa']
        ez, _ = k.kw(mat, 'E_z_MPa')
        if ez is not None and lage in ('z', 'schraeg', None):
            E_m = min(E_m, ez)
        P = float(s.get('last_N') or 0)
        r = m12_schraube(F_i, d, float(d_w) if d_w else None, float(d_h) if d_h is not None else None,
                         float(s['klemmlaenge_mm']) if s.get('klemmlaenge_mm') else None, E_m, P)
        kraefte.append(r['F_schraube_N'])
        S = k.S(teil, 'z')
        # Pressung unter dem Kopf
        if r['pressung_MPa'] is None:
            out.append(uebersprungen('M12', titel + ': Kopfpressung',
                                     'kopf_d_mm/loch_d_mm fehlen (keine passende Bohrung im STEP)', Q['M12'], teil))
        else:
            dr_, drq = k.kw(mat, 'druck_MPa')
            if dr_ is None:
                dr_, drq = m['festigkeit_xy_MPa'], 'Zugfestigkeit XY als konservativer Ersatz'
            # Vorspannung liegt dauernd an: Dauerlast (Kriechbruch), dazu Temperatur/aussen aus realterme
            ap = k.abm(teil, 'festigkeit', item=s, dauerlast=True)
            dr_eff = dr_ / ap[0]
            q = dr_eff / r['pressung_MPa']
            out.append(ergebnis('M12', titel + ': Kopfpressung', realterme.deckel(_sicherheit_stufe(q, S), ap[2]),
                                wert=_r(r['pressung_MPa'], 2), grenze=_r(dr_eff / S, 2), einheit='MPa',
                                quelle=Q['M12'], teil=teil,
                                daten={'druck_roh_MPa': dr_, 'abminderung': _r(ap[0], 3), 'realterme': ap[1]},
                                hinweis=f'p = F_i/(pi/4 (d_w^2 - d_h^2)), d_w {d_w}, d_h {d_h} ({dhq}); '
                                        f'Grenze {dr_:.0f} MPa ({drq}) / f {ap[0]:.2f} / S {S:.2f}; Kriechen -> D4'
                                        + _rt(ap)))
        # Klaffen / Klemmkraft
        kmin = s.get('klemmkraft_min_N')
        if P > 0 or kmin is not None:
            Fm = r['F_klemm_N']
            if Fm <= 0:
                st, hw = 'fehler', 'Verbindung klafft'
            elif kmin is not None and Fm < float(kmin):
                st, hw = 'fehler', f'Restklemmkraft unter {kmin} N'
            else:
                st, hw = 'ok', 'kein Klaffen'
            out.append(ergebnis('M12', titel + ': Klaffen', st, wert=_r(Fm, 1),
                                grenze=float(kmin) if kmin is not None else 0.0, einheit='N', quelle=Q['M12'],
                                teil=teil, daten={'C': _r(r['C'], 3), 'P_klaffen_N': _r(r['P_klaffen_N'], 1),
                                                  'F_schraube_N': _r(r['F_schraube_N'], 1)},
                                hinweis=f'{hw}; F_klemm = F_i - (1-C) P, P = {P} N, C = '
                                        + (f'{r["C"]:.3f}' if r['C'] is not None
                                           else '0 angenommen (klemmlaenge_mm fehlt, konservativ)')
                                        + '; Vorspannungsverlust durch Kriechen -> D4'))
        # Restvorspannung nach Kriechen: Kunststoff unter dem Kopf kriecht -> F_rest = r F_i (hoechstens warnung)
        rv, rvq = rest_vorspannung(k, mat, s)
        F_rest = rv * F_i
        Fm_rest = F_rest - (1 - (r['C'] if r['C'] is not None else 0.0)) * P
        if Fm_rest <= 0:
            st, hw = 'fehler', 'Verbindung klafft nach dem Kriechen'
        elif kmin is not None and Fm_rest < float(kmin):
            st, hw = 'fehler', f'Restklemmkraft nach dem Kriechen unter {kmin} N'
        else:
            st, hw = 'ok', 'Restklemmkraft nach dem Kriechen > 0'
        out.append(ergebnis('M12', titel + ': Restvorspannung', realterme.deckel(st, True), wert=_r(Fm_rest, 1),
                            grenze=float(kmin) if kmin is not None else 0.0, einheit='N', quelle=Q['M12'], teil=teil,
                            daten={'F_rest_N': _r(F_rest, 1), 'rest_faktor': _r(rv, 3)},
                            hinweis=f'{hw}; F_rest = {rv:.2f} x F_i = {F_rest:.1f} N ({rvq}), F_klemm = F_rest - (1-C) P; '
                                    'ohne gemessene Kriechkurve des gedruckten Teils hoechstens warnung; '
                                    'Abhilfe: Insert/Mutter mit Metall unter dem Kopf, Scheibe, groesserer Kopf'))
        # Einschraubtiefe direkt im Kunststoff
        if s.get('art') in (None, 'direkt', 'kunststoff'):
            if s.get('einschraub_mm') is None:
                out.append(uebersprungen('M12', titel + ': Einschraubtiefe', '"einschraub_mm" fehlt', Q['M12'], teil))
            else:
                q = float(s['einschraub_mm']) / d
                out.append(ergebnis('M12', titel + ': Einschraubtiefe',
                                    'ok' if q >= 2.5 else 'info' if q >= 2.0 else 'warnung', wert=_r(q, 2), grenze=2.0,
                                    einheit='x D', quelle=Q['M12'], teil=teil,
                                    hinweis='Kunststoff: Einschraubtiefe >= 2..2,5 D'
                                            + ('' if s.get('art') else ' (art fehlt -> als direkt geschraubt gewertet)')))
    return out, kraefte


def m13_insert(F, d_a, L):
    return F / (math.pi * d_a * L)


def _pruefe_inserts(k, teil, mat, schraubenkraefte):
    out = []
    m = _mat(mat)
    for i, s in enumerate(_liste(k.ts(teil).get('inserts'))):
        titel = f'Insert {s.get("name") or i + 1} ausreissen'
        fehlt = _fehlt(s, ('d_aussen_mm', 'laenge_mm'))
        if fehlt or m is None:
            out.append(uebersprungen('M13', titel, f'Felder fehlen: {fehlt}' if fehlt else k.material(teil)[1],
                                     Q['M13'], teil))
            continue
        if s.get('kraft_N') is not None:
            F, fq = float(s['kraft_N']), 'soll.json'
        elif schraubenkraefte:
            F, fq = max(schraubenkraefte), 'groesste Schraubenkraft aus M12 (Vorspannung + C*P)'
        else:
            out.append(uebersprungen('M13', titel, '"kraft_N" fehlt und keine Schrauben im Teil', Q['M13'], teil))
            continue
        tau = m13_insert(F, float(s['d_aussen_mm']), float(s['laenge_mm']))
        tz, tq = k.kw(mat, 'schub_z_MPa')
        if tz is None:
            tz, tq = m['festigkeit_z_MPa'] / math.sqrt(3), 'sigma_Z/sqrt(3)'
        S = k.S(teil, 'z')
        # Vorspannung zieht dauernd am Insert: Dauerlast (Kriechbruch), ausser der Eintrag sagt kurzzeit
        ai = k.abm(teil, 'festigkeit', item=s, dauerlast=True)
        q = tz / ai[0] / tau
        out.append(ergebnis('M13', titel, realterme.deckel(_sicherheit_stufe(q, S), ai[2]), wert=_r(q, 2),
                            grenze=_r(S, 2), einheit='S', quelle=Q['M13'], teil=teil,
                            daten={'tau_MPa': _r(tau, 3), 'F_N': _r(F, 1), 'S_roh': _r(tz / tau, 2),
                                   'abminderung': _r(ai[0], 3), 'realterme': ai[1]},
                            hinweis=f'tau = F/(pi d_a L) = {tau:.2f} MPa gegen {tz:.1f} MPa ({tq}) / f {ai[0]:.2f}, '
                                    f'F aus {fq}; Domfuss-Rundung siehe M6' + _rt(ai)))
    return out


# ================================================================ M14 Pressitz

def m14_pressitz(E, nu, d, D, delta, welle='starr'):
    """Lame, Nabe auf Welle. Q = (D^2 + d^2)/(D^2 - d^2); starr: p = E delta/(d (Q + nu)); gleiche Vollwelle:
    p = E delta/(d (Q + 1)); sigma_theta (Bohrung) = p Q."""
    Qf = (D ** 2 + d ** 2) / (D ** 2 - d ** 2)
    p = E * delta / (d * (Qf + (nu if welle == 'starr' else 1.0)))
    return p, p * Qf


def _pruefe_pressitze(k, teil, mat, dr):
    out = []
    m = _mat(mat)
    for i, s in enumerate(_liste(k.ts(teil).get('pressitze'))):
        titel = f'Pressitz {s.get("name") or i + 1}'
        fehlt = _fehlt(s, ('d_mm', 'D_aussen_mm', 'uebermass_mm'))
        if fehlt or m is None:
            out.append(uebersprungen('M14', titel, f'Felder fehlen: {fehlt}' if fehlt else k.material(teil)[1],
                                     Q['M14'], teil))
            continue
        d, D, de = float(s['d_mm']), float(s['D_aussen_mm']), float(s['uebermass_mm'])
        if D <= d:
            out.append(uebersprungen('M14', titel, 'D_aussen_mm <= d_mm', Q['M14'], teil))
            continue
        welle = s.get('welle', 'starr')
        p, st_ = m14_pressitz(m['E_MPa'], m['nu'], d, D, de, welle)
        lage, _ = _lage(s.get('achse'), dr)
        # stehende Bohrung (Achse || Druckrichtung): Ringspannung in der Schichtebene; sonst sigma_Z
        sig, sn = (m['festigkeit_xy_MPa'], 'sigma_XY (stehende Bohrung)') if lage == 'z' else \
            (m['festigkeit_z_MPa'], 'sigma_Z (liegende/unbekannte Bohrung)')
        S = k.S(teil, 'xy' if lage == 'z' else 'z')
        ap = k.abm(teil, 'festigkeit', item=s, dauerlast=True)     # Uebermass wirkt dauernd
        q = sig / ap[0] / st_
        hw = (f'p = {p:.2f} MPa, sigma_theta = p (D^2 + d^2)/(D^2 - d^2), Welle {welle}, gegen {sn} {sig} / f '
              f'{ap[0]:.2f}' + _rt(ap))
        mu, _ = k.kw(mat, 'mu', s)
        daten = {'p_MPa': _r(p, 3), 'sigma_theta_MPa': _r(st_, 2), 'eps_theta': _r(st_ / m['E_MPa'], 5),
                 'S_roh': _r(sig / st_, 2), 'abminderung': _r(ap[0], 3), 'realterme': ap[1]}
        if mu is not None and s.get('laenge_mm'):
            daten['haltekraft_N'] = _r(mu * p * math.pi * d * float(s['laenge_mm']), 1)
        out.append(ergebnis('M14', titel, realterme.deckel(_sicherheit_stufe(q, S), ap[2]), wert=_r(q, 2),
                            grenze=_r(S, 2), einheit='S',
                            quelle=Q['M14'], teil=teil, daten=daten, hinweis=hw + '; Relaxation -> D3'))
    return out


# ================================================================ M15 Filmscharnier / Federsteg

def m15_scharnier(L, t, eps_zul, E=None, b=None):
    th_max = 2 * L * eps_zul / t
    k_th = E * b * t ** 3 / (12 * L) if E and b else None
    return th_max, k_th


def _pruefe_scharniere(k, teil, mat, dr, dr_q):
    out = []
    m = _mat(mat)
    ts = k.ts(teil)
    for i, s in enumerate(_liste(ts.get('scharniere'))):
        titel = f'Filmscharnier {s.get("name") or i + 1}'
        fehlt = _fehlt(s, ('L_mm', 't_mm', 'winkel_grad'))
        if fehlt:
            out.append(uebersprungen('M15', titel, f'Felder fehlen: {fehlt}', Q['M15'], teil))
            continue
        L, t, th = float(s['L_mm']), float(s['t_mm']), math.radians(float(s['winkel_grad']))
        lage, c = _lage(s.get('achse'), dr)
        if s.get('achse') is None or dr is None:
            out.append(uebersprungen('M15', titel + ': Druckrichtung',
                                     '"achse" (Dehnrichtung quer zur Faltlinie) fehlt' if s.get('achse') is None
                                     else dr_q, Q['M15'], teil))
        else:
            out.append(ergebnis('M15', titel + ': Druckrichtung', {'z': 'fehler', 'schraeg': 'warnung', 'xy': 'ok'}[lage],
                                wert=_r(math.degrees(math.acos(min(1, c))), 1), grenze=75.0,
                                einheit='Grad zur Schichtnormalen', quelle=Q['M15'], teil=teil,
                                hinweis='Biegung nur in XY: Dehnung quer zu den Schichten reisst den Steg'
                                if lage != 'xy' else 'Biegung in der Schichtebene'))
        eps_ist = th * t / (2 * L)
        feld = 'eps_zul_xy' if lage == 'xy' else 'eps_zul_z'
        ez, ezq = k.kw(mat, feld, s, 'eps_zul') if mat else (s.get('eps_zul'), 'soll.json')
        hw_t = '' if t >= 1.8 or ts.get('ausnahmen', {}).get('wand_min') else \
            '; t < 1,8 mm: Ausnahme soll.json ausnahmen.wand_min fuer die CAD-Wandpruefung noetig'
        if ez is None:
            out.append(uebersprungen('M15', titel, f'eps bei Sollwinkel = {eps_ist:.4f}; eps_zul unbekannt ({feld})'
                                     + hw_t, Q['M15'], teil))
            continue
        S = k.S(teil, 'xy')
        th_max, k_th = m15_scharnier(L, t, float(ez), m['E_MPa'] if m else None, s.get('b_mm'))
        q = th_max / th
        out.append(ergebnis('M15', titel, _sicherheit_stufe(q, S), wert=_r(math.degrees(th), 1),
                            grenze=_r(math.degrees(th_max / S), 1), einheit='Grad', quelle=Q['M15'], teil=teil,
                            daten={'theta_max_grad': _r(math.degrees(th_max), 1), 'eps_ist': _r(eps_ist, 5),
                                   'k_theta_Nmm_rad': _r(k_th, 3)},
                            hinweis=f'theta_max = 2 L eps_zul/t, eps_zul {ez} ({ezq}), S {S:.2f}' + hw_t))
    return out


# ================================================================ M16 Torsion

def m16_tau(s):
    art, T = s.get('art'), float(s['T_Nmm'])
    if art == 'offen':
        b, t = float(s['b_mm']), float(s['t_mm'])
        return 3 * T / (max(b, t) * min(b, t) ** 2)
    if art == 'rund':
        return 16 * T / (math.pi * float(s['d_mm']) ** 3)
    if art == 'rohr':
        d, di = float(s['d_mm']), float(s['d_innen_mm'])
        return 16 * T * d / (math.pi * (d ** 4 - di ** 4))
    if art == 'bredt':
        return T / (2 * float(s['A_m_mm2']) * float(s['t_mm']))
    raise ValueError(f'art {art!r} unbekannt (offen, rund, rohr, bredt)')


def _pruefe_torsion(k, teil, mat):
    out = []
    m = _mat(mat)
    for i, s in enumerate(_liste(k.ts(teil).get('torsion'))):
        titel = f'Torsion {s.get("name") or i + 1}'
        noetig = {'offen': ('b_mm', 't_mm'), 'rund': ('d_mm',), 'rohr': ('d_mm', 'd_innen_mm'),
                  'bredt': ('A_m_mm2', 't_mm')}.get(s.get('art'))
        fehlt = ['art (offen/rund/rohr/bredt)'] if noetig is None else _fehlt(s, ('T_Nmm',) + noetig)
        if fehlt or m is None:
            out.append(uebersprungen('M16', titel, f'Felder fehlen: {fehlt}' if fehlt else k.material(teil)[1],
                                     Q['M16'], teil))
            continue
        tau = m16_tau(s)
        tz, tq = k.kw(mat, 'schub_z_MPa')
        if tz is None:
            tz, tq = m['festigkeit_z_MPa'] / math.sqrt(3), 'sigma_Z/sqrt(3)'
        S = k.S(teil, 'z')
        at = k.abm(teil, 'festigkeit', item=s)                     # Dauer unbekannt -> unguenstig
        q = tz / at[0] / tau
        out.append(ergebnis('M16', titel, realterme.deckel(_sicherheit_stufe(q, S), at[2]), wert=_r(q, 2),
                            grenze=_r(S, 2), einheit='S', quelle=Q['M16'], teil=teil,
                            daten={'tau_MPa': _r(tau, 3), 'S_roh': _r(tz / tau, 2), 'abminderung': _r(at[0], 3),
                                   'realterme': at[1]},
                            hinweis=f'tau = {tau:.2f} MPa ({s["art"]}) gegen {tz:.1f} MPa ({tq}) / f {at[0]:.2f}'
                                    + _rt(at) + '; Torsionsschub '
                                    'liegt bei jeder Wellenlage auch in Schichtebenen -> immer gegen Z'
                                    + ('; offen: Formel fuer b >> t' if s['art'] == 'offen' else '')))
    return out


# ================================================================ M19 Deckeldurchbiegung

# Timoshenko/Woinowsky-Krieger, nu = 0,3; Schluessel: Seitenverhaeltnis lang/kurz; w = alpha q b^4/D bzw. beta F b^2/D
_ALPHA_GELENKIG = [(1.0, .00406), (1.1, .00485), (1.2, .00564), (1.3, .00638), (1.4, .00705), (1.5, .00772),
                   (1.6, .00830), (1.7, .00883), (1.8, .00931), (1.9, .00974), (2.0, .01013), (3.0, .01223),
                   (4.0, .01282), (5.0, .01297), (1e9, .01302)]
_ALPHA_EINGESPANNT = [(1.0, .00126), (1.1, .00150), (1.2, .00172), (1.3, .00191), (1.4, .00207), (1.5, .00220),
                      (1.6, .00230), (1.7, .00238), (1.8, .00245), (1.9, .00249), (2.0, .00254), (1e9, .00260)]
_BETA_GELENKIG = [(1.0, .01160), (1.1, .01265), (1.2, .01353), (1.4, .01484), (1.6, .01570), (1.8, .01620),
                  (2.0, .01651), (3.0, .01690), (1e9, .01695)]
_BETA_EINGESPANNT = [(1.0, .00560), (1.2, .00647), (1.4, .00691), (1.6, .00712), (1.8, .00720), (2.0, .00722),
                     (1e9, .00725)]


def _tab(tab, r):
    if r <= tab[0][0]:
        return tab[0][1]
    for (x0, y0), (x1, y1) in zip(tab, tab[1:]):
        if r <= x1:
            if x1 >= 1e8:
                return y1 if r > 2 * x0 else y0 + (y1 - y0) * (r - x0) / x0   # gegen Unendlich: sanft auf Grenzwert
            return y0 + (y1 - y0) * (r - x0) / (x1 - x0)
    return tab[-1][1]


def m19_platte(E, nu, a, b, t, q=None, F=None, rand='gelenkig'):
    """Rechteckplatte. D = E t^3/(12(1-nu^2)); Flaechenlast w = alpha q b^4/D, Mittenlast w = beta F b^2/D."""
    lang, kurz = max(a, b), min(a, b)
    r = lang / kurz
    D = E * t ** 3 / (12 * (1 - nu ** 2))
    if F is not None:
        beta = _tab(_BETA_GELENKIG if rand == 'gelenkig' else _BETA_EINGESPANNT, r)
        return beta * F * kurz ** 2 / D, beta, D
    alpha = _tab(_ALPHA_GELENKIG if rand == 'gelenkig' else _ALPHA_EINGESPANNT, r)
    return alpha * q * kurz ** 4 / D, alpha, D


def _pruefe_deckel(k, teil, mat):
    out = []
    m = _mat(mat)
    for i, s in enumerate(_liste(k.ts(teil).get('deckelbiegung'))):
        titel = f'Deckeldurchbiegung {s.get("name") or i + 1}'
        fehlt = _fehlt(s, ('a_mm', 'b_mm', 't_mm'))
        if s.get('druck_MPa') is None and s.get('last_N') is None:
            fehlt.append('druck_MPa oder last_N')
        if fehlt or m is None:
            out.append(uebersprungen('M19', titel, f'Felder fehlen: {fehlt}' if fehlt else k.material(teil)[1],
                                     Q['M19'], teil))
            continue
        a, b, t = float(s['a_mm']), float(s['b_mm']), float(s['t_mm'])
        rand = str(s.get('rand', 'gelenkig')).strip().lower()
        if rand not in ('gelenkig', 'eingespannt'):   # Tippfehler nie still als die guenstigere Lagerung lesen
            out.append(uebersprungen('M19', titel, f'rand {s.get("rand")!r} unbekannt (gelenkig | eingespannt)',
                                     Q['M19'], teil))
            continue
        art = s.get('last_art') or ('flaeche' if s.get('druck_MPa') is not None else 'punkt')
        if art == 'punkt':
            w, beiwert, D = m19_platte(m['E_MPa'], m['nu'], a, b, t, F=float(s['last_N']), rand=rand)
        else:
            q = float(s['druck_MPa']) if s.get('druck_MPa') is not None else float(s['last_N']) / (a * b)
            w, beiwert, D = m19_platte(m['E_MPa'], m['nu'], a, b, t, q=q, rand=rand)
        hw = (f'D = {D:.0f} Nmm, Beiwert {beiwert:.5f} ({art}, {rand})'
              + ('; w > t/2: Membranwirkung, lineare Theorie ueberschaetzt w (konservativ)' if w > t / 2 else '')
              + '; Kriechen unter Dauerlast -> D3')
        if s.get('abstand_mm') is None:
            out.append(ergebnis('M19', titel, 'info', wert=_r(w, 4), einheit='mm', quelle=Q['M19'], teil=teil,
                                hinweis=hw + '; "abstand_mm" (zur Platine) fehlt fuer das Kriterium'))
            continue
        ab = float(s['abstand_mm'])
        st = 'ok' if w <= 0.8 * ab else 'warnung' if w <= ab else 'fehler'
        out.append(ergebnis('M19', titel, st, wert=_r(w, 4), grenze=ab, einheit='mm', quelle=Q['M19'], teil=teil,
                            hinweis=hw))
    return out


# ================================================================ M21 plastische Reserve

def _pruefe_reserve(k, teil, mat, dr):
    ts = k.ts(teil)
    elemente = _liste(ts.get('schnapper')) + _liste(ts.get('balken')) + _liste(ts.get('scharniere'))
    if not elemente:
        return []
    if mat is None:
        return [uebersprungen('M21', 'Plastische Reserve', k.material(teil)[1], Q['M21'], teil)]
    lagen = {_lage(e.get('achse'), dr)[0] for e in elemente}
    if mat == 'PLA':
        hw = 'PLA sproede: keine plastische Reserve ansetzen'
    elif 'z' in lagen or None in lagen or 'schraeg' in lagen:
        hw = (f'{mat}: Rechteck M_p = 1,5 M_y nur fuer Biegung in der Schichtebene; quer zu den Schichten (oder Lage '
              'unbekannt) keine Reserve - Bruch zwischen den Lagen ist sproede')
    else:
        hw = f'{mat} zaeh: Rechteck M_p = 1,5 M_y - Kollaps erst bei 1,5-facher Fliesslast (nicht als Sicherheit angerechnet)'
    return [ergebnis('M21', 'Plastische Reserve', 'info', wert=1.0 if mat == 'PLA' else 1.5, einheit='M_p/M_y',
                     quelle=Q['M21'], teil=teil, hinweis=hw)]


# ================================================================ M22 Bruchmechanik

def m22_KI(sigma, a_mm, Y=1.12):
    """K_I = Y sigma sqrt(pi a) in MPa*sqrt(m) (a in mm -> m)."""
    return Y * sigma * math.sqrt(math.pi * a_mm / 1000.0)


def _linienbreite(k):
    sp = os.path.join(k.pdir, 'print', 'slice.json')
    try:
        cfg = json.load(open(sp, encoding='utf-8')).get('config')
        if cfg and os.path.exists(cfg):
            werte = {}
            for z in open(cfg, encoding='utf-8', errors='replace'):
                if '=' in z:
                    a, b = z.split('=', 1)
                    werte[a.strip()] = b.strip()
            for key in ('perimeter_extrusion_width', 'extrusion_width'):
                v = werte.get(key, '')
                if v and not v.endswith('%') and float(v) > 0:
                    return float(v), f'Slicer {key}'
    except Exception:  # noqa: BLE001
        pass
    return LINIENBREITE_STD, 'Standard 1,125 x 0,4 mm (Slicer-Automatik)'


def _pruefe_bruch(k, teil, mat):
    kand = []
    for fall, spec, erg, kk in k.faelle_zu(teil, mech=True):
        for lname, lf in ((erg or {}).get('lastfaelle') or {}).items():
            # groesserer Wert gilt: linear ist der Eckwert die Bewertungsspannung (bis +27 % ueber IP),
            # bei NLGEOM sind beide Werte IP-Werte (Befund M22-IP-statt-Ecke)
            werte = [float(v) for v in (lf.get('max_vonMises_MPa'), lf.get('max_vonMises_integrationspunkte_MPa'))
                     if v is not None]
            s = max(werte) if werte else None
            if s:
                kand.append((float(s), f'FEM {fall}/{lname}'))
    m = _mat(mat)
    for s in _liste(k.ts(teil).get('schnapper')):
        if m and not _fehlt(s, ('L_mm', 'b_mm', 't_mm', 'hinterschnitt_mm')):
            kand.append((m1_schnapper({**s, 'E_MPa': m['E_MPa']})['sigma_MPa'], f'M1 {s.get("name", "")}'))
    if not kand:
        return []
    titel = 'Bruchmechanik Fehlstelle'
    kic, kq = k.kw(mat, 'K_IC_MPa_sqrtm') if mat else (None, None)
    if kic is None:
        return [uebersprungen('M22', titel, 'K_IC unbekannt (kennwerte.py K_IC_MPa_sqrtm)', Q['M22'], teil)]
    sig, wo = max(kand)
    a, aq = _linienbreite(k)
    KI = m22_KI(sig, a)
    S = k.S(teil, 'z')
    q = kic / KI
    return [ergebnis('M22', titel, _sicherheit_stufe(q, S), wert=_r(KI, 3), grenze=_r(kic / S, 3),
                     einheit='MPa*sqrt(m)', quelle=Q['M22'], teil=teil,
                     hinweis=f'K_I = 1,12 sigma sqrt(pi a), sigma {sig:.1f} MPa ({wo}, Spitze - konservativ), '
                             f'a = {a} mm ({aq}); K_IC {kic} ({kq}) gilt in XY, zwischen den Lagen kleiner')]


# ================================================================ M23 Lewis

_LEWIS_Y = [(12, .245), (13, .261), (14, .277), (15, .290), (16, .296), (17, .303), (18, .309), (19, .314),
            (20, .322), (21, .328), (22, .331), (24, .337), (26, .346), (28, .353), (30, .359), (34, .371),
            (38, .384), (43, .397), (50, .409), (60, .422), (75, .435), (100, .447), (150, .460), (300, .472),
            (400, .480)]


def lewis_Y(z):
    if z < 12:
        return None
    for (z0, y0), (z1, y1) in zip(_LEWIS_Y, _LEWIS_Y[1:]):
        if z <= z1:
            return y0 + (y1 - y0) * (z - z0) / (z1 - z0)
    return _LEWIS_Y[-1][1]


def _pruefe_zahnraeder(k, teil, mat, dr, dr_q):
    out = []
    m = _mat(mat)
    for i, s in enumerate(_liste(k.ts(teil).get('zahnraeder'))):
        titel = f'Zahnrad {s.get("name") or i + 1} (Lewis)'
        fehlt = _fehlt(s, ('m_mm', 'z', 'b_mm'))
        if s.get('F_t_N') is None and s.get('M_Nmm') is None:
            fehlt.append('F_t_N oder M_Nmm')
        if fehlt or m is None:
            out.append(uebersprungen('M23', titel, f'Felder fehlen: {fehlt}' if fehlt else k.material(teil)[1],
                                     Q['M23'], teil))
            continue
        mm, z, b = float(s['m_mm']), int(s['z']), float(s['b_mm'])
        Y = lewis_Y(z)
        if Y is None:
            out.append(ergebnis('M23', titel, 'warnung', wert=z, grenze=12, einheit='Zaehne', quelle=Q['M23'],
                                teil=teil, hinweis='z < 12: Unterschnitt, Lewis-Tabelle gilt nicht'))
            continue
        Ft = float(s['F_t_N']) if s.get('F_t_N') is not None else 2 * float(s['M_Nmm']) / (mm * z)
        sigma = Ft / (b * mm * Y)
        lage, _ = _lage(s.get('achse'), dr)
        # liegend gedruckt = Radachse || Druckrichtung -> Zahnfuss-Biegung in der Schichtebene
        if s.get('achse') is None or dr is None:
            out.append(uebersprungen('M23', titel + ': Druckrichtung', '"achse" fehlt' if s.get('achse') is None
                                     else dr_q, Q['M23'], teil))
        else:
            out.append(ergebnis('M23', titel + ': Druckrichtung',
                                {'z': 'ok', 'schraeg': 'warnung', 'xy': 'fehler'}[lage], quelle=Q['M23'], teil=teil,
                                hinweis='liegend gedruckt (Achse || Druckrichtung)' if lage == 'z' else
                                'Zahnrad stehend: Zahnfuss-Biegung quer zu den Schichten - liegend drucken'))
        sig, sn = (m['festigkeit_xy_MPa'], 'sigma_XY') if lage == 'z' else (m['festigkeit_z_MPa'], 'sigma_Z')
        S = k.S(teil, 'xy' if lage == 'z' else 'z')
        az = k.abm(teil, 'festigkeit', item=s)                     # Dauer unbekannt -> unguenstig
        q = sig / az[0] / sigma
        out.append(ergebnis('M23', titel, realterme.deckel(_sicherheit_stufe(q, S), az[2]), wert=_r(sigma, 2),
                            grenze=_r(sig / az[0] / S, 2), einheit='MPa', quelle=Q['M23'], teil=teil,
                            daten={'festigkeit_roh_MPa': sig, 'abminderung': _r(az[0], 3), 'realterme': az[1]},
                            hinweis=f'sigma = F_t/(b m Y), F_t {Ft:.1f} N, Y {Y:.3f} (z {z}), gegen {sn} {sig} / f '
                                    f'{az[0]:.2f} / S {S:.2f}' + _rt(az)))
    return out


# ================================================================ M24 Constraints

def m24_fg(constraints):
    """FG = 6 - C; doppelt gesperrte Freiheitsgrade = Ueberbestimmung."""
    C, gesperrt, doppelt = 0, [], []
    for c in constraints:
        if c.get('sperrt'):
            for f in c['sperrt']:
                f = str(f).lower()
                (doppelt if f in gesperrt else gesperrt).append(f)
            C += len(c['sperrt'])
        else:
            C += int(c.get('anzahl') or 1)
    return 6 - C, sorted(set(doppelt)), [f for f in ('x', 'y', 'z', 'rx', 'ry', 'rz') if f not in gesperrt]


def _pruefe_constraints(k, teil):
    ts = k.ts(teil)
    cs = _liste(ts.get('constraints'))
    if not cs:
        return []
    fg, doppelt, frei = m24_fg(cs)
    st, hw = 'ok', f'FG = 6 - C = {fg}'
    if fg < 0 or doppelt:
        st = 'warnung'
        hw += f'; ueberbestimmt (doppelt gesperrt: {doppelt or "Anzahl > 6"}) - Zwang bei Toleranz/Waermedehnung (D8/D9)'
    elif fg > 0:
        st = 'info'
        hw += f'; frei: {frei}' if any(c.get('sperrt') for c in cs) else ''
    if ts.get('fg_soll') is not None and int(ts['fg_soll']) != fg:
        st = 'warnung'
        hw += f'; Soll-FG {ts["fg_soll"]}'
    return [ergebnis('M24', 'Constraint-Zaehlung', st, wert=fg, grenze=ts.get('fg_soll'), einheit='FG',
                     quelle=Q['M24'], teil=teil, hinweis=hw)]


# ================================================================ M26 Sicherheitsziel aus Streuung

def m26_ke(s_rel, R):
    """k_e = 1 - s z (z = Quantil der Normalverteilung zur Zuverlaessigkeit R; s = 0,08: Katalogwert 2.72)."""
    z = statistics.NormalDist().inv_cdf(R)
    return 1 - s_rel * z, z


def _streuung(projekt, mat, richtung):
    feld = 'streuung_xy' if richtung == 'xy' else 'streuung_z'
    if projekt.get(feld) is not None:
        return float(projekt[feld]), 'soll.json _projekt'
    v = kennwerte.wert(mat, feld) if mat else None
    return (v, 'kennwerte.py') if v is not None else (None, None)


def m26_sicherheit(projekt, mat, richtung):
    s, _ = _streuung(projekt, mat, richtung)
    if s is None:
        return None
    ke, _ = m26_ke(s, float(projekt.get('zuverlaessigkeit') or 0.99))
    return float(projekt.get('lastfaktor') or 1.0) / ke if ke > 0 else None


def _pruefe_m26(k, stoffe):
    out = []
    R = float(k.projekt.get('zuverlaessigkeit') or 0.99)
    lf = float(k.projekt.get('lastfaktor') or 1.0)
    for mat in stoffe:
        for richtung in ('xy', 'z'):
            titel = f'Sicherheitsziel {mat} {richtung.upper()}'
            s, sq = _streuung(k.projekt, mat, richtung)
            if s is None:
                out.append(uebersprungen('M26', titel, f'Streuung {richtung} unbekannt (kennwerte.py streuung_'
                                         f'{richtung} oder _projekt); Katalogwert 0,08 gilt fuer Stahl, nicht Druck',
                                         Q['M26']))
                continue
            ke, z = m26_ke(s, R)
            if ke <= 0:
                out.append(ergebnis('M26', titel, 'fehler', wert=_r(ke, 3), grenze=0.0, einheit='k_e', quelle=Q['M26'],
                                    hinweis=f'Streuung {s} zu gross fuer Zuverlaessigkeit {R} (z {z:.2f})'))
                continue
            S = lf / ke
            basis = float(k.projekt.get('sicherheit') or S_STANDARD)
            out.append(ergebnis('M26', titel, 'info' if S <= basis else 'warnung', wert=_r(S, 3), grenze=basis,
                                einheit='S_ziel', quelle=Q['M26'],
                                daten={'k_e': _r(ke, 4), 'z': _r(z, 3), 'streuung': s},
                                hinweis=f'k_e = 1 - s z = {ke:.3f} (s {s} aus {sq}, R {R}), S_ziel = Lastfaktor {lf}/k_e;'
                                        f' ' + ('Standard-S reicht' if S <= basis else
                                                f'hoeher als S {basis} - die anderen Pruefungen rechnen mit {S:.2f}')))
    return out


# ================================================================ soll-gesteuerte Pruefungen ohne Eintrag

# ID -> (soll-Feld je Teil, Titel). Ohne Eintrag in KEINEM Teil: ein 'uebersprungen' je Pruefung (nicht schweigen),
# damit der Ausloeser-Mechanismus (pruefungen.AUSLOESER) es bei erkanntem Merkmal zu 'fehler' hochstufen kann.
SOLL_GESTEUERT = (
    ('M1', 'schnapper', 'Schnapphaken'),
    ('M2', 'schnapper', 'Fuegekraft Schnapphaken'),
    ('M12', 'schrauben', 'Schrauben'),
    ('M13', 'inserts', 'Inserts ausreissen'),
    ('M14', 'pressitze', 'Pressitz'),
    ('M15', 'scharniere', 'Filmscharnier'),
    ('M16', 'torsion', 'Torsion'),
    ('M19', 'deckelbiegung', 'Deckeldurchbiegung'),
    ('M23', 'zahnraeder', 'Zahnrad (Lewis)'),
)
LOCH_SCHRAUBE = ((1.6, 1.8, 'Kernloch M2'), (2.4, 2.6, 'Kernloch M3'), (3.2, 4.2, 'Insert M2/M3'))


def _bohrungs_hinweis(k):
    """Schraub-/Insert-Bohrungen in schon gelesenen Geometrien (keine neue STEP-Analyse)."""
    n = {}
    for teil, g in k._geo.items():
        for b in (g or {}).get('bohrungen', []):
            for lo, hi, art in LOCH_SCHRAUBE:
                if lo <= b['d_mm'] <= hi:
                    n[art] = n.get(art, 0) + 1
    return ('; im STEP: ' + ', '.join(f'{v} x {a}' for a, v in n.items())) if n else ''


def _ohne_soll(k, erg):
    ids = {e['id'] for e in erg}
    out, bh = [], None
    for id_, feld, titel in SOLL_GESTEUERT:
        if id_ in ids:
            continue
        if any(_liste(k.ts(t).get(feld)) for t in k.soll if not t.startswith('_')):
            grund = f'soll.json "{feld}" vorhanden, aber {id_} nicht rechenbar (Felder fehlen, siehe M1)'
        else:
            grund = f'kein Teil hat soll.json "{feld}" - nicht gerechnet'
        if id_ in ('M12', 'M13'):
            bh = _bohrungs_hinweis(k) if bh is None else bh
            grund += bh
        out.append(uebersprungen(id_, titel, grund + '; falls vorhanden eintragen (FELDER.md), sonst '
                                 f'_projekt.nicht_relevant.{id_} mit Begruendung', Q[id_]))
    return out


# ================================================================ Einstieg

def pruefe(pdir):
    k = Kontext(pdir)
    erg = []

    def lauf(id_, fn, *a, teil=None):
        try:
            r = fn(*a)
            return r
        except Exception as ex:  # noqa: BLE001 - eine kaputte Pruefung darf die anderen nicht verdecken
            return [ergebnis(id_, f'{id_} Absturz', 'fehler', teil=teil, hinweis=f'{type(ex).__name__}: {ex}')]

    stoffe = []
    for teil in k.teile():
        mat, _ = k.material(teil)
        if mat and mat not in stoffe:
            stoffe.append(mat)
        dr, dr_q = k.druckrichtung(teil)
        erg += lauf('M1', _pruefe_schnapper, k, teil, mat, dr, dr_q, teil=teil)
        erg += lauf('M3', _pruefe_balken, k, teil, mat, teil=teil)
        erg += lauf('M4', _pruefe_knicken, k, teil, mat, dr, dr_q, teil=teil)
        erg += lauf('M5', _pruefe_rippen, k, teil, mat, dr, teil=teil)
        erg += lauf('M6', _pruefe_kerben, k, teil, teil=teil)
        kraefte = []
        try:
            r, kraefte = _pruefe_schrauben(k, teil, mat, dr)
            erg += r
        except Exception as ex:  # noqa: BLE001
            erg.append(ergebnis('M12', 'M12 Absturz', 'fehler', teil=teil, hinweis=f'{type(ex).__name__}: {ex}'))
        erg += lauf('M13', _pruefe_inserts, k, teil, mat, kraefte, teil=teil)
        erg += lauf('M14', _pruefe_pressitze, k, teil, mat, dr, teil=teil)
        erg += lauf('M15', _pruefe_scharniere, k, teil, mat, dr, dr_q, teil=teil)
        erg += lauf('M16', _pruefe_torsion, k, teil, mat, teil=teil)
        erg += lauf('M19', _pruefe_deckel, k, teil, mat, teil=teil)
        erg += lauf('M21', _pruefe_reserve, k, teil, mat, dr, teil=teil)
        erg += lauf('M22', _pruefe_bruch, k, teil, mat, teil=teil)
        erg += lauf('M23', _pruefe_zahnraeder, k, teil, mat, dr, dr_q, teil=teil)
        erg += lauf('M24', _pruefe_constraints, k, teil, teil=teil)
    erg += lauf('M26', _pruefe_m26, k, stoffe or list(DRUCKSTOFFE))
    erg += _ohne_soll(k, erg)
    if not erg:
        erg.append(uebersprungen('M1', 'Mechanik am Teil', 'keine Teile (soll.json, out/*.step, fem/) gefunden'))
    return erg
