"""FEM: Gmsh-Netz -> CalculiX (Mechanik, linear/nichtlinear, Kontakt) bzw. Elmer (Waerme). Alles in mm, N, MPa.

Lastfall = fem/<fall>.json im Projekt:
{
  "koerper": [ {"step": "out/halter.step", "material": "PETG"},
               {"zylinder": [x, y, z, dx, dy, dz, r], "material": "STARR", "name": "stift"},
               {"box": [x0, y0, z0, x1, y1, z1], "material": "FR4", "waerme_W": 1.5} ],
  "verbinden": true,             # true: Koerper verschmelzen (konformes Netz, verklebt). false: getrennt -> "kontakt"
  "netz": {"groesse": 2.0, "felder": [{"box": [..6..], "innen": 0.35, "aussen": 2.0, "dicke": 2}],
           "kombination": "min", "gerade_kanten": false},
  "lagerung": [{"wo": AUSWAHL, "fest": "xyz"},
               {"wo": AUSWAHL, "fest": "xy", "weg": {"z": -1.4}}],   # Wegvorgabe -> Reaktionskraft im Ergebnis
  "name": "montage",             # Lastfallname, wenn es nur Wegvorgaben und keine "lasten" gibt
  "lasten": [{"name": "andruck", "wo": AUSWAHL, "kraft_N": [0, 0, 0.25]}],    # je Last ein Lastfall
  "nichtlinear": false,
  "kontakt": [{"slave": AUSWAHL, "master": AUSWAHL, "steifigkeit_N_mm3": 500, "reibung": 0.3}],
  "hochrechnen": {"last": "andruck", "auf_verschiebung_mm": 5}            # nur linear
  -- Waerme (Elmer) --
  "konvektion": {"h_W_m2K": 8, "T_umgebung_C": 25},   # optional "auto": true, "L_mm": Hoehe -> h aus W1
  "flaechen": [{"wo": AUSWAHL, "temperatur_C": 40}],
  "strahlung": {"emission": 0.9}, "innenluft": true | {"box": [..6..]},          # optional, W2 / W5
  "sonne": {"G_W_m2": 1000, "absorption": 0.6, "richtung": [0, 0, -1]}             # optional, W6
}
AUSWAHL waehlt Randflaechen ueber ihren Mittelpunkt, alle Angaben UND-verknuepft:
  {"ebene": ["y", -22.0], "tol": 0.001, "kreise": [{"ebene": "xz", "mitte": [16, 4], "r": 5}, ..] (ODER),
   "box": [x0, y0, z0, x1, y1, z1], "koerper": "stift"}
"""
import json
import math
import os
import subprocess
import time

import numpy as np

from .material import DRUCKSTOFFE, MATERIAL, ueberschrieben
from . import werkzeuge

ACHSE = {'x': 0, 'y': 1, 'z': 2}
# gmsh-Tet10 -> CalculiX-C3D10: die letzten zwei Kantenknoten sind vertauscht
GMSH2CCX = [0, 1, 2, 3, 4, 5, 6, 7, 9, 8]
# Flaechen eines Tetraeders (Eckknoten 0-basiert), Nummer = CalculiX-Flaechennummer S1..S4
TET_FLAECHEN = [(0, 1, 2), (0, 3, 1), (1, 3, 2), (2, 3, 0)]
TET10_KANTE = {(0, 1): 4, (1, 2): 5, (0, 2): 6, (0, 3): 7, (2, 3): 8, (1, 3): 9}   # gmsh-Reihenfolge


# ---------------------------------------------------------------- Netz

def netz(pdir, spec, ordnung=2):
    """Koerper laden, ggf. verschmelzen, vernetzen. Rueckgabe: Knoten (N,3), Tets (M,4|10 gmsh-Ordnung),
    Koerper-Index je Tet, Koerpernamen, Volumen je Koerper (mm3)."""
    import gmsh
    gmsh.initialize()
    try:
        gmsh.option.setNumber('General.Terminal', 0)
        gmsh.option.setString('Geometry.OCCTargetUnit', 'MM')
        occ = gmsh.model.occ
        eingaben, namen = [], []
        for i, k in enumerate(spec['koerper']):
            if 'step' in k:
                p = k['step'] if os.path.isabs(k['step']) else os.path.join(pdir, k['step'])
                dt = occ.importShapes(p)
            elif 'zylinder' in k:
                dt = [(3, occ.addCylinder(*k['zylinder']))]
            elif 'box' in k:
                x0, y0, z0, x1, y1, z1 = k['box']
                dt = [(3, occ.addBox(x0, y0, z0, x1 - x0, y1 - y0, z1 - z0))]
            else:
                raise RuntimeError(f'Koerper {i}: step, zylinder oder box angeben')
            eingaben.append([d for d in dt if d[0] == 3])
            namen.append(k.get('name') or os.path.splitext(os.path.basename(k.get('step', f'k{i}')))[0])
        flach = [d for e in eingaben for d in e]
        zuordnung = {}
        if spec.get('verbinden', True) and len(flach) > 1:
            _, m = occ.fragment(flach[:1], flach[1:])
            k_idx = [i for i, e in enumerate(eingaben) for _ in e]
            for j, stuecke in enumerate(m):              # Ueberlappungen gehoeren dem zuerst genannten Koerper
                for d, t in stuecke:
                    zuordnung.setdefault(t, k_idx[j])
        else:
            for i, e in enumerate(eingaben):
                for d, t in e:
                    zuordnung[t] = i
        occ.synchronize()

        n = spec.get('netz', {})
        gmsh.option.setNumber('Mesh.MeshSizeMax', n.get('groesse', 2.0))
        felder = []
        for f in n.get('felder', []):
            fid = gmsh.model.mesh.field.add('Box')
            x0, y0, z0, x1, y1, z1 = f['box']
            for key, v in {'VIn': f['innen'], 'VOut': f.get('aussen', n.get('groesse', 2.0)), 'XMin': x0, 'XMax': x1,
                           'YMin': y0, 'YMax': y1, 'ZMin': z0, 'ZMax': z1, 'Thickness': f.get('dicke', 0)}.items():
                gmsh.model.mesh.field.setNumber(fid, key, v)
            felder.append(fid)
        if felder:
            comb = gmsh.model.mesh.field.add('Max' if n.get('kombination') == 'max' else 'Min')
            gmsh.model.mesh.field.setNumbers(comb, 'FieldsList', felder)
            gmsh.model.mesh.field.setAsBackgroundMesh(comb)
            gmsh.option.setNumber('Mesh.MeshSizeExtendFromBoundary', 0)
            gmsh.option.setNumber('Mesh.MeshSizeFromPoints', 0)
            gmsh.option.setNumber('Mesh.MeshSizeFromCurvature', 0)
        gmsh.model.mesh.generate(3)
        if ordnung == 2:
            gmsh.option.setNumber('Mesh.SecondOrderLinear', 1 if n.get('gerade_kanten') else 0)
            gmsh.model.mesh.setOrder(2)

        tags, coords, _ = gmsh.model.mesh.getNodes()
        idx = np.full(int(tags.max()) + 1, -1)
        idx[tags.astype(int)] = np.arange(len(tags))
        p = coords.reshape(-1, 3)
        typ = 11 if ordnung == 2 else 4
        tets, koerper = [], []
        vol = np.zeros(len(eingaben))
        for d, t in gmsh.model.getEntities(3):
            et, _, en = gmsh.model.mesh.getElements(3, t)
            for ty, conn in zip(et, en):
                if ty == typ:
                    c = idx[np.asarray(conn, int)].reshape(-1, 10 if ordnung == 2 else 4)
                    tets.append(c)
                    koerper.append(np.full(len(c), zuordnung.get(t, 0)))
            vol[zuordnung.get(t, 0)] += occ.getMass(3, t)
    finally:
        gmsh.finalize()
    t = np.vstack(tets)
    used = np.unique(t)
    remap = np.full(len(p), -1)
    remap[used] = np.arange(len(used))
    return p[used], remap[t], np.concatenate(koerper), namen, vol


def randflaechen(tets):
    """Aussenflaechen: (tet, flaechennr 0..3, eckknoten[3]) - Flaechen, die nur zu einem Tet gehoeren."""
    ecken = tets[:, :4]
    f = np.concatenate([ecken[:, list(fl)] for fl in TET_FLAECHEN])
    tet_id = np.tile(np.arange(len(tets)), 4)
    fl_nr = np.repeat(np.arange(4), len(tets))
    key = np.sort(f, axis=1)
    _, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    rand = cnt[inv.ravel()] == 1
    return tet_id[rand], fl_nr[rand], f[rand]


def _flaechen_knoten(tets, tet_id, fl_nr):
    """Alle Knoten (Ecken + Kantenmitten) der gewaehlten Randflaechen."""
    out = set()
    for t, nr in zip(tet_id, fl_nr):
        e = TET_FLAECHEN[nr]
        out.update(int(tets[t, i]) for i in e)
        if tets.shape[1] == 10:
            for a, b in ((e[0], e[1]), (e[1], e[2]), (e[0], e[2])):
                out.add(int(tets[t, TET10_KANTE[tuple(sorted((a, b)))]]))
    return np.array(sorted(out))


def auswahl(wo, knoten, tets, koerper, namen, rand):
    """Randflaechen nach AUSWAHL -> (tet_id, fl_nr)."""
    tet_id, fl_nr, f = rand
    m = knoten[f].mean(1)
    ok = np.ones(len(m), bool)
    tol = wo.get('tol', 1e-3)
    if 'ebene' in wo:
        a, w = wo['ebene']
        ok &= np.all(np.abs(knoten[f][:, :, ACHSE[a]] - w) < tol, axis=1)
    if 'box' in wo:
        x0, y0, z0, x1, y1, z1 = wo['box']
        ok &= (m[:, 0] >= x0) & (m[:, 0] <= x1) & (m[:, 1] >= y0) & (m[:, 1] <= y1) & (m[:, 2] >= z0) & (m[:, 2] <= z1)
    if 'kreise' in wo:
        in_k = np.zeros(len(m), bool)
        for k in wo['kreise']:
            a, b = ACHSE[k['ebene'][0]], ACHSE[k['ebene'][1]]
            in_k |= (m[:, a] - k['mitte'][0]) ** 2 + (m[:, b] - k['mitte'][1]) ** 2 < k['r'] ** 2
        ok &= in_k
    if 'koerper' in wo:
        ok &= koerper[tet_id] == namen.index(wo['koerper'])
    if not ok.any():
        raise RuntimeError(f'Auswahl {wo} trifft keine Randflaeche')
    return tet_id[ok], fl_nr[ok]


# ---------------------------------------------------------------- CalculiX

G_MM_S2 = 9810.0                                   # 1 g in mm/s^2 (Einheiten mm, N, t, s)
RHO_T_MM3 = 1e-12                                  # kg/m^3 -> t/mm^3

# 5-Punkt-Regel (Grad 3) im Einheits-Tetraeder, baryzentrisch; Gewichte summieren zu 1 (mal Referenzvolumen 1/6)
_Q5_L = np.array([[0.25, 0.25, 0.25, 0.25], [0.5, 1 / 6, 1 / 6, 1 / 6], [1 / 6, 0.5, 1 / 6, 1 / 6],
                  [1 / 6, 1 / 6, 0.5, 1 / 6], [1 / 6, 1 / 6, 1 / 6, 0.5]])
_Q5_W = np.array([-0.8, 0.45, 0.45, 0.45, 0.45])


def mechanik(pdir, fall):
    spec = json.load(open(os.path.join(pdir, 'fem', fall + '.json'), encoding='utf-8'))
    with ueberschrieben(spec.get('material_override')):
        return _mechanik(pdir, fall)


