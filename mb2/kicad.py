"""KiCad 10: kicad-cli + direktes Lesen/Schreiben der Projektdateien + pcbnew (KiCads Python) fuer Freerouting.
Uebernommen aus maker-bridge/kicad.py, ohne Fusion-Uebergabe und ohne Freerouting-Download."""
import glob
import json
import math
import os
import re
import shutil
import subprocess
import uuid
import zipfile

from . import sexpr
from .sexpr import child, children, num
from .werkzeuge import java_freerouting, kicad_home


def cli_path():
    return os.path.join(kicad_home(), 'bin', 'kicad-cli.exe')


def share_dir():
    return os.path.join(kicad_home(), 'share', 'kicad')


def run_cli(args, timeout=600):
    p = subprocess.run([cli_path(), *args], capture_output=True, text=True, encoding='utf-8',
                       errors='replace', timeout=timeout, stdin=subprocess.DEVNULL)
    return {'returncode': p.returncode, 'stdout': p.stdout[-6000:], 'stderr': p.stderr[-4000:]}


def _uid():
    return str(uuid.uuid4())


# ---------------------------------------------------------------- Projekt anlegen

def new_project(folder, name, width_mm, height_mm, corner_holes=True, hole_inset_mm=3.5):
    """Legt <folder>/<name>.kicad_pro/.kicad_sch/.kicad_pcb an – Platine mit Rechteck-Outline."""
    os.makedirs(folder, exist_ok=True)
    pro = os.path.join(folder, name + '.kicad_pro')
    sch = os.path.join(folder, name + '.kicad_sch')
    pcb = os.path.join(folder, name + '.kicad_pcb')
    for f in (pro, sch, pcb):
        if os.path.exists(f):
            raise RuntimeError('Existiert schon: ' + f)
    shutil.copy(os.path.join(share_dir(), 'template', 'kicad.kicad_pro'), pro)
    with open(sch, 'w', encoding='utf-8') as f:
        f.write('(kicad_sch\n\t(version 20250114)\n\t(generator "eeschema")\n\t(generator_version "9.0")\n'
                f'\t(uuid "{_uid()}")\n\t(paper "A4")\n\t(lib_symbols)\n'
                '\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)\n)\n')

    x0, y0 = 100.0, 100.0
    x1, y1 = x0 + width_mm, y0 + height_mm
    items = [f'\t(gr_rect\n\t\t(start {x0} {y0})\n\t\t(end {x1} {y1})\n'
             f'\t\t(stroke\n\t\t\t(width 0.05)\n\t\t\t(type default)\n\t\t)\n\t\t(fill no)\n'
             f'\t\t(layer "Edge.Cuts")\n\t\t(uuid "{_uid()}")\n\t)\n']
    if corner_holes:
        i = hole_inset_mm
        for n, (hx, hy) in enumerate([(x0 + i, y0 + i), (x1 - i, y0 + i), (x1 - i, y1 - i), (x0 + i, y1 - i)], 1):
            items.append(footprint_block('MountingHole', 'MountingHole_3.2mm_M3', f'H{n}', hx, hy))
    layers = _template_layers()
    with open(pcb, 'w', encoding='utf-8') as f:
        f.write('(kicad_pcb\n\t(version 20241229)\n\t(generator "pcbnew")\n\t(generator_version "9.0")\n'
                '\t(general\n\t\t(thickness 1.6)\n\t\t(legacy_teardrops no)\n\t)\n\t(paper "A4")\n'
                f'{layers}\t(setup\n\t\t(pad_to_mask_clearance 0)\n\t)\n\t(net 0 "")\n'
                + ''.join(items) + ')\n')
    return {'project': pro, 'schematic': sch, 'pcb': pcb,
            'outline_mm': [width_mm, height_mm], 'corner_holes': corner_holes}


def _template_layers():
    """Layer-Block aus einem KiCad-Template übernehmen (garantiert gültiger Stackup)."""
    src = os.path.join(share_dir(), 'template', 'Arduino_Nano', 'Arduino_Nano.kicad_pcb')
    txt = open(src, encoding='utf-8').read()
    m = re.search(r'\n\t\(layers\n.*?\n\t\)\n', txt, re.S)
    return m.group(0)[1:] if m else ''


