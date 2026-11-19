"""Nicht-planare Bahnen direkt als G-Code (ohne Slicer) – erster Fall: Becher mit Flechtwand.

Idee: Die Wand ist EINE durchgehende Spirale (wie Vasenmodus). Ihre Hoehe schwingt mit k Wellen je Umlauf, k ist
eine halbe Zahl (z. B. 20,5). Dadurch kippt die Phase von Runde zu Runde von selbst: Wo Runde n ein Wellental hat,
hat Runde n-1 einen Wellenberg -> die Straenge beruehren sich nur dort (Kreuzungspunkte), dazwischen bleiben
Fenster offen. Abstand zweier Runden an gleicher Stelle: d(theta) = h - 2A*sin(k*theta)  (h = Steigung je Runde).
Mit h = b + 2A ist der kleinste Abstand genau die Strangdicke b (Beruehrung, Haftung), der groesste b + 4A.

Pruefungen (alle analytisch bzw. auf der fertigen Punktliste):
- Abstand zur Vorrunde an jedem Punkt >= b (keine Durchdringung) und an den Kreuzungen <= b * 1,15 (Haftung)
- Kollision Hotend: kein bereits gedruckter Punkt ragt in den Duesenkegel/Heizblock ueber der Spitze
- Steigung |dz/ds| <= Grenze, freie Spannweite zwischen Kreuzungen <= Grenze (Bruecke)
- Bettgrenzen MK4 (250 x 210, Hoehe 220)
"""
import json
import math
import os

import numpy as np

# MK4 / Nextruder, 0,4-mm-Messingduese. Konservative Huellkontur ueber der Duesenspitze (r = Abstand von der
# Duesenachse in mm -> freie Hoehe ueber der Spitze in mm). Duesenspitze Flaeche ~ D1,0; Kegel ~ 40 Grad
# Halbwinkel bis ~4 mm Hoehe, darueber Heizblock/Silikonsocke ~ D22 (Annahme, nicht vermessen -> grosszuegig).
DUESE = {'spitze_r': 0.5, 'kegel_halbwinkel_grad': 40.0, 'kegel_hoehe': 3.5, 'block_r': 12.0}
BETT = (250.0, 210.0, 220.0)
FIL_D = 1.75


def freie_hoehe(r):
    """Wie hoch darf ein schon gedrucktes Material im Abstand r (mm) von der Duesenachse ueber der Spitze liegen."""
    d = DUESE
    if r <= d['spitze_r']:
        return 0.0
    h = (r - d['spitze_r']) / math.tan(math.radians(d['kegel_halbwinkel_grad']))
    if h < d['kegel_hoehe']:
        return h
    return d['kegel_hoehe'] if r < d['block_r'] else 1e9


def becher(p):
    """Punktliste [(x, y, z, art)] fuer Boden + Flechtwand + Rand. art: 'boden', 'wand', 'welle', 'rand'."""
    cx, cy = p['mitte']
    R, H = p['d_mm'] / 2, p['h_mm']
    w, b, A, k = p['linie_mm'], p['strang_mm'], p['amplitude_mm'], p['wellen_je_runde']
    pts = []
    # Boden: konzentrische Ringe von aussen nach innen, Schichten 0,2 mm
    for s in range(p['boden_schichten']):
        z = 0.2 * (s + 1)
        r = R
        while r > w / 2:
            n = max(24, int(2 * math.pi * r / 0.8))
            for i in range(n + 1):
                t = 2 * math.pi * i / n
                pts.append((cx + r * math.cos(t), cy + r * math.sin(t), z, 'boden'))
            r -= w
    z0 = 0.2 * p['boden_schichten']
    # Glatte Wand als Spirale mit 0,2 mm je Runde (Vasenmodus)
    seg = p['punkte_je_runde']
    runden_glatt = int(round(p['wand_glatt_mm'] / 0.2))
    z = z0
    for i in range(runden_glatt * seg):
        t = 2 * math.pi * i / seg
        z = z0 + 0.2 * (i / seg + 1)
        pts.append((cx + R * math.cos(t), cy + R * math.sin(t), z, 'wand'))
    # Flechtzone: Steigung h(theta) und Amplitude a(theta) rampen ueber 'rampe_runden' hoch und am Ende runter
    z_basis, theta = z, 0.0
    rampe = p['rampe_runden'] * 2 * math.pi
    rand_h = p['rand_runden'] * p['rand_hoehe_mm']
    # Gesamtlaenge in Runden so waehlen, dass H erreicht wird: mittlere Steigung ~ b + 2A
    ziel = H - rand_h
    dtheta = 2 * math.pi / seg
    zb = z_basis
    phasen = []
    while True:
        # Amplitude: hoch rampen, oben runter rampen (Restweg schaetzen)
        rest = ziel - zb
        a_auf = min(1.0, max(0.0, theta - 2 * math.pi) / rampe) if rampe > 0 else 1.0  # erst 1 Runde Steigung b, dann Welle
        a_ab = min(1.0, max(0.0, rest / ((b + 2 * A) * p['rampe_runden']))) if p['rampe_runden'] else 1.0
        a = A * min(a_auf, a_ab)
        h = max(0.2, b + 2 * a)                  # Steigung je Runde
        zb += h * dtheta / (2 * math.pi)
        theta += dtheta
        zz = zb + a * math.sin(k * theta)
        pts.append((cx + R * math.cos(theta), cy + R * math.sin(theta), zz, 'welle'))
        phasen.append((theta, zb, a, h))
        if zb >= ziel and a < 1e-6:
            break
        if theta > 2 * math.pi * 400:
            raise RuntimeError('Flechtzone endet nicht')
    # Rand: glatte Spirale mit rand_hoehe_mm je Runde
    zr = pts[-1][2]
    for i in range(1, p['rand_runden'] * seg + 1):
        t = theta + 2 * math.pi * i / seg
        zr2 = zr + p['rand_hoehe_mm'] * i / seg
        pts.append((cx + R * math.cos(t), cy + R * math.sin(t), zr2, 'rand'))
    return pts


