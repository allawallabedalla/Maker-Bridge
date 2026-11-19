"""CAD mit build123d: Teil-Skript ausfuehren, pruefen, STEP/3MF/PNG schreiben, Druckplatte legen.

Ein Teil-Skript (projects/<p>/cad/<teil>.py) ist normales build123d-Python und setzt am Ende:
    teil          Part/Solid - der Koerper (Pflicht)
    platzhalter   {"Name": Part, ...} - Bauteile, die nicht kollidieren duerfen (optional)
    druck         Drehung fuer den Druck, z. B. (180, 0, 0) - Grad um X, Y, Z (optional)
    schnitt       Schnittebene fuers Renderbild, z. B. ('Y', 0.0) (optional; Standard: Teilmitte, Normale = mittlere
                  Achse der Bounding Box). Bild: Blender-Iso + Draufsicht + Schnitt, sonst matplotlib.
Sollwerte stehen in cad/soll.json: {"<teil>": {"volumen_mm3": .., "bbox_mm": [x, y, z], "ausnahmen": {..}}}
"""
import json
import math
import os
import runpy

from build123d import Compound, Face, Location, Mesher, Rotation, Vector, export_step, import_step

WAND_MIN = 1.8      # mm, Nutzerregel
SPALT_MIN = 0.4     # mm, Duesenbreite
RASTER = 1.0        # mm, Abstand der Messpunkte
MAX_PUNKTE = 40000
BETT = (250.0, 210.0)


# ---------------------------------------------------------------- Teil bauen

def _lade_skript(pfad):
    ns = runpy.run_path(pfad, run_name='__teil__')
    if 'teil' not in ns:
        raise RuntimeError(f'{pfad}: setzt keine Variable "teil"')
    teil = ns['teil']
    teil = getattr(teil, 'part', teil)            # BuildPart -> Part
    ph = {k: getattr(v, 'part', v) for k, v in (ns.get('platzhalter') or {}).items()}
    _lade_skript.schnitt = ns.get('schnitt')        # optional fuers Renderbild, siehe Modulkopf
    _lade_skript.quellen = dict(ns.get('quellen') or {})
    return teil, ph, tuple(ns.get('druck') or (0, 0, 0))


# Regel des Nutzers (11.11.2026): Entwerfen darf mit vorlaeufigen Massen, GEDRUCKT wird nur mit validen CAD-Daten.
# Jeder Platzhalter (Kaufteil) braucht im Skript eine Quelle:  quellen = {"Name": "<art>:<beleg>"}
#   step:<pfad>         Hersteller-STEP (Pfad relativ zum Projekt oder absolut, muss existieren)
#   zeichnung:<beleg>   offizielle Massszeichnung/Datenblatt (URL oder Datei + Seite)
#   gemessen:<wer/wann> vom Nutzer gemessen (z. B. "gemessen:Nutzer 11.11.2026 Messschieber")
#   eigen:<teil>        eigenes Druckteil/Platine aus diesem Projekt (z. B. electronics/board.step)
#   norm:<norm>         Normteil mit Normmassen (z. B. "norm:DIN 912 M3x30")
#   freiraum:<zweck>    kein Bauteil, sondern ein Konstruktions-Freiraum (z. B. "freiraum:3 mm Luft ueber Verstaerker")
# Fehlt der Eintrag oder steht "geschaetzt…", gilt der Platzhalter als ungeprueft -> audit-Mangel, slice "NICHT drucken".
QUELL_ARTEN = ('step', 'zeichnung', 'gemessen', 'eigen', 'norm', 'freiraum')


