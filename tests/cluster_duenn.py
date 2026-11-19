"""Duenne Stellen und enge Spalte einer 3MF-Druckplatte nach Ort gruppieren (Audit-Hilfe).
Aufruf: python tests/cluster_duenn.py <datei.3mf> [wand_min] [spalt_min]"""
import sys
from collections import defaultdict

from mb2 import cad

pfad = sys.argv[1]
wand_min = float(sys.argv[2]) if len(sys.argv) > 2 else 1.8
spalt_min = float(sys.argv[3]) if len(sys.argv) > 3 else 0.4

for name, s in cad.lies_3mf(pfad):
    bb = s.bounding_box()
    d = cad.wand_und_spalt(s)
    print(f'\n=== {name}  bbox min ({bb.min.X:.1f}, {bb.min.Y:.1f}, {bb.min.Z:.1f})  max ({bb.max.X:.1f}, {bb.max.Y:.1f}, {bb.max.Z:.1f})')
    for art, liste, grenze in (('Wand', d['wand'], wand_min), ('Spalt', d['spalt'], spalt_min)):
        gruppen = defaultdict(list)
        for x, y, z, w in liste:
            if w < grenze - 1e-3:
                gruppen[(round(w, 1), round(z - bb.min.Z, 0))].append((x, y))
        print(f'  {art} < {grenze}: {sum(len(v) for v in gruppen.values())} Punkte')
        for (w, zr), pts in sorted(gruppen.items(), key=lambda kv: (kv[0][0], -len(kv[1])))[:14]:
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            print(f'    {art} {w:.1f} mm  Hoehe ueber Unterseite {zr:4.0f} mm  {len(pts):4d} Pkt  '
                  f'x {min(xs):6.1f}..{max(xs):6.1f}  y {min(ys):6.1f}..{max(ys):6.1f}')
