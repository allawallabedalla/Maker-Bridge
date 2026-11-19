"""Laeuft IN Blender (blender --background --factory-startup --python blender_szene.py -- job.json).

Job (JSON, von render.py geschrieben):
  {"netze": [{"name", "stl", "farbe": [r,g,b,a]}],
   "marker": [[x,y,z], ...], "marker_r": 0.6,
   "ansichten": [{"name", "png", "richtung": [dx,dy,dz], "netze": [namen], "marker": bool}],
   "aufloesung": 900, "bett": [x0, y0, x1, y1] | null}
Kamera orthografisch, Workbench (schnell, keine GPU-Pflicht), Kavitaet + Umriss fuer technische Lesbarkeit.
"""
import json
import sys

import bpy
from mathutils import Matrix, Vector

job = json.load(open(sys.argv[sys.argv.index('--') + 1], encoding='utf-8'))

for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)

sc = bpy.context.scene
sc.render.engine = 'BLENDER_WORKBENCH'
sc.render.resolution_x = sc.render.resolution_y = job.get('aufloesung', 900)
sc.render.film_transparent = False
sc.render.image_settings.file_format = 'PNG'
sh = sc.display.shading
sh.light = 'STUDIO'
sh.color_type = 'MATERIAL'
sh.show_cavity = True
sh.cavity_type = 'BOTH'
sh.show_object_outline = True
sh.object_outline_color = (0.1, 0.1, 0.1)
sh.show_specular_highlight = False
if sc.world is None:
    sc.world = bpy.data.worlds.new('Welt')
sc.world.color = (1.0, 1.0, 1.0)
try:
    sc.view_settings.view_transform = 'Standard'
except TypeError:
    pass

objekte = {}
for n in job['netze']:
    vorher = set(bpy.data.objects)
    bpy.ops.wm.stl_import(filepath=n['stl'])
    neu = [o for o in bpy.data.objects if o not in vorher]
    if not neu:
        continue
    ob = neu[0]
    ob.name = n['name']
    m = bpy.data.materials.new(n['name'])
    m.diffuse_color = n['farbe']                     # Alpha < 1 zeichnet Workbench transparent
    ob.data.materials.append(m)
    objekte[n['name']] = ob

marker = []
mat_rot = bpy.data.materials.new('marker')
mat_rot.diffuse_color = (0.9, 0.05, 0.05, 1.0)
for i, p in enumerate(job.get('marker') or []):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=job.get('marker_r', 0.6), location=p, segments=12, ring_count=8)
    ob = bpy.context.active_object
    ob.name = f'marker_{i}'
    ob.data.materials.append(mat_rot)
    marker.append(ob)

if job.get('bett'):
    x0, y0, x1, y1 = job['bett']
    bpy.ops.mesh.primitive_plane_add(size=1, location=((x0 + x1) / 2, (y0 + y1) / 2, -0.3))
    ob = bpy.context.active_object
    ob.scale = (x1 - x0, y1 - y0, 1)
    ob.name = 'bett'
    mb = bpy.data.materials.new('bett')
    mb.diffuse_color = (0.18, 0.18, 0.2, 1.0)
    ob.data.materials.append(mb)
    objekte['bett'] = ob

cam_data = bpy.data.cameras.new('Kamera')
cam_data.type = 'ORTHO'
cam = bpy.data.objects.new('Kamera', cam_data)
sc.collection.objects.link(cam)
sc.camera = cam


def ecken(obs):
    pts = []
    for ob in obs:
        pts += [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    return pts


def kamera(a):
    """Kameralage + noetige ortho_scale fuer eine Ansicht."""
    obs = [objekte[n] for n in a['netze'] if n in objekte]
    pts = ecken(obs)
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    mitte = (lo + hi) / 2
    d = Vector(a['richtung']).normalized()           # von der Mitte zur Kamera
    f = -d
    up = Vector((0, 0, 1)) if abs(f.z) < 0.99 else Vector((0, 1, 0))
    rechts = f.cross(up).normalized()
    oben = rechts.cross(f).normalized()
    rot = Matrix((rechts, oben, d)).transposed()     # Spalten: X=rechts, Y=oben, Z=zurueck
    abstand = (hi - lo).length * 2 + 50
    us = [(p - mitte).dot(rechts) for p in pts]
    vs = [(p - mitte).dot(oben) for p in pts]
    return {'matrix': Matrix.Translation(mitte + d * abstand) @ rot.to_4x4(), 'abstand': abstand,
            'scale': max(max(us) - min(us), max(vs) - min(vs)) * 1.12,
            'mu': (max(us) + min(us)) / 2, 'mv': (max(vs) + min(vs)) / 2}


bpy.context.view_layer.update()                     # matrix_world nach scale/location aktualisieren
kams = [kamera(a) for a in job['ansichten']]
gemeinsam = max(k['scale'] for k in kams) if job.get('gleicher_massstab') else None
for a, k in zip(job['ansichten'], kams):
    sichtbar = set(a['netze'])
    for name, ob in objekte.items():
        ob.hide_render = name not in sichtbar
    for ob in marker:
        ob.hide_render = not a.get('marker', True)
    cam.matrix_world = k['matrix']
    cam_data.ortho_scale = gemeinsam or k['scale']   # gleicher Massstab: Ansichten direkt vergleichbar
    cam_data.shift_x = k['mu'] / cam_data.ortho_scale
    cam_data.shift_y = k['mv'] / cam_data.ortho_scale
    cam_data.clip_end = k['abstand'] * 3
    sc.render.filepath = a['png']
    bpy.ops.render.render(write_still=True)
    print('GERENDERT', a['png'])