def _mechanik(pdir, fall):
    """Mechanik mit CalculiX. Neue, optionale Lastfall-Felder (ohne sie bleibt alles wie vorher):
      "schwerkraft": true | {"g": 1.0, "richtung": [0, 0, -1], "in_allen_lastfaellen": false}
          Eigengewicht (Dichte aus material.py). Standard: eigener Lastfall "eigengewicht" (Wegvorgaben dort 0),
          Ergebnis mit Masse, Schwerpunkt, statischer Durchbiegung und Rayleigh-Eigenfrequenz (S1).
      "konvergenz": {"faktoren": [1.0, 0.7, 0.5]}
          Netzstudie (F20-F22): alle Netzgroessen mal Faktor, je Faktor ein Lauf; Hauptergebnis bleibt Faktor 1.
      "druckrichtung": "z" | "x" | "y" | [dx, dy, dz]   (auch je Koerper)
          Aufbaurichtung des Drucks im Koordinatensystem des Lastfalls -> Tsai-Hill (M7) in der Bewertung.
      "orthotrop": true | {"E_z_MPa": .., "G_MPa": .., "nu_z": ..}
          transversal-isotrope Steifigkeit (M8) fuer Druckstoffe; braucht druckrichtung. Werte aus kennwerte.py,
          fehlen sie, wird isotrop gerechnet und das in "hinweise" vermerkt.
    Zusaetzlich je Lastfall: Gleichgewicht (Reaktionskraefte aller Lager, F23), Formaenderungsenergie, Ort und Tensor
    der max. Spannung, Spannungsfeld als .npz (Tensor je Element, fuer fem_plausi), bei NLGEOM Newton-/Kontaktdaten."""
    spec = json.load(open(os.path.join(pdir, 'fem', fall + '.json'), encoding='utf-8'))
    exe = werkzeuge.ccx()
    if not exe:
        raise RuntimeError('CalculiX fehlt - ' + werkzeuge.INSTALL['ccx'])
    t0 = time.time()
    arbeit = os.path.join(pdir, 'fem', fall)
    hinweise = []
    L = _mech_lauf(pdir, spec, arbeit, exe, hinweise)
    knoten, tets, koerper, namen, mats, druck, nl, rand, fest = (L[k] for k in (
        'knoten', 'tets', 'koerper', 'namen', 'mats', 'druck', 'nl', 'rand', 'fest'))

    erg = {'fall': fall, 'loeser': 'CalculiX ' + ('nichtlinear (NLGEOM' + (', Kontakt)' if spec.get('kontakt') else ')')
                                                  if nl else 'linear'),
           'knoten': len(knoten), 'tetraeder': len(tets), 'koerper': namen, 'lastfaelle': {}}
    stoffe = sorted({m for m in mats if m in DRUCKSTOFFE})
    for name, a in L['ergebnisse'].items():
        kn, F, u, rf = a['kn'], a['F'], a['u'], a['rf_weg']
        vm_el, vm_ip = a['vm_el'], a['vm_ip']
        vm_max = float(vm_el[druck].max()) if druck.any() else 0.0
        r = {'kraft_N': F.tolist(), 'max_vonMises_MPa': round(vm_max, 3),
             'max_vonMises_integrationspunkte_MPa': round(float(vm_ip[druck].max()), 3) if druck.any() else 0.0,
             'max_verschiebung_mm': round(float(np.linalg.norm(u, axis=1).max()), 5)}
        fn = np.linalg.norm(F)
        if len(kn):
            um = u[kn].mean(0)
            r['verschiebung_lastflaeche_mm'] = [round(float(v), 5) for v in um]
            if fn > 0:
                weg = float(um @ F / fn)
                r['federrate_N_mm'] = round(fn / weg, 4) if abs(weg) > 1e-12 else None
        wege = [f[2] for f in fest if f[2]]
        if rf:                                         # Reaktionskraft an jeder Wegvorgabe = Montagekraft
            r['reaktionskraft_N'] = [[round(float(v), 4) for v in vec] for vec in rf]
            w = np.array([wege[0].get(c, 0.0) for c in 'xyz'])
            if np.linalg.norm(w) > 0:
                # RF = von aussen aufgebrachte Kraft an den gefuehrten Knoten -> positiv = Kraft in Wegrichtung
                r['kraft_in_wegrichtung_N'] = round(float(np.asarray(rf[0]) @ w / np.linalg.norm(w)), 4)
        r['sicherheit'] = {m: {'xy': round(MATERIAL[m]['festigkeit_xy_MPa'] / vm_max, 2) if vm_max else None,
                               'z': round(MATERIAL[m]['festigkeit_z_MPa'] / vm_max, 2) if vm_max else None}
                           for m in DRUCKSTOFFE}
        hr = spec.get('hochrechnen')
        if hr and not nl and hr['last'] == name and r.get('federrate_N_mm'):
            k = hr['auf_verschiebung_mm'] / (fn / r['federrate_N_mm'])
            r['hochgerechnet'] = {'verschiebung_mm': hr['auf_verschiebung_mm'], 'kraft_N': round(fn * k, 3),
                                  'max_vonMises_MPa': round(vm_max * k, 2)}
        png = os.path.join(pdir, 'fem', f'{fall}_{name}.png')
        _bild_mech(knoten, tets, rand, vm_el, druck, u, png, f'{fall} / {name}: von Mises (MPa)')
        r['bild'] = png
        # ---- neu (optional auswertbar, aendert keine bisherigen Werte)
        r.update(a['zusatz'])
        if a.get('tensor') is not None and druck.any():
            npz = os.path.join(arbeit, f'{name}.spannung.npz')
            el = np.where(druck)[0]
            np.savez_compressed(npz, elemente=el, tensor=a['tensor'][el].astype(np.float32),
                                koerper=koerper[el], tiefe=L['tiefe'][el].astype(np.float32),
                                schwerpunkt=L['xc'][el].astype(np.float32), volumen=L['vol_el'][el].astype(np.float32),
                                am_lager=L['am_lager'][el],
                                namen=np.array(namen), mats=np.array(mats),
                                punkte=np.array('integrationspunkte' if nl else 'ecken'))
            r['spannungsfeld'] = npz
        erg['lastfaelle'][name] = r
    rk, dauer = _realkontext(pdir, spec, fall, list(erg['lastfaelle']))
    erg['bewertung'] = bewertung_mech(erg['lastfaelle'], stoffe, kontext=rk, dauer=dauer, projekt=projekt_soll(pdir))
    if L.get('orthotrop'):
        erg['orthotrop'] = L['orthotrop']
    if L.get('schwer') is not None:
        erg['masse_kg'] = round(float(L['masse_t'].sum() * 1000), 6)
        erg['schwerpunkt_mm'] = [round(float(v), 4) for v in L['schwerpunkt']]

    konv = spec.get('konvergenz')
    if konv:
        erg['konvergenz'] = _konvergenz(pdir, spec, arbeit, exe, konv, L, erg, hinweise)
    if hinweise:
        erg['hinweise'] = hinweise
    erg['rechenzeit_s'] = round(time.time() - t0, 1)
    json.dump(erg, open(os.path.join(pdir, 'fem', fall + '.erg.json'), 'w', encoding='utf-8'), indent=1,
              ensure_ascii=False)
    return erg


def _netz_skaliert(spec, f):
    """Lastfall mit allen Netzgroessen mal f (Netzstudie)."""
    s = json.loads(json.dumps(spec))
    n = s.setdefault('netz', {})
    g = n.get('groesse', 2.0)
    for fe in n.get('felder', []):
        fe['innen'] = fe['innen'] * f
        fe['aussen'] = fe.get('aussen', g) * f
    n['groesse'] = g * f
    return s


def _konvergenz(pdir, spec, arbeit, exe, konv, L0, erg, hinweise):
    """F20-F22: gleiche Rechnung auf feineren/groeberen Netzen. Rohdaten; die Bewertung macht pruefungen/fem_plausi."""
    faktoren = sorted({float(f) for f in konv.get('faktoren', [1.0, 0.7, 0.5])} | {1.0}, reverse=True)
    aus = {'faktoren': faktoren, 'tetraeder': [], 'knoten': [], 'lastfaelle': {}}
    for f in faktoren:
        if f == 1.0:
            L = L0
        else:
            L = _mech_lauf(pdir, _netz_skaliert(spec, f), os.path.join(arbeit, f'konv_{f:g}'), exe, [],
                           nur_kennzahlen=True)
        aus['tetraeder'].append(len(L['tets']))
        aus['knoten'].append(len(L['knoten']))
        for name, a in L['ergebnisse'].items():
            d = aus['lastfaelle'].setdefault(name, {'max_verschiebung_mm': [], 'verschiebung_lastrichtung_mm': [],
                                                    'kraft_weg_N': [], 'max_vonMises_MPa': [], 'energie_Nmm': [],
                                                    'ort_max_mm': []})
            u, druck = a['u'], L['druck']
            d['max_verschiebung_mm'].append(float(np.linalg.norm(u, axis=1).max()))
            F = a['F']
            d['verschiebung_lastrichtung_mm'].append(
                float(u[a['kn']].mean(0) @ F / np.linalg.norm(F)) if len(a['kn']) and np.linalg.norm(F) > 0 else None)
            wege = [w for _, _, w in L['fest'] if w]
            if a['rf_weg'] and wege:                   # Reaktion an der ersten Wegvorgabe, in Wegrichtung
                w = np.array([wege[0].get(c, 0.0) for c in 'xyz'])
                d['kraft_weg_N'].append(float(np.asarray(a['rf_weg'][0]) @ w / np.linalg.norm(w))
                                        if np.linalg.norm(w) > 0 else None)
            else:
                d['kraft_weg_N'].append(None)
            d['max_vonMises_MPa'].append(float(a['vm_el'][druck].max()) if druck.any() else 0.0)
            d['energie_Nmm'].append(a['zusatz'].get('energie_Nmm'))
            d['ort_max_mm'].append((a['zusatz'].get('spannung_max') or {}).get('ort_mm'))
    aus['hinweis'] = 'Faktor 1 = Hauptergebnis; Elementgroesse h ~ Faktor. Bewertung: pruefungen/fem_plausi (F20-F22)'
    return aus


def _richtung(d):
    """'x'/'y'/'z'/'-z' oder Vektor -> Einheitsvektor."""
    if isinstance(d, str):
        v = np.zeros(3)
        v[ACHSE[d.strip().lstrip('+-').lower()]] = -1.0 if d.strip().startswith('-') else 1.0
    else:
        v = np.asarray(d, float)
    n = np.linalg.norm(v)
    if n == 0:
        raise RuntimeError(f'Druckrichtung {d} ungueltig')
    return v / n


def _basis(d):
    """Orthonormalbasis (e1, e2, d) mit d = lokale 3-Achse (Aufbaurichtung)."""
    d = np.asarray(d, float) / np.linalg.norm(d)
    h = np.array([1.0, 0, 0]) if abs(d[0]) < 0.9 else np.array([0, 1.0, 0])
    e1 = np.cross(h, d)
    e1 /= np.linalg.norm(e1)
    return np.array([e1, np.cross(d, e1), d]).T          # Spalten = lokale Achsen in globalen Koordinaten


_VOIGT = [(0, 0), (1, 1), (2, 2), (0, 1), (0, 2), (1, 2)]   # Reihenfolge wie CalculiX: xx yy zz xy xz yz


def elastizitaet(E, nu, ortho=None):
    """Steifigkeit 6x6 (Voigt, Ingenieur-Gleitungen, Reihenfolge xx yy zz xy xz yz). ortho = dict mit
    E_z, G_z, nu_z (Querkontraktion Ebene->Z) und richtung (Einheitsvektor der Aufbaurichtung): transversal-isotrop."""
    if not ortho:
        lam, mu = E * nu / ((1 + nu) * (1 - 2 * nu)), E / (2 * (1 + nu))
        C = np.zeros((6, 6))
        C[:3, :3] = lam
        C[:3, :3] += 2 * mu * np.eye(3)
        C[3:, 3:] = mu * np.eye(3)
        return C
    Ez, Gz, nz = ortho['E_z'], ortho['G_z'], ortho.get('nu_z', nu)
    S = np.zeros((6, 6))
    S[0, 0] = S[1, 1] = 1 / E
    S[2, 2] = 1 / Ez
    S[0, 1] = S[1, 0] = -nu / E
    S[0, 2] = S[2, 0] = S[1, 2] = S[2, 1] = -nz / E
    S[3, 3] = 2 * (1 + nu) / E
    S[4, 4] = S[5, 5] = 1 / Gz
    Cl = np.linalg.inv(S)
    T = np.zeros((3, 3, 3, 3))                            # Voigt -> Tensor (fuer Ingenieur-Gleitung C_IJ = C_ijkl)
    for I, (i, j) in enumerate(_VOIGT):
        for J, (k, l) in enumerate(_VOIGT):
            for a, b in {(i, j), (j, i)}:
                for c, d in {(k, l), (l, k)}:
                    T[a, b, c, d] = Cl[I, J]
    Q = _basis(np.asarray(ortho['richtung'], float))
    Tg = np.einsum('ia,jb,kc,ld,abcd->ijkl', Q, Q, Q, Q, T)
    return np.array([[Tg[i, j, k, l] for (k, l) in _VOIGT] for (i, j) in _VOIGT])


def _orthotrop(spec, k, mat, hinweise):
    """Transversal-isotrope Konstanten fuer Koerper k oder None (dann isotrop)."""
    o = spec.get('orthotrop')
    if not o or mat not in DRUCKSTOFFE:
        return None
    o = o if isinstance(o, dict) else {}
    dr = spec['koerper'][k].get('druckrichtung', spec.get('druckrichtung'))
    try:
        d_vec = None if dr is None else _richtung(dr)
    except (KeyError, ValueError, RuntimeError, TypeError):
        d_vec = None
    if d_vec is None:
        hinweise.append(f'orthotrop fuer Koerper {k}: keine/ungueltige druckrichtung {dr!r} -> isotrop gerechnet')
        return None
    from . import kennwerte
    Ez = o.get('E_z_MPa', kennwerte.wert(mat, 'E_z_MPa'))
    Gz = o.get('G_MPa', kennwerte.wert(mat, 'G_MPa'))
    if Ez is None:
        hinweise.append(f'orthotrop fuer {mat}: E_z unbekannt (kennwerte.py) -> isotrop gerechnet, '
                        'Steifigkeit in Z damit ueberschaetzt')
        return None
    m = MATERIAL[mat]
    if Gz is None:
        Gz = Ez / (2 * (1 + m['nu']))
        hinweise.append(f'orthotrop fuer {mat}: G zwischen den Schichten unbekannt -> geschaetzt E_z/(2(1+nu)) '
                        f'= {Gz:.0f} MPa')
    return {'E_z': float(Ez), 'G_z': float(Gz), 'nu_z': float(o.get('nu_z', m['nu'])),
            'richtung': d_vec.tolist()}


def _schwerkraft(spec):
    s = spec.get('schwerkraft')
    if not s:
        return None
    s = s if isinstance(s, dict) else {}
    r = np.asarray(s.get('richtung', [0, 0, -1]), float)
    return {'g': r / np.linalg.norm(r) * float(s.get('g', 1.0)) * G_MM_S2,
            'in_allen': bool(s.get('in_allen_lastfaellen'))}


def _tet10_N(Lb):
    """Formfunktionen Tet10 (gmsh-Reihenfolge) an baryzentrischem Punkt."""
    N = np.zeros(10)
    N[:4] = Lb * (2 * Lb - 1)
    for (a, b), k in TET10_KANTE.items():
        N[k] = 4 * Lb[a] * Lb[b]
    return N


def _tet10_dN(Lb):
    dN = np.zeros((10, 3))
    for i in range(4):
        dN[i] = (4 * Lb[i] - 1) * _DL[i]
    for (a, b), k in TET10_KANTE.items():
        dN[k] = 4 * (Lb[b] * _DL[a] + Lb[a] * _DL[b])
    return dN