def quellen_pruefen(projekt_dir, platzhalter_namen, quellen):
    """-> (quellen je Platzhalter, Liste ungepruefter Platzhalter mit Grund)."""
    erg, offen = {}, []
    for n in platzhalter_namen:
        q = (quellen or {}).get(n)
        if not q and n.startswith('Einsetzweg_'):     # abgeleiteter Koerper erbt die Quelle seines Bauteils
            q = (quellen or {}).get(n[len('Einsetzweg_'):])
        erg[n] = q
        if not q:
            offen.append(f'{n}: keine Quelle')
            continue
        art, _, beleg = str(q).partition(':')
        art = art.strip().lower()
        if art not in QUELL_ARTEN or not beleg.strip():
            offen.append(f'{n}: {q}')
        elif art in ('step', 'eigen') and beleg.strip().lower().endswith(('.step', '.stp')):
            p = beleg.strip()
            if not os.path.isabs(p):
                p = os.path.join(projekt_dir, p)
            if not os.path.exists(p):
                offen.append(f'{n}: STEP fehlt ({beleg.strip()})')
    return erg, offen


def build(projekt_dir, teil_name):
    """Skript ausfuehren, alle Pruefungen, STEP + 3MF + PNG schreiben. Gibt den Pruefbericht zurueck."""
    skript = os.path.join(projekt_dir, 'cad', teil_name + '.py')
    out = os.path.join(projekt_dir, 'out')
    os.makedirs(out, exist_ok=True)
    teil, ph, druck = _lade_skript(skript)
    soll = {}
    soll_pfad = os.path.join(projekt_dir, 'cad', 'soll.json')
    if os.path.exists(soll_pfad):
        soll = json.load(open(soll_pfad, encoding='utf-8')).get(teil_name, {})

    bericht = {'teil': teil_name, **pruefen(teil, ph, soll)}
    bericht['quellen'], bericht['ungeprueft'] = quellen_pruefen(projekt_dir, list(ph), _lade_skript.quellen)
    if bericht['ungeprueft']:
        bericht.setdefault('warnungen', []).append(
            'Platzhalter ohne valide CAD-Quelle (Entwurf ok, vor dem Druck noetig): ' + '; '.join(bericht['ungeprueft']))
    step = os.path.join(out, teil_name + '.step')
    export_step(teil, step)
    druckteil = auf_bett(teil, druck)
    m3f = os.path.join(out, teil_name + '.3mf')
    _export_3mf(druckteil, m3f)
    from . import render
    png = os.path.join(out, teil_name + '.png')
    render.teil_png(teil, png, platzhalter=ph, titel=teil_name, markierungen=bericht.get('_markierungen'),
                    schnitt=getattr(_lade_skript, 'schnitt', None))
    bericht.pop('_markierungen', None)
    bericht['dateien'] = {'step': step, '3mf': m3f, 'png': png}
    bericht['druck_drehung'] = list(druck)
    json.dump(bericht, open(os.path.join(out, teil_name + '.pruefung.json'), 'w', encoding='utf-8'),
              indent=1, ensure_ascii=False)
    return bericht


def _export_3mf(shape, pfad):
    m = Mesher()
    m.add_shape(shape, linear_deflection=0.01, angular_deflection=0.2)
    m.write(pfad)


def auf_bett(teil, drehung=(0, 0, 0)):
    """Fuer den Druck drehen und mit der Unterseite auf Z=0 legen, Mitte bei X=Y=0."""
    s =Rotation(*drehung) * teil if any(drehung) else teil
    bb = s.bounding_box()
    return Location((-(bb.min.X + bb.max.X) / 2, -(bb.min.Y + bb.max.Y) / 2, -bb.min.Z)) * s


# ---------------------------------------------------------------- Pruefungen

