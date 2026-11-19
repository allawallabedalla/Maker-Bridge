"""Gegentests fuer mb2/pruefungen/fem_plausi.py (F20-F25, M7-M9) und die neuen Mechanik-Felder in mb2/fem.py.
Jede Formel hat mindestens einen Handrechen-Gegentest. Aufruf aus maker-bridge-2/:
    .venv/Scripts/python.exe tests/test_pruef_fem_plausi.py
Kleine Koerper (Sekunden je CalculiX-Lauf). MB2_LANG=1 rechnet zusaetzlich den echten Taster-Fall (frag-mich-alles-
gehaeuse) in einer Kopie mit Netzstudie, Druckrichtung und Slicer-Daten (ca. 2-3 min)."""
import json
import math
import os
import shutil
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mb2 import fem                                   # noqa: E402
from mb2.material import MATERIAL                     # noqa: E402
from mb2.pruefungen import fem_plausi as fp           # noqa: E402

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJEKTE = ['testdose', 'schnapphaken', 'stifthalter-fem', 'frag-mich-alles-gehaeuse', 'bodenklima-sondenkopf']
TMP = tempfile.mkdtemp(prefix='mb2_fem_plausi_')


def projekt(name, faelle, soll=None, slice_json=None):
    d = os.path.join(TMP, name)
    os.makedirs(os.path.join(d, 'fem'), exist_ok=True)
    os.makedirs(os.path.join(d, 'cad'), exist_ok=True)
    for fall, spec in faelle.items():
        json.dump(spec, open(os.path.join(d, 'fem', fall + '.json'), 'w'))
    if soll:
        json.dump(soll, open(os.path.join(d, 'cad', 'soll.json'), 'w'))
    if slice_json:
        os.makedirs(os.path.join(d, 'print'), exist_ok=True)
        json.dump(slice_json, open(os.path.join(d, 'print', 'slice.json'), 'w'))
    return d


def nach_id(liste, id, teil=None):
    return [e for e in liste if e['id'] == id and (teil is None or e.get('teil') == teil)]


# Stab 40 x 4 x 4 mit Symmetrie-Lagern: exakte Loesung linear -> Tet10 trifft sie exakt
L, B = 40.0, 4.0
A = B * B
ZUG_SYM = [{'wo': {'ebene': ['x', 0]}, 'fest': 'x'}, {'wo': {'ebene': ['y', 0]}, 'fest': 'y'},
           {'wo': {'ebene': ['z', 0]}, 'fest': 'z'}]


def zug_spec(weg=0.125, **extra):
    s = {'koerper': [{'box': [0, 0, 0, L, B, B], 'material': 'PETG', 'name': 'stab'}], 'netz': {'groesse': 2.0},
         'name': 'zug', 'lagerung': ZUG_SYM + [{'wo': {'ebene': ['x', L]}, 'fest': 'x', 'weg': {'x': weg}}]}
    s.update(extra)
    return s


# ---------------------------------------------------------------- reine Formeln (ohne Loeser)

def test_tsai_hill_hand():
    X, Z = 45.0, 28.0
    sxy, sz = X / math.sqrt(3), Z / math.sqrt(3)
    # einachsig in Z (lokal 3): Index = (s/Z)^2
    assert abs(fp.tsai_hill_index([0, 0, 14, 0, 0, 0], X, Z, sxy, sz) - 0.25) < 1e-12
    # einachsig in der Ebene: (s/X)^2, auch um 30 Grad gedreht (drehinvariant)
    assert abs(fp.tsai_hill_index([22.5, 0, 0, 0, 0, 0], X, Z, sxy, sz) - 0.25) < 1e-12
    c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
    rot = [22.5 * c * c, 22.5 * s * s, 0, 22.5 * c * s, 0, 0]
    assert abs(fp.tsai_hill_index(rot, X, Z, sxy, sz) - 0.25) < 1e-12
    # Schub zwischen den Schichten tau13: (tau/S_z)^2
    assert abs(fp.tsai_hill_index([0, 0, 0, 0, 8.0, 0], X, Z, sxy, sz) - (8 / sz) ** 2) < 1e-12
    # Zug in der Ebene + Zug in Z gleichzeitig: Katalogform (Kreuzterm fehlt) ist hier massgebend
    kat = 10 ** 2 / X ** 2 + 10 ** 2 / Z ** 2
    assert abs(fp.tsai_hill_index([10, 0, 10, 0, 0, 0], X, Z, sxy, sz) - kat) < 1e-12
    # Zug in der Ebene + Druck in Z: volles Hill groesser: (a - s3)^2/Z^2 + R^2 (4/X^2 - 1/Z^2), a = R = 5
    hill = (5 + 10) ** 2 / Z ** 2 + 25 * (4 / X ** 2 - 1 / Z ** 2)
    assert abs(fp.tsai_hill_index([10, 0, -10, 0, 0, 0], X, Z, sxy, sz) - max(hill, kat)) < 1e-12
    assert hill > kat
    # Drehung global -> lokal: Zug in x, Druckrichtung x -> lokal s33
    loc = fp.drehe_voigt(np.array([7.0, 0, 0, 0, 0, 0]), [1, 0, 0])
    assert abs(loc[2] - 7.0) < 1e-12 and np.abs(loc[[0, 1, 3, 4, 5]]).max() < 1e-12
    S, e, p, info = fp.tsai_hill_sicherheit(np.array([[[7.0, 0, 0, 0, 0, 0]] * 4]), 'PETG', [1, 0, 0])
    assert abs(S - 28 / 7) < 1e-9                              # laengs Druckrichtung: Z / sigma, schubunabhaengig
    # Schubfestigkeit kleiner als X/sqrt(3) (z. B. X/2): ungunstigste Lage in der Ebene, Zug in der Ebene
    # a = R = s/2: Index = s^2/4 (1/X^2 + 4/X^2) = 1,25 s^2/X^2 -> Versagen bei X/sqrt(1,25) = 0,894 X
    assert abs(fp.tsai_hill_index([X / math.sqrt(1.25), 0, 0, 0, 0, 0], X, Z, X / 2, sz) - 1) < 1e-12