def pruefen(pts, p):
    """Geometrische Pruefungen auf der Punktliste. Liefert dict mit Werten und Fehlern."""
    P = np.array([(x, y, z) for x, y, z, _ in pts])
    art = np.array([a for *_, a in pts])
    seg = p['punkte_je_runde']
    fehler, warn = [], []
    wand = np.where(art != 'boden')[0]
    W = P[wand]
    # 1) Abstand zur Vorrunde (gleicher Winkel = Index - seg)
    d = W[seg:, 2] - W[:-seg, 2]
    welle = (art[wand][seg:] == 'welle') & (art[wand][:-seg] == 'welle')
    d_min, d_max = float(d.min()), float(d.max())
    b = p['strang_mm']
    if d_min < 0.15:
        fehler.append(f'Runden durchdringen sich: kleinster Abstand {d_min:.2f} mm')
    dw = d[welle]
    # Kreuzungen = lokale Minima von d in der Flechtzone
    if dw.size:
        loc = np.where((dw[1:-1] <= dw[:-2]) & (dw[1:-1] <= dw[2:]))[0] + 1
        kreuz = dw[loc]
        haft_max = float(kreuz.max()) if kreuz.size else None
        if haft_max and haft_max > b * 1.15:
            warn.append(f'Kreuzungen ohne sichere Beruehrung: groesster Abstand {haft_max:.2f} mm > {b * 1.15:.2f}')
    else:
        haft_max = None
    # 2) Steigung
    ds = np.linalg.norm(np.diff(W[:, :2], axis=0), axis=1)
    dz = np.abs(np.diff(W[:, 2]))
    steig = float(np.degrees(np.arctan((dz / np.maximum(ds, 1e-9)).max())))
    if steig > p['steigung_max_grad']:
        fehler.append(f'Steigung {steig:.0f} Grad > {p["steigung_max_grad"]}')
    # 3) Freie Spannweite zwischen Kreuzungen (halbe Wellenlaenge)
    U = math.pi * p['d_mm']
    spann = U / p['wellen_je_runde']  # d(theta) hat ein Minimum je Welle -> Kreuzungen eine Wellenlaenge auseinander
    if spann > p['spannweite_max_mm']:
        warn.append(f'freie Spannweite {spann:.1f} mm > {p["spannweite_max_mm"]}')
    # 4) Kollision Hotend: fuer Stichproben-Punkte alle frueheren Punkte im Umkreis block_r pruefen
    n = len(P)
    kol, kol_max = 0, -1e9
    stride = max(1, n // 6000)
    # Der eigene, gerade abgelegte Strang direkt hinter der Duese (letzte ~3 mm Bahn) zaehlt nicht: beim Bergab-
    # Fahren liegt er naturgemaess etwas ueber der Spitze. Dafuer begrenzt die Steigungspruefung den Winkel.
    schritt = float(np.median(np.linalg.norm(np.diff(W[:200, :2], axis=0), axis=1))) or 0.3
    nb = max(3, int(3.0 / schritt))
    for i in range(seg * 2, n, stride):
        q = P[:i - nb]
        r = np.hypot(q[:, 0] - P[i, 0], q[:, 1] - P[i, 1])
        m = r < DUESE['block_r']
        if not m.any():
            continue
        frei = np.array([freie_hoehe(x) for x in r[m]])
        # Oberkante eines Strangs = Duesenhoehe beim Drucken (q.z). >0 = Material ragt in die Huelle
        ueber = q[m, 2] - (P[i, 2] + frei)
        # direkt unter der Spitze (r < spitze_r): Material darf nicht hoeher als die Spitze liegen
        unter = r[m] <= DUESE['spitze_r']
        ueber[unter] = q[m, 2][unter] - P[i, 2] - 0.02   # nichts ueber der Spitze; Quetschung prueft Punkt 1
        mx = float(ueber.max())
        kol_max = max(kol_max, mx)
        if mx > 0:
            kol += 1
    if kol:
        fehler.append(f'Hotend-Kollision an {kol} Stichproben (max {kol_max:.2f} mm)')
    # 5) Bett
    if (P[:, 0].min() < 0 or P[:, 0].max() > BETT[0] or P[:, 1].min() < 0 or P[:, 1].max() > BETT[1]
            or P[:, 2].max() > BETT[2]):
        fehler.append('ausserhalb des Bauraums')
    laenge = float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum())
    return {'ok': not fehler, 'fehler': fehler, 'warnungen': warn,
            'abstand_vorrunde_min_mm': round(d_min, 3), 'abstand_vorrunde_max_mm': round(d_max, 3),
            'kreuzung_abstand_max_mm': None if haft_max is None else round(haft_max, 3),
            'steigung_max_grad': round(steig, 1), 'spannweite_mm': round(spann, 1),
            'kollision_reserve_mm': round(-kol_max, 2), 'punkte': n, 'bahnlaenge_mm': round(laenge),
            'hoehe_mm': round(float(P[:, 2].max()), 2)}


