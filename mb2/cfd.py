"""Stroemung, Waerme und Stofftransport numerisch (CFD), loeserneutral: OpenFOAM oder Elmer (seit 19.11.2026).

Eine Fallbeschreibung ``cfd/<fall>.json`` - zwei Loeser:
- ``"loeser": "openfoam"``  OpenFOAM (Foundation, Version 12): ``foamRun`` mit ``solver incompressibleFluid``,
  stationaer (SIMPLE), laminar; Stofftransport als Funktionsobjekt ``scalarTransport``. Netz: Gmsh-MSH 2.2 ->
  ``gmshToFoam``. Schluesselwoerter aus den offiziellen Tutorials pitzDailySteady/blockedChannel/
  pitzDailyScalarTransport und etc/caseDicts (github.com/OpenFOAM/OpenFOAM-12, gelesen 19.11.2026).
  Staerke: reine Stroemung (auch spaeter turbulent/mehrphasig).
- ``"loeser": "elmer"``  Elmer: Navier-Stokes (FlowSolve) + optional HeatSolve (Convection = Computed) und
  AdvectionDiffusion. Schluesselwoerter aus den Elmer-Tests FlowResNoslip, NaturalConvection, AdvDiffFluxes
  (github.com/ElmerCSC/elmerfem). Staerke: Kopplung mit Waerme/Elektrik in einem Fall.

Fallbeschreibung (Einheiten: mm, ml/min, SI fuer Stoffwerte):
    {"loeser": "openfoam|elmer",
     "geometrie": {"step": "out/fluid.step"}  |  {"kanal": {"d_mm": 1.0, "L_mm": 20}},   # Fluidraum (nicht das Bauteil!)
     "einlass": {"wo": AUSWAHL, "Q_ml_min": 10, "T_C": 40, "c": 1.0},                  # AUSWAHL wie fem.py
     "auslass": {"wo": AUSWAHL},                                                        # alles andere = Wand
     "medium": {"viskositaet_Pa_s": .., "dichte_kg_m3": .., "diffusivitaet_m2_s": ..,  # mit _herkunft im soll
                "waermeleitung_W_mK": .., "waermekapazitaet_J_kgK": ..},
     "wand": {"T_C": 20},                                                               # optional (Waerme, Elmer)
     "netz": {"groesse": 0.15}, "netzstudie": [0.3, 0.2, 0.15],                         # optional, mm
     "iterationen": 2000, "modell": {...}}                                              # V&V-40-Einstufung
Kanal ohne STEP: Zylinder entlang x von 0 bis L, Einlass x = 0, Auslass x = L (Code-Verifikation gegen
Hagen-Poiseuille, siehe ``verifikation``).
Ergebnis ``cfd/<fall>.erg.json``: dp_Pa (mittlerer Druck Einlass - Auslass), Q_ein/Q_aus (m3/s, OpenFOAM),
c_aus/T_aus (Mittel am Auslass), netzstudie, analytisch (bei Kanal). Gerechnet wird NUR auf einem Rechner mit dem
Loeser (Befehl ``cfd_rechnen``); ohne Loeser schreibt ``cfd_vorbereiten`` den Fall zum Weitergeben.
OpenFOAM rechnet kinematischen Druck p/rho - dp_Pa ist schon mit rho multipliziert.
"""
import glob
import json
import math
import os
import shutil
import subprocess

import numpy as np

from . import fem, werkzeuge

KOPF = ('FoamFile\n{{\n    format      ascii;\n    class       {klasse};\n    object      {objekt};\n}}\n\n')
WAND, EIN, AUS = 1, 2, 3
GRUPPEN = {WAND: 'wand', EIN: 'einlass', AUS: 'auslass'}


def lade(pdir, fall):
    return json.load(open(os.path.join(pdir, 'cfd', fall + '.json'), encoding='utf-8'))