def _elem_integrale(knoten, tets):
    """Volumen, Schwerpunkt je Element und Matrix W (M,10): Integral u dV = W @ u (5-Punkt-Regel, Grad 3)."""
    X = knoten[tets]
    vol, xint, W = np.zeros(len(tets)), np.zeros((len(tets), 3)), np.zeros((len(tets), 10))
    Ns, dets = [], []
    for Lb, w in zip(_Q5_L, _Q5_W):
        N = _tet10_N(Lb)
        detJ = np.linalg.det(np.einsum('mni,nj->mij', X, _tet10_dN(Lb))) / 6 * w
        vol += detJ
        xint += detJ[:, None] * np.einsum('n,mni->mi', N, X)
        W += detJ[:, None] * N[None]
        Ns.append(N)
        dets.append(detJ)
    return vol, xint / vol[:, None], W, (np.array(Ns), np.array(dets))


def dauerlast_je_lastfall(spec, namen, soll=None, fall=None):
    """{lastfall: True/False/None} fuer die Abminderung (realterme A_K). None = unbekannt -> unguenstig (Dauerlast).
    Lastfall-Datei: "dauerlast": true/false oder "kurzzeit": true (ganzer Fall oder je Eintrag in "lasten", z. B.
    Fuegen eines Schnappers, Tastendruck, Fallstoss); Eigengewicht ruht immer (True); soll.json Teil.dauerlast mit
    "fem": "fall[/lastfall]" -> True."""
    spec = spec or {}

    def flag(d):
        if d.get('kurzzeit') is True:
            return False
        return d['dauerlast'] if isinstance(d.get('dauerlast'), bool) else None
    fallweit = flag(spec)
    je = {l.get('name'): flag(l) for l in spec.get('lasten', []) if isinstance(l, dict)}
    out = {}
    for n in namen:
        v = je.get(n)
        if v is None:
            v = fallweit
        if v is None and n == 'eigengewicht':
            v = True
        out[n] = v
    for t, ts in (soll or {}).items():
        dl = ts.get('dauerlast') if isinstance(ts, dict) and not str(t).startswith('_') else None
        if isinstance(dl, dict) and dl.get('fem') and fall:
            f, _, lf = str(dl['fem']).partition('/')
            if f == fall:
                for n in namen:
                    if not lf or lf == n:
                        out[n] = True
    return out


def projekt_soll(pdir):
    try:
        from .pruefungen import soll as _soll
        return _soll(pdir).get('_projekt', {})
    except Exception:  # noqa: BLE001
        return {}


def _realkontext(pdir, spec, fall, namen):
    """(realterme-Kontext aus soll.json + Merkmale, Dauerlast je Lastfall); unlesbar -> (None, ...) = Standards."""
    try:
        from .pruefungen import soll as _soll
        so = _soll(pdir)
    except Exception:  # noqa: BLE001
        so = {}
    try:
        from . import realterme
        rk = realterme.kontext(pdir, soll=so)
    except Exception:  # noqa: BLE001 - ohne Kontext: unguenstige Standards, angenommen
        rk = None
    return rk, dauerlast_je_lastfall(spec, namen, so, fall)


def _endlich(x, n=3):
    return round(float(x), n) if x is not None and math.isfinite(x) else (None if x is None else 1e9)


def bewertung_mech(lastfaelle, stoffe, kontext=None, dauer=None, projekt=None):
    """Gesamtbewertung der Mechanik-Lastfaelle (Sicherheit z >= 2 nach Abminderung, Tsai-Hill, Energiebilanz).
    kontext: realterme.kontext (Temperatur, aussen, ...); None -> unguenstige Standards, Ergebnis hoechstens warnung.
    dauer: {lastfall: True/False/None} (dauerlast_je_lastfall). 'min_sicherheit_z' bleibt der Rohwert (23 C,
    Vollmaterial, Kurzzeit); 'ok' haengt am wirksamen Wert sigma_Z / (S f) >= ... d. h. S_roh / f >= 2."""
    from . import realterme, sicherheit
    k0 = dict(kontext) if kontext is not None else realterme.kontext(None)
    # Ein Sicherheitsziel fuer alle Pruefungen (mb2/sicherheit.py): Minimum 2,0, Projektziel und M26 erhoehen es
    s_ziel = {m: sicherheit.ziel(projekt, None, m, 'z')[0] for m in stoffe} if stoffe else {}
    S_Z = max(s_ziel.values()) if s_ziel else sicherheit.S_STANDARD
    dauer = dauer or {}
    cache = {}

    def abm(m, n):
        key = (m, dauer.get(n))
        if key not in cache:
            kk = {**k0, 'material': m, 'dauerlast': dauer.get(n)}
            tt, a_t = [], False
            if kk.get('T_teil_C') is None:                  # Teiltemperatur samt Herkunft in die Terme
                kk['T_teil_C'], tt, a_t = realterme.teil_temperatur(kk)
            f, terme, ang = realterme.abminderung('festigkeit', kk)
            cache[key] = (f, tt + terme, ang or a_t or kontext is None)
        return cache[key]
    # Bewertung gegen das schwaechste genutzte Druckmaterial, Schichtrichtung (konservativ)
    # None = keine Spannung (unendliche Sicherheit); 0.0 ist ein Wert und darf nicht als 'fehlt' gelten (Befund I1)
    mins = [min(1e9 if lf['sicherheit'][m]['z'] is None else lf['sicherheit'][m]['z'] for m in stoffe)
            for lf in lastfaelle.values()] if stoffe else []
    je, w_min, w_wo, ang_alle = {}, None, None, False
    for n, lf in lastfaelle.items():
        je[n] = {}
        for m in stoffe:
            f, terme, ang = abm(m, n)
            ang_alle = ang_alle or ang
            sz = lf['sicherheit'][m]['z']
            sw = 1e9 if sz is None else sz / f
            je[n][m] = {'S_z': sz, 'f': _endlich(f), 'S_z_wirksam': _endlich(sw, 2), 'dauerlast': dauer.get(n),
                        'S_ziel': round(s_ziel[m], 3)}
            if w_min is None or sw / s_ziel[m] < w_min / s_ziel[w_wo[1]]:
                w_min, w_wo = sw, (n, m, f, terme)
    bw = {'material': stoffe, 'min_sicherheit_z': min(mins) if mins else None,
          'min_sicherheit_z_wirksam': _endlich(w_min, 2) if w_min is not None else None,
          'ok': bool(mins) and w_min is not None and w_min >= s_ziel[w_wo[1]],
          'S_ziel': round(S_Z, 3),
          'hinweis': f'Sicherheit >= {S_Z:.2f} (mb2/sicherheit.py: Minimum 2, Projektziel, M26) gegen Festigkeit in '
                     'Schichtrichtung nach Abminderung f (Temperatur, Dauerlast/Kriechbruch, aussen; mb2/realterme.py) '
                     'gefordert',
          'angenommen': ang_alle, 'je_lastfall': je}
    if w_wo:
        bw.update({'abminderung': _endlich(w_wo[2]), 'realterme': w_wo[3], 'massgebend': f'{w_wo[0]}/{w_wo[1]}'})
        bw['hinweis'] += (f'; massgebend {w_wo[0]} ({w_wo[1]}): S_roh / f {w_wo[2]:.2f}; ' + realterme.hinweis(w_wo[3]))
    if ang_alle:
        bw['hinweis'] += '; Annahmen (Dauer, Temperatur o. ae. unbekannt) -> hoechstens warnung'
    # M7 nur mit Druckrichtung: Tsai-Hill zusaetzlich (ersetzt nichts, kann die Bewertung nur verschaerfen)
    th = [(lf['tsai_hill']['sicherheit'], n, lf['tsai_hill'].get('material')) for n, lf in lastfaelle.items()
          if (lf.get('tsai_hill') or {}).get('sicherheit') is not None]
    th_w = None
    if th:
        bw['min_sicherheit_tsai_hill'] = round(min(t[0] for t in th), 2)
        def f_th(mat_, n):
            mat_ = mat_ if mat_ in DRUCKSTOFFE else (stoffe[0] if stoffe else None)
            return abm(mat_, n)[0] if mat_ else 1.0
        th_w = min(t[0] / f_th(t[2], t[1]) for t in th)
        bw['min_sicherheit_tsai_hill_wirksam'] = _endlich(th_w, 2)
        bw['ok'] = bw['ok'] and th_w >= S_Z
        bw['hinweis'] += f'; zusaetzlich Tsai-Hill (Druckrichtung) / f >= {S_Z:.2f}'
    # Energiebilanz (Clapeyron, Befund I2): ein verletzter Lauf darf nie als ok durchgehen
    eb_schlecht = sorted(n for n, lf in lastfaelle.items()
                         if abs((lf.get('energiebilanz') or {}).get('abweichung') or 0.0) > CLAPEYRON_TOL)
    if eb_schlecht:
        bw['ok'] = False
        bw['energiebilanz_verletzt'] = eb_schlecht
        bw['hinweis'] += ('; ENERGIEBILANZ VERLETZT (' + ', '.join(eb_schlecht) +
                         ') - Loeserergebnis unzuverlaessig, auch nach einfaedigem Neulauf')
    # Stufe wie die Pruefungen: ok nur ohne Annahmen; warnung zwischen 1 und 2; fehler darunter oder bei Bilanzfehler
    s_min = min([x for x in (w_min, th_w) if x is not None], default=None)
    if eb_schlecht or s_min is None or s_min < 1.0:
        bw['stufe'] = 'fehler'
    elif bw['ok']:
        bw['stufe'] = realterme.deckel('ok', ang_alle)
    else:
        bw['stufe'] = 'warnung'
    return bw


