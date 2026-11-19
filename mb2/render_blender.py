"""Renderbilder mit Blender (headless, Workbench, orthografisch): Iso, Draufsicht, Schnitt durch die Teilmitte.

Platzhalter halbtransparent in eigener Farbe, Schnittflaechen dunkel abgesetzt, Pruef-Fehlerstellen als rote Kugeln.
Die Einzelbilder werden mit matplotlib zu EINEM PNG mit Titel und Legende zusammengesetzt.
Aufgerufen aus render.py; jeder Fehler hier fuehrt dort zum matplotlib-Rueckfall.
"""
import json
import os
import shutil
import struct
import subprocess
import tempfile

import matplotlib

matplotlib.use('Agg')
import matplotlib.image as mpimg  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

TEIL_FARBE = (0.80, 0.64, 0.30)
SCHNITT_FARBE = (0.62, 0.22, 0.16)
PH_FARBEN = [(0.16, 0.42, 0.85), (0.20, 0.66, 0.30), (0.58, 0.30, 0.78), (0.08, 0.66, 0.72),
             (0.92, 0.50, 0.10), (0.85, 0.25, 0.55)]
PLATTE_FARBEN = [(0.80, 0.64, 0.30), (0.30, 0.62, 0.80), (0.62, 0.78, 0.30), (0.80, 0.32, 0.50), (0.50, 0.38, 0.75)]
_EL, _AZ = np.radians(28), np.radians(-55)
ISO = [float(np.cos(_AZ) * np.cos(_EL)), float(np.sin(_AZ) * np.cos(_EL)), float(np.sin(_EL))]
ACHSEN = 'XYZ'


def _dreiecke(shape, tol=0.05):
    verts, tris = shape.tessellate(tol, 0.3)
    v = np.array([(p.X, p.Y, p.Z) for p in verts])
    return v[np.array(tris)] if tris else np.zeros((0, 3, 3))


def _stl(tri, pfad):
    """Binaeres STL ohne Abhaengigkeiten."""
    tri = np.asarray(tri, dtype=np.float32).reshape(-1, 3, 3)
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    rec = np.zeros(len(tri), dtype=[('n', '<f4', 3), ('v', '<f4', (3, 3)), ('a', '<u2')])
    rec['n'], rec['v'] = n, tri
    with open(pfad, 'wb') as f:
        f.write(b'mb2'.ljust(80, b' '))
        f.write(struct.pack('<I', len(tri)))
        f.write(rec.tobytes())
    return pfad


def _halbiert(shape, achse, wert):
    """An der Ebene achse=wert schneiden, die Seite unterhalb behalten (Kamera schaut von +achse)."""
    from build123d import Keep, Plane, split
    z = [0.0, 0.0, 0.0]
    z[achse] = 1.0
    o = [0.0, 0.0, 0.0]
    o[achse] = wert
    return split(shape, Plane(origin=tuple(o), z_dir=tuple(z)), keep=Keep.BOTTOM)


def _schnitt_trennen(tri, achse, wert, tol=1e-3):
    """Dreiecke in Schnittflaeche (alle Ecken auf der Ebene) und Rest aufteilen."""
    if not len(tri):
        return tri, tri
    auf = np.all(np.abs(tri[:, :, achse] - wert) < tol, axis=1)
    return tri[auf], tri[~auf]


def _lauf(job, arbeit):
    from . import werkzeuge
    exe = werkzeuge.blender()
    if not exe:
        raise RuntimeError('Blender nicht installiert')
    jp = os.path.join(arbeit, 'job.json')
    with open(jp, 'w', encoding='utf-8') as f:
        json.dump(job, f)
    skript = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'blender_szene.py')
    p = subprocess.run([exe, '--background', '--factory-startup', '--python', skript, '--', jp],
                       capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL,
                       encoding='utf-8', errors='replace')
    fehlt = [a['png'] for a in job['ansichten'] if not os.path.exists(a['png'])]
    if p.returncode or fehlt:
        raise RuntimeError(f'Blender Code {p.returncode}, fehlt {fehlt}: ' + ((p.stderr or '') + (p.stdout or ''))[-1500:])


