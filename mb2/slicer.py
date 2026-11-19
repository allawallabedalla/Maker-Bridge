"""PrusaSlicer-CLI fuer den Prusa MK4 mit Input Shaper, Duese 0,4 (kein MK4S).

Profile NICHT per --printer-profile (die CLI faellt dabei still auf Standardwerte zurueck), sondern aus dem
Prusa-Bundle selbst aufgeloest (inkl. 'inherits') und per --load uebergeben. Danach wird im G-Code geprueft,
dass Drucker, Druck- und Filamentprofil wirklich drin sind. Uebernommen aus maker-bridge/slicer.py, ohne GUI und
ohne PrusaLink.
"""
import functools
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import zipfile
import zlib

from .werkzeuge import prusa_bundle, prusa_slicer

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATADIR = os.path.join(BASE, 'slicer_data')
DRUCKER = 'Original Prusa MK4 Input Shaper 0.4 nozzle'
MODELL = 'MK4IS'
BETT_MITTE = (125, 105)


def _bundle():
    return prusa_bundle()


def ensure_datadir():
    """Eigener Profilordner - die PrusaSlicer-Einstellungen des Nutzers bleiben unberuehrt."""
    dst = os.path.join(DATADIR, 'vendor', 'PrusaResearch.ini')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if not os.path.exists(dst) or os.path.getmtime(_bundle()) > os.path.getmtime(dst):
        shutil.copy2(_bundle(), dst)
        _sections.cache_clear()
    ini = os.path.join(DATADIR, 'PrusaSlicer.ini')
    if not os.path.exists(ini):
        with open(ini, 'w', encoding='utf-8') as f:
            f.write('use_binary_gcode_when_supported = 1\n\n[vendor:PrusaResearch]\nMK4 = 0.4\n')


@functools.lru_cache(maxsize=1)
def _sections():
    secs, cur = {}, None
    with open(os.path.join(DATADIR, 'vendor', 'PrusaResearch.ini'), encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            m = re.match(r'^\[(printer|print|filament):(.+)\]\s*$', line)
            if m:
                cur = secs.setdefault((m.group(1), m.group(2)), {})
            elif line.startswith('['):
                cur = None
            elif cur is not None and not line.startswith('#'):
                if ' = ' in line:
                    k, v = line.split(' = ', 1)
                    cur[k.strip()] = v
                elif line.rstrip().endswith('='):
                    cur[line.rstrip()[:-1].strip()] = ''
    return secs


def resolve(kind, name, _tiefe=0):
    secs = _sections()
    if (kind, name) not in secs:
        raise RuntimeError(f'{kind}-Profil nicht im Prusa-Bundle: {name!r} (slice_profiles listet die gueltigen)')
    if _tiefe > 20:
        raise RuntimeError('Zyklische Vererbung in ' + name)
    own, out = secs[(kind, name)], {}
    for parent in [p.strip().strip('"') for p in own.get('inherits', '').split(';') if p.strip()]:
        out.update(resolve(kind, parent, _tiefe + 1))
    out.update(own)
    out.pop('inherits', None)
    return out


def build_config(druck, material, overrides=None):
    ensure_datadir()
    if not druck.endswith(f'@{MODELL} 0.4'):
        raise RuntimeError(f'Druckprofil {druck!r} ist nicht fuer den MK4 IS 0.4 (muss auf "@{MODELL} 0.4" enden)')
    if not re.search(r'@PGIS$|@PG$', material):
        raise RuntimeError(f'Filament {material!r} ist kein MK4-Profil (muss auf "@PGIS" oder "@PG" enden)')
    cfg = {**resolve('printer', DRUCKER), **resolve('print', druck), **resolve('filament', material)}
    cfg.update({'printer_settings_id': DRUCKER, 'print_settings_id': druck, 'filament_settings_id': f'"{material}"'})
    for k in [k for k in cfg if k.startswith('compatible_')]:
        cfg.pop(k)
    cfg.update({k: str(v) for k, v in (overrides or {}).items()})
    text = ''.join(f'{k} = {v}\n' for k, v in sorted(cfg.items()))
    pfad = os.path.join(DATADIR, 'resolved', hashlib.sha1(text.encode()).hexdigest()[:12] + '.ini')
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, 'w', encoding='utf-8') as f:
        f.write(text)
    return pfad, cfg