def test_richardson_hand():
    r = fp.richardson([1, 0.5, 0.25], [1 + 2 * h ** 2 for h in (1, 0.5, 0.25)])      # p = 2, f_inf = 1
    assert abs(r['p'] - 2) < 1e-9 and abs(r['f_inf'] - 1) < 1e-9
    r = fp.richardson([1, 0.7, 0.5], [1 + h ** 3 for h in (1, 0.7, 0.5)])             # ungleiche Verhaeltnisse
    assert abs(r['p'] - 3) < 1e-6 and abs(r['f_inf'] - 1) < 1e-6, r
    r = fp.richardson([1, 0.5, 0.25], [h ** -0.5 for h in (1, 0.5, 0.25)])            # Singularitaet: divergent
    assert r['p'] < 0 and r['f_inf'] is None
    r = fp.richardson([1, 0.5, 0.25], [1 + (-0.5) ** k for k in range(3)])            # oszillierend
    assert not r['monoton']
    assert fp.richardson([1, 0.5], [1, 2]) is None


def test_bewerte_konvergenz_hand():
    h = [1.0, 0.7, 0.5]
    d = {'energie_Nmm': [1 - 0.1 * x ** 4 for x in h], 'max_vonMises_MPa': [10 * x ** -0.4 for x in h],
         'verschiebung_lastrichtung_mm': [1 - 0.04 * x ** 3 for x in h], 'max_verschiebung_mm': [1, 1, 1],
         'ort_max_mm': [[0, 0, 0]] * 3}
    out = fp.bewerte_konvergenz('t', h, d, 0)
    st = {(e['id'], e['titel']): e['stufe'] for e in out}
    assert st[('F20', 'Netzkonvergenz')] == 'ok'
    # Hand: f_inf = 1, Hauptnetz (h = 1) 0,96 -> Fehler 4 % < 5 % -> ok
    f21u = [e for e in out if e['titel'] == 'Richardson Verschiebung'][0]
    assert abs(f21u['wert'] - 4.0) < 1e-6 and f21u['stufe'] == 'ok', f21u
    d['verschiebung_lastrichtung_mm'] = [1 - 0.06 * x ** 3 for x in h]   # 6 % -> warnung
    f21u = [e for e in fp.bewerte_konvergenz('t', h, d, 0) if e['titel'] == 'Richardson Verschiebung'][0]
    assert abs(f21u['wert'] - 6.0) < 1e-6 and f21u['stufe'] == 'warnung'
    assert st[('F22', 'Singularitaet')] == 'warnung'           # sigma ~ h^-0.4 waechst, Energie konvergiert


def test_elastizitaet_hand():
    E, nu = 2000.0, 0.38
    C = fem.elastizitaet(E, nu)
    eps = np.linalg.solve(C, [10, 0, 0, 0, 0, 0])
    assert abs(eps[0] - 10 / E) < 1e-12 and abs(eps[1] + nu * 10 / E) < 1e-12
    o = {'E_z': 1000.0, 'G_z': 400.0, 'nu_z': nu, 'richtung': [1.0, 0, 0]}   # Aufbaurichtung = global x
    Co = fem.elastizitaet(E, nu, o)
    eps = np.linalg.solve(Co, [10, 0, 0, 0, 0, 0])
    assert abs(eps[0] - 10 / 1000) < 1e-12                     # Zug laengs Aufbaurichtung: E_z
    assert abs(eps[1] + nu * 10 / E) < 1e-12                   # Querdehnung: nu_31 = nu * E_z / E
    eps = np.linalg.solve(Co, [0, 0, 0, 0, 5, 0])              # Gleitung xz liegt zwischen den Schichten
    assert abs(eps[4] - 5 / 400) < 1e-12
    assert np.allclose(Co, Co.T)
    # Ortho mit E_z = E, G_z = E/(2(1+nu)) = isotrop
    oi = dict(o, E_z=E, G_z=E / (2 * (1 + nu)), richtung=[0.3, 0.4, 0.866])
    assert np.allclose(fem.elastizitaet(E, nu, oi), C, atol=1e-8)


