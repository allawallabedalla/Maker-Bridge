"""Renderbilder fuer die Sichtkontrolle durch Agenten und Nutzer.

Standard: Blender headless (render_blender.py + blender_szene.py) -> Iso, Draufsicht, Schnitt durch die Teilmitte.
Rueckfall (Blender fehlt oder scheitert, oder MB2_RENDER=matplotlib): reine matplotlib-Ansichten wie bisher.
FEM-Feldbilder bleiben matplotlib.
"""
import os
import sys

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

LICHT = np.array([0.4, -0.5, 0.75])
LICHT = LICHT / np.linalg.norm(LICHT)


def _dreiecke(shape, tol=0.05):
    verts, tris = shape.tessellate(tol, 0.3)
    v = np.array([(p.X, p.Y, p.Z) for p in verts])
    return v[np.array(tris)] if tris else np.zeros((0, 3, 3))


def _schattiert(tri, farbe, alpha=1.0):
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    hell = 0.35 + 0.65 * np.clip(np.abs(n @ LICHT), 0, 1)
    c = np.outer(hell, np.array(matplotlib.colors.to_rgb(farbe)))
    return np.clip(np.column_stack([c, np.full(len(c), alpha)]), 0, 1)


def _achse(ax, alle, elev, azim, titel):
    lo, hi = alle.reshape(-1, 3).min(0), alle.reshape(-1, 3).max(0)
    mitte, span = (lo + hi) / 2, max((hi - lo).max(), 1e-3) / 2
    for setz, m in zip((ax.set_xlim, ax.set_ylim, ax.set_zlim), mitte):
        setz(m - span, m + span)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev, azim)
    ax.set_xlabel('X'); ax.set_ylabel('Y'); ax.set_zlabel('Z')
    ax.tick_params(labelsize=6)
    ax.set_title(titel, fontsize=9)


def _mpl_teil_png(teil, pfad, platzhalter=None, titel='', markierungen=None):
    """Rueckfall ohne Blender: zwei Ansichten (iso + von oben), Platzhalter halbtransparent blau, Fehler rot."""
    tri = _dreiecke(teil)
    ph = [(n, _dreiecke(p)) for n, p in (platzhalter or {}).items()]
    alle = np.concatenate([tri] + [t for _, t in ph if len(t)])
    bb = teil.bounding_box()
    fig = plt.figure(figsize=(12, 6), dpi=110)
    # eine einzige Sammlung, damit die Tiefensortierung ueber Teil UND Platzhalter geht
    gesamt = np.concatenate([tri] + [t for _, t in ph if len(t)])
    farben = np.concatenate([_schattiert(tri, '#c8a050')] + [_schattiert(t, '#2a6ad8', 0.55) for _, t in ph if len(t)])
    for k, (elev, azim, name) in enumerate(((28, -55, 'iso'), (90, -90, 'oben'))):
        ax = fig.add_subplot(1, 2, k + 1, projection='3d')
        ax.set_proj_type('ortho')
        ax.add_collection3d(Poly3DCollection(gesamt, facecolors=farben, edgecolor='none'))
        if markierungen:
            m = np.array(markierungen)
            ax.scatter(m[:, 0], m[:, 1], m[:, 2], c='red', s=8, depthshade=False)
        _achse(ax, alle, elev, azim, f'{titel} – {name}')
    fig.suptitle(f'{titel}: {bb.size.X:.1f} × {bb.size.Y:.1f} × {bb.size.Z:.1f} mm, '
                 f'{teil.volume / 1000:.2f} cm³' + (f' | Platzhalter: {", ".join(n for n, _ in ph)}' if ph else '')
                 + (f' | {len(markierungen)} Problemstellen (rot)' if markierungen else ''), fontsize=10)
    fig.tight_layout()
    fig.savefig(pfad)
    plt.close(fig)
    return pfad


