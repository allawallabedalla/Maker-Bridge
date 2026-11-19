"""CFD-Schnittstelle (mb2/cfd.py, 19.11.2026): Fallerzeugung OpenFOAM/Elmer, Auswertung, Katalog FL5-FL7.
Die Loeserlaeufe (Code-Verifikation gegen Hagen-Poiseuille) laufen nur auf einem Rechner mit OpenFOAM bzw. Elmer;
ohne Loeser melden sie 'werkzeug_fehlt', nie bestanden. Stoffwerte sind TESTFIXTURE-Werte.
Aufruf aus maker-bridge-2/:  uv run python tests/test_cfd.py"""
import json
import math
import os
import sys
import tempfile

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HIER))
sys.path.insert(0, HIER)
from _nachweis import NichtAusgefuehrt  # noqa: E402

from mb2 import cfd, werkzeuge  # noqa: E402
from mb2.pruefungen import stroemung  # noqa: E402

WASSER = {'viskositaet_Pa_s': 1.0e-3, 'dichte_kg_m3': 998.0, 'diffusivitaet_m2_s': 1e-9,
          'waermeleitung_W_mK': 0.6, 'waermekapazitaet_J_kgK': 4180.0}


def _projekt(spec, fall='kanal'):
    d = tempfile.mkdtemp(prefix='mb2_cfd_')
    os.makedirs(os.path.join(d, 'cfd'))
    json.dump(spec, open(os.path.join(d, 'cfd', fall + '.json'), 'w'))
    return d


def _kanal(loeser, **kw):
    s = {'loeser': loeser, 'geometrie': {'kanal': {'d_mm': 1.0, 'L_mm': 5.0}}, 'einlass': {'Q_ml_min': 1.0},
         'auslass': {}, 'medium': WASSER, 'netz': {'groesse': 0.25}, 'iterationen': 500}
    s.update(kw)
    return s


def test_openfoam_fall():
    d = _projekt(_kanal('openfoam', einlass={'Q_ml_min': 1.0, 'c': 1.0}))
    arbeit, netz, info = cfd.vorbereiten(d, 'kanal')
    assert abs(info['A_einlass_mm2'] / (math.pi * 0.25) - 1) < 0.05, info     # Netzflaeche ~ pi r^2
    msh = open(os.path.join(arbeit, 'netz.msh')).read()
    assert msh.startswith('$MeshFormat\n2.2 0 8') and '2 2 "einlass"' in msh and '2 3 "auslass"' in msh, msh[:200]
    n_knoten = int(msh.split('$Nodes\n')[1].split('\n')[0])
    assert n_knoten == info['knoten']
    x = [float(z.split()[1]) for z in msh.split('$Nodes\n')[1].split('$EndNodes')[0].strip().split('\n')[1:]]
    assert abs(max(x) - 5e-3) < 1e-9                                         # Koordinaten in m
    t = lambda f: open(os.path.join(arbeit, f)).read()  # noqa: E731
    assert 'solver          incompressibleFluid;' in t('system/controlDict')
    assert 'default steadyState;' in t('system/fvSchemes') and 'simulationType laminar;' in t('constant/momentumTransport')
    assert f'{1e-6 / 60:.9g}' in t('0/U') and 'flowRateInletVelocity' in t('0/U')
    assert f'{1e-3 / 998:.9g}' in t('constant/physicalProperties')            # nu = mu / rho
    assert 'scalarTransport' in t('system/controlDict') and os.path.exists(os.path.join(arbeit, '0', 'c'))
    assert 'gmshToFoam netz.msh' in t('Allrun.mb2') and 'foamRun' in t('Allrun.mb2')


def test_elmer_fall_gekoppelt():
    d = _projekt(_kanal('elmer', einlass={'Q_ml_min': 1.0, 'T_C': 40, 'c': 1.0}, wand={'T_C': 20}))
    arbeit, netz, info = cfd.vorbereiten(d, 'kanal')
    sif = open(os.path.join(arbeit, 'case.sif')).read()
    for w in ('Procedure = "FlowSolve" "FlowSolver"', 'Procedure = "HeatSolve" "HeatSolver"',
              'Procedure = "AdvectionDiffusion" "AdvectionDiffusionSolver"', 'Convection = Computed',
              'Heat Capacity = 4180', 'Konz Diffusivity = 1e-09', 'Temperature = 313.15', 'Coordinate Scaling = 0.001'):
        assert w in sif, w
    # Pfropfen: v = Q / A in +x (in den Kanal hinein)
    A = cfd.flaeche_m2(netz, cfd.EIN)
    v1 = float(sif.split('Velocity 1 = ')[2].split('\n')[0])                   # 1. Vorkommen: Wand, 2.: Einlass
    assert abs(v1 - 1e-6 / 60 / A) / v1 < 1e-6 and v1 > 0, v1
    assert info['waerme'] and info['stoff']
    assert os.path.exists(os.path.join(arbeit, 'netz', 'mesh.boundary'))