def _mech_lauf(pdir, spec, arbeit, exe, hinweise, nur_kennzahlen=False):
    """Ein CalculiX-Lauf (alle Lastfaelle) -> Rohdaten je Lastfall."""
    knoten, tets, koerper, namen, _ = netz(pdir, spec, 2)
    rand = randflaechen(tets)
    mats = [k['material'].upper() for k in spec['koerper']]
    druck = np.isin(np.array(mats)[koerper], DRUCKSTOFFE)
    nl = bool(spec.get('nichtlinear') or spec.get('kontakt'))
    if spec.get('kontakt') and spec.get('verbinden', True):
        raise RuntimeError('Kontakt braucht "verbinden": false (getrennte Netze)')

    # Lagerung: "fest" = Achsen auf 0, "weg" = vorgegebene Verschiebung (z. B. Montageweg beim Schnapphaken)
    fest = [(_flaechen_knoten(tets, *auswahl(l['wo'], knoten, tets, koerper, namen, rand)), l.get('fest', 'xyz'),
             l.get('weg')) for l in spec['lagerung']]
    lasten = []
    for l in spec.get('lasten', []):
        kn = _flaechen_knoten(tets, *auswahl(l['wo'], knoten, tets, koerper, namen, rand))
        lasten.append((l['name'], kn, np.asarray(l['kraft_N'], float)))
    schwer = _schwerkraft(spec)
    hat_weg = any(f[2] for f in fest)
    if not lasten and (not schwer or hat_weg or schwer['in_allen']):   # nur Wegvorgabe: ein Lastfall (wie bisher)
        lasten = [(spec.get('name', 'weg'), np.array([], int), np.zeros(3))]
    grav = {}
    if schwer:
        if schwer['in_allen']:
            grav = {n: schwer['g'] for n, _, _ in lasten}
        else:
            lasten.append(('eigengewicht', np.array([], int), np.zeros(3)))
            grav = {'eigengewicht': schwer['g']}

    ortho = {k: _orthotrop(spec, k, mats[k], hinweise) for k in range(len(mats))}
    Cs = {k: elastizitaet(MATERIAL[mats[k]]['E_MPa'], MATERIAL[mats[k]]['nu'], ortho[k]) for k in range(len(mats))}

    os.makedirs(arbeit, exist_ok=True)
    roh = {}
    # linear: alle Lastfaelle als unabhaengige Steps in einem Lauf; nichtlinear: je Lastfall ein Lauf
    laeufe = [lasten] if not nl else [[l] for l in lasten]
    lager_alle = np.unique(np.concatenate([f[0] for f in fest])) if fest else np.array([], int)
    vol_el, xc, W, quad = _elem_integrale(knoten, tets)
    rho = np.array([MATERIAL[m].get('dichte_kg_m3', 0.0) * RHO_T_MM3 for m in mats])[koerper]
    masse = rho * vol_el
    cmask = np.zeros((len(knoten), 3))                 # gesperrte Freiheitsgrade (RF gilt nur dort)
    for kn_f, achsen, weg in fest:                    # Wegvorgaben sperren ihre Richtung ebenfalls
        for c in set(achsen) | set(weg or {}):
            cmask[kn_f, ACHSE[c]] = 1.0
    n_weg = sum(1 for f in fest if f[2])

    def rechne(lauf, job, env):
        p = subprocess.run([exe, '-i', job], cwd=arbeit, capture_output=True, text=True, timeout=7200,
                           stdin=subprocess.DEVNULL, env=env)
        dat = os.path.join(arbeit, job + '.dat')
        if p.returncode or not os.path.exists(dat) or 'ERROR' in p.stdout:
            raise RuntimeError('CalculiX: ' + (p.stdout + p.stderr)[-1500:])
        u_blocks, s_blocks, rf, rfn = _lies_dat(dat, len(knoten), mit_knoten_rf=True)
        if nl:                                        # nur das letzte Inkrement zaehlt
            u_blocks, s_blocks, rf, rfn = u_blocks[-1:], s_blocks[-1:], rf[-n_weg:] if n_weg else [], rfn[-1:]
        newton = _lies_sta_cvg(os.path.join(arbeit, job)) if nl else None
        teil = {}
        for i, ((name, kn, F), u, s) in enumerate(zip(lauf, u_blocks, s_blocks)):
            teil[name] = dict(kn=kn, F=F, u=u, s=s, rf_weg=rf[i * n_weg:(i + 1) * n_weg],
                              rfn=rfn[i] if i < len(rfn) else {}, newton=newton, grav=grav.get(name))
        return teil

    def clapeyron(teil):
        """Energiebilanz linear: U_innen = 1/2 u^T K u (aus dem Verschiebungsfeld) gegen 1/2 F^T u (aeussere Arbeit).
        Ein falsches oertliches Verschiebungsfeld e erhoeht u^T K u um e^T K e > 0 -> faellt auf, auch wenn das
        Gleichgewicht der Reaktionen (F23) stimmt (Befund I2: SPOOLES mehrfaedig lieferte einzelne kaputte Laeufe)."""
        out = {}
        for name, a in teil.items():
            w = _energie(a['u'], a, cmask, rho, W, tets)
            ui = _innere_energie(knoten, tets, a['u'], koerper, Cs)
            ab = (ui / w - 1) if abs(w) > 1e-15 else (0.0 if abs(ui) < 1e-12 else math.inf)
            out[name] = {'innen_Nmm': float('%.7g' % ui), 'aussen_Nmm': w, 'abweichung': float('%.4g' % ab),
                         'grenze': CLAPEYRON_TOL}
        return out

    for lauf in laeufe:
        job = 'lauf' if not nl else 'lauf_' + lauf[0][0]
        inp = _inp(knoten, tets, koerper, mats, druck, fest, lauf, nl, spec, rand, namen,
                   schwer=grav, ortho=ortho, lager_alle=lager_alle)
        open(os.path.join(arbeit, job + '.inp'), 'w').write(inp)
        teil = rechne(lauf, job, werkzeuge.ccx_env())
        if not nl:
            eb = clapeyron(teil)
            if any(abs(v['abweichung']) > CLAPEYRON_TOL for v in eb.values()):
                # einmal einfaedig nachrechnen (deterministisch); bleibt es falsch, wird es gemeldet, nie verschwiegen
                hinweise.append('Energiebilanz verletzt (' + ', '.join(f'{n} {v["abweichung"] * 100:+.3g} %'
                                                                      for n, v in eb.items()) +
                                ') -> CalculiX einfaedig neu gerechnet')
                env1 = dict(werkzeuge.ccx_env(), OMP_NUM_THREADS='1', CCX_NPROC_EQUATION_SOLVER='1',
                            CCX_NPROC_STIFFNESS='1', CCX_NPROC_RESULTS='1', PASTIX_NUM_THREADS='1', STARPU_NCPU='1')
                teil = rechne(lauf, job, env1)
                eb = clapeyron(teil)
                for v in eb.values():
                    v['neu_gerechnet'] = 'einfaedig'
            for name, v in eb.items():
                teil[name]['clapeyron'] = v
        roh.update(teil)
    out = dict(knoten=knoten, tets=tets, koerper=koerper, namen=namen, mats=mats, druck=druck, nl=nl, rand=rand,
               fest=fest, ergebnisse={}, vol_el=vol_el, xc=xc, masse_t=masse,
               schwer=schwer, schwerpunkt=(masse @ xc) / masse.sum() if masse.sum() > 0 else np.zeros(3),
               orthotrop={namen[k]: v for k, v in ortho.items() if v})
    if not nur_kennzahlen:
        out['tiefe'] = _tiefe(knoten, tets, rand, xc)
    # Element beruehrt eine Lagerflaeche -> Spitzen dort koennen Randbedingungs-Artefakte sein (nur Hinweis)
    out['am_lager'] = np.isin(tets, lager_alle).any(1) if len(lager_alle) else np.zeros(len(tets), bool)
    mitte = 0.5 * (knoten.min(0) + knoten.max(0))
    laenge = float(np.linalg.norm(np.ptp(knoten, axis=0)))
    for name, a in roh.items():
        u, s = a['u'], a['s']
        tensor = np.zeros((len(tets), 4, 6))
        if nl:                                        # Loeserwerte an den 4 Integrationspunkten
            for e, ips in s.items():
                tensor[e, :len(ips)] = np.array(ips)[:4]
        else:                                         # Eckwerte des FE-Feldes (Maximum im Element)
            for k in np.unique(koerper[druck]):
                el = np.where(koerper == k)[0]
                tensor[el] = spannung_feld(knoten, tets, u, Cs[k], elemente=el)
        vm_ip = _von_mises(s, len(tets))
        vm_el = vm_ip.copy() if nl else np.where(druck, _vm_voigt(tensor).max(1), vm_ip)
        z = {}
        if not nur_kennzahlen:
            z.update(_gleichgewicht(knoten, u if nl else None, a, fest, cmask, rho, W, mitte, laenge, tets))
        if not nl:                                    # Formaenderungsenergie = halbe Arbeit der aeusseren Kraefte
            z['energie_Nmm'] = _energie(u, a, cmask, rho, W, tets)
            if a.get('clapeyron'):
                z['energiebilanz'] = a['clapeyron']
        if druck.any():
            e = int(np.argmax(np.where(druck, vm_el, -1)))
            vmp = _vm_voigt(tensor[e])
            pnr = int(np.argmax(vmp))
            ort = knoten[tets[e, pnr]] if not nl else knoten[tets[e, :4]].mean(0)
            z['spannung_max'] = {'MPa': round(float(vm_el[e]), 3), 'tensor_MPa': [round(float(v), 4) for v in tensor[e, pnr]],
                                 'ort_mm': [round(float(v), 3) for v in ort], 'element': e + 1,
                                 'koerper': namen[koerper[e]],
                                 'tiefe_mm': round(float(out['tiefe'][e]), 3) if 'tiefe' in out else None,
                                 'am_lager': bool(out['am_lager'][e]),
                                 'auswertung': 'integrationspunkt' if nl else 'ecke'}
        if a['grav'] is not None and not nur_kennzahlen:
            z.update(_eigengewicht(u, a['grav'], masse, W, quad, tets, rho, a['kn'], fest))
        if nl and not nur_kennzahlen:
            z['newton'] = a['newton']
            if spec.get('kontakt'):
                z['kontakt'] = [_durchdringung(knoten, u, tets, koerper, namen, rand, kt) for kt in spec['kontakt']]
        if not nur_kennzahlen:
            th = _tsai_hill_lastfall(spec, tensor, koerper, mats, druck, namen, knoten, tets, nl)
            if th:
                th['am_lager'] = bool(out['am_lager'][th['element'] - 1])
                z['tsai_hill'] = th
        out['ergebnisse'][name] = dict(kn=a['kn'], F=a['F'], u=u, rf_weg=a['rf_weg'], vm_el=vm_el, vm_ip=vm_ip,
                                       tensor=None if nur_kennzahlen else tensor, zusatz=z)
    return out


def _tiefe(knoten, tets, rand, xc):
    """Abstand Elementschwerpunkt -> naechster Randknoten (mm), etwas zu gross (konservativ fuer Kern-Erkennung)."""
    from scipy.spatial import cKDTree
    rk = _flaechen_knoten(tets, rand[0], rand[1])
    return cKDTree(knoten[rk]).query(xc)[0]


def _knotenlasten(n, a, rho, W, tets):
    """Aeussere Knotenkraefte (n,3): CLOAD (gleich verteilt wie im .inp) + konsistentes Eigengewicht rho*g*Int(N dV)."""
    F = np.zeros((n, 3))
    if len(a['kn']) and np.linalg.norm(a['F']) > 0:
        np.add.at(F, a['kn'], a['F'] / len(a['kn']))
    if a['grav'] is not None:
        np.add.at(F, tets.ravel(), ((rho[:, None] * W).ravel()[:, None] * np.asarray(a['grav'])[None]))
    return F


def _gleichgewicht(knoten, u_nl, a, fest, cmask, rho, W, mitte, laenge, tets):
    """F23-Rohdaten: Summe Reaktionen und aeussere Lasten (Kraft, Moment um die Mitte der Bounding Box).
    CalculiX-RF = innere Knotenkraft an allen 3 Richtungen -> nur gesperrte Freiheitsgrade zaehlen als Reaktion;
    Last auf gesperrten Freiheitsgraden geht direkt ins Lager (eigene Summe). Bei NLGEOM mit verformter Lage."""
    pos = knoten if u_nl is None else knoten + u_nl
    rfn = a['rfn']
    if not rfn:
        return {}
    RF = np.zeros((len(knoten), 3))
    ids = np.array(sorted(rfn))
    RF[ids] = np.array([rfn[i] for i in ids])
    R = RF * cmask
    F = _knotenlasten(len(knoten), a, rho, W, tets)
    Ff, Fl = F * (1 - cmask), F * cmask
    mom = lambda V: np.cross(pos - mitte, V).sum(0)  # noqa: E731
    je_lager = []
    for kn_f, achsen, weg in fest:
        m = np.zeros(3)
        m[[ACHSE[c] for c in set(achsen) | set(weg or {})]] = 1.0
        je_lager.append([round(float(v), 6) for v in (RF[kn_f] * m).sum(0)])
    rd = lambda v: [float('%.7g' % x) for x in v]  # noqa: E731
    return {'gleichgewicht': {'reaktion_N': rd(R.sum(0)), 'last_N': rd(Ff.sum(0)), 'reaktion_moment_Nmm': rd(mom(R)),
                              'last_moment_Nmm': rd(mom(Ff)), 'bezug_mm': rd(mitte), 'laenge_mm': round(laenge, 3),
                              'reaktion_je_lager_N': je_lager, 'last_gesamt_N': rd(F.sum(0)),
                              'last_auf_lager_N': rd(Fl.sum(0)), 'lagerknoten': int(len(ids)),
                              'hinweis': 'reaktion + last = 0 (last = auf freien Freiheitsgraden)'}}


def _energie(u, a, cmask, rho, W, tets):
    """1/2 * Arbeit der aeusseren Kraefte (linear): Lasten an freien Freiheitsgraden + Reaktionen an gesperrten
    (dort nur Wegvorgaben != 0 leisten Arbeit)."""
    F = _knotenlasten(len(u), a, rho, W, tets) * (1 - cmask)
    w = float((F * u).sum())
    for i, f in a['rfn'].items():
        w += float(np.dot(np.asarray(f) * cmask[i], u[i]))
    return float('%.7g' % (0.5 * w))


CLAPEYRON_TOL = 0.005                              # |U_innen / (F u / 2) - 1|, Direktloeser: ~1e-6
# 4-Punkt-Gaussregel (Grad 2, exakt fuer eps^T C eps bei Tet10), baryzentrisch, Gewichte je 1/4
_G4_A, _G4_B = 0.5854101966249685, 0.1381966011250105
_G4_L = np.array([[_G4_A, _G4_B, _G4_B, _G4_B], [_G4_B, _G4_A, _G4_B, _G4_B],
                  [_G4_B, _G4_B, _G4_A, _G4_B], [_G4_B, _G4_B, _G4_B, _G4_A]])


def _innere_energie(knoten, tets, u, koerper, Cs):
    """Formaenderungsenergie 1/2 Int(eps^T C eps dV) aus dem Verschiebungsfeld (Tet10, C je Koerper, Voigt mit
    Ingenieur-Gleitungen). Unabhaengig vom Loeser - Gegenprobe zu 1/2 F^T u (Satz von Clapeyron)."""
    X, U = knoten[tets], u[tets]
    summe = 0.0
    for Lb in _G4_L:
        dN = _tet10_dN(Lb)
        J = np.einsum('mni,nj->mij', X, dN)
        det = np.linalg.det(J)
        G = np.einsum('nj,mjk->mnk', dN, np.linalg.inv(J))
        H = np.einsum('mni,mnk->mik', U, G)
        eps = np.stack([H[:, 0, 0], H[:, 1, 1], H[:, 2, 2], H[:, 0, 1] + H[:, 1, 0], H[:, 0, 2] + H[:, 2, 0],
                        H[:, 1, 2] + H[:, 2, 1]], axis=1)
        for k, C in Cs.items():
            m = koerper == k
            if m.any():
                summe += float(np.einsum('mi,ij,mj,m->', eps[m], np.asarray(C), eps[m], np.abs(det[m]))) / 24.0
    return 0.5 * summe


def _eigengewicht(u, g, masse, W, quad, tets, rho, kn, fest):
    """Statische Durchbiegung unter 1 g und Rayleigh-Quotient mit dieser Biegeform:
    omega^2 = g . Int(rho u dV) / Int(rho |u|^2 dV) (konsistente Masse; obere Schranke fuer f1)."""
    Ns, dets = quad
    ue = u[tets]
    ug = np.einsum('mn,mni->mi', W, ue)
    zaehler = float((rho[:, None] * ug).sum(0) @ np.asarray(g))
    nenner = 0.0
    for N, d in zip(Ns, dets):
        up = np.einsum('n,mni->mi', N, ue)
        nenner += float((rho * d * (up ** 2).sum(1)).sum())
    gn = np.asarray(g) / np.linalg.norm(g)
    r = {'masse_kg': round(float(masse.sum() * 1000), 6),
         'durchbiegung_g_richtung_max_mm': round(float((u @ gn).max()), 6),
         'durchbiegung_mittel_mm': round(float((ug @ gn).sum() / W.sum()), 6)}
    if any(f[2] for f in fest) or len(kn):
        r['hinweis_eigengewicht'] = 'Wegvorgaben in diesem Lastfall auf 0 gehalten'
    if zaehler > 0 and nenner > 0:
        r['rayleigh_f1_Hz'] = round(float(np.sqrt(zaehler / nenner) / (2 * np.pi)), 3)
    return r


def _lies_sta_cvg(job):
    """F24-Rohdaten aus <job>.sta (Inkremente) und <job>.cvg (Residuen je Iteration)."""
    r = {}
    try:
        rows = []
        for line in open(job + '.sta', encoding='utf-8', errors='replace'):
            p = line.split()
            if len(p) == 7:
                try:
                    rows.append([float(v) for v in p])
                except ValueError:
                    pass
        if rows:
            a = np.array(rows)
            r.update({'inkremente': int(len(a)), 'zeit_erreicht': float(a[-1, 5]),
                      'abbrueche': int((a[:, 2] - 1).sum()), 'iterationen_max': int(a[:, 3].max()),
                      'iterationen_mittel': round(float(a[:, 3].mean()), 2)})
    except OSError:
        pass
    try:
        rows = []
        for line in open(job + '.cvg', encoding='utf-8', errors='replace'):
            p = line.split()
            if len(p) == 9:
                try:
                    rows.append([float(v) for v in p])
                except ValueError:
                    pass
        if rows:
            last = rows[-1]
            r.update({'letzte_iteration': {'kontakt_elemente': int(last[4]), 'residuum_kraft_prozent': last[5],
                                           'korrektur_weg_prozent': last[6]}})
    except OSError:
        pass
    return r or None