def test_f23_f25_synthetisch():
    g = {'reaktion_N': [-100, 0, 0], 'last_N': [99, 0, 0], 'reaktion_moment_Nmm': [0, 0, 0],
         'last_moment_Nmm': [0, 0, 0], 'laenge_mm': 40, 'reaktion_je_lager_N': [[-100, 0, 0]]}
    e = fp._f23('t', {'gleichgewicht': g})
    assert e['stufe'] == 'warnung' and abs(e['wert'] - 1.0) < 1e-9       # 1 N von 100 N fehlt
    g['last_N'] = [50, 0, 0]
    assert fp._f23('t', {'gleichgewicht': g})['stufe'] == 'fehler'
    g['last_N'], g['last_moment_Nmm'] = [100, 0, 0], [0, 0, 1.0]           # 1 Nmm / (100 N * 40 mm) = 0,025 %
    e = fp._f23('t', {'gleichgewicht': g})
    assert e['stufe'] == 'ok' and abs(e['daten']['moment_prozent'] - 0.025) < 1e-9
    assert fp._f23('t', {})['stufe'] == 'uebersprungen'
    MATERIAL['TPU_TEST'] = {'E_MPa': 30.0, 'nu': 0.48}
    try:
        assert fp._f25('f', {'koerper': [{'material': 'TPU_TEST'}]})[0]['stufe'] == 'warnung'
        assert fp._f25('f', {'koerper': [{'material': 'PETG'}]})[0]['stufe'] == 'ok'
    finally:
        del MATERIAL['TPU_TEST']


def test_durchdringung_synthetisch():
    spec = {'koerper': [{'box': [0, 0, -2, 4, 4, 0], 'material': 'STARR', 'name': 'unten'},
                        {'box': [0, 0, 0, 4, 4, 2], 'material': 'PETG', 'name': 'oben'}],
            'verbinden': False, 'netz': {'groesse': 1.0}}
    kn, tets, kp, namen, _ = fem.netz(TMP, spec, 2)
    rand = fem.randflaechen(tets)
    u = np.zeros_like(kn)
    oben = np.unique(tets[kp == 1])
    u[oben, 2] = -0.01                                  # Oberer Block 0,01 mm in den unteren geschoben
    kt = {'slave': {'ebene': ['z', 0.0], 'koerper': 'oben'}, 'master': {'ebene': ['z', 0.0], 'koerper': 'unten'}}
    r = fem._durchdringung(kn, u, tets, kp, namen, rand, kt)
    assert abs(r['durchdringung_max_mm'] - 0.01) < 1e-9, r
    assert 0.5 < r['element_mm'] < 1.5 and r['knoten_durchdrungen'] == r['slave_knoten']
    u[oben, 2] = +0.01                                  # abgehoben: keine Durchdringung
    assert fem._durchdringung(kn, u, tets, kp, namen, rand, kt)['durchdringung_max_mm'] == 0.0


def test_sta_cvg_schnapphaken():
    """Echte Ausgabe des Schnapphaken-Kontaktlaufs lesen (nur lesen, nichts rechnen)."""
    job = os.path.join(HIER, 'projects', 'schnapphaken', 'fem', 'montage', 'lauf_montage')
    if not os.path.exists(job + '.sta'):
        print('  (schnapphaken/montage nicht gerechnet - uebersprungen)')
        return
    r = fem._lies_sta_cvg(job)
    assert r['inkremente'] == 14 and abs(r['zeit_erreicht'] - 1.0) < 1e-9 and r['abbrueche'] == 0
    assert r['iterationen_max'] == 10 and r['letzte_iteration']['korrektur_weg_prozent'] < 1e-3
    # Durchdringung aus dem echten Endzustand (Netz neu erzeugen, .dat lesen): Grat r 0,6, Element ~0,12 mm
    from mb2.befehle import pdir
    d = pdir('schnapphaken')
    spec = json.load(open(os.path.join(d, 'fem', 'montage.json'), encoding='utf-8'))
    kn, tets, kp, namen, _ = fem.netz(d, spec, 2)
    u = fem._lies_dat(job + '.dat', len(kn))[0][-1]
    k = fem._durchdringung(kn, u, tets, kp, namen, fem.randflaechen(tets), spec['kontakt'][0])
    print('   Schnapphaken-Kontakt:', k)
    assert 0 < k['durchdringung_max_mm'] < 0.05 and 0.08 < k['element_mm'] < 0.2


# ---------------------------------------------------------------- mit CalculiX (kleine Koerper)