def _geometrie(spec):
    g = spec.get('geometrie') or {}
    if 'kanal' in g:
        k = g['kanal']
        r, L = k['d_mm'] / 2, k['L_mm']
        return ({'koerper': [{'zylinder': [0, 0, 0, L, 0, 0, r], 'material': 'FLUID', 'name': 'fluid'}],
                 'netz': spec.get('netz', {})},
                {'ebene': ['x', 0.0], 'tol': 1e-6 * max(L, 1)}, {'ebene': ['x', float(L)], 'tol': 1e-6 * max(L, 1)})
    if 'step' in g:
        return ({'koerper': [{'step': g['step'], 'material': 'FLUID', 'name': 'fluid'}], 'netz': spec.get('netz', {})},
                spec['einlass']['wo'], spec['auslass']['wo'])
    raise ValueError('cfd: geometrie {step} oder {kanal: {d_mm, L_mm}} fehlt')


def vernetzen(pdir, spec, groesse=None):
    """Fluidraum vernetzen (lineare Tetraeder), Randgruppen 1 Wand, 2 Einlass, 3 Auslass."""
    gs, w_ein, w_aus = _geometrie(spec)
    if groesse:
        gs = dict(gs, netz=dict(gs['netz'], groesse=groesse))
    knoten, tets, koerper, namen, _ = fem.netz(pdir, gs, 1)
    rand = fem.randflaechen(tets)
    gruppe = np.full(len(rand[0]), WAND)
    for g, wo in ((EIN, w_ein), (AUS, w_aus)):
        tid, fnr = fem.auswahl(wo, knoten, tets, koerper, namen, rand)
        sel = set(zip(tid.tolist(), fnr.tolist()))
        gruppe[[k for k, tf in enumerate(zip(rand[0].tolist(), rand[1].tolist())) if tf in sel]] = g
    A, nrm, mitte = fem._randgeometrie(knoten, tets, rand)
    return {'knoten': knoten, 'tets': tets, 'koerper': koerper, 'rand': rand, 'gruppe': gruppe, 'A_mm2': A,
            'normale': nrm, 'mitte': mitte}


def flaeche_m2(netz, g):
    return float(netz['A_mm2'][netz['gruppe'] == g].sum()) * 1e-6


def schreibe_msh22(pfad, netz):
    """Gmsh-MSH 2.2 ASCII (das Format, das gmshToFoam zeilenweise liest), Koordinaten in m.
    Physikalische Gruppen: 1 wand, 2 einlass, 3 auslass (Flaechen), 4 fluid (Volumen) -> OpenFOAM-Patches."""
    kn, tets, (tid, _, f), gr = netz['knoten'], netz['tets'], netz['rand'], netz['gruppe']
    z = ['$MeshFormat', '2.2 0 8', '$EndMeshFormat', '$PhysicalNames', '4']
    z += [f'2 {g} "{n}"' for g, n in GRUPPEN.items()] + ['3 4 "fluid"', '$EndPhysicalNames', '$Nodes', str(len(kn))]
    z += [f'{i + 1} {x * 1e-3:.12g} {y * 1e-3:.12g} {w * 1e-3:.12g}' for i, (x, y, w) in enumerate(kn)]
    z += ['$EndNodes', '$Elements', str(len(f) + len(tets))]
    nr = 0
    for k in range(len(f)):
        nr += 1
        z.append(f'{nr} 2 2 {gr[k]} {gr[k]} ' + ' '.join(str(int(n) + 1) for n in f[k]))
    for t in tets:
        nr += 1
        z.append(f'{nr} 4 2 4 4 ' + ' '.join(str(int(n) + 1) for n in t[:4]))
    z.append('$EndElements')
    open(pfad, 'w').write('\n'.join(z) + '\n')


def _foam(pfad, klasse, objekt, rumpf):
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    open(pfad, 'w').write(KOPF.format(klasse=klasse, objekt=objekt) + rumpf.strip() + '\n')