def list_profiles(drucker, suche=''):
    ensure_datadir()
    secs = _sections()
    prints = sorted(n for k, n in secs if k == 'print' and not n.startswith('*') and n.endswith(f'@{MODELL} 0.4'))
    fil, gesehen = [], set()
    for kuerzel in ('@PGIS', '@PG'):                      # @PGIS hat Vorrang vor dem aelteren @PG
        for n in sorted(n for k, n in secs if k == 'filament' and not n.startswith('*') and n.endswith(' ' + kuerzel)):
            if n[:-len(kuerzel)].strip() not in gesehen:
                gesehen.add(n[:-len(kuerzel)].strip())
                fil.append(n)
    if suche:
        fil = [f for f in fil if suche.lower() in f.lower()]
    return {'drucker': drucker, 'druckprofile': prints, 'filamente': sorted(fil)[:150]}


# ---------------------------------------------------------------- Metadaten aus .bgcode

def _bgcode_meta(path):
    meta = {}
    with open(path, 'rb') as f:
        if f.read(4) != b'GCDE':
            return meta
        _ver, chk = struct.unpack('<IH', f.read(6))
        while True:
            hdr = f.read(8)
            if len(hdr) < 8:
                break
            btype, comp, usize = struct.unpack('<HHI', hdr)
            csize = struct.unpack('<I', f.read(4))[0] if comp else usize
            f.read(6 if btype == 5 else 2)
            data = f.read(csize)
            if chk == 1:
                f.read(4)
            if btype in (0, 2, 3, 4):
                if comp == 1:
                    data = zlib.decompress(data)
                elif comp != 0:
                    continue
                for line in data.decode('utf-8', 'replace').splitlines():
                    if '=' in line:
                        k, v = line.split('=', 1)
                        meta.setdefault(k.strip(), v.strip())
    return meta


_META_KEYS = ['printer_settings_id', 'print_settings_id', 'filament_settings_id', 'printer_model',
              'estimated printing time (normal mode)', 'filament used [g]', 'filament used [m]', 'filament_type',
              'layer_height', 'fill_density', 'support_material', 'nozzle_diameter', 'max_layer_z']


def summarize(path):
    meta = _bgcode_meta(path)
    return {k: meta[k].strip('"') for k in _META_KEYS if k in meta}


# ---------------------------------------------------------------- Slicen

def _cli(args, timeout):
    return subprocess.run([prusa_slicer(), '--datadir', DATADIR, *args], capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=timeout, stdin=subprocess.DEVNULL)


