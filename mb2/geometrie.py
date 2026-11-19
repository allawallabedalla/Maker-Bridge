"""Geometrie-Merkmale aus out/<teil>.step fuer die analytischen Pruefungen (OCW_PRUEFKATALOG.md, M5/M6/M12).

Alles in mm, Koordinaten des Teil-Skripts (wie STEP und FEM-Lastfaelle). Nur lesen, nichts schreiben.

- ``baurichtung(drehung)``  Schichtnormale (Druck-Z) im Teil-Koordinatensystem aus der Druckdrehung von cad.py
- ``innenkanten(teil)``     scharfe konkave Kanten (Innenecken ohne Rundung) mit oertlicher Wanddicke t
- ``kehlen(teil)``          konkave Rundungen (Zylinder-Teilflaechen) mit Radius rho und oertlicher Wanddicke t
- ``bohrungen(teil)``       volle konkave Zylinder (Bohrungen) mit Durchmesser, Achse, Tiefe
- ``rippen(teil)``          duenne Platten (zwei gegenueberliegende Ebenen, Abstand t) mit freiem Rand: h, t, a, freie Enden

Grenzen (ehrlich): nur ebene Rippen und zylindrische Kehlen/Bohrungen; Torus-/Freiformkehlen werden nicht erkannt.
Die oertliche Wanddicke kommt aus einem Strahl 0,5 mm neben der Kante senkrecht in die Nachbarflaeche.
"""
import math

import numpy as np

T_MAX_RIPPE = 5.0      # mm, dicker gilt nicht als Rippe/Steg
SCHRITT = 0.5          # mm, Abstand des Wanddicken-Strahls von der Kante
KONKAV_MIN = 0.17      # sin(~10 Grad): flachere Knicke zaehlen nicht als Innenecke


def lade(pfad):
    from build123d import import_step
    return import_step(pfad)


def baurichtung(drehung):
    """Druck-Z (Schichtnormale) im Teil-Koordinatensystem. cad.auf_bett dreht das Teil mit Rotation(*drehung);
    die Druck-Z-Achse ist im Teil also R^-1 * e_z."""
    from build123d import Rotation, Vertex
    if not any(drehung):
        return np.array([0.0, 0.0, 1.0])
    p = (Rotation(*drehung).inverse() * Vertex(0, 0, 1)).center()
    v = np.array([p.X, p.Y, p.Z])
    return v / np.linalg.norm(v)


# ---------------------------------------------------------------- Grundwerkzeuge

