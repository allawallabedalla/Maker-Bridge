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
    'openfoam': 'OpenFOAM 12 (OpenFOAM Foundation): Linux Paket, Windows ueber WSL2 mit Ubuntu - Anleitung auf '
                'openfoam.org/download (Befehle dort ablesen; die Bridge fuehrt keine ungeprueften Installationsbefehle '
                'aus). Andere Installation: Umgebungsvariable MB2_OPENFOAM_BASHRC auf deren etc/bashrc setzen',
    'gcc': 'Windows: MSYS2 (winget install MSYS2.MSYS2), in "MSYS2 UCRT64": pacman -S mingw-w64-ucrt-x86_64-gcc; '
           'Linux: apt install gcc',
    'prusaslicer': 'Windows: Installer von prusa3d.com; Linux: apt install prusa-slicer',
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


def c_compiler(cpp=False):
    """C/C++-Compiler fuer Firmware-Hosttests (seit 19.11.2026): MSYS2 (Windows) oder PATH. None, wenn keiner da ist."""
    namen = ('g++', 'clang++', 'c++') if cpp else ('gcc', 'clang', 'cc')
    for n in namen:
        p = os.path.join(MSYS2_BIN, n + '.exe')
        if os.path.exists(p):
            return p
    for n in namen:
        p = shutil.which(n)
        if p:
            return p
    return None


def _wsl_pfad(p):
    """C:\\a\\b -> /mnt/c/a/b (WSL-Standard-Mount)."""
    if not (len(p) > 1 and p[1] == ':'):
        p = os.path.abspath(p)
    if len(p) > 1 and p[1] == ':':
        return '/mnt/' + p[0].lower() + p[2:].replace('\\', '/')
    return p.replace('\\', '/')


@functools.lru_cache(maxsize=1)
def openfoam():
    """OpenFOAM finden (seit 19.11.2026): {'art': 'nativ'|'wsl', 'bashrc': Pfad oder None} oder None.
    Reihenfolge: MB2_OPENFOAM_BASHRC, foamRun im PATH, /opt/openfoam*/etc/bashrc, ~/OpenFOAM/OpenFOAM-*/etc/bashrc;
    unter Windows dasselbe in WSL."""
    eigen = os.environ.get('MB2_OPENFOAM_BASHRC')
    if os.name == 'nt':
        if not shutil.which('wsl'):
            return None
        such = eigen or '$(ls -d /opt/openfoam*/etc/bashrc $HOME/OpenFOAM/OpenFOAM-*/etc/bashrc 2>/dev/null | tail -1)'
        try:
            r = subprocess.run(['wsl', '-e', 'bash', '-lc', f'f={such}; [ -n "$f" ] && . "$f" && command -v foamRun >/dev/null && echo "$f"'],
                               capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            return None
        f = r.stdout.strip().splitlines()
        return {'art': 'wsl', 'bashrc': f[-1]} if r.returncode == 0 and f else None
    if eigen and os.path.exists(eigen):
        return {'art': 'nativ', 'bashrc': eigen}
    if shutil.which('foamRun'):
        return {'art': 'nativ', 'bashrc': None}
    kand = glob.glob('/opt/openfoam*/etc/bashrc') + glob.glob(os.path.expanduser('~/OpenFOAM/OpenFOAM-*/etc/bashrc'))
    return {'art': 'nativ', 'bashrc': _newest_liste(kand)} if kand else None


def _newest_liste(kand):
    key = lambda h: [int(x) if x.isdigit() else 0 for x in re.split(r'[.\-+_\\/]', h)]  # noqa: E731
    return sorted(kand, key=key)[-1]


def openfoam_befehl(arbeit, befehl):
    """Befehlszeile fuer einen OpenFOAM-Aufruf im Fallordner (nativ oder ueber WSL)."""
    of = openfoam()
    if not of:
        raise RuntimeError('OpenFOAM fehlt - ' + INSTALL['openfoam'])
    quelle = f'. "{of["bashrc"]}" && ' if of.get('bashrc') else ''
    if of['art'] == 'wsl':
        return ['wsl', '-e', 'bash', '-lc', f'{quelle}cd "{_wsl_pfad(arbeit)}" && {befehl}']
    return ['bash', '-lc', f'{quelle}cd "{arbeit}" && {befehl}']


def openfoam_ausfuehren(arbeit, befehl, timeout=7200):
    return subprocess.run(openfoam_befehl(arbeit, befehl), capture_output=True, text=True, timeout=timeout,
                          stdin=subprocess.DEVNULL)


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
    """Windows: prusa-slicer-console.exe unter Program Files. Linux/macOS: prusa-slicer im PATH (seit 19.11.2026)."""
    for root in (r'C:\Program Files\Prusa3D\PrusaSlicer', r'C:\Program Files\PrusaSlicer'):
        p = os.path.join(root, 'prusa-slicer-console.exe')
        if os.path.exists(p):
            return p
    for n in ('prusa-slicer', 'PrusaSlicer'):
        p = shutil.which(n)
        if p:
            return p
    raise RuntimeError('PrusaSlicer nicht gefunden (Windows: Installer von prusa3d.com; Linux: apt install prusa-slicer).')


def prusa_bundle():
    """PrusaResearch.ini des installierten Slicers (Windows: neben der exe; Linux: /usr/share/PrusaSlicer)."""
    exe = prusa_slicer()
    kand = [os.path.join(os.path.dirname(exe), 'resources', 'profiles', 'PrusaResearch.ini'),
            os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(exe))), 'share', 'PrusaSlicer', 'profiles',
                         'PrusaResearch.ini'),
            '/usr/share/PrusaSlicer/profiles/PrusaResearch.ini', '/usr/share/prusa-slicer/profiles/PrusaResearch.ini']
    for k in kand:
        if os.path.exists(k):
            return k
    raise RuntimeError(f'PrusaResearch.ini nicht gefunden (gesucht: {kand})')


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


