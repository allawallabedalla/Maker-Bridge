"""Plausibilitaet der Werkstoff-Kennwerte (mb2/kennwerte.py). Als Skript laufen lassen:
    .venv\\Scripts\\python.exe tests/test_kennwerte.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from mb2 import kennwerte as kw  # noqa: E402
from mb2.material import MATERIAL, DRUCKSTOFFE  # noqa: E402

# Groessenordnungen (unter, ober) fuer unverstaerkte Thermoplaste, gedruckt
BEREICH = {
    'eps_zul_xy': (0.003, 0.05), 'eps_zul_z': (0.002, 0.03), 'eps_dauer': (0.001, 0.02),
    'alpha_1_K': (30e-6, 150e-6), 'cp_J_kgK': (900.0, 2200.0),
    'E_z_MPa': (500.0, 4000.0), 'G_MPa': (200.0, 1500.0),
    'schub_xy_MPa': (5.0, 50.0), 'schub_z_MPa': (3.0, 40.0), 'druck_MPa': (15.0, 120.0),
    'kriech_E_inf_zu_E0': (0.1, 1.0), 'kriech_tau_h': (0.1, 1e6), 'kriechmodul_1000h_MPa': (200.0, 3500.0),
    'aktivierung_U_kJ_mol': (40.0, 500.0), 'S_e_MPa': (1.0, 40.0), 'mu': (0.05, 0.8),
    'K_IC_MPa_sqrtm': (0.5, 6.0), 'emission': (0.8, 0.99), 'schwindung': (0.0, 0.02),
    'streuung_xy': (0.01, 0.3), 'streuung_z': (0.02, 0.4),
}
ok = 0


def pruef(bed, text):
    global ok
    assert bed, text
    ok += 1


# 1) Struktur: jeder Druckstoff hat jedes Feld (Wert-Tupel oder None), jeder Wert eine Quelle mit Herkunft
for m in DRUCKSTOFFE:
    e = kw.KENNWERTE[m]
    for f in kw.FELDER:
        pruef(f in e, f'{m}.{f} fehlt im Eintrag (None statt Weglassen)')
        v = e[f]
        if v is None:
            pruef(kw.wert(m, f) is None and f in kw.OFFEN, f'{m}.{f} None ohne Grund in OFFEN')
            continue
        w, q = v
        pruef(isinstance(w, float) and math.isfinite(w), f'{m}.{f} kein float')
        pruef(isinstance(q, str) and q.startswith('[') and len(q) > 25, f'{m}.{f} Quelle fehlt/zu kurz')
        lo, hi = BEREICH[f]
        pruef(lo <= w <= hi, f'{m}.{f} = {w} ausserhalb Groessenordnung {lo}..{hi}')
    for f in e:
        pruef(f in kw.FELDER, f'{m}: unbekanntes Feld {f}')

# 2) Physik: Richtungen und Zusammenhaenge
for m in DRUCKSTOFFE:
    g = lambda f: kw.wert(m, f)  # noqa: E731
    M = MATERIAL[m]
    pruef(g('eps_zul_z') < g('eps_zul_xy'), f'{m}: eps_z >= eps_xy')
    pruef(g('eps_dauer') < g('eps_zul_xy'), f'{m}: eps_dauer >= eps_xy')
    pruef(g('E_z_MPa') <= M['E_MPa'], f'{m}: E_z > E_xy')
    pruef(g('schub_z_MPa') < g('schub_xy_MPa'), f'{m}: tau_z >= tau_xy')
    pruef(g('schub_xy_MPa') < M['festigkeit_xy_MPa'], f'{m}: tau_xy >= sigma_xy')
    pruef(g('streuung_z') > g('streuung_xy'), f'{m}: Streuung Z <= XY')
    # G nicht groesser als isotrop aus material.py
    pruef(g('G_MPa') <= M['E_MPa'] / (2 * (1 + M['nu'])) + 1, f'{m}: G > E/(2(1+nu))')
    # zulaessige Dehnung * E darf die Festigkeit nicht wesentlich uebersteigen (sonst Bruch vor eps_zul)
    pruef(g('eps_zul_z') * g('E_z_MPa') <= M['festigkeit_z_MPa'], f'{m}: eps_z * E_z > sigma_z')
    pruef(g('eps_zul_xy') * M['E_MPa'] <= 1.1 * M['festigkeit_xy_MPa'], f'{m}: eps_xy * E > sigma_xy')
    pruef(g('S_e_MPa') is None or g('S_e_MPa') < M['festigkeit_z_MPa'], f'{m}: S_e >= sigma_z')
    pruef(g('kriechmodul_1000h_MPa') is None or g('kriechmodul_1000h_MPa') < M['E_MPa'], f'{m}: E_1000h >= E0')
    pruef(kw.vorlaeufig(m, 'schwindung') and not kw.vorlaeufig(m, 'alpha_1_K'), f'{m}: vorlaeufig falsch')
# ASA dehnt sich am staerksten (Rangfolge D10 Verzug)
pruef(kw.wert('ASA', 'alpha_1_K') > kw.wert('PETG', 'alpha_1_K'), 'alpha ASA <= PETG')
pruef(kw.wert('ASA', 'schwindung') > kw.wert('PLA', 'schwindung'), 'Schwindung ASA <= PLA')

# 3) Handrechen-Gegentests der Herleitungen
# G = E/(2(1+nu)): PLA 2300/(2*1,36) = 845,6 -> 845; PETG 1500/2,76 = 543,5 -> 540; ASA 2000/2,70 = 740,7 -> 740
for m, E, nu, soll in (('PLA', 2300, 0.36, 845), ('PETG', 1500, 0.38, 540), ('ASA', 2000, 0.35, 740)):
    G = E / (2 * (1 + nu))
    pruef(abs(G - soll) / soll < 0.01, f'{m}: G Hand {G:.1f} != {soll}')
    pruef(kw.wert(m, 'G_MPa') == soll, f'{m}: G in kennwerte != {soll}')
# Tresca tau = sigma/2 aus material.py: PLA 50/2 = 25, 30/2 = 15; PETG 45/2 = 22,5, 28/2 = 14; ASA 40/2, 25/2
for m in DRUCKSTOFFE:
    pruef(kw.wert(m, 'schub_xy_MPa') == MATERIAL[m]['festigkeit_xy_MPa'] / 2, f'{m}: tau_xy != sigma_xy/2')
    pruef(kw.wert(m, 'schub_z_MPa') == MATERIAL[m]['festigkeit_z_MPa'] / 2, f'{m}: tau_z != sigma_z/2')
# ASA S_e: R=0,05, sigma_max 8 -> sigma_min 0,4; sigma_a 3,8; sigma_m 4,2; sigma_ut 8/0,25 = 32
s_max = 8.0
s_min = 0.05 * s_max
s_a, s_m, s_ut = (s_max - s_min) / 2, (s_max + s_min) / 2, s_max / 0.25
Se = s_a / (1 - s_m / s_ut)
pruef(abs(s_a - 3.8) < 1e-9 and abs(s_m - 4.2) < 1e-9 and abs(Se - 4.373) < 0.01, f'Goodman {Se}')
pruef(kw.wert('ASA', 'S_e_MPa') <= Se, 'ASA S_e ueber Goodman-Handwert')
# ASA Kriechmodul: 1100/2300 * 2000 = 956,5 -> abgerundet 900 (konservativ, nicht hoeher)
E1000 = 1100 / 2300 * 2000
pruef(abs(E1000 - 956.5) < 0.1 and kw.wert('ASA', 'kriechmodul_1000h_MPa') <= E1000, f'Kriechmodul {E1000}')
# ASA eps_z: 0,5 * 27,4/2379 = 0,00576 -> 0,006 (+-5 %)
eps = 0.5 * 27.4 / 2379
pruef(abs(eps - 0.00576) < 1e-5 and abs(kw.wert('ASA', 'eps_zul_z') - eps) / eps < 0.05, f'eps_z ASA {eps}')
# E_z PLA: 2300 * 1,4/1,5 = 2146,7 -> 2100 (abgerundet)
Ez = 2300 * 1.4 / 1.5
pruef(abs(Ez - 2146.7) < 0.1 and kw.wert('PLA', 'E_z_MPa') <= Ez, f'E_z PLA {Ez}')
# Katalog M26: k_e = 1 - 0,08 * z, z(99 %) = 2,326 -> 0,814 mit streuung_xy 0,08
k_e = 1 - 2.326 * kw.wert('PLA', 'streuung_xy')
pruef(abs(k_e - 0.814) < 0.001, f'k_e {k_e}')
# Schnapphaken-Beispiel (Katalog M1): eps = 1,5 t y / L^2, t 1,6, y 0,8, L 12 -> 0,01333
eps_h = 1.5 * 1.6 * 0.8 / 12 ** 2
pruef(abs(eps_h - 0.013333) < 1e-5, 'M1 Handrechnung')
pruef(eps_h < kw.wert('PETG', 'eps_zul_xy') and eps_h > kw.wert('PLA', 'eps_zul_z'),
      'Beispielhaken: PETG XY ok, PLA quer zu den Schichten nicht')

# 4) Zugriff: unbekanntes Material -> None, unbekanntes Feld -> AssertionError, FR4 unveraendert
pruef(kw.wert('HOLZ', 'alpha_1_K') is None and kw.quelle('HOLZ', 'mu') is None, 'unbekanntes Material')
try:
    kw.wert('PLA', 'gibtsnicht')
    pruef(False, 'kein Assert bei unbekanntem Feld')
except AssertionError:
    ok += 1
pruef(kw.wert('FR4', 'alpha_1_K') == 15e-6 and kw.wert('FR4', 'emission') == 0.9, 'FR4 veraendert')

print(f'test_kennwerte: {ok} Pruefungen ok')