def footprint_block(lib, fp_name, ref, x, y, rot=0, value=None):
    """Footprint aus der KiCad-Bibliothek als Block für eine .kicad_pcb erzeugen."""
    path = os.path.join(share_dir(), 'footprints', lib + '.pretty', fp_name + '.kicad_mod')
    txt = open(path, encoding='utf-8').read().strip()
    txt = re.sub(r'^\(footprint\s+"[^"]*"', f'(footprint "{lib}:{fp_name}"', txt, count=1)
    txt = re.sub(r'\n\s*\((version|generator|generator_version)\s[^\n]*\)', '', txt)
    at = f'(at {x} {y}' + (f' {rot}' if rot else '') + ')'
    txt = re.sub(r'(\(layer\s+"[FB]\.Cu"\))', r'\1\n\t\t(uuid "%s")\n\t\t%s' % (_uid(), at), txt, count=1)
    txt = txt.replace('"REF**"', f'"{ref}"')
    if value:
        txt = re.sub(r'(\(property\s+"Value"\s+)"[^"]*"', r'\1"%s"' % value, txt, count=1)
    return '\t' + txt.replace('\n', '\n\t') + '\n'


# ---------------------------------------------------------------- Board lesen

def _rot(lx, ly, a_deg):
    a = math.radians(a_deg)
    return lx * math.cos(a) + ly * math.sin(a), -lx * math.sin(a) + ly * math.cos(a)


def _xy(node):
    return (num(node[1]), num(node[2])) if node and len(node) >= 3 else None


def _shape_points(g):
    pts = []
    for key in ('start', 'end', 'mid', 'center'):
        p = child(g, key)
        if p:
            pts.append(_xy(p))
    if sexpr.head(g) in ('gr_circle', 'fp_circle') and child(g, 'center') and child(g, 'end'):
        cx, cy = _xy(child(g, 'center'))
        ex, ey = _xy(child(g, 'end'))
        r = math.hypot(ex - cx, ey - cy)
        pts = [(cx - r, cy - r), (cx + r, cy + r)]
    poly = child(g, 'pts')
    if poly:
        pts += [_xy(p) for p in children(poly, 'xy')]
    return [p for p in pts if p]


def _layer(g):
    l = child(g, 'layer')
    return l[1] if l else None


def board_info(pcb_path):
    """Outline, Dicke, Bohrungen und Bauteile – Koordinaten im lokalen Platinen-Frame:
    Ursprung = linke untere Ecke der Platine, X nach rechts, Y nach oben, mm.
    Das ist derselbe Frame wie im STEP-Export dieser Brücke (kicad_export_step)."""
    tree = sexpr.parse(open(pcb_path, encoding='utf-8').read())
    gen = child(tree, 'general')
    thick = num(child(gen, 'thickness')[1]) if gen and child(gen, 'thickness') else 1.6

    edge_pts = []
    for g in tree[1:]:
        if isinstance(g, list) and str(sexpr.head(g)).startswith('gr_') and _layer(g) == 'Edge.Cuts':
            edge_pts += _shape_points(g)
    fps = children(tree, 'footprint')
    for fp in fps:  # Outline-Anteile in Footprints
        at = child(fp, 'at')
        fx, fy = _xy(at)
        fa = num(at[3]) if len(at) > 3 else 0
        for g in fp[1:]:
            if isinstance(g, list) and str(sexpr.head(g)).startswith('fp_') and _layer(g) == 'Edge.Cuts':
                for lx, ly in _shape_points(g):
                    dx, dy = _rot(lx, ly, fa)
                    edge_pts.append((fx + dx, fy + dy))
    if not edge_pts:
        raise RuntimeError('Keine Edge.Cuts-Kontur gefunden.')
    minx = min(p[0] for p in edge_pts); maxx = max(p[0] for p in edge_pts)
    miny = min(p[1] for p in edge_pts); maxy = max(p[1] for p in edge_pts)
    W, H = maxx - minx, maxy - miny

    def loc(x, y):
        return [round(x - minx, 3), round(maxy - y, 3)]

    parts, holes = [], []
    for fp in fps:
        lib_id = fp[1] if len(fp) > 1 and isinstance(fp[1], str) else ''
        at = child(fp, 'at')
        fx, fy = _xy(at)
        fa = num(at[3]) if len(at) > 3 else 0
        ref = sexpr.prop(fp, 'Reference')
        side = 'bottom' if _layer(fp) == 'B.Cu' else 'top'
        cy_pts = []
        for g in fp[1:]:
            if isinstance(g, list) and _layer(g) in ('F.CrtYd', 'B.CrtYd'):
                for lx, ly in _shape_points(g):
                    dx, dy = _rot(lx, ly, fa)
                    cy_pts.append(loc(fx + dx, fy + dy))
        entry = {'ref': ref, 'value': sexpr.prop(fp, 'Value'), 'footprint': lib_id, 'side': side,
                 'pos': loc(fx, fy), 'rot': fa}
        if cy_pts:
            bx0 = min(p[0] for p in cy_pts); bx1 = max(p[0] for p in cy_pts)
            by0 = min(p[1] for p in cy_pts); by1 = max(p[1] for p in cy_pts)
            entry['courtyard'] = [[round(bx0, 3), round(by0, 3)], [round(bx1, 3), round(by1, 3)]]
            edges = [n for n, d in (('left', bx0), ('right', W - bx1), ('bottom', by0), ('top', H - by1)) if d < 1.5]
            if edges:
                entry['at_board_edge'] = edges
        for pad in children(fp, 'pad'):
            drill = child(pad, 'drill')
            if drill and 'MountingHole' in lib_id:
                pat = child(pad, 'at')
                px, py = _xy(pat)
                dx, dy = _rot(px, py, fa)
                d = num(drill[1]) if num(drill[1]) is not None else num(drill[2])
                holes.append({'ref': ref, 'pos': loc(fx + dx, fy + dy), 'drill_mm': d})
                break
        parts.append(entry)
    return {
        'frame': 'Ursprung linke untere Platinenecke, X rechts, Y oben, Z=0 Platinenunterseite, mm',
        'kicad_origin_for_export': [minx, maxy],
        'board_size_mm': [round(W, 3), round(H, 3)], 'thickness_mm': thick,
        'mounting_holes': holes, 'parts': parts,
    }