def openfoam_fall(arbeit, spec, netz):
    """OpenFOAM-12-Fall: 0/, constant/, system/ und Allrun.mb2 (gmshToFoam, foamRun)."""
    shutil.rmtree(arbeit, ignore_errors=True)
    os.makedirs(arbeit)
    m, e = spec['medium'], spec['einlass']
    nu = m['viskositaet_Pa_s'] / m['dichte_kg_m3']
    Q = e['Q_ml_min'] * 1e-6 / 60
    schreibe_msh22(os.path.join(arbeit, 'netz.msh'), netz)
    it = int(spec.get('iterationen', 2000))
    sk = 'c' in e and m.get('diffusivitaet_m2_s')
    funktionen = f'''
    p_einlass {{ type surfaceFieldValue; libs ("libfieldFunctionObjects.so"); writeControl timeStep; writeInterval 1;
                 writeFields false; select patch; patch einlass; operation areaAverage; fields (p); }}
    p_auslass {{ type surfaceFieldValue; libs ("libfieldFunctionObjects.so"); writeControl timeStep; writeInterval 1;
                 writeFields false; select patch; patch auslass; operation areaAverage; fields (p); }}
    q_einlass {{ type surfaceFieldValue; libs ("libfieldFunctionObjects.so"); writeControl timeStep; writeInterval 1;
                 writeFields false; select patch; patch einlass; operation sum; fields (phi); }}
    q_auslass {{ type surfaceFieldValue; libs ("libfieldFunctionObjects.so"); writeControl timeStep; writeInterval 1;
                 writeFields false; select patch; patch auslass; operation sum; fields (phi); }}'''
    if sk:
        funktionen += f'''
    c_transport {{ type scalarTransport; libs ("libsolverFunctionObjects.so"); field c; diffusivity constant;
                   D {m["diffusivitaet_m2_s"]:.9g}; }}
    c_auslass {{ type surfaceFieldValue; libs ("libfieldFunctionObjects.so"); writeControl timeStep; writeInterval 1;
                 writeFields false; select patch; patch auslass; operation areaAverage; fields (c); }}'''
    _foam(f'{arbeit}/system/controlDict', 'dictionary', 'controlDict', f'''
application     foamRun;
solver          incompressibleFluid;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {it};
deltaT          1;
writeControl    timeStep;
writeInterval   {it};
purgeWrite      0;
writeFormat     ascii;
writePrecision  8;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable true;
functions
{{{funktionen}
}}''')
    _foam(f'{arbeit}/system/fvSchemes', 'dictionary', 'fvSchemes', '''
ddtSchemes { default steadyState; }
gradSchemes { default Gauss linear; }
divSchemes { default none; div(phi,U) bounded Gauss linearUpwind grad(U); div(phi,c) bounded Gauss linearUpwind grad(c);
             div((nuEff*dev2(T(grad(U))))) Gauss linear; }
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes { default corrected; }''')
    _foam(f'{arbeit}/system/fvSolution', 'dictionary', 'fvSolution', '''
solvers
{
    p { solver GAMG; tolerance 1e-08; relTol 0.01; smoother GaussSeidel; }
    "(U|c)" { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-09; relTol 0.1; }
}
SIMPLE
{
    nNonOrthogonalCorrectors 1;
    consistent      yes;
    residualControl { p 1e-6; U 1e-7; }
}
relaxationFactors { equations { U 0.9; ".*" 0.9; } }''')
    _foam(f'{arbeit}/constant/momentumTransport', 'dictionary', 'momentumTransport', 'simulationType laminar;')
    _foam(f'{arbeit}/constant/physicalProperties', 'dictionary', 'physicalProperties',
          f'viscosityModel  constant;\nnu              [0 2 -1 0 0 0 0] {nu:.9g};')
    _foam(f'{arbeit}/0/U', 'volVectorField', 'U', f'''
dimensions      [0 1 -1 0 0 0 0];
internalField   uniform (0 0 0);
boundaryField
{{
    einlass {{ type flowRateInletVelocity; volumetricFlowRate {Q:.9g}; value uniform (0 0 0); }}
    auslass {{ type zeroGradient; }}
    wand    {{ type noSlip; }}
}}''')
    _foam(f'{arbeit}/0/p', 'volScalarField', 'p', '''
dimensions      [0 2 -2 0 0 0 0];
internalField   uniform 0;
boundaryField
{
    einlass { type zeroGradient; }
    auslass { type fixedValue; value uniform 0; }
    wand    { type zeroGradient; }
}''')
    if sk:
        _foam(f'{arbeit}/0/c', 'volScalarField', 'c', f'''
dimensions      [0 0 0 0 0 0 0];
internalField   uniform 0;
boundaryField
{{
    einlass {{ type fixedValue; value uniform {e["c"]:.9g}; }}
    auslass {{ type zeroGradient; }}
    wand    {{ type zeroGradient; }}
}}''')
    open(f'{arbeit}/Allrun.mb2', 'w', newline='\n').write(
        '#!/bin/sh\ncd "${0%/*}" || exit 1\nset -e\ngmshToFoam netz.msh > log.gmshToFoam 2>&1\n'
        'foamRun > log.foamRun 2>&1\n')
    return {'Q_m3_s': Q, 'nu_m2_s': nu, 'skalar': bool(sk)}