def pruefen(teil, platzhalter=None, soll=None):
    soll = soll or {}
    fehler, warn = [], []
    solids = teil.solids()
    bb = teil.bounding_box()
    r = {'gueltig': bool(teil.is_valid), 'solids': len(solids), 'volumen_mm3': round(teil.volume, 2),
         'bbox_mm': [round(bb.size.X, 3), round(bb.size.Y, 3), round(bb.size.Z, 3)],
         'bbox_min_mm': [round(bb.min.X, 3), round(bb.min.Y, 3), round(bb.min.Z, 3)]}
    if not r['gueltig']:
        fehler.append('Koerper ungueltig (BRepCheck)')
    if len(solids) != 1:
        fehler.append(f'{len(solids)} Koerper statt 1 (lose Teile oder nichts gebaut)')
    if teil.volume <= 0:
        fehler.append('Volumen <= 0')

    # Soll-Vergleich
    if 'volumen_mm3' in soll:
        tol = soll.get('volumen_tol', 0.02)
        dv = teil.volume / soll['volumen_mm3'] - 1
        r['volumen_abweichung'] = round(dv, 4)
        if abs(dv) > tol:
            fehler.append(f'Volumen {teil.volume:.0f} mm3 weicht {dv:+.1%} vom Soll {soll["volumen_mm3"]} ab')
    if 'bbox_mm' in soll:
        tol = soll.get('bbox_tol', 0.1)
        for ach, ist, sl in zip('XYZ', r['bbox_mm'], soll['bbox_mm']):
            if abs(ist - sl) > tol:
                fehler.append(f'Bounding Box {ach}: {ist} mm statt {sl} mm')

    # Kollisionen
    kol = {}
    for name, p in (platzhalter or {}).items():
        try:
            v = (teil & p).volume
        except Exception:  # noqa: BLE001 - leerer Schnitt wirft je nach OCCT-Version
            v = 0.0
        kol[name] = round(v, 4)
        if v > 1e-3:
            fehler.append(f'Kollision mit {name}: {v:.3f} mm3')
    r['kollision_mm3'] = kol

    # Wandstaerke + Spalte
    ausn = soll.get('ausnahmen', {})
    wand_min = ausn.get('wand_min', WAND_MIN)
    spalt_min = ausn.get('spalt_min', SPALT_MIN)
    dicke = wand_und_spalt(teil)
    r['wand_min_mm'] = dicke['wand_min']
    r['spalt_min_mm'] = dicke['spalt_min']
    r['messpunkte'] = dicke['punkte']
    duenn = [p for p in dicke['wand'] if p[3] < wand_min - 1e-3]
    eng = [p for p in dicke['spalt'] if p[3] < spalt_min - 1e-3]
    if duenn:
        fehler.append(f'{len(duenn)} Stellen mit Wand < {wand_min} mm, duennste {min(p[3] for p in duenn):.2f} mm '
                      f'bei {_fmt(min(duenn, key=lambda p: p[3]))}')
    if eng:
        fehler.append(f'{len(eng)} Stellen mit Spalt < {spalt_min} mm, engster {min(p[3] for p in eng):.2f} mm '
                      f'bei {_fmt(min(eng, key=lambda p: p[3]))}')
    if ausn:
        warn.append(f'Ausnahmen aus soll.json aktiv: {ausn}')
    r['fehler'], r['warnungen'] = fehler, warn
    r['ok'] = not fehler
    r['_markierungen'] = [p[:3] for p in duenn + eng][:400]
    return r


def _fmt(p):
    return f'({p[0]:.1f}, {p[1]:.1f}, {p[2]:.1f})'