def test_zug_isotrop_gleichgewicht_energie_m7_m9():
    d = projekt('zug', {'zug': zug_spec(druckrichtung='z')},
                slice_json={'stats': {'fill_density': '20%', 'nozzle_diameter': '0.4', 'layer_height': '0.2'},
                            'perimeter': 2})
    e = fem.mechanik(d, 'zug')
    r = e['lastfaelle']['zug']
    # Hand: sigma = E * w / L = 2000 * 0.125 / 40 = 6,25 MPa, F = sigma * A = 100 N, Energie = F w / 2 = 6,25 Nmm
    assert abs(r['kraft_in_wegrichtung_N'] - 100.0) < 0.01, r['kraft_in_wegrichtung_N']
    assert abs(r['max_vonMises_MPa'] - 6.25) < 0.01
    assert abs(r['energie_Nmm'] - 6.25) < 0.001, r['energie_Nmm']
    f = np.load(r['spannungsfeld'])
    assert np.allclose(f['tensor'][..., 0], 6.25, atol=1e-3) and np.abs(f['tensor'][..., 1:]).max() < 1e-3
    # M7 mit Druckrichtung z (Zug in der Ebene), a = R = sigma/2:
    #   Katalog a^2/X^2 + R^2 max(3/X^2, 1/S_xy^2), Hill sigma^2/X^2 -> bei S_xy = X/sqrt(3): S = X/sigma = 7,2
    X, Z, sxy, sz, _ = fp.festigkeiten('PETG')
    idx = max(3.125 ** 2 / X ** 2 + 3.125 ** 2 * max(3 / X ** 2, 1 / sxy ** 2), 6.25 ** 2 / X ** 2)
    S_hand = 1 / math.sqrt(idx)
    assert abs(r['tsai_hill']['sicherheit'] / S_hand - 1) < 1e-3, (r['tsai_hill'], S_hand)
    assert abs(e['bewertung']['min_sicherheit_tsai_hill'] - round(S_hand, 2)) < 0.011
    out = fp.pruefe(d)
    f23 = nach_id(out, 'F23')[0]
    assert f23['stufe'] == 'ok' and f23['wert'] < 1e-3, f23
    assert nach_id(out, 'M7')[0]['stufe'] == 'ok' and abs(nach_id(out, 'M7')[0]['wert'] / S_hand - 1) < 1e-3
    # M9: 20 % Fuellung, Schale 2 x 0,45 = 0,9 mm; Kern traegt 6,25 MPa gegen 0,3 * 0,2^1,5 * 28 = 0,7513 MPa
    # -> S = 0,12 < 1: seit Audit 15.11.2026 'fehler' (vorher hoechstens warnung)
    m9 = nach_id(out, 'M9')[0]
    soll = 0.3 * 0.2 ** 1.5 * 28 / 6.25
    assert m9['stufe'] == 'fehler' and abs(m9['wert'] - soll) < 1e-3, (m9, soll)
    assert abs(m9['daten']['schale_mm'] - 0.9) < 1e-9 and abs(m9['daten']['E_faktor'] - 0.04) < 1e-9
    assert nach_id(out, 'M8')[0]['stufe'] == 'uebersprungen'
    assert nach_id(out, 'F25')[0]['stufe'] == 'ok'
    assert nach_id(out, 'F20')[0]['stufe'] == 'uebersprungen'
    spec_falsch = zug_spec(druckrichtung='oben')                     # ungueltig -> kein Absturz, M7 uebersprungen
    d3 = projekt('zug_falsch', {'zug': spec_falsch})
    fem.mechanik(d3, 'zug')
    assert nach_id(fp.pruefe(d3), 'M7')[0]['stufe'] == 'uebersprungen'
    # Druckrichtung x aus soll.json (Zug quer zu den Schichten): S = Z / sigma = 28 / 6,25 = 4,48
    spec = zug_spec()
    json.dump(spec, open(os.path.join(d, 'fem', 'zug.json'), 'w'))
    json.dump({'stab': {'druckrichtung': 'x'}}, open(os.path.join(d, 'cad', 'soll.json'), 'w'))
    fem.mechanik(d, 'zug')
    m7 = nach_id(fp.pruefe(d), 'M7')[0]
    assert abs(m7['wert'] / 4.48 - 1) < 1e-3 and 'soll.json' in m7['hinweis'], m7


def test_m9_ungesliced_standardprofil():
    """Ohne print/slice.json: Standardprofil 0.20mm SPEED @MK4IS 0.4 = 15 % Fuellung, 2 Perimeter x 0,45, Decklagen
    min(5, 3) x 0,2 -> Schale min(0,9, 0,6) = 0,6 mm; Kernfestigkeit 0,3 * 0,15^1,5 * 28 = 0,48799 MPa.
      Weg 0,125: sigma 6,25 -> S = 0,0781 < 1 -> fehler (vorher 'uebersprungen')
      Weg 0,004: sigma = 2000*0,004/40 = 0,2 MPa -> S = 2,44 >= 2 -> rechnerisch ok, Profil angenommen -> warnung"""
    sk = 0.3 * 0.15 ** 1.5 * 28
    for weg, sigma, stufe in ((0.125, 6.25, 'fehler'), (0.004, 0.2, 'warnung')):
        d = projekt(f'zug_ungesliced_{weg}', {'zug': zug_spec(weg=weg)})
        fem.mechanik(d, 'zug')
        m9 = nach_id(fp.pruefe(d), 'M9')[0]
        assert m9['stufe'] == stufe and abs(m9['wert'] / (sk / sigma) - 1) < 2e-3, (weg, m9, sk / sigma)
        assert abs(m9['daten']['schale_mm'] - 0.6) < 1e-9 and m9['daten']['profil_angenommen'] is True, m9
        assert '0.20mm SPEED @MK4IS 0.4' in m9['hinweis']