def elmer_fall(arbeit, spec, netz):
    """Elmer-Fall: Netz (mb2-Reihenfolge), case.sif mit Navier-Stokes, optional HeatSolve und AdvectionDiffusion."""
    shutil.rmtree(arbeit, ignore_errors=True)
    os.makedirs(arbeit)
    m, e = spec['medium'], spec['einlass']
    fem._elmer_netz(arbeit, netz['knoten'], netz['tets'], netz['koerper'], netz['rand'], netz['gruppe'])
    A_ein = flaeche_m2(netz, EIN)
    Q = e['Q_ml_min'] * 1e-6 / 60
    sel = netz['gruppe'] == EIN
    n_ein = (netz['normale'][sel] * netz['A_mm2'][sel, None]).sum(0)
    n_ein /= np.linalg.norm(n_ein)
    v = -n_ein * Q / A_ein                     # Pfropfen in den Kanal hinein (Einlaufstrecke einplanen, FL3)
    waerme = 'T_C' in e and m.get('waermeleitung_W_mK') and m.get('waermekapazitaet_J_kgK')
    stoff = 'c' in e and m.get('diffusivitaet_m2_s')
    aktiv = [1] + ([2] if waerme else []) + ([3] if stoff else [])
    z = ['Header', '  Mesh DB "." "netz"', 'End', 'Simulation', '  Coordinate System = Cartesian 3D',
         '  Coordinate Scaling = 0.001', '  Simulation Type = Steady State', '  Steady State Max Iterations = 30',
         '  Output Intervals = 1', 'End', 'Body 1', '  Equation = 1', '  Material = 1', 'End',
         'Equation 1', f'  Active Solvers({len(aktiv) + 1}) = {" ".join(map(str, aktiv))} 4',
         '  Convection = Computed', 'End',
         'Solver 1', '  Equation = Navier-Stokes', '  Variable = Flow Solution[Velocity:3 Pressure:1]',
         '  Procedure = "FlowSolve" "FlowSolver"', '  Stabilize = True', '  Linear System Solver = Iterative',
         '  Linear System Iterative Method = BiCGStabl', '  Linear System Preconditioning = ILU0',
         '  Linear System Max Iterations = 1000', '  Linear System Convergence Tolerance = 1.0e-10',
         '  Nonlinear System Max Iterations = 30', '  Nonlinear System Convergence Tolerance = 1.0e-7',
         '  Nonlinear System Newton After Iterations = 3', '  Nonlinear System Newton After Tolerance = 1.0e-4',
         '  Steady State Convergence Tolerance = 1.0e-7', 'End']
    if waerme:
        z += ['Solver 2', '  Equation = Heat Equation', '  Procedure = "HeatSolve" "HeatSolver"',
              '  Variable = -dofs 1 Temperature', '  Stabilize = True', '  Linear System Solver = Iterative',
              '  Linear System Iterative Method = BiCGStabl', '  Linear System Preconditioning = ILU0',
              '  Linear System Convergence Tolerance = 1.0e-10', '  Steady State Convergence Tolerance = 1.0e-7', 'End']
    if stoff:
        z += ['Solver 3', '  Equation = "AdvDiff"', '  Variable = Konz',
              '  Procedure = "AdvectionDiffusion" "AdvectionDiffusionSolver"', '  Linear System Solver = Iterative',
              '  Linear System Iterative Method = BiCGStab', '  Linear System Preconditioning = ILU0',
              '  Linear System Convergence Tolerance = 1.0e-10', '  Steady State Convergence Tolerance = 1.0e-7',
              '  Bubbles = True', 'End']
    z += ['Solver 4', '  Exec Solver = After Simulation', '  Equation = "Ausgabe"',
          '  Procedure = "ResultOutputSolve" "ResultOutputSolver"', '  Output File Name = "erg"', '  Vtu Format = True',
          '  Ascii Output = True', 'End',
          'Material 1', f'  Density = {m["dichte_kg_m3"]:.9g}', f'  Viscosity = {m["viskositaet_Pa_s"]:.9g}']
    if waerme:
        z += [f'  Heat Conductivity = {m["waermeleitung_W_mK"]:.9g}', f'  Heat Capacity = {m["waermekapazitaet_J_kgK"]:.9g}']
    if stoff:
        z.append(f'  Konz Diffusivity = {m["diffusivitaet_m2_s"]:.9g}')
    z.append('End')
    bc_ein = [f'  Velocity {i + 1} = {v[i]:.9g}' for i in range(3)]
    if waerme:
        bc_ein.append(f'  Temperature = {e["T_C"] + 273.15:.9g}')
    if stoff:
        bc_ein.append(f'  Konz = {e["c"]:.9g}')
    bc_wand = [f'  Velocity {i + 1} = 0' for i in range(3)]
    if waerme and (spec.get('wand') or {}).get('T_C') is not None:
        bc_wand.append(f'  Temperature = {spec["wand"]["T_C"] + 273.15:.9g}')
    z += ['Boundary Condition 1', f'  Target Boundaries(1) = {WAND}', *bc_wand, 'End',
          'Boundary Condition 2', f'  Target Boundaries(1) = {EIN}', *bc_ein, 'End',
          'Boundary Condition 3', f'  Target Boundaries(1) = {AUS}', 'End']       # natuerlich: Spannung 0
    open(os.path.join(arbeit, 'case.sif'), 'w').write('\n'.join(z) + '\n')
    open(os.path.join(arbeit, 'ELMERSOLVER_STARTINFO'), 'w').write('case.sif\n1\n')
    return {'Q_m3_s': Q, 'v_ein_m_s': float(np.linalg.norm(v)), 'waerme': bool(waerme), 'stoff': bool(stoff)}