# ---------------------------------------------------------------- Einrichten nach Bedarf (seit 19.11.2026)

# Nur Befehle, die in diesem Projekt tatsaechlich gelaufen sind (Ubuntu 24.04); alles andere ist Anleitung.
GEPRUEFT = {
    'ccx': {'linux': ['sudo', '-n', 'apt-get', 'install', '-y', 'calculix-ccx']},
    'gcc': {'linux': ['sudo', '-n', 'apt-get', 'install', '-y', 'gcc']},
}
ANLEITUNG_WINDOWS = {
    'elmer': 'Windows nativ: Installer von nic.funet.fi/pub/sci/physics/elmer/bin/windows/ (siehe INSTALL). '
             'Oder WSL laut github.com/ElmerCSC/elmer-wsl: "wsl --install --no-distribution", elmer-wsl.tar.gz aus dem '
             'neuesten Release laden, "wsl --import Elmer --version 2 $env:USERPROFILE\\Elmer-WSL\\ elmer-wsl.tar.gz"',
}


def _vorhanden():
    def probe(fn):
        try:
            return bool(fn())
        except Exception:  # noqa: BLE001
            return False
    return {'ccx': bool(ccx()), 'elmer': bool(elmer_bin()), 'openfoam': bool(openfoam()), 'gcc': bool(c_compiler()),
            'prusaslicer': probe(prusa_slicer), 'kicad': probe(kicad_home)}


def einrichten(werkzeug=None, ausfuehren=False):
    """Status + Weg zum Einrichten je Werkzeug. ausfuehren nur fuer GEPRUEFT-Befehle (nach Zustimmung des Nutzers)."""
    da = _vorhanden()
    ziel = [werkzeug] if werkzeug else [w for w, ok in da.items() if not ok]
    sys_ = 'windows' if os.name == 'nt' else 'linux'
    out = {'vorhanden': da, 'fehlt': [w for w, ok in da.items() if not ok], 'schritte': {}}
    for w in ziel:
        if w not in da:
            out['schritte'][w] = {'fehler': f'unbekannt ({", ".join(da)})'}
            continue
        befehl = (GEPRUEFT.get(w) or {}).get(sys_)
        s = {'vorhanden': da[w], 'anleitung': (ANLEITUNG_WINDOWS.get(w) if sys_ == 'windows' else None) or INSTALL.get(w, ''),
             'befehl': ' '.join(befehl) if befehl else None}
        if ausfuehren and befehl and not da[w]:
            try:
                r = subprocess.run(befehl, capture_output=True, text=True, timeout=1800, stdin=subprocess.DEVNULL)
                s['ausgefuehrt'] = {'exit': r.returncode, 'ausgabe': (r.stdout + r.stderr)[-800:]}
            except (OSError, subprocess.SubprocessError) as ex:
                s['ausgefuehrt'] = {'exit': None, 'ausgabe': str(ex)}
            openfoam.cache_clear()
            s['vorhanden_danach'] = _vorhanden()[w]
        elif ausfuehren and not befehl:
            s['hinweis'] = 'kein geprueft hinterlegter Befehl - Anleitung von Hand ausfuehren'
        out['schritte'][w] = s
    return out