def test_m7_druckrichtung_aus_cad_druck_drehung():
    """Kein druckrichtung in Lastfall/soll, aber out/stab.pruefung.json druck_drehung (0, 90, 0): Schichtnormale =
    Teil-x (Stabachse) -> Zug quer zu den Schichten: S = Z / sigma = 28 / 6,25 = 4,48 (vorher 'uebersprungen')."""
    d = projekt('zug_cad', {'zug': zug_spec()})
    os.makedirs(os.path.join(d, 'out'), exist_ok=True)
    json.dump({'druck_drehung': [0, 90, 0]}, open(os.path.join(d, 'out', 'stab.pruefung.json'), 'w'))
    fem.mechanik(d, 'zug')
    m7 = nach_id(fp.pruefe(d), 'M7')[0]
    assert m7['stufe'] == 'ok' and abs(m7['wert'] / 4.48 - 1) < 1e-3 and 'druck_drehung' in m7['hinweis'], m7


def test_bewertung_realterme_hand():
    """fem.bewertung_mech teilt S_z durch f aus realterme (Rohwert bleibt in min_sicherheit_z).
    (a) PETG, T_max 23, innen, dauerlast false: A_T 1 (Tg 78 - 23 = 55 K), f = 1 -> S 6,0 ok (keine Annahme).
    (b) wie (a), Dauer unbekannt: A_K 1,7 angenommen -> 6,0/1,7 = 3,53 >= 2, ok=True, stufe warnung.
    (c) PLA, T_max 40, dauerlast true: A_T = 1 + (30 - 17)*0,04 = 1,52, f = 1,52*1,7 = 2,584
        -> S 4,0/2,584 = 1,548 < 2 -> ok False, stufe warnung (vorher ok mit S 4 >= 2).
    (d) ohne Kontext: PETG, Luft 30 C angenommen (A_T 1), Dauer angenommen -> f 1,7, stufe hoechstens warnung."""
    lf = {'a': {'sicherheit': {'PETG': {'xy': 9.0, 'z': 6.0}, 'PLA': {'xy': 5.0, 'z': 4.0}}}}
    k = {'T_max_C': 23, 'aussen': False}
    bw = fem.bewertung_mech(lf, ['PETG'], kontext=k, dauer={'a': False})
    assert bw['ok'] and bw['stufe'] == 'ok' and bw['min_sicherheit_z_wirksam'] == 6.0 and not bw['angenommen'], bw
    bw = fem.bewertung_mech(lf, ['PETG'], kontext=k, dauer={})
    assert bw['ok'] and bw['stufe'] == 'warnung' and bw['min_sicherheit_z_wirksam'] == round(6 / 1.7, 2), bw
    assert bw['min_sicherheit_z'] == 6.0 and 'A_K' in bw['hinweis']
    bw = fem.bewertung_mech(lf, ['PLA'], kontext={'T_max_C': 40, 'aussen': False}, dauer={'a': True})
    assert abs(bw['abminderung'] - 2.584) < 1e-3 and bw['min_sicherheit_z_wirksam'] == round(4 / 2.584, 2), bw
    assert bw['ok'] is False and bw['stufe'] == 'warnung', bw
    bw = fem.bewertung_mech(lf, ['PETG'])
    assert bw['angenommen'] and bw['stufe'] == 'warnung' and abs(bw['abminderung'] - 1.7) < 1e-9, bw
    # Tsai-Hill wird ebenso abgemindert: 3,0 / 1,7 = 1,76 < 2 -> nicht ok
    lf['a']['tsai_hill'] = {'sicherheit': 3.0, 'material': 'PETG'}
    bw = fem.bewertung_mech(lf, ['PETG'], kontext=k, dauer={})
    assert bw['min_sicherheit_tsai_hill'] == 3.0 and bw['min_sicherheit_tsai_hill_wirksam'] == round(3 / 1.7, 2)
    assert bw['ok'] is False and bw['stufe'] == 'warnung', bw


def test_dauerlast_je_lastfall():
    spec = {'kurzzeit': True, 'lasten': [{'name': 'druck', 'kraft_N': [0, 0, -1]},
                                         {'name': 'halten', 'dauerlast': True, 'kraft_N': [0, 0, -1]}]}
    d = fem.dauerlast_je_lastfall(spec, ['druck', 'halten', 'eigengewicht'])
    assert d == {'druck': False, 'halten': True, 'eigengewicht': False}, d       # fallweit kurzzeit gilt auch fuers Gewicht
    d = fem.dauerlast_je_lastfall({}, ['x', 'eigengewicht'], {'deckel': {'dauerlast': {'fem': 'f/x'}}}, 'f')
    assert d == {'x': True, 'eigengewicht': True}, d
    assert fem.dauerlast_je_lastfall({}, ['x'])['x'] is None