# ---------------------------------------------------------------------------------------------- Auswertung

def _letzte_zeile(pfad):
    z = [l for l in open(pfad, encoding='utf-8', errors='replace').read().splitlines() if l.strip() and not l.startswith('#')]
    return [float(x) for x in z[-1].split()] if z else None


def lies_openfoam(arbeit, rho):
    """Mittelwerte aus postProcessing/<name>/<zeit>/*.dat (letzte Iteration). p ist kinematisch -> mal rho."""
    def wert(name):
        d = sorted(glob.glob(os.path.join(arbeit, 'postProcessing', name, '*', '*.dat')))
        z = _letzte_zeile(d[-1]) if d else None
        return z[-1] if z else None
    p_e, p_a, q_e, q_a = (wert(n) for n in ('p_einlass', 'p_auslass', 'q_einlass', 'q_auslass'))
    if p_e is None or p_a is None:
        raise RuntimeError('OpenFOAM: keine postProcessing-Werte (log.foamRun lesen)')
    erg = {'dp_Pa': (p_e - p_a) * rho, 'Q_ein_m3_s': abs(q_e) if q_e is not None else None,
           'Q_aus_m3_s': abs(q_a) if q_a is not None else None}
    c = wert('c_auslass')
    if c is not None:
        erg['c_aus'] = c
    return erg


def lies_elmer(arbeit, netz):
    """Mittelwerte (flaechengewichtet ueber die Randdreiecke) aus erg*.vtu."""
    vtus = sorted(glob.glob(os.path.join(arbeit, 'netz', '*.vtu')))
    if not vtus:
        raise RuntimeError('Elmer: keine .vtu (Ausgabe pruefen)')
    n = len(netz['knoten'])
    f, A, gr = netz['rand'][2], netz['A_mm2'], netz['gruppe']

    def mittel(feld, g):
        werte = fem._lies_vtu_feld(vtus[-1], feld, n)
        s = gr == g
        return float((werte[f[s]].mean(1) * A[s]).sum() / A[s].sum())
    erg = {'dp_Pa': mittel('pressure', EIN) - mittel('pressure', AUS)}
    txt = open(vtus[-1], encoding='utf-8', errors='replace').read().lower()
    if 'name="temperature"' in txt:
        erg['T_aus_C'] = mittel('temperature', AUS) - 273.15
    if 'name="konz"' in txt:
        erg['c_aus'] = mittel('konz', AUS)
    return erg