# ---------------------------------------------------------------- Checks & Exporte

def _report(kind, path, out):
    r = run_cli(['sch' if kind == 'erc' else 'pcb', kind, '--format', 'json', '--severity-all',
                 '-o', out, path])
    summary = {'returncode': r['returncode']}
    if os.path.exists(out):
        data = json.load(open(out, encoding='utf-8'))
        vios = []
        for sheet in data.get('sheets', [{'violations': data.get('violations', [])}]):
            vios += sheet.get('violations', [])
        vios += data.get('unconnected_items', []) + data.get('schematic_parity', [])
        by = {}
        for v in vios:
            by[v.get('severity', '?')] = by.get(v.get('severity', '?'), 0) + 1
        summary.update({'counts': by, 'report': out,
                        'violations': [{'severity': v.get('severity'), 'type': v.get('type'),
                                        'description': v.get('description'),
                                        'items': [i.get('description') for i in v.get('items', [])][:4]}
                                       for v in vios[:60]]})
    else:
        summary['cli'] = r
    return summary


def erc(sch_path):
    return _report('erc', sch_path, os.path.splitext(sch_path)[0] + '-erc.json')


def drc(pcb_path):
    return _report('drc', pcb_path, os.path.splitext(pcb_path)[0] + '-drc.json')


def export_step(pcb_path, out_path, board_only=False):
    info = board_info(pcb_path)
    ox, oy = info['kicad_origin_for_export']
    args = ['pcb', 'export', 'step', '-f', '--subst-models', '--user-origin', f'{ox}x{oy}mm', '-o', out_path]
    if board_only:
        args.append('--board-only')
    r = run_cli(args + [pcb_path])
    return {'step': out_path, 'ok': os.path.exists(out_path) and r['returncode'] == 0,
            'board_size_mm': info['board_size_mm'], 'thickness_mm': info['thickness_mm'], 'cli': r}


def render(pcb_path, out_png, side='top', iso=False):
    args = ['pcb', 'render', '-o', out_png, '--side', side, '--quality', 'high', '-w', '1400', '-h', '1000']
    if iso:
        args += ['--rotate', '-45,0,45', '--zoom', '0.8']
    r = run_cli(args + [pcb_path])
    return out_png if os.path.exists(out_png) else r