def _durchdringung(knoten, u, tets, koerper, namen, rand, kt):
    """F24: groesste Durchdringung der Slave-Knoten in die Master-Flaeche (verformt), Elementgroesse am Slave."""
    tid_s, fnr_s = auswahl(kt['slave'], knoten, tets, koerper, namen, rand)
    tid_m, fnr_m = auswahl(kt['master'], knoten, tets, koerper, namen, rand)
    pos = knoten + u
    sk = _flaechen_knoten(tets, tid_s, fnr_s)
    fl = np.array([[tets[t, i] for i in TET_FLAECHEN[f]] for t, f in zip(tid_m, fnr_m)])
    gegen = np.array([tets[t, ({0, 1, 2, 3} - set(TET_FLAECHEN[f])).pop()] for t, f in zip(tid_m, fnr_m)])
    A, B, C = pos[fl[:, 0]], pos[fl[:, 1]], pos[fl[:, 2]]
    n = np.cross(B - A, C - A)
    n /= np.linalg.norm(n, axis=1)[:, None]
    n *= np.where(np.einsum('ij,ij->i', n, pos[gegen] - A) > 0, -1.0, 1.0)[:, None]   # nach aussen
    ecken_s = np.array([[tets[t, i] for i in TET_FLAECHEN[f]] for t, f in zip(tid_s, fnr_s)])
    h = float(np.mean([np.linalg.norm(knoten[ecken_s[:, i]] - knoten[ecken_s[:, (i + 1) % 3]], axis=1).mean()
                       for i in range(3)]))
    dmax, anz = 0.0, 0
    v0, v1 = B - A, C - A
    d00, d01, d11 = (v0 * v0).sum(1), (v0 * v1).sum(1), (v1 * v1).sum(1)
    den = d00 * d11 - d01 ** 2
    for k in range(0, len(sk), 256):
        P = pos[sk[k:k + 256]]
        w = P[:, None, :] - A[None]
        dist = np.einsum('sti,ti->st', w, n)               # < 0: Knoten innerhalb des Master-Koerpers
        d20, d21 = np.einsum('sti,ti->st', w, v0), np.einsum('sti,ti->st', w, v1)
        b1 = (d11 * d20 - d01 * d21) / den
        b2 = (d00 * d21 - d01 * d20) / den
        innen = (b1 >= -1e-6) & (b2 >= -1e-6) & (b1 + b2 <= 1 + 1e-6) & (dist < 0) & (dist > -2 * h)
        pen = np.where(innen, -dist, 0.0).max(1)
        dmax = max(dmax, float(pen.max()) if len(pen) else 0.0)
        anz += int((pen > 0).sum())
    return {'durchdringung_max_mm': round(dmax, 6), 'element_mm': round(h, 4), 'knoten_durchdrungen': anz,
            'slave_knoten': int(len(sk)), 'steifigkeit_N_mm3': kt.get('steifigkeit_N_mm3', 500.0)}


def _tsai_hill_lastfall(spec, tensor, koerper, mats, druck, namen, knoten, tets, nl):
    """M7 je Lastfall, nur wenn eine Druckrichtung im Lastfall steht."""
    from .pruefungen.fem_plausi import tsai_hill_sicherheit
    best = None
    for k in np.unique(koerper[druck]):
        dr = spec['koerper'][k].get('druckrichtung', spec.get('druckrichtung'))
        if dr is None:
            continue
        try:
            _richtung(dr)
        except (KeyError, ValueError, RuntimeError, TypeError):
            continue                                   # ungueltig -> keine Tsai-Hill-Bewertung (fem_plausi meldet es)
        el = np.where(koerper == k)[0]
        S, e, p, info = tsai_hill_sicherheit(tensor[el], mats[k], _richtung(dr))
        if S is None:
            continue
        if best is None or S < best['sicherheit']:
            ee = el[e]
            ort = knoten[tets[ee, p]] if not nl else knoten[tets[ee, :4]].mean(0)
            best = {'sicherheit': round(float(S), 3), 'koerper': namen[k], 'material': mats[k],
                    'druckrichtung': _richtung(dr).round(4).tolist(), 'ort_mm': [round(float(v), 3) for v in ort],
                    'element': int(ee) + 1, **info}
    return best


def _inp(knoten, tets, koerper, mats, druck, fest, lasten, nl, spec, rand, namen, schwer=None, ortho=None,
         lager_alle=None):
    fest = [tuple(f) + (None,) * (3 - len(f)) for f in fest]   # aeltere Aufrufer: (knoten, achsen)
    schwer, ortho = schwer or {}, ortho or {}
    z = ['*HEADING', 'maker-bridge-2', '*NODE, NSET=NALL']
    z += [f'{i + 1},{x:.9g},{y:.9g},{w:.9g}' for i, (x, y, w) in enumerate(knoten)]
    for k in np.unique(koerper):
        z.append(f'*ELEMENT, TYPE=C3D10, ELSET=K{k}')
        for e in np.where(koerper == k)[0]:
            z.append(f'{e + 1},' + ','.join(str(int(tets[e, j]) + 1) for j in GMSH2CCX))
    z.append('*ELSET, ELSET=EDRUCK')
    z += _zeilen(np.where(druck)[0] + 1)
    for k in np.unique(koerper):
        m = MATERIAL[mats[k]]
        o = ortho.get(k)
        z += [f'*MATERIAL, NAME=M{k}']
        if o:
            E, nu, G12 = m['E_MPa'], m['nu'], m['E_MPa'] / (2 * (1 + m['nu']))
            z += ['*ELASTIC, TYPE=ENGINEERING CONSTANTS',
                  f'{E:.9g},{E:.9g},{o["E_z"]:.9g},{nu:.9g},{o["nu_z"]:.9g},{o["nu_z"]:.9g},{G12:.9g},{o["G_z"]:.9g}',
                  f'{o["G_z"]:.9g}']
        else:
            z += ['*ELASTIC', f'{m["E_MPa"]},{m["nu"]}']
        if schwer:
            z += ['*DENSITY', f'{m.get("dichte_kg_m3", 0.0) * RHO_T_MM3:.9g}']
        if o:
            Q = _basis(np.asarray(o['richtung'], float))
            a, b = Q[:, 0], Q[:, 1]
            z += [f'*ORIENTATION, NAME=OR{k}, SYSTEM=RECTANGULAR', ','.join(f'{v:.12g}' for v in (*a, *b))]
            z.append(f'*SOLID SECTION, ELSET=K{k}, MATERIAL=M{k}, ORIENTATION=OR{k}')
        else:
            z.append(f'*SOLID SECTION, ELSET=K{k}, MATERIAL=M{k}')
    for kontakt_nr, kt in enumerate(spec.get('kontakt', [])):
        for rolle in ('slave', 'master'):
            tid, fnr = auswahl(kt[rolle], knoten, tets, koerper, namen, rand)
            z.append(f'*SURFACE, NAME={rolle[0].upper()}{kontakt_nr}, TYPE=ELEMENT')
            z += [f'{t + 1},S{f + 1}' for t, f in zip(tid, fnr)]
        z += [f'*SURFACE INTERACTION, NAME=I{kontakt_nr}', '*SURFACE BEHAVIOR, PRESSURE-OVERCLOSURE=LINEAR',
              f'{kt.get("steifigkeit_N_mm3", 500.0)}']
        if kt.get('reibung'):
            z += ['*FRICTION', f'{kt["reibung"]},{kt.get("haft_steifigkeit", 50.0)}']
        z += [f'*CONTACT PAIR, INTERACTION=I{kontakt_nr}, TYPE=SURFACE TO SURFACE', f'S{kontakt_nr},M{kontakt_nr}']
    z.append('*BOUNDARY')
    for kn, achsen, _ in fest:
        for a in sorted({ACHSE[c] + 1 for c in achsen}):
            z += [f'{int(n) + 1},{a},{a}' for n in kn]
    wege = [(i, kn, w) for i, (kn, _, w) in enumerate(fest) if w]
    for i, kn, _ in wege:
        z.append(f'*NSET, NSET=NW{i}')
        z += _zeilen(kn + 1)
    if lager_alle is not None and len(lager_alle):
        z.append('*NSET, NSET=NRF')
        z += _zeilen(np.asarray(lager_alle) + 1)
    for name, kn, F in lasten:
        z += ['*STEP' + (', NLGEOM, INC=500' if nl else ''), '*STATIC, SOLVER=SPOOLES'] + (['0.02,1.0,1e-7,0.1'] if nl else [])
        # SPOOLES fest: der Standardlöser PaStiX im MSYS2-ccx hängt (getestet 05.11.2026)
        nur_g = name == 'eigengewicht' and name in schwer
        for i, _, w in wege:                           # vorgegebener Weg, im Step linear aufgebracht
            z.append('*BOUNDARY')
            z += [f'NW{i},{ACHSE[a] + 1},{ACHSE[a] + 1},{0.0 if nur_g else v}' for a, v in w.items()]
        z.append('*CLOAD, OP=NEW')
        for a in range(3):
            if F[a]:
                z += [f'{int(n) + 1},{a + 1},{F[a] / len(kn):.12g}' for n in kn]
        if schwer:                                     # Eigengewicht: nur in den Lastfaellen mit Schwerkraft
            z.append('*DLOAD, OP=NEW')
            g = schwer.get(name)
            if g is not None:
                gb = float(np.linalg.norm(g))
                z += [f'K{k},GRAV,{gb:.9g},' + ','.join(f'{v / gb:.9g}' for v in g) for k in np.unique(koerper)]
        z += ['*NODE PRINT, NSET=NALL', 'U', '*EL PRINT, ELSET=EDRUCK', 'S']
        for i, _, _ in wege:
            z += [f'*NODE PRINT, NSET=NW{i}, TOTALS=ONLY', 'RF']
        if lager_alle is not None and len(lager_alle):
            z += ['*NODE PRINT, NSET=NRF', 'RF']
        z.append('*END STEP')
    return '\n'.join(z) + '\n'


def _zeilen(ids, n=16):
    return [','.join(str(int(i)) for i in ids[k:k + n]) for k in range(0, len(ids), n)]


def _lies_dat(pfad, n_knoten, mit_knoten_rf=False):
    """.dat -> Verschiebungsfelder (N,3), Spannungen {elem: [(6,), ...]} und Reaktionskraft-Summen je Ausgabeblock.
    mit_knoten_rf: zusaetzlich je Ausgabeblock die Knoten-Reaktionen der Lager {knoten0: [fx, fy, fz]}."""
    u_bl, s_bl, rf, rfn, cur, art = [], [], [], [], None, None
    for line in open(pfad, encoding='utf-8', errors='replace'):
        s = line.strip()
        if s.startswith('total force'):
            cur, art = None, 'rf'
            continue
        if art == 'rf' and s:
            rf.append([float(v) for v in s.split()[:3]])
            art = None
            continue
        if s.startswith('displacements'):
            cur, art = np.zeros((n_knoten, 3)), 'u'
            u_bl.append(cur)
            continue
        if s.startswith('stresses'):
            cur, art = {}, 's'
            s_bl.append(cur)
            continue
        if s.startswith('forces'):                     # Knoten-Reaktionen (NODE PRINT RF ohne TOTALS=ONLY)
            cur, art = {}, 'rfn'
            rfn.append(cur)
            continue
        if not s or cur is None:
            continue
        parts = s.split()
        try:
            if art == 'u' and len(parts) == 4:
                cur[int(parts[0]) - 1] = [float(v) for v in parts[1:]]
            elif art == 's' and len(parts) == 8:
                cur.setdefault(int(parts[0]) - 1, []).append([float(v) for v in parts[2:]])
            elif art == 'rfn' and len(parts) == 4:
                cur[int(parts[0]) - 1] = [float(v) for v in parts[1:]]
        except ValueError:
            cur, art = None, None
    return (u_bl, s_bl, rf, rfn) if mit_knoten_rf else (u_bl, s_bl, rf)


def _vm_voigt(s):
    """von Mises aus Voigt-Spannungen (..., 6) in CalculiX-Reihenfolge xx yy zz xy xz yz."""
    sx, sy, sz, txy, txz, tyz = np.moveaxis(np.asarray(s), -1, 0)
    return np.sqrt(0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2) + 3 * (txy ** 2 + txz ** 2 + tyz ** 2))


def _von_mises(s, n):
    vm = np.zeros(n)
    for e, ips in s.items():
        vm[e] = _vm_voigt(np.array(ips)).max()
    return vm


_DL = np.array([[-1, -1, -1], [1, 0, 0], [0, 1, 0], [0, 0, 1]], float)   # dL_i/dxi (Baryzentrische Koordinaten)
ECKEN = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], float)


def spannung_feld(knoten, tets, u, C, punkte=ECKEN, elemente=None):
    """Spannungstensor (Voigt xx yy zz xy xz yz) des FE-Feldes aus den Verschiebungen (Tet10, gmsh-Reihenfolge) an
    Referenzpunkten, C = 6x6-Steifigkeit (elastizitaet). Rueckgabe (M, P, 6)."""
    sel = np.arange(len(tets)) if elemente is None else np.asarray(elemente)
    t = tets[sel]
    X, U = knoten[t], u[t]                                    # (M,10,3)
    out = np.zeros((len(sel), len(punkte), 6))
    for j, xi in enumerate(punkte):
        dN = _tet10_dN(np.array([1 - xi.sum(), *xi]))
        J = np.einsum('mni,nj->mij', X, dN)                   # dx/dxi
        G = np.einsum('nj,mjk->mnk', dN, np.linalg.inv(J))     # dN/dx
        H = np.einsum('mni,mnk->mik', U, G)                    # grad u
        eps = np.stack([H[:, 0, 0], H[:, 1, 1], H[:, 2, 2], H[:, 0, 1] + H[:, 1, 0], H[:, 0, 2] + H[:, 2, 0],
                        H[:, 1, 2] + H[:, 2, 1]], axis=1)      # Ingenieur-Gleitungen
        out[:, j] = eps @ np.asarray(C).T
    return out