def test_zug_orthotrop_m8():
    """Aufbaurichtung = Stabachse x, E_z = 1000: sigma = E_z * w / L = 3,125 MPa, F = 50 N; Querdehnung
    eps_y = -nu * sigma / E (nu_31 = nu E_z / E) -> u_y(y = 4) = -0,38 * 3,125 / 2000 * 4 = -0,002375 mm."""
    d = projekt('ortho', {'zug': zug_spec(druckrichtung='x', orthotrop={'E_z_MPa': 1000.0, 'G_MPa': 400.0})})
    e = fem.mechanik(d, 'zug')
    r = e['lastfaelle']['zug']
    assert abs(r['kraft_in_wegrichtung_N'] - 50.0) < 0.01, r['kraft_in_wegrichtung_N']
    assert abs(r['max_vonMises_MPa'] - 3.125) < 0.005, r['max_vonMises_MPa']
    assert e['orthotrop']['stab']['E_z'] == 1000.0
    spec = zug_spec(druckrichtung='x', orthotrop={'E_z_MPa': 1000.0, 'G_MPa': 400.0})
    kn, tets, kp, namen, _ = fem.netz(d, spec, 2)
    u = fem._lies_dat(os.path.join(d, 'fem', 'zug', 'lauf.dat'), len(kn))[0][0]
    rand_y = np.abs(kn[:, 1] - B) < 1e-9
    assert abs(u[rand_y, 1].mean() + 0.38 * 3.125 / 2000 * 4) < 2e-6, u[rand_y, 1].mean()
    out = fp.pruefe(d)
    assert nach_id(out, 'M8')[0]['stufe'] == 'info'
    assert abs(nach_id(out, 'M7')[0]['wert'] / (28 / 3.125) - 1) < 1e-3  # Z / sigma = 8,96
    assert nach_id(out, 'F23')[0]['stufe'] == 'ok'
    # orthotrop ohne Werte (kennwerte.py: E_z unbekannt) -> isotrop gerechnet + Hinweis, M8 warnt
    d2 = projekt('ortho_leer', {'zug': zug_spec(druckrichtung='x', orthotrop=True)})
    e2 = fem.mechanik(d2, 'zug')
    from mb2 import kennwerte
    if kennwerte.wert('PETG', 'E_z_MPa') is None:
        assert abs(e2['lastfaelle']['zug']['kraft_in_wegrichtung_N'] - 100.0) < 0.01
        assert any('E_z unbekannt' in h for h in e2['hinweise'])
        assert nach_id(fp.pruefe(d2), 'M8')[0]['stufe'] == 'warnung'


def test_kragarm_schwerkraft_rayleigh():
    """Kragarm 60 x 4 x 4 PETG unter 1 g. Hand: q = rho A g = 1,27e-9 * 16 * 9810 = 1,9934e-4 N/mm,
    w_max = q L^4 / (8 E I) = 0,007569 mm; f1 = 1,875^2/(2 pi) * sqrt(E I / (rho A L^4)) = 225,2 Hz."""
    Lk = 60.0
    spec = {'koerper': [{'box': [0, 0, 0, Lk, B, B], 'material': 'PETG', 'name': 'arm'}], 'netz': {'groesse': 1.0},
            'lagerung': [{'wo': {'ebene': ['x', 0]}, 'fest': 'xyz'}], 'schwerkraft': True}
    d = projekt('kragarm', {'g': spec})
    e = fem.mechanik(d, 'g')
    r = e['lastfaelle']['eigengewicht']
    E, I, rho = 2000.0, B ** 4 / 12, 1270e-12
    q = rho * A * 9810
    w = q * Lk ** 4 / (8 * E * I)
    f1 = 1.875 ** 2 / (2 * math.pi) * math.sqrt(E * I / (rho * A * Lk ** 4))
    assert abs(e['masse_kg'] / (rho * A * Lk * 1000) - 1) < 1e-3, e['masse_kg']
    assert abs(r['durchbiegung_g_richtung_max_mm'] / w - 1) < 0.04, (r['durchbiegung_g_richtung_max_mm'], w)
    assert abs(r['rayleigh_f1_Hz'] / f1 - 1) < 0.04, (r['rayleigh_f1_Hz'], f1)
    g = r['gleichgewicht']
    assert abs(g['last_gesamt_N'][2] / (-q * Lk) - 1) < 1e-5, (g['last_gesamt_N'], q * Lk)
    assert nach_id(fp.pruefe(d), 'F23')[0]['stufe'] == 'ok'


