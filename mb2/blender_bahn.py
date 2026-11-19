"""Blender-Skript (headless): Druckbahn als Strang-Roehren rendern. Aufruf:
blender -b --factory-startup --python blender_bahn.py -- <bahn.npy> <ausgabe_praefix> [strang_mm]
Erzeugt <praefix>_iso.png und <praefix>_nah.png (Workbench, Kavitaet + Schatten)."""
import math
import sys

import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:]
bahn, praefix = argv[0], argv[1]
strang = float(argv[2]) if len(argv) > 2 else 0.45
B = np.load(bahn)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
cx, cy = float(B[:, 0].mean()), float(B[:, 1].mean())
P = B[:, :3] - np.array([cx, cy, 0.0], dtype=np.float32)

FARBEN = {0: (0.16, 0.17, 0.19, 1), 1: (0.18, 0.19, 0.21, 1), 2: (0.20, 0.21, 0.24, 1), 3: (0.18, 0.19, 0.21, 1)}


def kurve(punkte, farbe, name):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = strang / 2
    cu.bevel_resolution = 2
    sp = cu.splines.new('POLY')
    sp.points.add(len(punkte) - 1)
    co = np.ones((len(punkte), 4), dtype=np.float32)
    co[:, :3] = punkte
    sp.points.foreach_set('co', co.ravel())
    ob = bpy.data.objects.new(name, cu)
    sc.collection.objects.link(ob)
    m = bpy.data.materials.new(name + '_m')
    m.diffuse_color = farbe
    ob.data.materials.append(m)
    return ob


# zusammenhaengende Abschnitte gleicher Art
art = B[:, 3].astype(int)
grenzen = np.where(np.diff(art) != 0)[0] + 1
for k, (a, b) in enumerate(zip(np.r_[0, grenzen], np.r_[grenzen, len(B)])):
    if b - a > 1:
        kurve(P[a:b], FARBEN[int(art[a])], f'bahn{k}')

# Druckbett
bpy.ops.mesh.primitive_plane_add(size=120, location=(0, 0, -0.01))
bett = bpy.context.active_object
mb = bpy.data.materials.new('bett')
mb.diffuse_color = (0.55, 0.52, 0.46, 1)
bett.data.materials.append(mb)

sc.render.engine = 'BLENDER_WORKBENCH'
sh = sc.display.shading
sh.light = 'STUDIO'
sh.color_type = 'MATERIAL'
sh.show_cavity = True
sh.cavity_type = 'BOTH'
sh.show_shadows = True
sh.shadow_intensity = 0.6
sh.show_specular_highlight = True
sc.display.shadow_focus = 0.2
sc.render.film_transparent = False
sc.world = bpy.data.worlds.new('w')
sc.world.color = (0.93, 0.93, 0.92)
sc.render.image_settings.file_format = 'PNG'

cam_d = bpy.data.cameras.new('cam')
cam = bpy.data.objects.new('cam', cam_d)
sc.collection.objects.link(cam)
sc.camera = cam
H = float(P[:, 2].max())


def schuss(pos, ziel, linse, aufl, datei):
    cam.location = Vector(pos)
    cam.rotation_euler = (Vector(ziel) - Vector(pos)).to_track_quat('-Z', 'Y').to_euler()
    cam_d.lens = linse
    cam_d.clip_end = 2000
    sc.render.resolution_x, sc.render.resolution_y = aufl
    sc.render.filepath = datei
    bpy.ops.render.render(write_still=True)


schuss((150, -190, 120), (0, 0, H * 0.42), 50, (1400, 1600), praefix + '_iso.png')
r = float(np.hypot(P[:, 0], P[:, 1]).max())
schuss((r + 38, -18, H * 0.55), (r * 0.8, 0, H * 0.5), 60, (1400, 1600), praefix + '_nah.png')
