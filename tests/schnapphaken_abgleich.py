"""Kontakt + NLGEOM pruefen (Aufruf aus maker-bridge-2/ nach fem_mech schnapphaken montage UND kraft).
Grundannahme der ersten Versuche war falsch: beim Kontakt ist der Lastpunkt Ergebnis, nicht Vorgabe. Deshalb:
(1) Kontakt-Lauf gegen Kraft-Lauf (linear, ohne Kontakt, mit dem Stifthalter abgesichert): gleiche Steifigkeit am Grat
(2) Biegespannung in Balkenmitte gegen Gleichgewicht F * (x_Grat - 7) * z / I
(3) Balkentheorie mit starrer Einspannung nur zur Info (PETG-Sockel gibt nach -> FE weicher)."""
import json
import os

import numpy as np

from mb2 import fem
from mb2.befehle import pdir

E, B, H, X_GRAT = 2000.0, 6.0, 1.8, 14.0
I = B * H ** 3 / 12
d = pdir('schnapphaken')


def lauf(fall, job):
    spec = json.load(open(os.path.join(d, 'fem', fall + '.json'), encoding='utf-8'))
    kn, tets, kp, _, _ = fem.netz(d, spec, 2)
    u, s, rf = fem._lies_dat(os.path.join(d, 'fem', fall, job + '.dat'), len(kn))
    return kn, tets, kp, u[-1], s[-1], rf


# Kontakt-Lauf
def unterseite(kn):
    """Zungenunterseite unter dem Grat: misst die Biegung, nicht die oertliche Eindrueckung am Kontakt."""
    return np.where((np.abs(kn[:, 0] - X_GRAT) < 0.25) & (np.abs(kn[:, 2]) < 1e-6))[0]


kn, tets, kp, u, s, rf = lauf('montage', 'lauf_montage')
F_k = abs(rf[-1][2])
w_k = -u[unterseite(kn), 2].mean()
k_kontakt = F_k / w_k
mitte = kn[tets[:, :4]].mean(1)
sel = [e for e in s if kp[e] == 0 and 6.5 < mitte[e, 0] < 7.5 and mitte[e, 2] > H - 0.35 and abs(mitte[e, 1]) < 2]
sxx = np.mean([np.mean([ip[0] for ip in s[e]]) for e in sel])
z_m = np.mean(mitte[sel, 2])
sigma_gg = F_k * (X_GRAT - 7.0) * (z_m - H / 2) / I

# Kraft-Lauf (linear)
kn2, _, _, u2, _, _ = lauf('kraft', 'lauf')
k_kraft = 5.0 / abs(u2[unterseite(kn2), 2].mean())
k_theorie = 3 * E * I / X_GRAT ** 3

print(f'(1) Biegesteifigkeit (Unterseite unter dem Grat): Kontakt+NLGEOM {k_kontakt:.3f} N/mm (F {F_k:.3f} N bei {w_k:.3f} mm) '
      f'vs Kraft linear {k_kraft:.3f} N/mm ({k_kontakt / k_kraft - 1:+.1%})')
print(f'(2) sigma_xx x=7: FE {sxx:.2f} MPa vs Gleichgewicht {sigma_gg:.2f} MPa ({sxx / sigma_gg - 1:+.1%}), {len(sel)} Elemente')
print(f'(3) Info: Balkentheorie starr eingespannt {k_theorie:.3f} N/mm ({k_kraft / k_theorie - 1:+.1%} FE weicher, Sockel)')
ok = abs(k_kontakt / k_kraft - 1) < 0.03 and abs(sxx / sigma_gg - 1) < 0.03
print('ABNAHME', 'BESTANDEN' if ok else 'NICHT BESTANDEN')
