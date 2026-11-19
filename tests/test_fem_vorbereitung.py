"""FEM ohne Loeser pruefen: Netz, Auswahlen und CalculiX-Eingabe fuer den Referenzfall. Aufruf aus maker-bridge-2/."""
import json
import os

import numpy as np

from mb2 import fem
from mb2.befehle import pdir
from mb2.material import DRUCKSTOFFE

d = pdir('stifthalter-fem')
spec = json.load(open(os.path.join(d, 'fem', 'referenz.json'), encoding='utf-8'))
kn, tets, kp, namen, vol = fem.netz(d, spec, 2)
rand = fem.randflaechen(tets)
print('knoten', len(kn), 'tets', len(tets), 'koerper', namen, 'je koerper', np.bincount(kp), 'vol', vol.round(1))
for l in spec['lagerung'] + spec['lasten']:
    t, f = fem.auswahl(l['wo'], kn, tets, kp, namen, rand)
    print(l.get('name', 'lager'), 'flaechen', len(t), 'knoten', len(fem._flaechen_knoten(tets, t, f)))
mats = [k['material'].upper() for k in spec['koerper']]
druck = np.isin(np.array(mats)[kp], DRUCKSTOFFE)
fest = [(fem._flaechen_knoten(tets, *fem.auswahl(l['wo'], kn, tets, kp, namen, rand)), 'xyz') for l in spec['lagerung']]
lasten = [(l['name'], fem._flaechen_knoten(tets, *fem.auswahl(l['wo'], kn, tets, kp, namen, rand)),
           np.array(l['kraft_N'], float)) for l in spec['lasten']]
inp = fem._inp(kn, tets, kp, mats, druck, fest, lasten, False, spec, rand, namen)
print('inp zeilen', inp.count('\n'), 'steps', inp.count('*STEP'))
# Jacobi-Vorzeichen der Tet10-Ecken in CalculiX-Reihenfolge: alle Volumina positiv?
e = tets[:, :4]
v = np.einsum('ij,ij->i', np.cross(kn[e[:, 1]] - kn[e[:, 0]], kn[e[:, 2]] - kn[e[:, 0]]), kn[e[:, 3]] - kn[e[:, 0]])
print('tet-volumen positiv:', bool((v > 0).all()), 'negativ:', int((v <= 0).sum()))
