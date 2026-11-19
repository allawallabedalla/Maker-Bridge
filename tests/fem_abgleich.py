"""Abnahme FEM: CalculiX-Lauf (fem_mech referenz) gegen fem_halter.py (scikit-fem). Aufruf aus maker-bridge-2/
nach `python -m mb2 fem_mech projekt=stifthalter-fem fall=referenz`.
Beweiskette: (1) eigene Spannungsauswertung an den CalculiX-Integrationspunkten == CalculiX selbst,
(2) dieselbe Auswertung an den scikit-fem-Quadraturpunkten == Referenzwert, (3) Eckwerte = echtes Maximum."""
import json
import os

import numpy as np
import skfem

from mb2 import fem
from mb2.befehle import pdir
from mb2.material import MATERIAL

REF = {'andruck': (0.25, 3.171, [0.0499, 0.0498, 0.3883], 0.644),     # aus fem_halter.py stifthalter_v5.step
       'quer_x': (0.1, 2.12, [0.1247, 0.0196, 0.02], None),
       'quer_y': (0.1, 0.47, [0.0196, 0.0295, 0.0199], None)}

d = pdir('stifthalter-fem')
spec = json.load(open(os.path.join(d, 'fem', 'referenz.json'), encoding='utf-8'))
kn, tets, kp, namen, _ = fem.netz(d, spec, 2)
u_bl, s_bl, _ = fem._lies_dat(os.path.join(d, 'fem', 'referenz', 'lauf.dat'), len(kn))
erg = json.load(open(os.path.join(d, 'fem', 'referenz.erg.json'), encoding='utf-8'))
halter = np.where(kp == 0)[0]
m = MATERIAL['PETG']
a, b = 0.1381966011250105, 0.5854101966249685
CCX_IP = np.array([[a, a, a], [b, a, a], [a, b, a], [a, a, b]])
# genau die Quadraturpunkte, die fem_halter.py nutzt (Standard-Basis fuer P2-Vektorelemente)
SKFEM_QP = skfem.Basis(skfem.MeshTet(), skfem.ElementVector(skfem.ElementTetP2())).X.T

zeilen, ok = [], True
for (name, (F, ref_vm, ref_u, ref_k)), u, s in zip(REF.items(), u_bl, s_bl):
    lf = erg['lastfaelle'][name]
    ccx_ip = fem._von_mises(s, len(tets))[halter].max()
    eig_ip = fem.von_mises_feld(kn, tets, u, m['E_MPa'], m['nu'], CCX_IP, halter).max()
    eig_qp = fem.von_mises_feld(kn, tets, u, m['E_MPa'], m['nu'], SKFEM_QP, halter).max()
    ecke = lf['max_vonMises_MPa']
    du = np.abs(np.array(lf['verschiebung_lastflaeche_mm']) - ref_u).max()
    z = (f'{name:8s} u-Abw {du:.5f} mm | sigma: ccx-IP {ccx_ip:.3f} = eigene IP {eig_ip:.3f} | '
         f'skfem-Punkte {eig_qp:.3f} vs Referenz {ref_vm:.3f} ({eig_qp / ref_vm - 1:+.1%}) | Ecken {ecke:.3f}')
    if ref_k:
        z += f' | k {lf["federrate_N_mm"]:.4f} vs {ref_k} N/mm'
    zeilen.append(z)
    ok &= du < 5e-4 and abs(eig_ip / ccx_ip - 1) < 0.01 and abs(eig_qp / ref_vm - 1) < 0.03
print('\n'.join(zeilen))
print('ABNAHME', 'BESTANDEN' if ok else 'NICHT BESTANDEN')