def wand_und_spalt(teil, raster=RASTER):
    """Strahl-Test auf einem Punktraster ueber alle Flaechen.
    Wand: von jedem Punkt nach innen (-Normale) bis zur Gegenseite. Spalt: nach aussen (+Normale) bis zur
    naechsten eigenen Flaeche. Gezaehlt wird nur, wenn die getroffene Flaeche gegenueber liegt (Normalen
    parallel bzw. antiparallel, < 30 Grad) - so erzeugen Ecken, Rundungen und Fasen keine falschen Treffer."""
    from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
    from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector

    si = IntCurvesFace_ShapeIntersector()
    si.Load(teil.wrapped, 1e-6)
    faces = teil.faces()
    flaeche = sum(f.area for f in faces)
    r = max(raster, math.sqrt(flaeche / MAX_PUNKTE))
    cos_gegen = math.cos(math.radians(30))
    wand, spalt, n_pkt = [], [], 0

    def treffer(p, d):
        si.Perform(gp_Lin(gp_Pnt(*(p + d * 1e-3)), gp_Dir(*d)), 0.0, 1e6)
        best = None
        for i in range(1, si.NbPnt() + 1):
            w = si.WParameter(i) + 1e-3
            if w > 2e-3 and (best is None or w < best[0]):
                best = (w, i)
        if best is None:
            return None
        w, i = best
        hp = si.Pnt(i)
        try:
            hn = Face(si.Face(i)).normal_at(Vector(hp.X(), hp.Y(), hp.Z()))
        except Exception:  # noqa: BLE001 - Normale an Singularitaeten
            return None
        return w, (hn.X, hn.Y, hn.Z)

    netz = len(faces) > 2000                 # Dreiecksnetz (3MF): kleine Flaechen nach Flaeche anteilig abtasten
    rest = 0.0
    for f in faces:
        if netz and f.area < 4 * r * r:
            rest += f.area / (r * r)
            if rest < 1.0:
                continue
            rest -= 1.0
            c = f.center()
            try:
                n = f.normal_at(c)
            except Exception:  # noqa: BLE001
                continue
            n_pkt += 1
            p, nn = (c.X, c.Y, c.Z), (n.X, n.Y, n.Z)
            for richtung, liste in (((-nn[0], -nn[1], -nn[2]), wand), (nn, spalt)):
                t = treffer(_v(p), _v(richtung))
                if t is None:
                    continue
                w, hn = t
                dot = hn[0] * richtung[0] + hn[1] * richtung[1] + hn[2] * richtung[2]
                if (dot if liste is wand else -dot) < cos_gegen or (liste is spalt and w > 5.0):
                    continue
                liste.append((p[0], p[1], p[2], round(w, 3)))
            continue
        nu = max(2, min(200, round(math.sqrt(f.area) / r) + 1))
        for iu in range(nu):
            for iv in range(nu):
                u, v = (iu + 0.5) / nu, (iv + 0.5) / nu
                try:
                    pos = f.position_at(u, v)
                    n = f.normal_at(u, v)
                except Exception:  # noqa: BLE001
                    continue
                if not _auf_flaeche(f, pos):
                    continue          # Parameterpunkt liegt in einem Ausschnitt der Flaeche
                n_pkt += 1
                p = (pos.X, pos.Y, pos.Z)
                nn = (n.X, n.Y, n.Z)
                for richtung, liste in (((-nn[0], -nn[1], -nn[2]), wand), (nn, spalt)):
                    t = treffer(_v(p), _v(richtung))
                    if t is None:
                        continue
                    w, hn = t
                    # Gegenflaeche: beim Austritt aus dem Material (Wand) zeigt ihre Normale in Strahlrichtung,
                    # beim Eintritt (Spalt) gegen den Strahl
                    dot = hn[0] * richtung[0] + hn[1] * richtung[1] + hn[2] * richtung[2]
                    if (dot if liste is wand else -dot) < cos_gegen:
                        continue
                    if liste is spalt and w > 5.0:
                        continue
                    liste.append((p[0], p[1], p[2], round(w, 3)))
    return {'punkte': n_pkt, 'wand': wand, 'spalt': spalt,
            'wand_min': round(min((p[3] for p in wand), default=float('nan')), 3),
            'spalt_min': round(min((p[3] for p in spalt), default=float('nan')), 3) if spalt else None}


def _v(t):
    import numpy as np
    return np.array(t, float)


def _auf_flaeche(f, pos):
    """Liegt der Punkt wirklich auf der (getrimmten) Flaeche? Parameterraster deckt auch Loecher ab."""
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.BRep import BRep_Tool
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.gp import gp_Pnt, gp_Pnt2d
    from OCP.TopAbs import TopAbs_IN, TopAbs_ON
    srf = BRep_Tool.Surface_s(f.wrapped)
    pr = GeomAPI_ProjectPointOnSurf(gp_Pnt(pos.X, pos.Y, pos.Z), srf)
    if pr.NbPoints() == 0:
        return False
    u, v = pr.LowerDistanceParameters()
    st = BRepClass_FaceClassifier(f.wrapped, gp_Pnt2d(u, v), 1e-6).State()
    return st in (TopAbs_IN, TopAbs_ON)