def test_konvergenz_f20_f22():
    """Kragarm 40 x 4 x 4, Ende per Wegvorgabe 1 mm gebogen. Hand (Euler-Bernoulli): F = 3 E I w / L^3
    = 3 * 2000 * 21,33 * 1 / 64000 = 2,0 N. Reaktion konvergiert (F21 ok); an der Einspannkante ist sigma
    singulaer (F22 Warnung/Info). Zug-Stab: exakt linear -> keine Singularitaet (F22 ok, F21 'Werte gleich').
    Zusaetzlich Kraftlast: Weg an der Lastflaeche (Knotenlasten = Punktlasten) - nur ausgeben."""
    konv = {'faktoren': [1.0, 0.7, 0.5]}
    arm = {'koerper': [{'box': [0, 0, 0, L, B, B], 'material': 'PETG', 'name': 'arm'}], 'netz': {'groesse': 2.0},
           'konvergenz': konv}
    weg = dict(arm, name='biegen', lagerung=[{'wo': {'ebene': ['x', 0]}, 'fest': 'xyz'},
                                              {'wo': {'ebene': ['x', L]}, 'fest': '', 'weg': {'z': -1.0}}])
    kraft = dict(arm, lagerung=[{'wo': {'ebene': ['x', 0]}, 'fest': 'xyz'}],
                 lasten=[{'name': 'quer', 'wo': {'ebene': ['x', L]}, 'kraft_N': [0, 0, -2.0]}])
    # L-Winkel mit scharfer Innenecke (270 Grad): sigma ~ r^-0,46 (Williams) -> waechst je Halbierung um ~37 %
    winkel = {'koerper': [{'box': [0, 0, 0, 20, 4, 4], 'material': 'PETG', 'name': 'arm'},
                          {'box': [0, 0, -16, 4, 4, 0], 'material': 'PETG', 'name': 'pfosten'}],
              'netz': {'groesse': 1.0}, 'konvergenz': konv, 'name': 'biegen',
              'lagerung': [{'wo': {'ebene': ['z', -16]}, 'fest': 'xyz'},
                           {'wo': {'ebene': ['x', 20]}, 'fest': '', 'weg': {'z': -0.2}}]}
    d = projekt('konv', {'k': weg, 'f': kraft, 'z': zug_spec(konvergenz=konv), 'w': winkel})
    e = fem.mechanik(d, 'k')
    k = e['konvergenz']
    assert k['faktoren'] == [1.0, 0.7, 0.5] and k['tetraeder'][0] < k['tetraeder'][1] < k['tetraeder'][2]
    Fw = k['lastfaelle']['biegen']['kraft_weg_N']
    assert abs(Fw[-1] / 2.0 - 1) < 0.05, Fw
    E_ = k['lastfaelle']['biegen']['energie_Nmm']
    assert E_[0] >= E_[1] >= E_[2], E_                 # Wegvorgabe: Energie faellt mit Verfeinerung (zu steif -> weicher)
    assert abs(E_[0] - 0.5 * Fw[0] * 1.0) < 1e-3 * E_[0]  # Energie = F w / 2
    fem.mechanik(d, 'z')
    fem.mechanik(d, 'f')
    fem.mechanik(d, 'w')
    out = fp.pruefe(d)
    st = {(e['teil'], e['id'], e['titel']): e for e in out}
    assert st[('k/biegen', 'F20', 'Netzkonvergenz')]['stufe'] == 'ok', st[('k/biegen', 'F20', 'Netzkonvergenz')]
    f21 = st[('k/biegen', 'F21', 'Richardson Kraft')]
    assert f21['stufe'] in ('ok', 'info') and f21['wert'] < 5, f21     # Kraft aendert sich < 0,3 %
    assert st[('k/biegen', 'F22', 'Singularitaet')]['stufe'] != 'fehler'   # Einspannkante: schwach singulaer
    w22 = st[('w/biegen', 'F22', 'Singularitaet')]
    assert w22['stufe'] == 'warnung' and abs(w22['daten']['ort_mm'][0] - 4) < 0.6 and abs(w22['daten']['ort_mm'][2]) < 0.6, w22
    assert st[('z/zug', 'F22', 'Singularitaet')]['stufe'] == 'ok', st[('z/zug', 'F22', 'Singularitaet')]
    assert st[('z/zug', 'F21', 'Richardson Kraft')]['stufe'] == 'ok'
    for key in (('k/biegen', 'F21', 'Richardson Kraft'), ('k/biegen', 'F22', 'Singularitaet'),
                ('f/quer', 'F20', 'Netzkonvergenz'), ('f/quer', 'F21', 'Richardson Verschiebung'),
                ('w/biegen', 'F22', 'Singularitaet'), ('w/biegen', 'F21', 'Richardson Spannung')):
        print('  ', key, st[key]['stufe'], st[key]['hinweis'][:120])