def von_mises_feld(knoten, tets, u, E, nu, punkte=ECKEN, elemente=None):
    """Von Mises des FE-Feldes direkt aus den Verschiebungen (Tet10, gmsh-Reihenfolge) an Referenzpunkten.
    Dehnung ist bei Tet10 linear im Element -> das Maximum liegt an den Ecken (Standard). Unabhaengig davon, an
    welchen Integrationspunkten ein Loeser auswertet. Rueckgabe: je Element das Maximum ueber die Punkte."""
    return _vm_voigt(spannung_feld(knoten, tets, u, elastizitaet(E, nu), punkte, elemente)).max(1)


def _knotenwerte(tets, el_werte, n_knoten, maske=None):
    summe, anz = np.zeros(n_knoten), np.zeros(n_knoten)
    sel = np.arange(len(tets)) if maske is None else np.where(maske)[0]
    for j in range(4):
        np.add.at(summe, tets[sel, j], el_werte[sel] if len(el_werte) == len(tets) else 0)
        np.add.at(anz, tets[sel, j], 1)
    return np.where(anz > 0, summe / np.maximum(anz, 1), 0)


def _bild_mech(knoten, tets, rand, vm_el, druck, u, png, titel):
    from . import render
    werte = _knotenwerte(tets, vm_el, len(knoten), druck)
    groesse = np.ptp(knoten, axis=0).max()
    umax = np.linalg.norm(u, axis=1).max()
    skala = max(1.0, round(0.05 * groesse / umax)) if umax > 0 else 1.0
    render.feld_png(knoten, rand[2], werte, png, titel, 'von Mises [MPa]', u, skala)


# ---------------------------------------------------------------- Elmer

SIGMA = 5.670374419e-8      # Stefan-Boltzmann, W/(m2 K4)
K0 = 273.15                 # 0 C in K
K_LUFT = 0.026              # W/(m K), ruhende Luft ~300 K (OCW 4.42J Gl. 3.15)
LUFT = 'LUFT'               # Material der Innenluft (nur Waerme, nicht in MATERIAL)
C_FREI = 1.42               # h = 1,42 (dT/L)^1/4 W/m2K, freie Konvektion laminar, Luft (OCW 3.185 §5.4, 4.42J Gl. 3.13)


def h_frei(dT_K, L_m):
    """W1: h der freien Konvektion (laminar, senkrechte Platte, Luft) aus mittlerer Uebertemperatur und Hoehe."""
    return C_FREI * (max(float(dT_K), 1e-3) / max(float(L_m), 1e-4)) ** 0.25


def waerme_optionen(spec):
    """Neue optionale Lastfall-Felder (W1/W2/W5/W6) auslesen. Alles leer -> waerme() rechnet wie bisher."""
    kv = spec.get('konvektion') or {}
    st = spec.get('strahlung')
    if st is True:
        st = {}
    il = spec.get('innenluft')
    if il is True:
        il = {}
    so = spec.get('sonne')
    if so is True:
        so = {}
    return {'auto': bool(kv.get('auto')), 'strahlung': st if isinstance(st, dict) else None,
            'innenluft': il if isinstance(il, dict) else None, 'sonne': so if isinstance(so, dict) else None}


def waerme(pdir, fall):
    spec = json.load(open(os.path.join(pdir, 'fem', fall + '.json'), encoding='utf-8'))
    with ueberschrieben(spec.get('material_override')):
        return _waerme(pdir, fall)


def _waerme(pdir, fall):
    """Stationaere Waermeleitung mit Elmer. Ohne die neuen Felder (strahlung, konvektion.auto, innenluft, sonne)
    identisch zur bisherigen Rechnung; neu ist nur die Energiebilanz (W3) und Zusatzdaten im Ergebnis.
    - strahlung {"emission": 0.9}: Strahlung εσ(T⁴-T∞⁴) gegen die Umgebung (Elmer 'Idealized', Rechnung in K).
      Jede Flaeche strahlt nur mit ihrem Himmelsanteil F (orthografische Sichtpruefung aus 26 Richtungen):
      Aussenflaechen F≈1, Innenflaechen eines geschlossenen Gehaeuses F=0 (sie sehen nur die eigene Wand).
    - konvektion {"auto": true, "L_mm": Hoehe}: h aus freier Konvektion h = 1,42 (ΔT/L)^¼ mit der mittleren
      Uebertemperatur der Konvektionsflaechen, Fixpunkt h_neu = h^0,2·h_korr^0,8 (exakt, falls ΔT ~ 1/h).
    - innenluft true | {"box": [..6..], "spalt_mm": δ, "emission": [ε1, ε2], "strahlung": true}: Hohlraum als
      Ersatzleiter k = k_Luft·Nu(=1) + 4·ε_eff·σ·T_m³·δ (W5). Ohne box: Bounding Box aller Koerper, nur
      geschlossene Hohlraeume (Luftteile ohne Kontakt zum Box-Rand) bleiben.
    - sonne {"G_W_m2": 1000, "absorption": 0.6, "richtung": [0, 0, -1]}: q = α·G auf die sichtbare Projektion
      (mit Abschattung), Summe = α·G·A_proj."""
    spec = json.load(open(os.path.join(pdir, 'fem', fall + '.json'), encoding='utf-8'))
    if not werkzeuge.elmer_bin():
        raise RuntimeError('Elmer fehlt - ' + werkzeuge.INSTALL['elmer'])
    t0 = time.time()
    arbeit = os.path.join(pdir, 'fem', fall)
    os.makedirs(arbeit, exist_ok=True)
    opt = waerme_optionen(spec)
    hinweise = []
    spec_n, luft_box = spec, None
    if opt['innenluft'] is not None:
        spec_n, luft_box = _mit_innenluft(pdir, spec, opt['innenluft'], hinweise)
    knoten, tets, koerper, namen, vol = netz(pdir, spec_n, 1)
    mats = [k['material'].upper() for k in spec_n['koerper']]
    luft = None
    if luft_box is not None:
        knoten, tets, koerper, namen, vol, mats, luft = _innenluft_netz(knoten, tets, koerper, namen, vol, mats,
                                                                        opt['innenluft'], luft_box, hinweise)
        if luft is None:
            spec_n = spec
    rand = randflaechen(tets)

    # Randgruppen: 1 = Konvektion (alle uebrigen Aussenflaechen), 2.. = feste Temperaturen
    flaechen = spec.get('flaechen', [])
    gruppe = np.ones(len(rand[0]), int)
    for i, fl in enumerate(flaechen):
        tid, fnr = auswahl(fl['wo'], knoten, tets, koerper, namen, rand)
        sel = set(zip(tid.tolist(), fnr.tolist()))
        gruppe[[k for k, tf in enumerate(zip(rand[0].tolist(), rand[1].tolist())) if tf in sel]] = i + 2
    n_fest = len(flaechen)
    A, nrm, _ = _randgeometrie(knoten, tets, rand)
    konv = gruppe == 1

    # Strahlung (Himmelsanteil) und Sonne (sichtbare Projektion) -> Konvektionsflaechen in Gruppen teilen
    eps_F, q_s, info = np.zeros(len(gruppe)), np.zeros(len(gruppe)), {}
    # Himmelsanteil immer bestimmen (nur Auswertung fuer W5: Innenflaechen geschlossener Hohlraeume), Rechnung bleibt
    sicht = _Sicht(knoten, rand[2], A, nrm)
    F = sicht.himmel()
    if opt['strahlung'] is not None or opt['sonne'] is not None:
        if opt['strahlung'] is not None:
            eps, eps_q = _emission(opt['strahlung'], mats)
            eps_F[konv] = eps * F[konv]
            a_k = A[konv].sum()
            info['strahlung'] = {'emission': eps, 'quelle': eps_q, 'himmel_anteil_mittel': round(
                float((F[konv] * A[konv]).sum() / a_k), 3) if a_k else 0.0,
                'A_strahlend_mm2': round(float((F[konv] * A[konv]).sum()), 1)}
            if (F[konv] < 0.05).any():
                hinweise.append(f'{round(float(A[konv][F[konv] < 0.05].sum()))} mm2 Innenflaechen ohne Sicht nach '
                                'aussen strahlen nicht (konservativ); Innenluft mit "innenluft" abbilden')
        if opt['sonne'] is not None:
            so = opt['sonne']
            d = np.asarray(so.get('richtung', [0, 0, -1]), float)
            d = d / np.linalg.norm(d)
            alpha = float(so.get('absorption', 0.6))
            G = float(so.get('G_W_m2', 1000.0))
            frac, c = sicht.anteil(d)
            q = alpha * G * frac * np.clip(c, 0, None)          # W/m2 je Flaeche (sichtbarer Anteil der Projektion)
            q_s[konv] = q[konv]
            info['sonne'] = {'G_W_m2': G, 'absorption': alpha, 'richtung': d.round(4).tolist(),
                             'A_proj_mm2': round(float((frac * np.clip(c, 0, None) * A)[konv].sum()), 1),
                             'P_W': round(float((q_s * A).sum() * 1e-6), 4)}
    rb = _gruppen_teilen(gruppe, konv, eps_F, q_s, A, n_fest)
    _elmer_netz(arbeit, knoten, tets, koerper, rand, gruppe)

    standard = {'h_W_m2K': 8.0, 'T_umgebung_C': 25.0}
    kv = spec.get('konvektion', standard)
    T_inf = kv.get('T_umgebung_C', 25.0)
    h = kv.get('h_W_m2K', 5.0 if opt['auto'] else 8.0)
    kelvin = any(e > 0 for _, e, _ in rb)
    hoehe = np.ptp(knoten[np.unique(tets[np.array(mats)[koerper] != LUFT])], axis=0)
    L_mm = float((kv.get('L_mm') if opt['auto'] else None) or hoehe[2] or hoehe.max())
    k_luft = luft['k_W_mK'] if luft else None
    tets_luft = np.unique(tets[koerper == luft['index']]) if luft else None
    verlauf = []
    for it in range(1, 9):
        h_lauf, k_lauf = h, k_luft
        z = _waerme_sif(spec_n, namen, mats, vol, h, T_inf, flaechen, rb, k_luft, kelvin)
        T, loads = _elmer_lauf(arbeit, z, len(knoten))
        Tf = T[rand[2]].mean(1)
        a_k = A[konv].sum()
        dT = float(((Tf[konv] - T_inf) * A[konv]).sum() / a_k) if a_k else 0.0
        schritt = {'lauf': it, 'h_W_m2K': round(float(h), 4), 'dT_mittel_K': round(dT, 3)}
        h_neu, k_neu = h, k_luft
        if opt['auto']:
            h_k = h_frei(dT, L_mm * 1e-3)
            schritt['h_korrelation_W_m2K'] = round(h_k, 4)
            if abs(h_k - h) > 0.01 * h:
                h_neu = h ** 0.2 * h_k ** 0.8
        if luft:
            schritt['k_luft_W_mK'] = round(k_luft, 5)
            k = _k_innenluft(luft, float(T[tets_luft].mean()) + K0)
            if abs(k - k_luft) > 0.01 * k_luft:
                k_neu = k
        verlauf.append(schritt)
        if h_neu == h and k_neu == k_luft:
            break
        h, k_luft = h_neu, k_neu
    else:
        hinweise.append('Fixpunkt (h bzw. k_Luft) nach 8 Laeufen nicht auf 1 % konvergiert')
    h, k_luft = h_lauf, k_lauf                       # Werte des letzten Laufs (zu T passend)

    tmax = float(T.max())
    erg = {'fall': fall, 'loeser': 'Elmer HeatSolver, stationaer', 'knoten': len(knoten), 'tetraeder': len(tets),
           'koerper': namen, 'T_max_C': round(tmax, 2), 'T_min_C': round(float(T.min()), 2),
           'T_max_je_koerper_C': {n: round(float(T[np.unique(tets[koerper == k])].max()), 2)
                                  for k, n in enumerate(namen)}}
    stoffe = sorted({m for m in mats if m in DRUCKSTOFFE})
    abst = {m: round(MATERIAL[m]['glasuebergang_C'] - max(T[np.unique(tets[np.array(mats)[koerper] == m])].max(), 0), 1)
            for m in stoffe}
    erg['bewertung'] = {'abstand_zum_glasuebergang_K': abst, 'ok': all(v >= 20 for v in abst.values()),
                        'hinweis': '>= 20 K Abstand zur Glasuebergangstemperatur gefordert'}

    # --- Zusatzdaten fuer die Katalog-Pruefungen (mb2/pruefungen/waerme.py), aendern die Rechnung nicht
    rbd = {'h_W_m2K': round(float(h), 4), 'T_umgebung_C': T_inf, 'kelvin': kelvin}
    if opt['auto']:
        rbd['konvektion_auto'] = {'L_mm': round(L_mm, 2), 'verlauf': verlauf,
                                  'quelle': 'W1: OCW 3.185 §5.4, 4.42J Gl. 3.13'}
    rbd.update(info)
    if luft:
        T_l = T[tets_luft]
        luft['k_W_mK'] = round(k_luft, 5)
        luft['T_mittel_C'] = round(float(T_l.mean()), 2)
        luft['dT_K'] = round(float(T_l.max() - T_l.min()), 2)
        luft['Ra_spalt'] = round(_rayleigh(luft['dT_K'], luft['spalt_mm'] * 1e-3, float(T_l.mean()) + K0), 1)
        luft['verlauf'] = [s.get('k_luft_W_mK') for s in verlauf]
        luft['quelle'] = 'W5: OCW 4.42J Gl. 3.15, 16.050 §9.3'
        rbd['innenluft'] = luft
    erg['randbedingungen'] = rbd
    erg['flaechen_mm2'] = {'konvektion': round(float(A[konv].sum()), 1), 'fest': round(float(A[~konv].sum()), 1),
                           'konvektion_ohne_sicht_nach_aussen': round(float(A[konv & (F < 0.05)].sum()), 1),
                           'konvektion_himmel_anteil_mittel': round(float((F * A)[konv].sum() / A[konv].sum()), 3)
                           if konv.any() else None}
    fest_kn = np.unique(tets[np.array(mats)[koerper] != LUFT])
    erg['geometrie'] = {'bbox_mm': np.ptp(knoten[fest_kn], axis=0).round(3).tolist(),
                        'bbox_min_mm': knoten[fest_kn].min(0).round(3).tolist()}
    erg['T_mittel_konvektion_C'] = round(float(T_inf + verlauf[-1]['dT_mittel_K']), 3)
    erg['koerper_info'] = _koerper_info(knoten, tets, koerper, namen, mats, spec_n, T, rand, konv, A)
    erg['energiebilanz'] = _energiebilanz(T, loads, rand, gruppe, A, rb, h, T_inf, n_fest, erg['koerper_info'],
                                          spec_n, vol)
    if hinweise:
        erg['hinweise'] = hinweise

    png = os.path.join(pdir, 'fem', f'{fall}.png')
    from . import render
    render.feld_png(knoten, rand[2], T, png, f'{fall}: Temperatur (°C)', 'T [°C]')
    erg['bild'] = png
    erg['rechenzeit_s'] = round(time.time() - t0, 1)
    json.dump(erg, open(os.path.join(pdir, 'fem', fall + '.erg.json'), 'w', encoding='utf-8'), indent=1,
              ensure_ascii=False)
    return erg