def test_auswertung_und_katalog():
    d = _projekt(_kanal('openfoam'))
    arbeit = os.path.join(d, 'cfd', 'kanal')
    for name, wert in (('p_einlass', 0.00714), ('p_auslass', 0.0), ('q_einlass', -1.6667e-8), ('q_auslass', 1.6600e-8)):
        os.makedirs(os.path.join(arbeit, 'postProcessing', name, '0'))
        open(os.path.join(arbeit, 'postProcessing', name, '0', 'surfaceFieldValue.dat'), 'w').write(
            f'# Time areaAverage(p)\n1 0.5\n500 {wert}\n')
    e = cfd.lies_openfoam(arbeit, 998.0)
    assert abs(e['dp_Pa'] - 0.00714 * 998) < 1e-9 and e['Q_ein_m3_s'] == 1.6667e-8, e
    an = cfd.analytisch(_kanal('openfoam'))
    nah = 128 * 1e-3 * 5e-3 * (1e-6 / 60) / (math.pi * 1e-12)            # 3,395 Pa
    assert abs(an['dp_Pa'] - nah) < 1e-9
    erg = dict(e, analytisch=dict(an, abweichung=e['dp_Pa'] / an['dp_Pa'] - 1), loeser='TESTFIXTURE',
               netzstudie=[{'groesse_mm': 0.3, 'dp_Pa': 3.30}, {'groesse_mm': 0.2, 'dp_Pa': 3.38},
                           {'groesse_mm': 0.15, 'dp_Pa': 3.39}])
    json.dump(erg, open(os.path.join(d, 'cfd', 'kanal.erg.json'), 'w'))
    r = {x['id']: x for x in stroemung.pruefe(d) if x['id'] in ('FL5', 'FL6', 'FL7')}
    assert r['FL5']['stufe'] == 'fehler', r['FL5']                          # 7,12 Pa gegen 3,40 Pa: +110 %
    erg['analytisch']['abweichung'] = 0.012
    json.dump(erg, open(os.path.join(d, 'cfd', 'kanal.erg.json'), 'w'))
    r = {x['id']: x for x in stroemung.pruefe(d) if x['id'] in ('FL5', 'FL6', 'FL7')}
    assert r['FL5']['stufe'] == 'ok' and r['FL6']['stufe'] == 'ok', r       # 0,4 % Massenbilanz
    assert r['FL7']['stufe'] == 'ok' and abs(r['FL7']['wert'] - 100 * 0.01 / 3.39) < 1e-3, r['FL7']
    # Fall nach dem Rechnen geaendert -> veraltet
    import time
    time.sleep(0.05)
    json.dump(_kanal('openfoam', iterationen=600), open(os.path.join(d, 'cfd', 'kanal.json'), 'w'))
    r = [x for x in stroemung.pruefe(d) if x['id'] == 'FL6']
    assert r[0]['stufe'] == 'uebersprungen' and 'veraltet' in r[0]['hinweis'], r
    # kein CFD-Fall
    assert {x['id'] for x in stroemung.pruefe(tempfile.mkdtemp()) if x['stufe'] == 'uebersprungen'} >= {'FL5', 'FL6', 'FL7'}


def test_werkzeug_einrichten():
    r = werkzeuge.einrichten('openfoam')
    s = r['schritte']['openfoam']
    assert 'openfoam.org' in s['anleitung'] and s['befehl'] is None             # nie ungepruefte Befehle
    assert werkzeuge._wsl_pfad(r'C:\Users\x\proj') == '/mnt/c/Users/x/proj'
    r = werkzeuge.einrichten('openfoam', ausfuehren=True)
    assert 'hinweis' in r['schritte']['openfoam'] or r['schritte']['openfoam']['vorhanden']


def _poiseuille(loeser):
    """Code-Verifikation am echten Loeser: Kanal d 1 mm, L 5 mm, 1 ml/min gegen Hagen-Poiseuille (< 5 %)."""
    if loeser == 'openfoam' and not werkzeuge.openfoam():
        raise NichtAusgefuehrt('werkzeug_fehlt', 'OpenFOAM fehlt - ' + werkzeuge.INSTALL['openfoam'][:60])
    if loeser == 'elmer' and not werkzeuge.elmer_solver():
        raise NichtAusgefuehrt('werkzeug_fehlt', 'Elmer fehlt')
    d = _projekt(_kanal(loeser, netz={'groesse': 0.1}, iterationen=2000))
    e = cfd.rechnen(d, 'kanal')
    assert abs(e['analytisch']['abweichung']) < 0.05, e


def test_openfoam_poiseuille():
    _poiseuille('openfoam')


def test_elmer_poiseuille():
    _poiseuille('elmer')


if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_') and callable(f):
            try:
                f()
                print('ok', n)
            except NichtAusgefuehrt as ex:
                print('nicht ausgefuehrt', n, ex)
    print('fertig')