# ---------------------------------------------------------------- Fremde Netze (3MF) pruefen

def lies_3mf(pfad):
    """3MF (z. B. Fusion-Export) -> [(name, Solid)] - Dreiecke zu einem geschlossenen OCCT-Koerper vernaeht.
    Eigener Leser, weil lib3mf an Fusions Materialangaben scheitert."""
    import xml.etree.ElementTree as ET
    import zipfile

    from build123d import Solid
    from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeSolid,
                                    BRepBuilderAPI_Sewing)
    from OCP.gp import gp_Pnt
    from OCP.ShapeFix import ShapeFix_Solid
    from OCP.TopAbs import TopAbs_SHELL
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    with zipfile.ZipFile(pfad) as z:
        root = ET.fromstring(z.read(next(n for n in z.namelist() if n.endswith('.model'))))
    ns = {'m': root.tag[1:].split('}')[0]}
    faktor = {'micron': 0.001, 'millimeter': 1.0, 'centimeter': 10.0, 'meter': 1000.0,
              'inch': 25.4}[root.get('unit', 'millimeter')]
    out = []
    for obj in root.iter(f'{{{ns["m"]}}}object'):
        mesh = obj.find('m:mesh', ns)
        if mesh is None:
            continue
        v = [(float(e.get('x')) * faktor, float(e.get('y')) * faktor, float(e.get('z')) * faktor)
             for e in mesh.find('m:vertices', ns)]
        naht = BRepBuilderAPI_Sewing(1e-4)
        for t in mesh.find('m:triangles', ns):
            a, b, c = (v[int(t.get(k))] for k in ('v1', 'v2', 'v3'))
            poly = BRepBuilderAPI_MakePolygon(gp_Pnt(*a), gp_Pnt(*b), gp_Pnt(*c), True)
            if poly.IsDone():
                f = BRepBuilderAPI_MakeFace(poly.Wire(), True)
                if f.IsDone():
                    naht.Add(f.Face())
        naht.Perform()
        ex = TopExp_Explorer(naht.SewedShape(), TopAbs_SHELL)
        solid = BRepBuilderAPI_MakeSolid(TopoDS.Shell(ex.Current())).Solid()
        fix = ShapeFix_Solid(solid)
        fix.Perform()
        out.append((obj.get('name') or obj.get('id'), Solid(fix.Solid())))
    return out


def pruefe_3mf(pfad, ziel_dir, wand_min=WAND_MIN, spalt_min=SPALT_MIN):
    """Jedes Objekt einer 3MF-Druckplatte pruefen (gueltig, Masse, Wand, Spalt) + ein PNG je Objekt."""
    from . import render
    os.makedirs(ziel_dir, exist_ok=True)
    erg = {}
    for name, s in lies_3mf(pfad):
        r = pruefen(s, soll={'ausnahmen': {'wand_min': wand_min, 'spalt_min': spalt_min}})
        r['warnungen'] = [w for w in r['warnungen'] if not w.startswith('Ausnahmen')]
        png = os.path.join(ziel_dir, name + '.png')
        render.teil_png(s, png, titel=name, markierungen=r.pop('_markierungen', None))
        r['png'] = png
        erg[name] = r
    return erg


# ---------------------------------------------------------------- Druckplatte

def geometrie_hash(step_pfad, drehung=None):
    """Hash der STEP-Geometrie ohne Kopfzeile FILE_NAME (dort steht nur der Exportzeitpunkt) plus Druckdrehung.
    Gleicher Hash -> gleiches Teil auf dem Bett, auch wenn cad_build die Datei neu geschrieben hat (seit 19.11.2026)."""
    import hashlib
    h = hashlib.sha256()
    with open(step_pfad, 'rb') as f:
        for z in f:
            if not z.startswith(b'FILE_NAME('):
                h.update(z)
    h.update(json.dumps(list(drehung or ())).encode())
    return h.hexdigest()[:16]