def _waerme_sif(spec, namen, mats, vol, h, T_inf, flaechen, rb, k_luft, kelvin):
    """Elmer-Eingabe. Ohne Strahlung/Sonne/Innenluft Zeile fuer Zeile wie bisher (plus 'Calculate Loads')."""
    t = (lambda v: v + K0) if kelvin else (lambda v: v)
    z = ['Header', '  Mesh DB "." "netz"', 'End', 'Simulation', '  Max Output Level = 3',
         '  Coordinate System = Cartesian', '  Coordinate Scaling = 0.001', '  Simulation Type = Steady state',
         '  Steady State Max Iterations = 1', '  Output Intervals = 1', 'End']
    if kelvin:
        z += ['Constants', f'  Stefan Boltzmann = {SIGMA}', 'End']
    for k in range(len(namen)):
        if mats[k] == LUFT:
            m = {'waermeleitung_W_mK': round(k_luft, 6), 'dichte_kg_m3': 1.2}
        else:
            m = MATERIAL[mats[k]]
        z += [f'Body {k + 1}', '  Equation = 1', f'  Material = {k + 1}', '  Initial Condition = 1']
        if spec['koerper'][k].get('waerme_W'):
            z.append(f'  Body Force = {k + 1}')
        z += ['End', f'Material {k + 1}', f'  Heat Conductivity = {m["waermeleitung_W_mK"]}',
              f'  Density = {m["dichte_kg_m3"]}', 'End']
        if spec['koerper'][k].get('waerme_W'):
            masse = vol[k] * 1e-9 * m['dichte_kg_m3']
            z += [f'Body Force {k + 1}', f'  Heat Source = {spec["koerper"][k]["waerme_W"] / masse:.9g}', 'End']
    z += ['Initial Condition 1', f'  Temperature = {t(T_inf)}', 'End',
          'Equation 1', '  Active Solvers(1) = 1', 'End',
          'Solver 1', '  Equation = Heat Equation', '  Procedure = "HeatSolve" "HeatSolver"', '  Variable = Temperature',
          '  Linear System Solver = Iterative', '  Linear System Iterative Method = BiCGStab',
          '  Linear System Preconditioning = ILU0', '  Linear System Max Iterations = 2000',
          '  Linear System Convergence Tolerance = 1.0e-10', '  Steady State Convergence Tolerance = 1.0e-6',
          '  Calculate Loads = True']
    if kelvin:
        z += ['  Nonlinear System Max Iterations = 60', '  Nonlinear System Convergence Tolerance = 1.0e-9',
              '  Nonlinear System Newton After Iterations = 3', '  Nonlinear System Newton After Tolerance = 1.0e-3']
    z += ['End',
          'Solver 2', '  Exec Solver = After Simulation', '  Equation = "Ausgabe"',
          '  Procedure = "ResultOutputSolve" "ResultOutputSolver"', '  Output File Name = "erg"',
          '  Vtu Format = True', '  Ascii Output = True', '  Single Precision = False', 'End']
    for g, e, q in rb:
        if g != 1:
            continue
        z += _rb_zeilen(1, h, t(T_inf), e, q)
    for i, fl in enumerate(flaechen):
        z += [f'Boundary Condition {i + 2}', f'  Target Boundaries(1) = {i + 2}',
              f'  Temperature = {t(fl["temperatur_C"])}', 'End']
    for g, e, q in rb:
        if g != 1:
            z += _rb_zeilen(g, h, t(T_inf), e, q)
    return z


def _rb_zeilen(g, h, T_ext, e, q):
    z = [f'Boundary Condition {g}', f'  Target Boundaries(1) = {g}', f'  Heat Transfer Coefficient = {h}',
         f'  External Temperature = {T_ext}']
    if e > 0:
        z += ['  Radiation = Idealized', f'  Emissivity = {e:.6g}']
    if q > 0:
        z += ['  Heat Flux BC = True', f'  Heat Flux = {q:.9g}']
    return z + ['End']


def _elmer_lauf(arbeit, z, n):
    """sif schreiben, ElmerSolver starten, Temperatur (C) und Knotenlasten (W, Calculate Loads) lesen."""
    open(os.path.join(arbeit, 'fall.sif'), 'w').write('\n'.join(z) + '\n')
    open(os.path.join(arbeit, 'ELMERSOLVER_STARTINFO'), 'w').write('fall.sif\n1\n')
    for f in os.listdir(os.path.join(arbeit, 'netz')):
        if f.endswith('.vtu'):
            os.remove(os.path.join(arbeit, 'netz', f))
    p = subprocess.run([werkzeuge.elmer_solver(), 'fall.sif'], cwd=arbeit,
                       capture_output=True, text=True, timeout=7200, env=werkzeuge.elmer_env(),
                       stdin=subprocess.DEVNULL)
    vtus = sorted(f for f in os.listdir(os.path.join(arbeit, 'netz')) if f.endswith('.vtu'))
    if p.returncode or not vtus:
        raise RuntimeError('Elmer: ' + (p.stdout + p.stderr)[-1500:])
    pfad = os.path.join(arbeit, 'netz', vtus[-1])
    T = _lies_vtu_temperatur(pfad, n)
    loads = _lies_vtu_feld(pfad, 'temperature loads', n)
    if any('Stefan Boltzmann' in s for s in z):
        T = T - K0
    return T, loads


def _randgeometrie(knoten, tets, rand):
    """Je Randflaeche: Flaeche (mm2), Normale nach aussen (Einheitsvektor), Mittelpunkt."""
    tid, fnr, f = rand
    P = knoten[f]
    n = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
    A = 0.5 * np.linalg.norm(n, axis=1)
    n = n / np.maximum(2 * A, 1e-300)[:, None]
    gegen_lokal = 6 - np.array([sum(fl) for fl in TET_FLAECHEN])[fnr]      # 4. Ecke = 0+1+2+3 - Flaechenecken
    gegen = tets[tid, gegen_lokal]
    innen = np.einsum('ij,ij->i', n, knoten[gegen] - P[:, 0]) > 0
    n[innen] *= -1
    return A, n, P.mean(1)


# 26 Blickrichtungen (Wuerfel-Ecken, -Kanten, -Flaechen) fuer den Himmelsanteil
_RICHTUNGEN = np.array([(i, j, k) for i in (-1, 0, 1) for j in (-1, 0, 1) for k in (-1, 0, 1) if (i, j, k) != (0, 0, 0)],
                       float)
_RICHTUNGEN /= np.linalg.norm(_RICHTUNGEN, axis=1)[:, None]


class _Sicht:
    """Orthografische Sichtbarkeit der Randflaechen (Z-Puffer auf Stichproben). Ein Mechanismus fuer Sonne
    (Abschattung) und Strahlung (Himmelsanteil F je Flaeche)."""

    def __init__(self, knoten, fl, A, nrm, zelle=None, je_zelle=6, max_proben=1_500_000):
        self.A, self.n, self.F = A, nrm, len(A)
        P = knoten[fl]
        ausd = float(np.ptp(knoten, axis=0).max())
        self.zelle = zelle or float(np.clip(ausd / 150, 0.3, 1.5))
        dichte = je_zelle / self.zelle ** 2
        anz = np.maximum(2, np.ceil(A * dichte)).astype(int)
        if anz.sum() > max_proben:
            anz = np.maximum(2, np.ceil(anz * max_proben / anz.sum())).astype(int)
        rng = np.random.default_rng(1)
        self.besitz = np.repeat(np.arange(self.F), anz)
        r1, r2 = rng.random(len(self.besitz)), rng.random(len(self.besitz))
        um = r1 + r2 > 1
        r1[um], r2[um] = 1 - r1[um], 1 - r2[um]
        Q = P[self.besitz]
        self.p = Q[:, 0] + r1[:, None] * (Q[:, 1] - Q[:, 0]) + r2[:, None] * (Q[:, 2] - Q[:, 0])
        self.anz = anz

    def anteil(self, d):
        """Blick (bzw. Licht) laeuft in Richtung d. Rueckgabe: sichtbarer Flaechenanteil je Flaeche, cos = -n·d."""
        d = np.asarray(d, float) / np.linalg.norm(d)
        c = -(self.n @ d)
        zu = c > 1e-9
        sel = zu[self.besitz]
        p, o = self.p[sel], self.besitz[sel]
        a = np.array([1.0, 0, 0]) if abs(d[0]) < 0.9 else np.array([0, 1.0, 0])
        u = np.cross(d, a)
        u /= np.linalg.norm(u)
        v = np.cross(d, u)
        iu = np.floor(p @ u / self.zelle).astype(np.int64)
        iv = np.floor(p @ v / self.zelle).astype(np.int64)
        key = (iu - iu.min()) * (iv.max() - iv.min() + 1) + (iv - iv.min())
        tiefe = -(p @ d)
        _, inv = np.unique(key, return_inverse=True)
        mx = np.full(inv.max() + 1 if len(inv) else 0, -np.inf)
        np.maximum.at(mx, inv, tiefe)
        # Toleranz: eigene Neigung der Flaeche in der Zelle (sonst verdeckt sich eine schraege Flaeche selbst)
        tan = np.sqrt(np.clip(1 - c ** 2, 0, None)) / np.maximum(c, 1e-6)
        tol = self.zelle * (1.0 + 1.5 * np.minimum(tan, 4.0))
        sicht = tiefe >= mx[inv] - tol[o]
        frac = np.bincount(o, weights=sicht.astype(float), minlength=self.F) / np.maximum(self.anz, 1)
        frac[~zu] = 0.0
        return frac, c

    def himmel(self):
        """Himmelsanteil F: cos-gewichtetes Mittel der Sichtbarkeit ueber die 26 Richtungen der Halbkugel."""
        num, den = np.zeros(self.F), np.zeros(self.F)
        for d in _RICHTUNGEN:
            frac, c = self.anteil(d)
            c = np.clip(c, 0, None)
            num += frac * c
            den += c
        return np.where(den > 0, num / np.maximum(den, 1e-12), 0.0)


def _emission(st, mats):
    """Emissionsgrad: Lastfall-Wert, sonst Kennwert des ersten Druckstoffs, sonst 0,9 (OCW-Katalog W2)."""
    if st.get('emission') is not None:
        return float(st['emission']), 'Lastfall'
    from . import kennwerte
    for m in mats:
        if m in DRUCKSTOFFE and kennwerte.wert(m, 'emission') is not None:
            return float(kennwerte.wert(m, 'emission')), f'kennwerte {m}: {kennwerte.quelle(m, "emission")}'
    return 0.9, 'Standard 0,9 (OCW 4.42J/16.050, Katalog W2)'


def _gruppen_teilen(gruppe, konv, eps_F, q_s, A, n_fest):
    """Konvektionsflaechen nach effektiver Emission (Stufe 0,05) und Sonnenfluss (10 Stufen) in Randgruppen teilen.
    Gruppenwert = flaechengewichtetes Mittel -> Summe ε·F·A und q·A bleiben exakt. Rueckgabe [(gruppe, ε, q)]."""
    if not (eps_F[konv] > 0).any() and not (q_s[konv] > 0).any():
        return [(1, 0.0, 0.0)]
    ie = np.round(eps_F / 0.05).astype(int)
    qm = q_s[konv].max() if konv.any() else 0.0
    iq = np.round(q_s / qm * 10).astype(int) if qm > 0 else np.zeros(len(q_s), int)
    idx = np.where(konv)[0]
    schl = sorted({(int(ie[i]), int(iq[i])) for i in idx})
    rb = []
    for j, (a, b) in enumerate(schl):
        m = idx[(ie[idx] == a) & (iq[idx] == b)]
        g = 1 if j == 0 else n_fest + 1 + j
        gruppe[m] = g
        w = A[m].sum()
        rb.append((g, float((eps_F[m] * A[m]).sum() / w), float((q_s[m] * A[m]).sum() / w)))
    return rb