class _Topo:
    """Flaechen, Kanten und Nachbarschaft (Kante -> Flaechen) eines Koerpers, dazu ein Strahl-Schnitt."""

    def __init__(self, teil):
        from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
        self.teil = teil
        self.faces = list(teil.faces())             # Index 0..n-1
        self._kanten = {}                            # Edge (Hash = IsSame) -> [Flaechen-Index]
        for j, f in enumerate(self.faces):
            for e in f.edges():
                lst = self._kanten.setdefault(e, [])
                if j not in lst:
                    lst.append(j)
        self.si = IntCurvesFace_ShapeIntersector()
        self.si.Load(teil.wrapped, 1e-6)
        self._nach = None

    @property
    def n_faces(self):
        return len(self.faces)

    def kanten(self):
        """[(kante (OCP), [flaechen-index ...])] - jede Kante einmal."""
        return [(e.wrapped, fl) for e, fl in self._kanten.items()]

    def nachbarn(self):
        """Flaechen-Index -> {Nachbar-Index: [Kanten]}"""
        if self._nach is None:
            n = {}
            for e, fl in self.kanten():
                for a in fl:
                    for b in fl:
                        if a != b:
                            n.setdefault(a, {}).setdefault(b, []).append(e)
            self._nach = n
        return self._nach

    def face(self, j):
        return self.faces[j]

    def normale(self, j, p):
        """Aussennormale der Flaeche j am Punkt p (Projektion auf die Flaeche, Orientierung beachtet)."""
        from build123d import Vector
        n = self.face(j).normal_at(Vector(*p))
        return np.array([n.X, n.Y, n.Z])

    def abstand(self, j, p):
        from OCP.BRepExtrema import BRepExtrema_DistShapeShape
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
        from OCP.gp import gp_Pnt
        v = BRepBuilderAPI_MakeVertex(gp_Pnt(*map(float, p))).Vertex()
        d = BRepExtrema_DistShapeShape(v, self.faces[j].wrapped)
        return d.Value() if d.IsDone() else 1e9

    def innen(self, p):
        """Liegt p im Material?"""
        from OCP.BRepClass3d import BRepClass3d_SolidClassifier
        from OCP.gp import gp_Pnt
        from OCP.TopAbs import TopAbs_IN
        c = BRepClass3d_SolidClassifier(self.teil.wrapped, gp_Pnt(*map(float, p)), 1e-6)
        return c.State() == TopAbs_IN

    def strahl(self, p, d):
        """Abstand von p entlang d bis zum naechsten Flaechentreffer (oder None)."""
        from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
        d = np.asarray(d, float) / np.linalg.norm(d)
        s = np.asarray(p, float) + d * 1e-3
        self.si.Perform(gp_Lin(gp_Pnt(*s), gp_Dir(*d)), 0.0, 1e6)
        w = [self.si.WParameter(i) + 1e-3 for i in range(1, self.si.NbPnt() + 1)]
        w = [x for x in w if x > 2e-3]
        return min(w) if w else None

    def dicke_neben(self, j, p, weg):
        """Wanddicke der Flaeche j: Punkt p + SCHRITT*weg (muss auf j liegen), Strahl nach innen (-Normale)."""
        for s in (SCHRITT, 0.2):
            q = np.asarray(p) + s * np.asarray(weg)
            if self.abstand(j, q) > 1e-3:
                continue
            n = self.normale(j, q)
            return self.strahl(q, -n)
        return None


def _kanten_mitte(e):
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    c = BRepAdaptor_Curve(e)
    u = 0.5 * (c.FirstParameter() + c.LastParameter())
    p, v = c.Value(u), c.DN(u, 1)
    t = np.array([v.X(), v.Y(), v.Z()])
    nt = np.linalg.norm(t)
    return np.array([p.X(), p.Y(), p.Z()]), (t / nt if nt > 1e-12 else None)


def _kanten_laenge(e):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    g = GProp_GProps()
    BRepGProp.LinearProperties_s(e, g)
    return g.Mass()


def _in_flaeche(topo, j, p, t, n):
    """Richtung in der Flaeche j weg von der Kante (senkrecht zur Kante)."""
    c = np.cross(t, n)
    c /= np.linalg.norm(c)
    for s in (SCHRITT, 0.2, 0.05):
        if topo.abstand(j, p + s * c) < 1e-3:
            return c
        if topo.abstand(j, p - s * c) < 1e-3:
            return -c
    return None


# ---------------------------------------------------------------- Innenkanten und Kehlen (M6)

def innenkanten(teil, topo=None):
    """Scharfe konkave Kanten. Je Kante: Punkt, Laenge, Knickwinkel, oertliche Wanddicke t (min. der beiden Seiten)."""
    topo = topo or _Topo(teil)
    out = []
    for e, fl in topo.kanten():
        if len(fl) != 2:
            continue
        p, t = _kanten_mitte(e)
        if t is None:
            continue
        a, b = fl
        try:
            na, nb = topo.normale(a, p), topo.normale(b, p)
        except Exception:  # noqa: BLE001 - Normale an Singularitaeten
            continue
        da = _in_flaeche(topo, a, p, t, na)
        db = _in_flaeche(topo, b, p, t, nb)
        if da is None or db is None:
            continue
        # konkav: die Nachbarflaeche b "schaut" in die Richtung, in die Flaeche a weiterlaeuft
        if float(nb @ da) <= KONKAV_MIN or float(na @ db) <= KONKAV_MIN:
            continue
        knick = math.degrees(math.acos(max(-1.0, min(1.0, float(na @ nb)))))
        ta, tb = topo.dicke_neben(a, p, da), topo.dicke_neben(b, p, db)
        dicken = [x for x in (ta, tb) if x is not None]
        out.append({'punkt': [round(float(x), 2) for x in p], 'laenge_mm': round(_kanten_laenge(e), 2),
                    'knick_grad': round(knick, 1), 't_mm': round(min(dicken), 3) if dicken else None})
    return out