def _zuschneiden(img, rand=12):
    """Weissen Rand wegschneiden, damit schmale Ansichten (Schnitt) nicht im Leerraum verschwinden."""
    inhalt = np.where(img[:, :, :3].min(axis=2) < 0.97)
    if not len(inhalt[0]):
        return img
    y0, y1 = max(inhalt[0].min() - rand, 0), min(inhalt[0].max() + rand, img.shape[0])
    x0, x1 = max(inhalt[1].min() - rand, 0), min(inhalt[1].max() + rand, img.shape[1])
    return img[y0:y1, x0:x1]


def _setzen(pngs, titel_je, titel, eintraege, pfad):
    """Einzelbilder nebeneinander, Breite je nach Inhalt. Gesamtbild 1540 x 660 px, unter der Verkleinerungsgrenze von 1568 px (≈ 1,5k Tokens beim Ansehen)."""
    bilder = [_zuschneiden(mpimg.imread(p)) for p in pngs]
    hmax = max(b.shape[0] for b in bilder)
    # gleicher Massstab: auf gemeinsame Hoehe auffuellen, Breiten echt -> Ansichten direkt vergleichbar
    bilder = [np.pad(b, ((0, hmax - b.shape[0]), (0, 0), (0, 0)), constant_values=1.0) for b in bilder]
    verh = [max(b.shape[1], 0.25 * hmax) for b in bilder]
    fig, axs = plt.subplots(1, len(pngs), figsize=(14, 6.0), dpi=110, gridspec_kw={'width_ratios': verh})
    for ax, img, t in zip(np.atleast_1d(axs), bilder, titel_je):
        ax.imshow(img)
        ax.set_title(t, fontsize=10)
        ax.axis('off')
    fig.suptitle(titel, fontsize=11)
    fig.legend(handles=[Patch(facecolor=c[:3], alpha=c[3] if len(c) > 3 else 1.0, edgecolor='0.3', label=n)
                        for n, c in eintraege], loc='lower center', ncol=min(len(eintraege), 6), fontsize=9,
               frameon=False)
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    fig.savefig(pfad)
    plt.close(fig)
    return pfad