def _mpl_platte_png(teile, namen, pfad, bett):
    fig = plt.figure(figsize=(10, 7), dpi=110)
    ax = fig.add_subplot(projection='3d')
    farben = ['#c8a050', '#50a0c8', '#a0c850', '#c85080', '#8060c0']
    alle = []
    for i, s in enumerate(teile):
        t = _dreiecke(s, 0.1)
        alle.append(t)
        ax.add_collection3d(Poly3DCollection(t, facecolors=_schattiert(t, farben[i % len(farben)]), edgecolor='none'))
        bb = s.bounding_box()
        ax.text(bb.center().X, bb.center().Y, bb.max.Z + 3, namen[i], fontsize=8, ha='center')
    ax.plot([0, bett[0], bett[0], 0, 0], [0, 0, bett[1], bett[1], 0], [0] * 5, 'k-', lw=0.8)
    ax.set_xlim(0, bett[0]); ax.set_ylim(0, bett[1]); ax.set_zlim(0, max(bett) * 0.6)
    ax.set_box_aspect((bett[0], bett[1], max(bett) * 0.6))
    ax.view_init(35, -60)
    ax.set_title(f'Druckplatte MK4 ({bett[0]:.0f} × {bett[1]:.0f} mm): {", ".join(namen)}')
    fig.tight_layout()
    fig.savefig(pfad)
    plt.close(fig)
    return pfad


def teil_png(teil, pfad, platzhalter=None, titel='', markierungen=None, schnitt=None):
    """Iso + Draufsicht + Schnitt aus Blender (render_blender.py), sonst matplotlib.
    schnitt = ('X'|'Y'|'Z', wert) oder None = Teilmitte, Normale = mittlere Achse der Bounding Box."""
    if os.environ.get('MB2_RENDER', '').lower() != 'matplotlib':
        try:
            from . import render_blender
            return render_blender.teil_png(teil, pfad, platzhalter, titel, markierungen, schnitt)
        except Exception as e:  # noqa: BLE001 - ein Bild darf den Build nie abbrechen
            print(f'[render] Blender fehlgeschlagen, matplotlib-Rueckfall: {e}', file=sys.stderr)
    return _mpl_teil_png(teil, pfad, platzhalter, titel, markierungen)


def platte_png(teile, namen, pfad, bett):
    if os.environ.get('MB2_RENDER', '').lower() != 'matplotlib':
        try:
            from . import render_blender
            return render_blender.platte_png(teile, namen, pfad, bett)
        except Exception as e:  # noqa: BLE001
            print(f'[render] Blender fehlgeschlagen, matplotlib-Rueckfall: {e}', file=sys.stderr)
    return _mpl_platte_png(teile, namen, pfad, bett)


def feld_png(knoten, flaechen, werte, pfad, titel, einheit, verformung=None, skala=1.0):
    """FEM-Ergebnis: Oberflaechendreiecke eingefaerbt nach Knotenwert (Mittel je Dreieck), optional verformt."""
    p = knoten + (verformung * skala if verformung is not None else 0)
    tri = p[flaechen]
    w = werte[flaechen].mean(1)
    norm = matplotlib.colors.Normalize(w.min(), w.max())
    farbe = matplotlib.colormaps['turbo'](norm(w))
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    farbe[:, :3] *= (0.55 + 0.45 * np.abs(n @ LICHT))[:, None]
    fig = plt.figure(figsize=(11, 6), dpi=110)
    for k, (elev, azim) in enumerate(((28, -55), (28, 125))):
        ax = fig.add_subplot(1, 2, k + 1, projection='3d')
        ax.add_collection3d(Poly3DCollection(tri, facecolors=farbe, edgecolor='none'))
        _achse(ax, tri, elev, azim, 'vorn' if k == 0 else 'hinten')
    sm = matplotlib.cm.ScalarMappable(norm=norm, cmap='turbo')
    fig.colorbar(sm, ax=fig.axes, shrink=0.6, label=einheit)
    fig.suptitle(titel + (f' (Verformung ×{skala:.0f})' if verformung is not None and skala != 1 else ''), fontsize=10)
    fig.savefig(pfad)
    plt.close(fig)
    return pfad