def test_kontakt_f24():
    """Zwei Bloecke 4 x 4 (PETG 4 hoch auf Symmetrie-Lagern, STARR 2 hoch darauf), STARR 0,01 mm nach unten.
    Hand (Reihenschaltung Block + Penalty k = 500 N/mm3): sigma (h/E + 1/k) = 0,01 -> sigma = 2,5 MPa,
    F = sigma A = 40 N, Durchdringung = sigma / k = 0,005 mm."""
    spec = {'koerper': [{'box': [0, 0, 0, 4, 4, 4], 'material': 'PETG', 'name': 'block'},
                        {'box': [0, 0, 4, 4, 4, 6], 'material': 'STARR', 'name': 'stempel'}],
            'verbinden': False, 'netz': {'groesse': 1.0}, 'name': 'druck',
            'lagerung': [{'wo': {'ebene': ['z', 0]}, 'fest': 'z'},
                         {'wo': {'ebene': ['x', 0], 'koerper': 'block'}, 'fest': 'x'},
                         {'wo': {'ebene': ['y', 0], 'koerper': 'block'}, 'fest': 'y'},
                         {'wo': {'ebene': ['z', 6], 'koerper': 'stempel'}, 'fest': 'xy', 'weg': {'z': -0.01}}],
            'kontakt': [{'slave': {'ebene': ['z', 4], 'koerper': 'block'},
                         'master': {'ebene': ['z', 4], 'koerper': 'stempel'}, 'steifigkeit_N_mm3': 500}],
            'nichtlinear': True}
    d = projekt('kontakt', {'druck': spec})
    e = fem.mechanik(d, 'druck')
    r = e['lastfaelle']['druck']
    assert abs(-r['reaktionskraft_N'][0][2] - 40.0) / 40 < 0.03, r['reaktionskraft_N']
    k = r['kontakt'][0]
    assert abs(k['durchdringung_max_mm'] - 0.005) < 0.0005, k
    assert abs(r['newton']['zeit_erreicht'] - 1.0) < 1e-9
    out = fp.pruefe(d)
    st = {(x['id'], x['titel']): x for x in out}
    assert st[('F24', 'Newton-Konvergenz')]['stufe'] in ('ok', 'info')
    # Katalog: Durchdringung < 1 % Element (0,0074 mm bei 0,74 mm) und < 0,05 mm -> 0,005 mm ok
    assert st[('F24', 'Kontakt-Durchdringung Paar 0')]['stufe'] == 'ok', st[('F24', 'Kontakt-Durchdringung Paar 0')]
    assert st[('F23', 'Gleichgewicht')]['stufe'] == 'ok', st[('F23', 'Gleichgewicht')]


# ---------------------------------------------------------------- echte Projekte

def test_echte_projekte_kein_absturz():
    for p in PROJEKTE:
        d = os.path.join(HIER, 'projects', p)
        out = fp.pruefe(d)
        for e in out:
            assert e['id'] in ('F20', 'F21', 'F22', 'F23', 'F24', 'F25', 'M7', 'M8', 'M9'), e
            assert e['quelle'] and e['stufe'] in ('ok', 'info', 'warnung', 'fehler', 'uebersprungen')
            assert e['stufe'] != 'uebersprungen' or e['hinweis']
        z = {s: sum(1 for e in out if e['stufe'] == s) for s in ('ok', 'info', 'warnung', 'fehler', 'uebersprungen')}
        print(f'   {p}: {len(out)} Ergebnisse {z}')


def test_taster_echt_lang():
    """Echter Fall frag-mich-alles-gehaeuse/taster in einer Kopie (Projekt bleibt unberuehrt)."""
    if os.environ.get('MB2_LANG') != '1':
        print('   (MB2_LANG=1 fuer den langen Lauf)')
        return
    q = os.path.join(HIER, 'projects', 'frag-mich-alles-gehaeuse')
    d = os.path.join(TMP, 'fma')
    for sub in ('fem', 'out', 'cad', 'print'):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    shutil.copy(os.path.join(q, 'out', 'front.step'), os.path.join(d, 'out'))
    shutil.copy(os.path.join(q, 'print', 'slice.json'), os.path.join(d, 'print'))
    spec = json.load(open(os.path.join(q, 'fem', 'taster.json'), encoding='utf-8'))
    spec['konvergenz'] = {'faktoren': [1.0, 0.8, 0.64]}
    json.dump(spec, open(os.path.join(d, 'fem', 'taster.json'), 'w'))
    json.dump({'front': {'druckrichtung': 'z'}}, open(os.path.join(d, 'cad', 'soll.json'), 'w'))
    ep = os.path.join(q, 'fem', 'taster.erg.json')
    e = fem.mechanik(d, 'taster')
    if os.path.getmtime(os.path.join(q, 'out', 'front.step')) < os.path.getmtime(ep):
        alt = json.load(open(ep, encoding='utf-8'))
        for lf in ('von_aussen', 'von_innen'):              # bisherige Werte unveraendert
            assert e['lastfaelle'][lf]['max_vonMises_MPa'] == alt['lastfaelle'][lf]['max_vonMises_MPa']
            assert e['lastfaelle'][lf]['federrate_N_mm'] == alt['lastfaelle'][lf]['federrate_N_mm']
        # seit Audit 15.11.2026 hat bewertung neue Schluessel (wirksame Sicherheit, Realterme) - Rohwerte gleich
        for key in ('min_sicherheit_z', 'min_sicherheit_tsai_hill', 'material'):
            assert e['bewertung'].get(key) == alt['bewertung'].get(key), key
    else:
        print('   (front.step neuer als taster.erg.json - Altwert-Vergleich entfaellt)')
    for x in fp.pruefe(d):
        print(f"   {x['teil']:22s} {x['id']} {x['titel'][:28]:28s} {x['stufe']:10s} {x['wert']}  {x['hinweis'][:110]}")


if __name__ == '__main__':
    fehl = 0
    try:
        for n, f in list(globals().items()):
            if n.startswith('test_'):
                try:
                    f()
                    print('ok', n)
                except Exception as ex:  # noqa: BLE001
                    fehl += 1
                    import traceback
                    traceback.print_exc()
                    print('FEHLER', n, type(ex).__name__, ex)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print('ALLE OK' if not fehl else f'{fehl} FEHLER')
    sys.exit(1 if fehl else 0)