def analytisch(spec):
    """Hagen-Poiseuille fuer den generierten Kanal (Code-Verifikation), sonst None."""
    k = (spec.get('geometrie') or {}).get('kanal')
    if not k:
        return None
    m = spec['medium']
    Q = spec['einlass']['Q_ml_min'] * 1e-6 / 60
    d, L = k['d_mm'] * 1e-3, k['L_mm'] * 1e-3
    return {'dp_Pa': 128 * m['viskositaet_Pa_s'] * L * Q / (math.pi * d ** 4), 'formel': 'Hagen-Poiseuille'}


# ---------------------------------------------------------------------------------------------- Ablauf

def vorbereiten(pdir, fall, groesse=None):
    """Fall schreiben, ohne zu rechnen (zum Weitergeben an den Rechner mit dem Loeser)."""
    spec = lade(pdir, fall)
    arbeit = os.path.join(pdir, 'cfd', fall + ('' if groesse is None else f'_h{groesse:g}'))
    netz = vernetzen(pdir, spec, groesse)
    info = (openfoam_fall if spec.get('loeser', 'openfoam') == 'openfoam' else elmer_fall)(arbeit, spec, netz)
    return arbeit, netz, dict(info, knoten=len(netz['knoten']), tetraeder=len(netz['tets']),
                              A_einlass_mm2=flaeche_m2(netz, EIN) * 1e6, A_auslass_mm2=flaeche_m2(netz, AUS) * 1e6)


def _laufen(arbeit, spec, netz):
    if spec.get('loeser', 'openfoam') == 'openfoam':
        r = werkzeuge.openfoam_ausfuehren(arbeit, 'sh Allrun.mb2', timeout=7200)
        if r.returncode:
            log = ''.join(open(p, errors='replace').read()[-1500:] for p in glob.glob(os.path.join(arbeit, 'log.*')))
            raise RuntimeError(f'OpenFOAM endete mit {r.returncode}: {log or r.stderr[-1500:]}')
        return lies_openfoam(arbeit, spec['medium']['dichte_kg_m3'])
    if not werkzeuge.elmer_solver():
        raise RuntimeError('Elmer fehlt - ' + werkzeuge.INSTALL['elmer'])
    r = subprocess.run([werkzeuge.elmer_solver(), 'case.sif'], cwd=arbeit, capture_output=True, text=True,
                       timeout=7200, env=werkzeuge.elmer_env(), stdin=subprocess.DEVNULL)
    if r.returncode:
        raise RuntimeError('Elmer: ' + (r.stdout + r.stderr)[-1500:])
    return lies_elmer(arbeit, netz)


def rechnen(pdir, fall):
    """Fall rechnen (Netzstudie, falls angegeben), Ergebnis cfd/<fall>.erg.json."""
    spec = lade(pdir, fall)
    loeser = spec.get('loeser', 'openfoam')
    if loeser == 'openfoam' and not werkzeuge.openfoam():
        raise RuntimeError('OpenFOAM fehlt - ' + werkzeuge.INSTALL['openfoam'])
    arbeit, netz, info = vorbereiten(pdir, fall)
    erg = dict(info, loeser=('OpenFOAM foamRun incompressibleFluid laminar' if loeser == 'openfoam'
                             else 'Elmer FlowSolve' + (' + HeatSolve' if info.get('waerme') else '') +
                             (' + AdvectionDiffusion' if info.get('stoff') else '')))
    erg.update(_laufen(arbeit, spec, netz))
    an = analytisch(spec)
    if an:
        erg['analytisch'] = dict(an, abweichung=erg['dp_Pa'] / an['dp_Pa'] - 1)
    studie = []
    for h in spec.get('netzstudie') or []:
        a2, n2, i2 = vorbereiten(pdir, fall, float(h))
        studie.append({'groesse_mm': float(h), 'knoten': i2['knoten'], **_laufen(a2, spec, n2)})
    if studie:
        erg['netzstudie'] = studie
    erg['modell'] = spec.get('modell')
    json.dump(erg, open(os.path.join(pdir, 'cfd', fall + '.erg.json'), 'w', encoding='utf-8'), indent=1,
              ensure_ascii=False, default=float)
    return erg