def platte(projekt_dir, teile, abstand=10.0):
    """Mehrere geprueften Teile druckfertig (gedreht, Unterseite Z=0) nebeneinander auf EIN 3MF legen.
    Reihen-Packung im Bett 250 x 210, Mitte des Pakets in der Bettmitte."""
    out = os.path.join(projekt_dir, 'out')
    stuecke = []
    for name in teile:
        ber = json.load(open(os.path.join(out, name + '.pruefung.json'), encoding='utf-8'))
        if not ber.get('ok'):
            raise RuntimeError(f'{name}: Pruefung nicht bestanden - erst beheben ({ber.get("fehler")})')
        s = auf_bett(import_step(os.path.join(out, name + '.step')), tuple(ber.get('druck_drehung', (0, 0, 0))))
        stuecke.append((name, s, s.bounding_box()))
    stuecke.sort(key=lambda t: -t[2].size.Y)
    x = y = zeile_h = 0.0
    breite = 0.0
    lage = []
    for name, s, bb in stuecke:
        if x and x + bb.size.X > BETT[0] - 10:
            x, y, zeile_h = 0.0, y + zeile_h + abstand, 0.0
        lage.append((name, s, x - bb.min.X, y - bb.min.Y))
        x += bb.size.X + abstand
        breite = max(breite, x - abstand)
        zeile_h = max(zeile_h, bb.size.Y)
    hoehe = y + zeile_h
    if breite > BETT[0] - 10 or hoehe > BETT[1] - 10:
        raise RuntimeError(f'Passt nicht aufs Bett: {breite:.0f} x {hoehe:.0f} mm (max. {BETT[0] - 10} x {BETT[1] - 10})')
    cx, cy = BETT[0] / 2 - breite / 2, BETT[1] / 2 - hoehe / 2
    gelegt = [Location((cx + dx, cy + dy, 0)) * s for _, s, dx, dy in lage]
    comp = Compound(children=gelegt)
    pfad = os.path.join(projekt_dir, 'print', 'platte.3mf')
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    _export_3mf(comp, pfad)
    # Lage je Teil (Bett-KS vor dem --center des Slicers). Die Objektreihenfolge im G-Code (M486) folgt NICHT der
    # Reihenfolge hier - Zuordnung daher ueber Lage/Groesse (bricklayers.objekt_zuordnung).
    boxen = {}
    for (n, *_), g in zip(lage, gelegt):
        b = g.bounding_box()
        boxen[n] = [round(b.min.X, 2), round(b.min.Y, 2), round(b.min.Z, 2),
                    round(b.max.X, 2), round(b.max.Y, 2), round(b.max.Z, 2)]
    hashes = {}
    for n in teile:
        ber = json.load(open(os.path.join(out, n + '.pruefung.json'), encoding='utf-8'))
        hashes[n] = geometrie_hash(os.path.join(out, n + '.step'), ber.get('druck_drehung'))
    json.dump({'teile': [n for n, *_ in lage], 'bbox_mm': boxen, 'geometrie_hash': hashes},
              open(os.path.join(projekt_dir, 'print', 'platte.json'), 'w', encoding='utf-8'), indent=1)
    from . import render
    png = os.path.join(projekt_dir, 'print', 'platte.png')
    render.platte_png(gelegt, [n for n, *_ in lage], png, BETT)
    bb = comp.bounding_box()
    return {'3mf': pfad, 'png': png, 'teile': [n for n, *_ in lage],
            'paket_mm': [round(breite, 1), round(hoehe, 1)], 'max_hoehe_mm': round(bb.max.Z, 2),
            'bett_min_max': [[round(bb.min.X, 1), round(bb.min.Y, 1)], [round(bb.max.X, 1), round(bb.max.Y, 1)]]}