def teil_png(teil, pfad, platzhalter=None, titel='', markierungen=None, schnitt=None):
    bb = teil.bounding_box()
    groesse = [bb.size.X, bb.size.Y, bb.size.Z]
    mitte = [bb.center().X, bb.center().Y, bb.center().Z]
    if schnitt:
        achse, wert = ACHSEN.index(str(schnitt[0]).upper()), float(schnitt[1])
    else:                                            # Normale = mittlere Achse -> Schnitt zeigt Laenge x Dicke
        achse = int(np.argsort(groesse)[1])
        wert = mitte[achse]
    arbeit = tempfile.mkdtemp(prefix='mb2_render_')
    try:
        netze, eintraege = [], [('Teil', TEIL_FARBE)]
        voll, im_schnitt = ['teil'], ['teil_s']

        def netz(name, tri, farbe):
            netze.append({'name': name, 'stl': _stl(tri, os.path.join(arbeit, name + '.stl')), 'farbe': list(farbe)})

        netz('teil', _dreiecke(teil), (*TEIL_FARBE, 1.0))
        sf, rest = _schnitt_trennen(_dreiecke(_halbiert(teil, achse, wert)), achse, wert)
        netz('teil_s', rest, (*TEIL_FARBE, 1.0))
        if len(sf):
            netz('teil_sf', sf, (*SCHNITT_FARBE, 1.0))
            im_schnitt.append('teil_sf')
            eintraege.append(('Schnittfläche', SCHNITT_FARBE))
        for i, (n, p) in enumerate((platzhalter or {}).items()):
            c = PH_FARBEN[i % len(PH_FARBEN)]
            tri = _dreiecke(p)
            if not len(tri):
                continue
            eintraege.append((n, (*c, 0.6)))
            netz(f'ph{i}', tri, (*c, 0.45))
            voll.append(f'ph{i}')
            try:
                halb = _dreiecke(_halbiert(p, achse, wert))
            except Exception:  # noqa: BLE001 - Platzhalter, der sich nicht schneiden laesst
                halb = np.zeros((0, 3, 3))
            if len(halb):
                netz(f'ph{i}_s', halb, (*c, 0.9))
                im_schnitt.append(f'ph{i}_s')
        richt = [0.0, 0.0, 0.0]
        richt[achse] = 1.0
        if achse == 2:                               # waagerechter Schnitt: leicht schraeg, sonst = Draufsicht
            richt = [0.25, -0.35, 1.0]
        ansichten = [
            {'name': 'iso', 'png': os.path.join(arbeit, 'iso.png'), 'richtung': ISO, 'netze': voll},
            {'name': 'oben', 'png': os.path.join(arbeit, 'oben.png'), 'richtung': [0, 0, 1], 'netze': voll},
            {'name': 'schnitt', 'png': os.path.join(arbeit, 'schnitt.png'), 'richtung': richt, 'netze': im_schnitt},
        ]
        _lauf({'netze': netze, 'marker': [list(map(float, m)) for m in (markierungen or [])],
               'marker_r': max(0.4, max(groesse) / 120), 'ansichten': ansichten, 'aufloesung': 900, 'gleicher_massstab': True}, arbeit)
        kopf = (f'{titel}: {bb.size.X:.1f} × {bb.size.Y:.1f} × {bb.size.Z:.1f} mm, {teil.volume / 1000:.2f} cm³'
                + (f' | {len(markierungen)} Problemstellen (rot)' if markierungen else ''))
        return _setzen([a['png'] for a in ansichten],
                       ['iso', 'von oben', f'Schnitt {ACHSEN[achse]} = {wert:.1f} (Blick von +{ACHSEN[achse]})'],
                       kopf, eintraege, pfad)
    finally:
        shutil.rmtree(arbeit, ignore_errors=True)


def platte_png(teile, namen, pfad, bett):
    arbeit = tempfile.mkdtemp(prefix='mb2_platte_')
    try:
        netze, farbe_je = [], {}
        for i, (s, n) in enumerate(zip(teile, namen)):
            c = farbe_je.setdefault(n, PLATTE_FARBEN[len(farbe_je) % len(PLATTE_FARBEN)])
            netze.append({'name': f't{i}', 'stl': _stl(_dreiecke(s, 0.05), os.path.join(arbeit, f't{i}.stl')),
                          'farbe': [*c, 1.0]})
        eintraege = [(f'{n} ×{namen.count(n)}', c) for n, c in farbe_je.items()]
        eintraege.append((f'Bett {bett[0]:.0f} × {bett[1]:.0f}', (0.18, 0.18, 0.2)))
        alle = [n['name'] for n in netze]
        ansichten = [
            {'name': 'iso', 'png': os.path.join(arbeit, 'iso.png'), 'richtung': ISO, 'netze': alle + ['bett']},
            {'name': 'nah', 'png': os.path.join(arbeit, 'nah.png'), 'richtung': ISO, 'netze': alle},
            {'name': 'oben', 'png': os.path.join(arbeit, 'oben.png'), 'richtung': [0, 0, 1], 'netze': alle + ['bett']},
        ]
        _lauf({'netze': netze, 'ansichten': ansichten, 'aufloesung': 900,
               'bett': [0.0, 0.0, float(bett[0]), float(bett[1])]}, arbeit)
        return _setzen([a['png'] for a in ansichten], ['Bett (iso)', 'Teile (iso, nah)', 'von oben'],
                       f'Druckplatte MK4 ({bett[0]:.0f} × {bett[1]:.0f} mm): {len(namen)} Teile', eintraege, pfad)
    finally:
        shutil.rmtree(arbeit, ignore_errors=True)