def _zylinder(f):
    """(radius, achsenpunkt, achsenrichtung, umfangswinkel_rad, hoehe) fuer Zylinderflaechen, sonst None."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepTools import BRepTools
    from OCP.GeomAbs import GeomAbs_Cylinder
    s = BRepAdaptor_Surface(f.wrapped)
    if s.GetType() != GeomAbs_Cylinder:
        return None
    cyl = s.Cylinder()
    ax = cyl.Axis()
    o, d = ax.Location(), ax.Direction()
    umin, umax, vmin, vmax = BRepTools.UVBounds_s(f.wrapped)
    return (cyl.Radius(), np.array([o.X(), o.Y(), o.Z()]), np.array([d.X(), d.Y(), d.Z()]), umax - umin,
            vmax - vmin)


def _konkav_zylinder(topo, j):
    """Zylinderflaeche j, deren Aussennormale zur Achse zeigt (Material aussen herum: Kehle oder Bohrung)."""
    f = topo.face(j)
    z = _zylinder(f)
    if z is None:
        return None
    r, o, d, span, hoehe = z
    c = f.center()
    p = np.array([c.X, c.Y, c.Z])
    try:
        from build123d import Vector
        pos = f.position_at(0.5, 0.5)
        p = np.array([pos.X, pos.Y, pos.Z])
    except Exception:  # noqa: BLE001
        pass
    radial = (p - o) - ((p - o) @ d) * d
    if np.linalg.norm(radial) < 1e-9:
        return None
    n = topo.normale(j, p)
    if float(n @ radial) >= 0:
        return None                                # konvex (Welle, Dom aussen)
    return {'r': r, 'o': o, 'd': d, 'span': span, 'hoehe': hoehe, 'p': p}


def _gruppen_zylinder(topo):
    """Konkave Zylinderflaechen nach (Achse, Radius) gruppieren: voller Umfang = Bohrung, sonst Kehle."""
    gruppen = []
    for j in range(topo.n_faces):
        k = _konkav_zylinder(topo, j)
        if k is None:
            continue
        for g in gruppen:
            h = g[0][1]
            if (abs(h['r'] - k['r']) < 1e-4 and abs(abs(float(h['d'] @ k['d'])) - 1) < 1e-6
                    and np.linalg.norm(np.cross(k['o'] - h['o'], h['d'])) < 1e-4):
                g.append((j, k))
                break
        else:
            gruppen.append([(j, k)])
    return gruppen


def kehlen(teil, topo=None):
    """Konkave Rundungen (Zylinder-Teilflaechen, Umfang < 300 Grad). t = min. Dicke der tangential anschliessenden
    Flaechen (die beiden Wandteile, die die Kehle verbindet)."""
    topo = topo or _Topo(teil)
    out = []
    for g in _gruppen_zylinder(topo):
        if sum(k['span'] for _, k in g) >= math.radians(300):
            continue                                 # Bohrung
        for j, k in g:
            dicken = []
            for nb, kanten in topo.nachbarn().get(j, {}).items():
                for e in kanten:
                    p, t = _kanten_mitte(e)
                    if t is None or abs(float(t @ k['d'])) < 0.99:
                        continue                     # nur Kanten laengs der Kehle (die Tangentenkanten)
                    try:
                        n1, n2 = topo.normale(j, p), topo.normale(nb, p)
                    except Exception:  # noqa: BLE001
                        continue
                    if float(n1 @ n2) < 0.98:
                        continue                     # nicht tangential -> keine Wand der Kehle
                    weg = _in_flaeche(topo, nb, p, t, n2)
                    if weg is None:
                        continue
                    dd = topo.dicke_neben(nb, p, weg)
                    if dd is not None:
                        dicken.append(dd)
            out.append({'punkt': [round(float(x), 2) for x in k['p']], 'rho_mm': round(k['r'], 3),
                        'umfang_grad': round(math.degrees(k['span']), 1), 'laenge_mm': round(k['hoehe'], 2),
                        't_mm': round(min(dicken), 3) if dicken else None})
    return out


def bohrungen(teil, topo=None):
    """Volle konkave Zylinder: Durchmesser, Achse, Mitte, Tiefe (Summe der Flaechenhoehen entlang der Achse)."""
    topo = topo or _Topo(teil)
    out = []
    for g in _gruppen_zylinder(topo):
        if sum(k['span'] for _, k in g) < math.radians(300):
            continue
        k = g[0][1]
        # Tiefe: Ausdehnung der Flaechen entlang der Achse
        werte = []
        for j, _ in g:
            bb = topo.face(j).bounding_box()
            for x in (bb.min.X, bb.max.X):
                for y in (bb.min.Y, bb.max.Y):
                    for z in (bb.min.Z, bb.max.Z):
                        werte.append(float(np.array([x, y, z]) @ k['d']))
        out.append({'d_mm': round(2 * k['r'], 3), 'achse': [round(float(x), 4) for x in k['d']],
                    'mitte': [round(float(x), 2) for x in k['p']], 'tiefe_mm': round(max(werte) - min(werte), 2)})
    return out


# ---------------------------------------------------------------- Rippen (M5)

def _ebene(topo, j):
    from build123d import GeomType
    f = topo.face(j)
    if f.geom_type != GeomType.PLANE:
        return None
    c = f.center()
    p = np.array([c.X, c.Y, c.Z])
    n = f.normal_at()
    return {'n': np.array([n.X, n.Y, n.Z]), 'p': p,
            'v': np.array([[v.X, v.Y, v.Z] for v in f.vertices()]) if f.vertices() else p[None, :]}


def _gegenkappe(topo, pk, m, h, n, t, s=0.2):
    """Ist die Platte auch am Ende gegenueber der Kappe (Abstand h) frei? Dann ist sie eine frei liegende
    Platte/ein Steg und keine Rippe. Geprueft mit Punkten im Material-Klassifikator: hinter dem Ende (in -m) und
    seitlich neben dem Ende (+-n) muss ueberall Luft sein. Liegt dort Material, ist das Ende die Wurzel.
    Geometrisch statt ueber Nachbarschaft, weil Flaechen oft geteilt oder mit Nachbarn verschmolzen sind."""
    q = np.asarray(pk) - h * m
    q_in = q + min(s, 0.25 * h) * m
    proben = [q - s * m, q_in + (0.5 * t + s) * n, q_in - (0.5 * t + s) * n]
    return not any(topo.innen(p) for p in proben)


def rippen(teil, topo=None, t_max=T_MAX_RIPPE):
    """Duenne ebene Platten mit freiem Rand ("Rippen").
    Kappe C = ebene Flaeche, deren zwei Nachbarn A, B gegenueberliegende Ebenen im Abstand t <= t_max sind.
    h = Ausdehnung von A bzw. B von der Kappe weg (das groessere - konservativ), a = Laenge laengs der Kappe
    (das kleinere), freie Enden = Kappen-artige Flaechen an A und B quer zur Laenge. Liegt auch gegenueber der
    Kappe eine Kappe, ist es eine frei liegende Platte (Deckel) und keine Rippe -> nicht gemeldet."""
    topo = topo or _Topo(teil)
    nach = topo.nachbarn()
    ebenen = {}

    def eb(j):
        if j not in ebenen:
            try:
                ebenen[j] = _ebene(topo, j)
            except Exception:  # noqa: BLE001
                ebenen[j] = None
        return ebenen[j]

    best = {}
    for c in range(topo.n_faces):
        ec = eb(c)
        if ec is None:
            continue
        m = ec['n']
        senk = [j for j in nach.get(c, {}) if eb(j) is not None and abs(float(eb(j)['n'] @ m)) < 0.05]
        for i, a in enumerate(senk):
            for b in senk[i + 1:]:
                ea, eb_ = eb(a), eb(b)
                if float(ea['n'] @ eb_['n']) > -0.995:
                    continue
                t = float((ea['p'] - eb_['p']) @ ea['n'])
                if not 0.2 < t <= t_max:
                    continue                          # Material zwischen A und B, duenn
                # A und B muessen sich gegenueberliegen (Ueberlappung quer zur Kappe), sonst nur Stufe/Absatz
                ra, rb = ea['v'] @ m, eb_['v'] @ m
                if min(ra.max(), rb.max()) - max(ra.min(), rb.min()) < 0.5 * t:
                    continue
                h = max(float(np.max((ec['p'] - ea['v']) @ m)), float(np.max((ec['p'] - eb_['v']) @ m)))
                w = np.cross(ea['n'], m)
                w /= np.linalg.norm(w)
                # Punkt mitten auf dem Kappenstreifen (Mitte der Kante C|A, um t/2 nach innen)
                pk = _kanten_mitte(nach[c][a][0])[0] - 0.5 * t * ea['n']
                if _gegenkappe(topo, pk, m, h, ea['n'], t):
                    continue                          # frei liegende Platte (Kappe auch gegenueber), keine Rippe
                d_frei = topo.strahl(pk, m)
                if d_frei is not None and d_frei < h:
                    continue                          # Ausschnitt/Schlitz in einer Wand: dahinter geht das Material weiter
                la = float(np.ptp(ea['v'] @ w))
                lb = float(np.ptp(eb_['v'] @ w))
                laenge = min(la, lb)
                enden = [j for j in set(nach.get(a, {})) & set(nach.get(b, {}))
                         if j != c and eb(j) is not None and abs(float(eb(j)['n'] @ w)) > 0.95]
                if h <= 1e-6 or laenge <= 1e-6:
                    continue
                # Mehrere Kappen an derselben Platte (oben UND an einem Ende): gestuetzt nur an zwei Raendern -
                # die schlankste Deutung gilt (konservativ).
                key = tuple(sorted((a, b)))
                r = {'h_mm': round(h, 3), 't_mm': round(t, 3), 'a_mm': round(laenge, 3), 'freie_enden': len(enden),
                     'kappe': [round(float(x), 2) for x in pk], 'normale_kappe': [round(float(x), 3) for x in m],
                     'ebene_normale': [round(float(x), 3) for x in ea['n']]}
                alt = best.get(key)
                if alt is None or r['h_mm'] / r['t_mm'] > alt['h_mm'] / alt['t_mm']:
                    best[key] = r
    # gleiche Rippe aus mehreren koplanaren Flaechenstuecken nur einmal
    eindeutig = {}
    for r in best.values():
        g = (r['t_mm'], round(r['h_mm'], 1), round(r['a_mm'], 1), tuple(np.round(r['kappe'], 1)),
             tuple(np.round(np.abs(r['ebene_normale']), 2)))
        eindeutig.setdefault(g, r)
    return list(eindeutig.values())


def merkmale(pfad):
    """Alle Merkmale eines STEP auf einmal (eine Topologie-Analyse)."""
    teil = lade(pfad)
    topo = _Topo(teil)
    return {'innenkanten': innenkanten(teil, topo), 'kehlen': kehlen(teil, topo), 'bohrungen': bohrungen(teil, topo),
            'rippen': rippen(teil, topo)}