def slice_platte(platte_3mf, ausgabe, druck, material, stuetzen=False, brim_mm=0.0, perimeter=0, bricklayers=None):
    """EIN 3MF (cad_plate) -> .bgcode, mittig aufs Bett. Danach Profilpruefung + PrusaSlicer-Projekt zum Ansehen.
    bricklayers = {'teile': Namen, 'bbox_mm': Lage je Teil aus print/platte.json}: dann ASCII-G-Code +
    Nachbearbeitung (mb2/bricklayers.py) -> <ausgabe ohne .bgcode>.gcode statt .bgcode. Die Teile werden ueber
    Lage/Groesse den G-Code-Objekten zugeordnet (Reihenfolge im G-Code ist eine andere)."""
    if not os.path.exists(platte_3mf):
        raise RuntimeError('Keine Druckplatte - erst cad_plate.')
    ov = {}
    # Eigene Druckeinstellungen des Nutzers je Projekt (print/druck_overrides.json), z. B. Umfänge, Naht, Infill, z_offset
    eigen = os.path.join(os.path.dirname(platte_3mf), 'druck_overrides.json')
    if os.path.exists(eigen):
        with open(eigen, encoding='utf-8') as f:
            ov.update(json.load(f))
    ov['support_material'] = int(stuetzen)
    if stuetzen:
        ov['support_material_auto'] = 1
    if brim_mm > 0:
        ov.update({'brim_width': brim_mm, 'brim_type': 'outer_only', 'brim_separation': 0.1})
    if perimeter > 0:
        ov['perimeters'] = int(perimeter)
    if bricklayers:
        ov['binary_gcode'] = 0
        ausgabe = os.path.splitext(ausgabe)[0] + '.gcode'
    cfg_pfad, cfg = build_config(druck, material, ov)
    if os.path.exists(ausgabe):
        os.remove(ausgabe)            # sonst gilt eine alte Datei als Erfolg, wenn das Slicen still scheitert
    mitte = f'{BETT_MITTE[0]},{BETT_MITTE[1]}'
    binaer = [] if bricklayers else ['--binary-gcode']   # Bricklayers braucht ASCII zum Nachbearbeiten
    p = _cli(['--load', cfg_pfad, '--export-gcode', *binaer, '--center', mitte, '-o', ausgabe, platte_3mf],
             1800)
    if p.returncode or not os.path.exists(ausgabe):
        return {'ok': False, 'log': (p.stdout + p.stderr)[-3000:]}
    bl_bericht = None
    if bricklayers:
        from . import bricklayers as bl
        alt = open(ausgabe, encoding='utf-8').read().split('\n')
        # bricklayers = {'teile': {name, ...}, 'bbox_mm': {name: [xmin, ymin, zmin, xmax, ymax, zmax]}}
        zu = bl.objekt_zuordnung(alt, bricklayers['bbox_mm'])
        idx = {zu[n] for n in bricklayers['teile']}
        neu, stat = bl.bearbeiten(alt, idx)
        bl_bericht = {**stat, 'zuordnung': zu, 'teile': sorted(bricklayers['teile']),
                      'pruefung': bl.pruefen(alt, neu, idx)}
        with open(ausgabe, 'w', encoding='utf-8', newline='\n') as f:
            f.write('\n'.join(neu))
        st = {k: v.strip('"') for k, v in bl.meta_ascii(neu).items() if k in _META_KEYS}
    else:
        st = summarize(ausgabe)
    probleme = []
    if bl_bericht and not bl_bericht['pruefung']['ok']:
        probleme += ['Bricklayers: ' + f for f in bl_bericht['pruefung']['fehler']]
    if st.get('printer_model') != MODELL:
        probleme.append(f'printer_model im G-Code ist {st.get("printer_model")!r}, erwartet {MODELL!r}')
    if st.get('print_settings_id') != druck:
        probleme.append(f'Druckprofil im G-Code {st.get("print_settings_id")!r} statt {druck!r}')
    if st.get('filament_settings_id') != material:
        probleme.append(f'Filament im G-Code {st.get("filament_settings_id")!r} statt {material!r}')
    if st.get('nozzle_diameter', '0.4').split(',')[0] != '0.4':
        probleme.append(f'Duese {st.get("nozzle_diameter")} statt 0.4')
    res = {'ok': not probleme, 'bgcode' if not bricklayers else 'gcode': ausgabe, 'stats': st, 'config': cfg_pfad}
    if bl_bericht:
        res['bricklayers'] = bl_bericht
    if probleme:
        res['probleme'] = probleme + ['NICHT drucken - Profile pruefen.']
    res['projekt_3mf'] = _projekt_3mf(platte_3mf, os.path.splitext(ausgabe)[0] + '.projekt.3mf', cfg_pfad, mitte)
    return res


def _projekt_3mf(platte_3mf, ziel, cfg_pfad, mitte):
    """PrusaSlicer-Projekt mit Modell UND aufgeloesten Profilen - zum Ansehen in der GUI (statt G-Code-Viewer)."""
    p = _cli(['--load', cfg_pfad, '--export-3mf', '--center', mitte, '-o', ziel, platte_3mf], 600)
    if p.returncode or not os.path.exists(ziel):
        return None
    zeilen = ['; generated by PrusaSlicer (maker-bridge-2)']
    with open(cfg_pfad, encoding='utf-8') as f:
        zeilen += ['; ' + z.rstrip('\n') for z in f if '=' in z]
    tmp = ziel + '.tmp'
    with zipfile.ZipFile(ziel) as zin, zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename != 'Metadata/Slic3r_PE.config':
                zout.writestr(item, zin.read(item.filename))
        zout.writestr('Metadata/Slic3r_PE.config', '\n'.join(zeilen) + '\n')
    os.replace(tmp, ziel)
    return ziel