def gcode_koerper(pts, p):
    """Nur die Bewegungen (ohne Start-/End-Code). E relativ (M83)."""
    q_boden = p['linie_mm'] * 0.2
    q_strang = p['strang_querschnitt_mm2']
    fil = math.pi / 4 * FIL_D ** 2
    zeilen, alt = [], None
    for x, y, z, a in pts:
        if alt is None:
            zeilen.append(f'G0 X{x:.3f} Y{y:.3f} Z{z + 0.4:.3f} F6000')
            zeilen.append(f'G1 Z{z:.3f} F600')
        else:
            l = math.dist(alt[:3], (x, y, z))
            q = q_boden if a == 'boden' else q_strang
            f = p['f_boden'] if a == 'boden' else (p['f_welle'] if a == 'welle' else p['f_wand'])
            zeilen.append(f'G1 X{x:.3f} Y{y:.3f} Z{z:.3f} E{l * q / fil:.5f} F{f}')
        alt = (x, y, z, a)
    return zeilen


STANDARD = {
    'mitte': (125.0, 105.0), 'd_mm': 70.0, 'h_mm': 80.0,
    'linie_mm': 0.45, 'strang_mm': 0.45, 'strang_querschnitt_mm2': 0.18,
    'amplitude_mm': 1.0, 'wellen_je_runde': 20.5, 'punkte_je_runde': 720,
    'boden_schichten': 6, 'wand_glatt_mm': 3.0, 'rampe_runden': 2,
    'rand_runden': 4, 'rand_hoehe_mm': 0.3,
    'steigung_max_grad': 45, 'spannweite_max_mm': 15,
    'f_boden': 1800, 'f_wand': 1500, 'f_welle': 900,
}


def bauen(pdir, param=None):
    p = dict(STANDARD, **(param or {}))
    pts = becher(p)
    erg = pruefen(pts, p)
    os.makedirs(os.path.join(pdir, 'print'), exist_ok=True)
    os.makedirs(os.path.join(pdir, 'out'), exist_ok=True)
    np.save(os.path.join(pdir, 'out', 'bahn.npy'), np.array([(x, y, z, {'boden': 0, 'wand': 1, 'welle': 2, 'rand': 3}[a])
                                                            for x, y, z, a in pts], dtype=np.float32))
    with open(os.path.join(pdir, 'print', 'bahn_koerper.gcode'), 'w', encoding='ascii') as f:
        f.write('; nicht-planare Bahn, nur Bewegungen (Start-/End-Code fehlt noch) - NICHT direkt drucken\n')
        f.write('M83\n' + '\n'.join(gcode_koerper(pts, p)) + '\n')
    erg['parameter'] = p
    json.dump(erg, open(os.path.join(pdir, 'out', 'bahn.pruefung.json'), 'w', encoding='utf-8'), indent=1,
              ensure_ascii=False)
    return erg