def sch_pdf(sch_path, out_pdf):
    r = run_cli(['sch', 'export', 'pdf', '-o', out_pdf, sch_path])
    return out_pdf if os.path.exists(out_pdf) else r


def export_fab(pcb_path, sch_path, out_dir):
    """Fertigungsdaten: Gerber + Bohrdaten (ZIP), Bestückungsliste, BOM."""
    g = os.path.join(out_dir, 'gerber')
    os.makedirs(g, exist_ok=True)
    res = {'gerbers': run_cli(['pcb', 'export', 'gerbers', '-o', g + os.sep, pcb_path])['returncode'],
           'drill': run_cli(['pcb', 'export', 'drill', '--format', 'excellon', '--generate-map',
                             '--map-format', 'pdf', '-o', g + os.sep, pcb_path])['returncode']}
    pos = os.path.join(out_dir, 'positions.csv')
    res['pos'] = run_cli(['pcb', 'export', 'pos', '--format', 'csv', '--units', 'mm', '--side', 'both',
                          '-o', pos, pcb_path])['returncode']
    if sch_path and os.path.exists(sch_path):
        bom = os.path.join(out_dir, 'bom.csv')
        res['bom'] = run_cli(['sch', 'export', 'bom', '--group-by', 'Value,Footprint',
                              '--fields', 'Reference,Value,Footprint,${QUANTITY},${DNP}',
                              '-o', bom, sch_path])['returncode']
    z = os.path.join(out_dir, os.path.splitext(os.path.basename(pcb_path))[0] + '_gerber.zip')
    with zipfile.ZipFile(z, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in os.listdir(g):
            zf.write(os.path.join(g, f), f)
    res['zip'] = z
    res['files'] = sorted(os.listdir(out_dir))
    return res


# ---------------------------------------------------------------- Katze im Bestückungsdruck
# Auf Wunsch des Nutzers kommt auf jede Platine eine Katze (sitzend, mit Schwanz, Augen, Nase, Schnurrhaaren).
# Einheiten: Höhe 9,6 = Ohrspitzen; Ursprung = Pfote links unten, Y nach oben.
_CAT = [(0, 0), (5.5, 0), (6.3, 0.5), (6.7, 1.5), (6.5, 2.6), (6.0, 2.9), (6.2, 2.2), (6.15, 1.4), (5.8, 0.95),
        (5.0, 0.7), (4.45, 0.85), (4.6, 2.0), (4.25, 4.0), (3.45, 5.2), (3.85, 6.0), (3.95, 7.0), (3.7, 7.9),
        (3.55, 9.6), (2.8, 8.35), (2.2, 8.45), (1.6, 8.35), (0.85, 9.6), (0.7, 7.9), (0.45, 7.0), (0.55, 6.0),
        (0.95, 5.2), (0.15, 4.0), (-0.15, 2.0)]
_CAT_EYES = [(1.45, 6.85), (2.95, 6.85)]
_CAT_NOSE = [(2.05, 6.15), (2.35, 6.15), (2.2, 5.9)]
_CAT_WHISKERS = [((1.7, 6.0), (-0.4, 6.4)), ((1.7, 5.85), (-0.4, 5.6)), ((2.7, 6.0), (4.8, 6.4)),
                 ((2.7, 5.85), (4.8, 5.6))]


def cat_sexpr(x, y, height=5.0, layer='F.SilkS', mirror=False):
    """S-Ausdrücke für die Katze; (x, y) = Pfote links unten in KiCad-Koordinaten (mm, Y nach unten)."""
    k = height / 9.6
    sx = -1 if mirror else 1

    def P(px, py):
        return f'(xy {x + sx * px * k:.4f} {y - py * k:.4f})'
    uids = []

    def u():
        uids.append(_uid())
        return uids[-1]
    w = max(0.15, round(0.03 * height, 3))
    out = [f'\t(gr_poly (pts {" ".join(P(*p) for p in _CAT)}) (stroke (width {w}) (type solid)) (fill no) '
           f'(layer "{layer}") (uuid "{u()}"))']
    for ex, ey in _CAT_EYES:
        r = 0.32 * k
        out.append(f'\t(gr_circle (center {x + sx * ex * k:.4f} {y - ey * k:.4f}) '
                   f'(end {x + sx * ex * k + r:.4f} {y - ey * k:.4f}) (stroke (width {w}) (type solid)) '
                   f'(fill yes) (layer "{layer}") (uuid "{u()}"))')
    out.append(f'\t(gr_poly (pts {" ".join(P(*p) for p in _CAT_NOSE)}) (stroke (width {w}) (type solid)) '
               f'(fill yes) (layer "{layer}") (uuid "{u()}"))')
    for a, c in _CAT_WHISKERS:
        out.append(f'\t(gr_line (start {P(*a)[4:-1]}) (end {P(*c)[4:-1]}) (stroke (width {w * 0.8:.3f}) '
                   f'(type solid)) (layer "{layer}") (uuid "{u()}"))')
    out.append(f'\t(group "Katze" (uuid "{_uid()}") (members {" ".join(chr(34) + i + chr(34) for i in uids)}))')
    return '\n'.join(out) + '\n'


def add_cat(pcb_path, x_mm, y_mm, height_mm=5.0, side='top'):
    """Katze in den Bestückungsdruck setzen. (x_mm, y_mm) = Pfote links unten im Platinen-Frame
    (Ursprung linke untere Platinenecke, Y nach oben, wie board_info). Eine vorhandene Katze wird ersetzt.
    Die Platine darf dabei nicht in KiCad offen sein."""
    info = board_info(pcb_path)
    ox, oy = info['kicad_origin_for_export']
    txt = open(pcb_path, encoding='utf-8').read()
    # alte Katze (Gruppe "Katze" samt Mitgliedern) entfernen
    m = re.search(r'\t\(group "Katze" \(uuid "[^"]+"\) \(members ([^)]*)\)\)\n', txt)
    if m:
        for mid in re.findall(r'"([^"]+)"', m.group(1)):
            txt = re.sub(r'\t\(gr_(?:poly|circle|line) [^\n]*\(uuid "' + re.escape(mid) + r'"\)\)\n', '', txt)
        txt = txt.replace(m.group(0), '')
    layer = 'F.SilkS' if side == 'top' else 'B.SilkS'
    block = cat_sexpr(ox + x_mm, oy - y_mm, height_mm, layer, mirror=(side != 'top'))
    i = txt.rstrip().rfind(')')
    txt = txt[:i] + block + txt[i:]
    open(pcb_path, 'w', encoding='utf-8').write(txt)
    return {'pcb': pcb_path, 'katze_bei_mm': [x_mm, y_mm], 'hoehe_mm': height_mm, 'seite': side,
            'drc': drc(pcb_path).get('counts')}


# ---------------------------------------------------------------- F8-Ersatz: Platine aus Schaltplan aktualisieren
# KiCad hat dafür keine CLI. Ablauf: kicad-cli exportiert die Netzliste (XML) -> hier geparst -> KiCads Python
# legt fehlende Footprints an (neben der Platine, Raster), tauscht geänderte Footprints (Lage bleibt), setzt Wert,
# Schaltplan-Pfad (Symbol-UUID) und alle Pad-Netze. Bestehende Lagen bleiben, nichts wird geroutet.

def _netzliste(sch_path):
    import tempfile
    import xml.etree.ElementTree as ET
    tmp = tempfile.mkdtemp(prefix='mb2_sync_')
    try:
        ox = os.path.join(tmp, 'netz.xml')
        r = subprocess.run([cli_path(), 'sch', 'export', 'netlist', '--format', 'kicadxml', '-o', ox, sch_path],
                           capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
        if not os.path.exists(ox):
            raise RuntimeError('Netzliste-Export fehlgeschlagen: ' + (r.stdout + r.stderr)[-600:])
        root = ET.parse(ox).getroot()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    teile = {}
    for c in root.iter('comp'):
        ref = c.get('ref')
        fpid = (c.findtext('footprint') or '').strip()
        sp = c.find('sheetpath')
        uid = (c.findtext('tstamps') or c.findtext('tstamp') or '').strip().split()[0:1]
        props = {p.get('name'): p.get('value') for p in c.findall('property')}
        teile[ref] = {'value': c.findtext('value') or '', 'footprint': fpid,
                      'path': (sp.get('tstamps') if sp is not None else '/') + (uid[0] if uid else ''),
                      'sheetname': sp.get('names') if sp is not None else '/',
                      'dnp': 'dnp' in props, 'ohne_bom': 'exclude_from_bom' in props, 'pins': {}}
    for n in root.iter('net'):
        for node in n.findall('node'):
            t = teile.get(node.get('ref'))
            if t is not None:
                t['pins'][node.get('pin')] = n.get('name')
    return teile


def _fp_libs(ed):
    """Footprint-Bibliotheken: KiCad-Standard + projekteigene fp-lib-table (${KIPRJMOD})."""
    libs = {os.path.splitext(os.path.basename(p))[0]: p
            for p in glob.glob(os.path.join(share_dir(), 'footprints', '*.pretty'))}
    t = os.path.join(ed, 'fp-lib-table')
    if os.path.exists(t):
        for m in re.finditer(r'\(lib \(name "?([^")\s]+)"?\).*?\(uri "?([^")]+)"?\)', open(t, encoding='utf-8').read()):
            libs[m.group(1)] = m.group(2).replace('${KIPRJMOD}', ed)
    return libs


_SYNC = r'''
import json, sys, pcbnew
pcb, daten = sys.argv[1], json.load(open(sys.argv[2], encoding='utf-8'))
teile, libs, nur_sch = daten['teile'], daten['libs'], daten['nur_schaltplan']
b = pcbnew.LoadBoard(pcb)
mm = pcbnew.FromMM
out = {'neu': [], 'getauscht': [], 'entfernt': [], 'fehlt_footprint': [], 'ohne_footprint': [], 'kollision': []}
bb = b.GetBoardEdgesBoundingBox()
gx0, gy0 = pcbnew.ToMM(bb.GetRight()) + 10, pcbnew.ToMM(bb.GetTop())
nets = {n: b.FindNet(n) for n in set(p for t in teile.values() for p in t['pins'].values())}
for n, ni in list(nets.items()):
    if ni is None:
        ni = pcbnew.NETINFO_ITEM(b, n); b.Add(ni); nets[n] = ni
def lade(fpid):
    lib, name = fpid.split(':', 1)
    if lib not in libs: return None
    return pcbnew.FootprintLoad(libs[lib], name)
nach_pfad = {f.GetPath().AsString(): f for f in b.GetFootprints() if f.GetPath().AsString() not in ('', '/')}
nach_ref = {f.GetReference(): f for f in b.GetFootprints()}
gesehen, k = set(), 0
for ref, t in sorted(teile.items()):
    if not t['footprint']:
        out['ohne_footprint'].append(ref); continue
    f = nach_pfad.get(t['path'])
    if f is None:
        g = nach_ref.get(ref)
        if g is not None and g.GetPath().AsString() not in ('', '/'):
            f = g                                     # Pfad veraltet, Referenz passt
        elif g is not None:
            out['kollision'].append(ref)              # Platinen-Teil ohne Schaltplan mit gleicher Referenz
            if nur_sch:
                b.RemoveNative(g); out['entfernt'].append(ref + ' (ohne Schaltplan)')
    if f is not None and f.GetFPIDAsString() != t['footprint']:
        nf = lade(t['footprint'])
        if nf is None:
            out['fehlt_footprint'].append(t['footprint']); gesehen.add(f.m_Uuid.AsString()); continue
        nf.SetPosition(f.GetPosition()); nf.SetOrientation(f.GetOrientation())
        if f.IsFlipped(): nf.Flip(nf.GetPosition(), False)
        b.RemoveNative(f); f = nf; b.Add(f); out['getauscht'].append(ref)
    if f is None:
        f = lade(t['footprint'])
        if f is None:
            out['fehlt_footprint'].append(t['footprint']); continue
        f.SetPosition(pcbnew.VECTOR2I(mm(gx0 + (k % 8) * 12), mm(gy0 + (k // 8) * 12))); k += 1
        b.Add(f); out['neu'].append(ref)
    gesehen.add(f.m_Uuid.AsString())
    f.SetReference(ref); f.SetValue(t['value']); f.SetFPIDAsString(t['footprint'])
    f.SetPath(pcbnew.KIID_PATH(t['path'])); f.SetSheetname(t['sheetname']); f.SetSheetfile(daten['sheetfile'])
    f.SetDNP(t['dnp']); f.SetExcludedFromBOM(t['ohne_bom'])
    for p in f.Pads():
        n = t['pins'].get(p.GetNumber())
        p.SetNet(nets[n] if n else b.FindNet(''))
for f in list(b.GetFootprints()):
    if f.m_Uuid.AsString() in gesehen: continue
    hat_pfad = f.GetPath().AsString() not in ('', '/')
    if hat_pfad or nur_sch:
        out['entfernt'].append(f.GetReference()); b.RemoveNative(f)
pcbnew.SaveBoard(pcb, b)
print('SYNC ' + json.dumps(out))
'''


def sync_from_schematic(pcb_path, nur_schaltplan=False):
    """F8 ohne Oberfläche. KiCad darf die Platine nicht offen haben. Sicherung: <name>.vor-sync.kicad_pcb.
    nur_schaltplan=True entfernt auch Footprints ohne Schaltplan-Symbol (z. B. Ecklöcher aus kicad_new)."""
    import tempfile
    ed = os.path.dirname(pcb_path)
    sch = os.path.splitext(pcb_path)[0] + '.kicad_sch'
    teile = _netzliste(sch)
    backup = os.path.splitext(pcb_path)[0] + '.vor-sync.kicad_pcb'
    shutil.copy2(pcb_path, backup)
    tmp = tempfile.mkdtemp(prefix='mb2_sync_')
    try:
        dj = os.path.join(tmp, 'sync.json')
        json.dump({'teile': teile, 'libs': _fp_libs(ed), 'nur_schaltplan': nur_schaltplan,
                   'sheetfile': os.path.basename(sch)}, open(dj, 'w', encoding='utf-8'))
        r = subprocess.run([kicad_python(), '-c', _SYNC, pcb_path, dj], capture_output=True, text=True,
                           timeout=600, stdin=subprocess.DEVNULL)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    zeile = next((l for l in r.stdout.splitlines() if l.startswith('SYNC ')), None)
    if not zeile:
        shutil.copy2(backup, pcb_path)
        raise RuntimeError('Sync fehlgeschlagen, Platine zurückgesetzt: ' + (r.stdout + r.stderr)[-800:])
    erg = json.loads(zeile[5:])
    erg.update({'pcb': pcb_path, 'backup': backup, 'teile_im_schaltplan': len(teile), 'drc': drc(pcb_path).get('counts')})
    return erg


# ---------------------------------------------------------------- Autorouter (Freerouting)
# Freerouting (Java) liegt portabel unter %USERPROFILE%\tools – ohne Installation und Admin-Rechte.
# Ablauf: Board -> Specctra-DSN (KiCads Python) -> Freerouting headless -> SES zurück -> Zonen neu füllen.

def kicad_python():
    return os.path.join(kicad_home(), 'bin', 'python.exe')


_DSN_EXPORT = r'''
import sys, pcbnew
b = pcbnew.LoadBoard(sys.argv[1])
if sys.argv[3] == '1':                    # bestehende (nicht gesperrte) Bahnen verwerfen
    for t in list(b.GetTracks()):
        if not t.IsLocked():
            b.RemoveNative(t)
ok = pcbnew.ExportSpecctraDSN(b, sys.argv[2])
print('DSN', ok)
'''

_SES_IMPORT = r'''
import sys, pcbnew
b = pcbnew.LoadBoard(sys.argv[1])
if sys.argv[3] == '1':
    for t in list(b.GetTracks()):
        if not t.IsLocked():
            b.RemoveNative(t)
ok = pcbnew.ImportSpecctraSES(b, sys.argv[2])
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
pcbnew.SaveBoard(sys.argv[1], b)
print('SES', ok)
'''


def autoroute(pcb_path, passes=100, rip_existing=True, timeout=3000):
    """Platine mit Freerouting entflechten. Gesperrte Bahnen/Vias bleiben stehen (z. B. Wärme-Vias, Via-Zaun).
    Breiten und Abstände kommen aus den Netzklassen der .kicad_pro. KiCad darf die Platine nicht offen haben."""
    java, jar = java_freerouting()
    if not (java and jar):
        raise RuntimeError('Freerouting/Java fehlen unter ~/tools – alte Bridge: freerouting_setup.')
    base = os.path.splitext(pcb_path)[0]
    dsn, ses, log = base + '.dsn', base + '.ses', base + '.freerouting.log'
    backup = base + '.vor-autoroute.kicad_pcb'
    shutil.copy2(pcb_path, backup)
    rip = '1' if rip_existing else '0'
    for f in (dsn, ses):
        if os.path.exists(f):
            os.remove(f)
    # stdin=DEVNULL: sonst erben die Kindprozesse den stdio-Kanal des MCP-Servers und blockieren (Export hing 300 s)
    r1 = subprocess.run([kicad_python(), '-c', _DSN_EXPORT, pcb_path, dsn, rip], capture_output=True, text=True,
                        timeout=300, stdin=subprocess.DEVNULL)
    if not os.path.exists(dsn):
        raise RuntimeError('DSN-Export fehlgeschlagen: ' + (r1.stdout + r1.stderr)[-800:])
    r2 = subprocess.run([java, '-jar', jar, '-de', dsn, '-do', ses, '-mp', str(passes), '-l', 'en',
                         '--gui.enabled=false'], capture_output=True, text=True, timeout=timeout,
                        cwd=os.path.dirname(dsn), stdin=subprocess.DEVNULL)
    text = r2.stdout + r2.stderr
    open(log, 'w', encoding='utf-8').write(text)
    if not os.path.exists(ses):
        raise RuntimeError('Freerouting hat keine .ses geschrieben, siehe ' + log)
    r3 = subprocess.run([kicad_python(), '-c', _SES_IMPORT, pcb_path, ses, rip], capture_output=True, text=True,
                        timeout=300, stdin=subprocess.DEVNULL)
    if 'SES True' not in r3.stdout:
        shutil.copy2(backup, pcb_path)
        raise RuntimeError('SES-Import fehlgeschlagen, Platine zurückgesetzt: ' + (r3.stdout + r3.stderr)[-800:])
    summary = [l for l in text.splitlines() if re.search(r'unrouted|completed|incomplete|error', l, re.I)][-8:]
    return {'pcb': pcb_path, 'backup': backup, 'log': log, 'freerouting': summary, 'drc': drc(pcb_path)}


# ---------------------------------------------------------------- Bibliotheken

def find_symbols(query, limit=40):
    q = query.lower()
    hits = []
    for lib in sorted(glob.glob(os.path.join(share_dir(), 'symbols', '*.kicad_sym'))):
        libname = os.path.splitext(os.path.basename(lib))[0]
        for m in re.finditer(r'^\t\(symbol "([^"]+)"', open(lib, encoding='utf-8').read(), re.M):
            full = f'{libname}:{m.group(1)}'
            if q in full.lower():
                hits.append(full)
                if len(hits) >= limit:
                    return hits
    return hits


def get_symbol(lib_id):
    """Symboldefinition (für lib_symbols in .kicad_sch) + Pinliste."""
    lib, name = lib_id.split(':', 1)
    txt = open(os.path.join(share_dir(), 'symbols', lib + '.kicad_sym'), encoding='utf-8').read()
    m = re.search(r'^\t\(symbol "%s"\n.*?^\t\)\n' % re.escape(name), txt, re.M | re.S)
    if not m:
        raise RuntimeError('Symbol nicht gefunden: ' + lib_id)
    block = m.group(0)
    node = sexpr.parse(block)
    ext = child(node, 'extends')
    pins = []

    def walk(n):
        for c in n[1:]:
            if isinstance(c, list):
                if sexpr.head(c) == 'pin':
                    at = child(c, 'at')
                    pins.append({'number': (child(c, 'number') or [None, None])[1],
                                 'name': (child(c, 'name') or [None, None])[1],
                                 'type': str(c[1]), 'at': [num(at[1]), num(at[2]), num(at[3]) if len(at) > 3 else 0]})
                else:
                    walk(c)
    walk(node)
    return {'lib_id': lib_id, 'extends': ext[1] if ext else None,
            'footprint': sexpr.prop(node, 'Footprint'), 'pins': pins,
            'definition': block.replace(f'(symbol "{name}"', f'(symbol "{lib_id}"', 1)}


def find_footprints(query, limit=40):
    q = query.lower()
    hits = []
    for lib in sorted(glob.glob(os.path.join(share_dir(), 'footprints', '*.pretty'))):
        libname = os.path.splitext(os.path.basename(lib))[0]
        for f in sorted(os.listdir(lib)):
            full = f'{libname}:{f[:-10]}'
            if f.endswith('.kicad_mod') and q in full.lower():
                hits.append(full)
                if len(hits) >= limit:
                    return hits
    return hits