def _bbox_koerper(pdir, spec):
    """Bounding Box aller Koerper (mm), ohne zu vernetzen."""
    import gmsh
    gmsh.initialize()
    try:
        gmsh.option.setNumber('General.Terminal', 0)
        gmsh.option.setString('Geometry.OCCTargetUnit', 'MM')
        occ = gmsh.model.occ
        for k in spec['koerper']:
            if 'step' in k:
                occ.importShapes(k['step'] if os.path.isabs(k['step']) else os.path.join(pdir, k['step']))
            elif 'zylinder' in k:
                occ.addCylinder(*k['zylinder'])
            elif 'box' in k:
                x0, y0, z0, x1, y1, z1 = k['box']
                occ.addBox(x0, y0, z0, x1 - x0, y1 - y0, z1 - z0)
        occ.synchronize()
        b = np.array(gmsh.model.getBoundingBox(-1, -1), float)
    finally:
        gmsh.finalize()
    return b


def _mit_innenluft(pdir, spec, il, hinweise):
    """Lastfall um den Luftkoerper erweitern (zuletzt genannt -> bekommt nur, was frei ist)."""
    if not spec.get('verbinden', True):
        hinweise.append('innenluft braucht "verbinden": true - nicht abgebildet')
        return spec, None
    box = np.asarray(il['box'], float) if il.get('box') else _bbox_koerper(pdir, spec)
    s = dict(spec)
    s['koerper'] = list(spec['koerper']) + [{'box': box.tolist(), 'material': LUFT, 'name': 'innenluft'}]
    return s, box


def _innenluft_netz(knoten, tets, koerper, namen, vol, mats, il, box, hinweise):
    """Ohne vorgegebene box: Luftteile mit Kontakt zum Box-Rand (Aussenluft) entfernen. Spalt δ = 2V/A."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    ia = len(namen) - 1
    behalten = np.ones(len(tets), bool)
    lt = np.where(koerper == ia)[0]
    if not il.get('box') and len(lt):
        fl = np.concatenate([np.sort(tets[lt][:, list(f)], axis=1) for f in TET_FLAECHEN])
        tid = np.tile(np.arange(len(lt)), 4)
        _, inv = np.unique(fl, axis=0, return_inverse=True)
        inv = inv.ravel()
        o = np.argsort(inv, kind='stable')
        gleich = inv[o][1:] == inv[o][:-1]
        a, b = tid[o][:-1][gleich], tid[o][1:][gleich]
        g = coo_matrix((np.ones(len(a)), (a, b)), shape=(len(lt), len(lt)))
        _, lab = connected_components(g, directed=False)
        tol = 1e-3
        am_rand = np.any((np.abs(knoten - box[:3]) < tol) | (np.abs(knoten - box[3:]) < tol), axis=1)
        rand_lab = np.unique(lab[am_rand[tets[lt]].any(1)])
        weg = np.isin(lab, rand_lab)
        behalten[lt[weg]] = False
        if weg.all():
            hinweise.append('innenluft: kein geschlossener Hohlraum gefunden (Oeffnungen?) - "innenluft.box" angeben; '
                            'Rechnung ohne Innenluft')
    if not behalten.all():
        tets, koerper = tets[behalten], koerper[behalten]
        used = np.unique(tets)
        remap = np.full(len(knoten), -1)
        remap[used] = np.arange(len(used))
        knoten, tets = knoten[used], remap[tets]
    lt = np.where(koerper == ia)[0]
    if not len(lt):
        if il.get('box'):
            hinweise.append('innenluft: box liegt vollstaendig in Koerpern - Rechnung ohne Innenluft')
        return knoten, tets, koerper, namen[:-1], vol[:-1], mats[:-1], None
    V = _tet_volumen(knoten, tets[lt]).sum()
    fl = np.concatenate([tets[lt][:, list(f)] for f in TET_FLAECHEN])
    key = np.sort(fl, axis=1)
    _, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    # benetzte Flaeche: Luft-Randflaechen, die an einem festen Koerper liegen (offene Luftflaechen zaehlen nicht)
    alle = np.sort(np.concatenate([tets[:, list(f)] for f in TET_FLAECHEN]), axis=1)
    _, inv_a, cnt_a = np.unique(np.concatenate([key, alle]), axis=0, return_inverse=True, return_counts=True)
    innen_global = cnt_a[inv_a.ravel()[:len(key)]] == 3            # 1x in key + 2x global = an Festkoerper
    au = fl[(cnt[inv.ravel()] == 1) & innen_global]
    if not len(au):
        au = fl[cnt[inv.ravel()] == 1]
    P = knoten[au]
    A_l = 0.5 * np.linalg.norm(np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]), axis=1).sum()
    vol = vol.copy()
    vol[ia] = V
    delta = float(il.get('spalt_mm') or 2 * V / A_l)
    if il.get('strahlung', True):
        e = il.get('emission') or [0.9, 0.9]
        e1, e2 = (float(e), float(e)) if np.isscalar(e) else (float(e[0]), float(e[1]))
        eps_eff = 1.0 / (1.0 / e1 + 1.0 / e2 - 1.0)
    else:
        eps_eff = 0.0
    luft = {'index': ia, 'V_mm3': round(float(V), 1), 'A_mm2': round(float(A_l), 1), 'spalt_mm': round(delta, 3),
            'spalt_quelle': 'Lastfall' if il.get('spalt_mm') else '2V/A', 'eps_eff': round(eps_eff, 4), 'Nu': 1.0}
    luft['k_W_mK'] = _k_innenluft(luft, None)
    if delta > 10:
        hinweise.append(f'innenluft: Spalt {delta:.1f} mm > 10 mm - Nu = 1 unterschaetzt den Uebergang (konservativ)')
    return knoten, tets, koerper, namen, vol, mats, luft


def _k_innenluft(luft, T_m_K, T_start_K=None):
    """W5: Ersatzleitfaehigkeit der Luftschicht k = k_Luft·Nu + 4·ε_eff·σ·T_m³·δ (Strahlung als Leiter, h_r·δ)."""
    if T_m_K is None:
        T_m_K = T_start_K or (25.0 + K0)
    return K_LUFT * luft['Nu'] + 4 * luft['eps_eff'] * SIGMA * T_m_K ** 3 * luft['spalt_mm'] * 1e-3


def _rayleigh(dT, L_m, T_film_K, nu=1.589e-5, a=2.25e-5, g=9.81):
    """Ra = g·β·ΔT·L³/(ν·α), Luft 300 K (Stoffwerte Incropera Tab. A.4), β = 1/T_film."""
    return g * (1.0 / T_film_K) * max(dT, 0.0) * L_m ** 3 / (nu * a)


def _tet_volumen(knoten, t):
    e = t[:, :4]
    return np.abs(np.einsum('ij,ij->i', np.cross(knoten[e[:, 1]] - knoten[e[:, 0]], knoten[e[:, 2]] - knoten[e[:, 0]]),
                            knoten[e[:, 3]] - knoten[e[:, 0]])) / 6.0


def _koerper_info(knoten, tets, koerper, namen, mats, spec, T, rand, konv, A):
    """Je Koerper: Material, Netzvolumen, Box, Leistung, Temperaturen, freie Flaeche, Kontaktflaechen zu anderen."""
    fl = np.concatenate([tets[:, list(f)] for f in TET_FLAECHEN])
    tid = np.tile(np.arange(len(tets)), 4)
    key = np.sort(fl, axis=1)
    _, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    inv = inv.ravel()
    o = np.argsort(inv, kind='stable')
    gleich = inv[o][1:] == inv[o][:-1]
    ta, tb = tid[o][:-1][gleich], tid[o][1:][gleich]
    fa = fl[o][:-1][gleich]
    verschieden = koerper[ta] != koerper[tb]
    P = knoten[fa[verschieden]]
    a_k = 0.5 * np.linalg.norm(np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]), axis=1)
    ka, kb = koerper[ta][verschieden], koerper[tb][verschieden]
    V = _tet_volumen(knoten, tets)
    rk = koerper[rand[0]]
    info = {}
    for k, n in enumerate(namen):
        el = koerper == k
        kn = np.unique(tets[el])
        kontakt = {}
        for j, m in enumerate(namen):
            if j != k:
                s = float(a_k[((ka == k) & (kb == j)) | ((ka == j) & (kb == k))].sum())
                if s > 0:
                    kontakt[m] = round(s, 2)
        info[n] = {'material': mats[k], 'volumen_mm3': round(float(V[el].sum()), 2),
                   'bbox_mm': np.ptp(knoten[kn], axis=0).round(3).tolist(),
                   'waerme_W': float(spec['koerper'][k].get('waerme_W') or 0.0),
                   'T_max_C': round(float(T[kn].max()), 3), 'T_min_C': round(float(T[kn].min()), 3),
                   'T_mittel_C': round(float(T[kn].mean()), 3),
                   'A_konvektion_mm2': round(float(A[konv & (rk == k)].sum()), 2),
                   'A_fest_mm2': round(float(A[~konv & (rk == k)].sum()), 2),
                   'kontakt_mm2': kontakt}
    return info


def _energiebilanz(T, loads, rand, gruppe, A, rb, h, T_inf, n_fest, kinfo, spec, vol):
    """W3: Σ Quellen (+ Sonne) = ∫h(T-T∞)dA + ∫εσ(T⁴-T∞⁴)dA + Waerme an festen Temperaturen (Elmer-Knotenlasten).
    Konvektion/Strahlung/Sonne als FE-Knotenlasten ∫(..)φ_i dA = A/12·(2f_i + f_j + f_k), nur an freien Knoten:
    an Knoten mit fester Temperatur steckt der Randfluss schon in Elmers Knotenlast (Calculate Loads, Bulk-Matrix).
    So schliesst die Bilanz bis auf Loeser- und Volumenfehler; falsche Vorzeichen/Einheiten fielen auf."""
    fest = (gruppe >= 2) & (gruppe <= n_fest + 1)
    kn_fest = np.unique(rand[2][fest])
    frei = np.ones(len(T), bool)
    frei[kn_fest] = False
    Am = A * 1e-6
    ecke = rand[2]
    w_frei = frei[ecke]

    def knotenlast(f, m):                                   # f: (F,3) Werte an den Ecken
        c = Am[m, None] / 12.0 * (f[m].sum(1)[:, None] + f[m])
        return float((c * w_frei[m]).sum())

    th = T[ecke] - T_inf
    rad = (T[ecke] + K0) ** 4 - (T_inf + K0) ** 4
    eins = np.ones_like(th)
    Qk = Qs = Qq = 0.0
    for g, e, q in rb:
        m = gruppe == g
        Qk += h * knotenlast(th, m)
        if e > 0:
            Qs += e * SIGMA * knotenlast(rad, m)
        if q > 0:
            Qq += q * knotenlast(eins, m)
    Qf = float(-loads[kn_fest].sum()) if len(kn_fest) else 0.0
    P_nenn = float(sum(k.get('waerme_W') or 0.0 for k in spec['koerper']))
    # Elmer verteilt waerme_W auf das CAD-Volumen -> eingespeist wird waerme_W · V_Netz / V_CAD
    P_netz = float(sum((k.get('waerme_W') or 0.0) * kinfo[n]['volumen_mm3'] / vol[i]
                       for i, (k, n) in enumerate(zip(spec['koerper'], kinfo)) if k.get('waerme_W')))
    ein = P_netz + Qq
    aus = Qk + Qs + Qf
    return {'P_nenn_W': round(P_nenn, 6), 'P_netz_W': round(P_netz, 6), 'Q_sonne_W': round(Qq, 6),
            'Q_konvektion_W': round(Qk, 6), 'Q_strahlung_W': round(Qs, 6), 'Q_feste_temperatur_W': round(Qf, 6),
            'Q_aus_W': round(aus, 6),
            'abweichung': round((aus - ein) / ein, 6) if abs(ein) > 1e-12 else None,
            'quelle': 'W3: OCW 2.092 L11'}


def _elmer_netz(arbeit, knoten, tets, koerper, rand, gruppe):
    """Elmer-Netz direkt schreiben (mesh.header/nodes/elements/boundary) - Knotenreihenfolge bleibt wie bei uns."""
    d = os.path.join(arbeit, 'netz')
    os.makedirs(d, exist_ok=True)
    tid, _, f = rand
    with open(os.path.join(d, 'mesh.header'), 'w') as h:
        h.write(f'{len(knoten)} {len(tets)} {len(tid)}\n2\n504 {len(tets)}\n303 {len(tid)}\n')
    with open(os.path.join(d, 'mesh.nodes'), 'w') as h:
        h.writelines(f'{i + 1} -1 {x:.9g} {y:.9g} {z:.9g}\n' for i, (x, y, z) in enumerate(knoten))
    with open(os.path.join(d, 'mesh.elements'), 'w') as h:
        h.writelines(f'{e + 1} {koerper[e] + 1} 504 {" ".join(str(int(n) + 1) for n in tets[e, :4])}\n'
                     for e in range(len(tets)))
    with open(os.path.join(d, 'mesh.boundary'), 'w') as h:
        h.writelines(f'{k + 1} {gruppe[k]} {tid[k] + 1} 0 303 {" ".join(str(int(n) + 1) for n in f[k])}\n'
                     for k in range(len(tid)))


def _lies_vtu_feld(pfad, name, n):
    """Knotenfeld aus der Elmer-.vtu (ASCII). Fehlt es, Nullen (z. B. 'temperature loads' bei alten Laeufen)."""
    txt = open(pfad, encoding='utf-8', errors='replace').read()
    i = txt.lower().find(f'name="{name}"')
    if i < 0:
        return np.zeros(n)
    a = txt.find('>', i) + 1
    v = np.array(txt[a:txt.find('</DataArray>', a)].split(), float)
    if len(v) != n:
        raise RuntimeError(f'Elmer-Feld {name}: {len(v)} Werte statt {n}')
    return v


def _lies_vtu_temperatur(pfad, n):
    txt = open(pfad, encoding='utf-8', errors='replace').read()
    i = txt.find('Name="temperature"')
    if i < 0:
        i = txt.lower().find('name="temperature"')
    a = txt.find('>', i) + 1
    b = txt.find('</DataArray>', a)
    T = np.array(txt[a:b].split(), float)
    if len(T) != n:
        raise RuntimeError(f'Elmer-Ergebnis hat {len(T)} Werte statt {n}')
    return T
