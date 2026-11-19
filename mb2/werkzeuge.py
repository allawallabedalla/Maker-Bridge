"""Externe Programme finden. Alles ist normal installiert (seit 05.11.2026, vorher portabel in ~/tools):

- CalculiX 2.23: MSYS2 (C:\\msys64), Paket mingw-w64-ucrt-x86_64-calculix-ccx – Update: `pacman -Syu` in MSYS2 UCRT64
- Elmer 26.1 (nogui, MPI): offizieller Installer nach C:\\Program Files\\Elmer 9.0-Release (Name im Installer veraltet,
  Build vom 20.01.2026 = rel26.1) + Microsoft MPI (winget Microsoft.msmpi)
- KiCad 10, PrusaSlicer: normal installiert
- Java + Freerouting: portabel in ~/tools (alte Bridge, freerouting_setup)
Linux/macOS (seit 19.11.2026): CalculiX und Elmer werden im PATH gesucht (`ccx`, `ElmerSolver`), z. B.
Debian/Ubuntu `apt install calculix-ccx` (geprueft: 2.21). Elmer gibt es dort nicht im Standard-Paketbestand.
"""
import functools
import glob
import os
import re
import shutil
import subprocess

TOOLS = os.path.join(os.path.expanduser('~'), 'tools')
MSYS2_BIN = r'C:\msys64\ucrt64\bin'
INSTALL = {
    'ccx': 'Windows: MSYS2 installieren (winget install MSYS2.MSYS2), dann in "MSYS2 UCRT64": '
           'pacman -S mingw-w64-ucrt-x86_64-calculix-ccx; Linux: ccx in den PATH (Debian/Ubuntu: apt install calculix-ccx)',
    'elmer': 'Windows: Elmer-Installer ElmerFEM-nogui-mpi-Windows-AMD64-rel26.1.exe von '
             'nic.funet.fi/pub/sci/physics/elmer/bin/windows/rel26.1/ + winget install Microsoft.msmpi; '
             'Linux: ElmerSolver in den PATH (nicht im Ubuntu-Standardbestand, siehe Elmer-Projektseite)',
}


def _newest(pattern):
    hits = glob.glob(pattern)
    key = lambda h: [int(x) if x.isdigit() else 0 for x in re.split(r'[.\-+_\\/]', h)]  # noqa: E731
    return sorted(hits, key=key)[-1] if hits else None


def ccx():
    p = os.path.join(MSYS2_BIN, 'ccx.exe')
    if os.path.exists(p):
        return p
    return shutil.which('ccx') or shutil.which('ccx_2.21') or None


@functools.cache
def physische_kerne():
    """PaStiX (Löser im MSYS2-ccx) bindet je Thread einen physischen Kern – mehr Threads (logische Kerne) hängen."""
    try:
        n = subprocess.run(['powershell', '-NoProfile', '-Command',
                            '(Get-CimInstance Win32_Processor | Measure-Object NumberOfCores -Sum).Sum'],
                           capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL).stdout.strip()
        return max(1, int(n))
    except Exception:  # noqa: BLE001
        return max(1, (os.cpu_count() or 2) // 2)


def ccx_env():
    n = str(physische_kerne())
    return dict(os.environ, OMP_NUM_THREADS=n, PASTIX_NUM_THREADS=n, STARPU_NCPU=n)


def elmer_bin():
    p = _newest(os.path.join(os.environ.get('ProgramFiles', r'C:\Program Files'), 'Elmer*', 'bin', 'ElmerSolver.exe'))
    p = p or shutil.which('ElmerSolver')
    return os.path.dirname(p) if p else None


def elmer_solver():
    """Pfad der ElmerSolver-Datei (Windows .exe oder Linux ohne Endung)."""
    b = elmer_bin()
    if not b:
        return None
    for n in ('ElmerSolver.exe', 'ElmerSolver'):
        if os.path.exists(os.path.join(b, n)):
            return os.path.join(b, n)
    return None


def elmer_env():
    b = elmer_bin()
    home = os.path.dirname(b)
    env = dict(os.environ, ELMER_HOME=home, ELMER_LIB=os.path.join(home, 'share', 'elmersolver', 'lib'))
    env['PATH'] = b + os.pathsep + os.path.join(home, 'lib') + os.pathsep + env.get('PATH', '')
    return env


def mpiexec():
    p = os.path.join(os.environ.get('ProgramFiles', r'C:\Program Files'), 'Microsoft MPI', 'Bin', 'mpiexec.exe')
    return p if os.path.exists(p) else None


def kicad_home():
    pats = [os.path.expandvars(r'%LOCALAPPDATA%\Programs\KiCad\*'), r'C:\Program Files\KiCad\*']
    hits = [h for p in pats for h in glob.glob(p) if os.path.exists(os.path.join(h, 'bin', 'kicad-cli.exe'))]
    if not hits:
        raise RuntimeError('KiCad nicht gefunden (kicad-cli.exe).')
    return sorted(hits, key=lambda h: [int(x) if x.isdigit() else 0 for x in re.split(r'[.\\]', h)])[-1]


def prusa_slicer():
    for root in (r'C:\Program Files\Prusa3D\PrusaSlicer', r'C:\Program Files\PrusaSlicer'):
        p = os.path.join(root, 'prusa-slicer-console.exe')
        if os.path.exists(p):
            return p
    raise RuntimeError('PrusaSlicer nicht gefunden.')


def blender():
    """Blender (fuer Renderbilder), neueste Version unter Program Files. None, wenn nicht installiert."""
    return _newest(os.path.join(os.environ.get('ProgramFiles', r'C:\Program Files'),
                                'Blender Foundation', 'Blender *', 'blender.exe'))


def java_freerouting():
    return (_newest(os.path.join(TOOLS, 'jdk-*', 'bin', 'java.exe')),
            _newest(os.path.join(TOOLS, 'freerouting', 'freerouting-*.jar')))


def status():
    def probe(fn):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - Status soll nie abbrechen
            return f'FEHLT: {e}'
    java, jar = java_freerouting()
    st = {'ccx': ccx() or 'FEHLT: ' + INSTALL['ccx'], 'elmer': elmer_bin() or 'FEHLT: ' + INSTALL['elmer'],
          'mpiexec': mpiexec(), 'kicad': probe(kicad_home), 'prusaslicer': probe(prusa_slicer),
          'java': java, 'freerouting': jar,
          'blender': blender() or 'FEHLT (Renderbilder fallen auf matplotlib zurueck)'}
    if ccx():
        st['ccx_version'] = subprocess.run([ccx(), '-v'], capture_output=True, text=True, timeout=60,
                                           stdin=subprocess.DEVNULL).stdout.strip()
    if elmer_bin():
        v = subprocess.run([elmer_solver(), '-v'], capture_output=True, text=True,
                           timeout=60, env=elmer_env(), stdin=subprocess.DEVNULL).stdout
        st['elmer_version'] = next((z.strip() for z in v.splitlines() if 'Version' in z), v[-200:])
    return st


if __name__ == '__main__':
    import json
    print(json.dumps(status(), indent=1))
