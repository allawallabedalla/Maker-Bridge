"""Elektronik-Pruefungen E1-E25 (OCW_PRUEFKATALOG.md 3.7) - analytischer Python-Schritt nach dem DRC.

Eingaben (alles nur GELESEN, nie im Projektordner geschrieben):
- ``<pdir>/electronics/<name>.kicad_pcb``: Layout ueber pcbnew (KiCad-10-Python, wie mb2/kicad.py es aufruft) - Pads, Bahnen,
  Vias, Zonen-Fuellungen, Sperrflaechen, Netzklassen. Gelesen wird eine Kopie im Temp-Ordner.
- ``<name>.kicad_sch``: Netzliste mit Pin-Namen und Pin-Typen ueber ``kicad-cli sch export netlist`` (ebenfalls aus einer Kopie).
  Ohne Schaltplan: Netze aus den Pads der Platine (dann ohne Pin-Typen, viele Pruefungen 'uebersprungen').
- Lagenaufbau: ``(setup (stackup ...))`` der .kicad_pcb, sonst ``_projekt.elektronik.lagenaufbau``, sonst Standard
  (JLC 2 Lagen: 35 um Cu, 1,51 mm FR4 er 4,5; 4 Lagen JLC7628: 35 um, Prepreg 0,21 mm er 4,4) - im Bericht als 'angenommen'.
- ``mb2/bauteile.json`` (+ optional ``<pdir>/electronics/bauteile.json``, gleiche Form, ergaenzt/ueberschreibt):
  Kennwerte je LCSC-Nr./MPN/Wert mit Quelle.
- ``cad/soll.json`` -> ``_projekt``: ``akku_mAh``, ``laufzeit_ziel_h``, ``T_max_C`` (siehe FELDER.md) und neu, alles optional,
  ``_projekt.elektronik``:
    ``netze``            {"<Netz>": {"V_min": .., "V_max": ..}}  feste Spannungen (hat Vorrang)
    ``i2c_kHz``          I2C-Takt, Standard 400 (Fast-mode, strengere Grenze als 100)
    ``modi``             [{"name": "tx", "I_mA": 120, "anteil": 0.001}, ...]  Betriebsarten fuer E6 (Anteile <= 1)
    ``V_abschalt_V``     Akku-Abschaltspannung der Firmware (E8)
    ``R_int_Ohm``        Akku-Innenwiderstand (E8)
    ``qi_spule_uH``      Induktivitaet der Qi-Empfaengerspule (E22)
    ``lautsprecher_Ohm`` Lautsprecherimpedanz (E20)
    ``funk``             {"r_m": .., "umgebung": "frei|sicht|land|dorf|stadt|innen", "hindernisse": ["ziegel_dach", 6],
                         "kabel": [{"typ": "rg174", "m": 3}], "magnetfuss_ohne_blech": false,
                         "G_t_dBi": 0, "G_r_dBi": 0, "P_t_dBm": .., "P_rx_min_dBm": ..} (E16; Pflicht, sobald die
                         Platine funkt – ohne Angabe 'fehler'; fehlt umgebung -> 'dorf')
    ``frequenzen``       {"<Netz>": Hz}  Signalfrequenz je Netz (E13)
    ``abtastrate_Hz``    ADC-Abtastrate fuer Anti-Alias (E12)
    ``T_a_C``            Luft an der Platine im Gehaeuse (E4; schliesst Eigenerwaermung ein, Sonne kommt bei aussen dazu).
                         Sonst realterme.teil_temperatur: T_max_C (fehlt: 40 C) + Sonne + P_ges * Rth_gehaeuse
    ``Rth_gehaeuse_K_W`` Waermewiderstand Gehaeuseluft -> Umgebung fuer die Eigenerwaermung (E4), sonst 15 K/W angenommen
    ``kuehlflaeche``     true/false: Kupferflaeche unter Reglern/Ladern (E4; false -> RthJA x1,5, fehlt -> x1,5 angenommen)
    ``lagenaufbau``      [{"typ": "copper", "dicke_mm": 0.035}, {"typ": "dielectric", "dicke_mm": 1.51, "er": 4.5}, ...]
    ``module``           Kaufmodule ohne KiCad-Platine (z. B. LILYGO T3 = ESP32 + SX1276, nur STEP unter electronics/):
                         [{"name": "LILYGO T3 v1.6.1", "funk": true, "f_MHz": 868, "akku": true, "akku_mAh": 2000,
                           "chemie": "lipo", "R_int_Ohm": 0.15, "V_abschalt_V": 3.4, "I_ruhe_uA": 300,
                           "wandler": "ldo|buck|boost|buckboost|keiner", "eta": 0.85, "V_out_V": 3.3, "dropout_V": 0.25,
                           "I_peak_mA": 400, "VDD_min_V": 3.0, "I_chg_mA": 500, "ntc": false}]
                         Ohne .kicad_pcb laufen damit die Pruefungen, die nur soll-Daten brauchen: E6, E8, E15 (Kaufmodul:
                         hoechstens 'warnung'), E16, E21; der Rest steht als ein Eintrag 'E-Rest' (uebersprungen).
                         Felder am Modul ergaenzen die gleichnamigen unter _projekt/_projekt.elektronik (die gehen vor).

REALTERME (mb2/realterme.py, Audit Scheinsicherheit 15.11.2026): E6 rechnet mit C_eff = C/abminderung('kapazitaet')
 (nutzbar 0,85, Kaelte, Alterung, Selbstentladung) und dem Wandler (I_bat = I*V_out/(eta*V_bat), eta 0,8), 'ok' erst ab
 1,25 x Ziel; E8 mit R_eff = R_int*abminderung('rint') und 0,15 V Reserve; E21 verlangt bei T_min_C < 10 oder aussen einen
 NTC am TS-Pin, 'ok' nur bis 0,5 C; E4 mit T_teil und RthJA*abminderung('rthja'); E15 hoechstens 'warnung', solange
 Metall im Gehaeuse ungeprueft ist. Annahmen (realterme 'angenommen') deckeln auf 'warnung'.

KONVENTION Strom je Netz (A), Reihenfolge:
 1. Netzklasse, deren NAME einen Strom traegt, z. B. "Leistung_2A", "Akku 500mA", "VBAT_1.5A": gilt fuer alle Netze der Klasse.
 2. Symbolfeld ``Strom`` an einem beliebigen Bauteil: "VBAT=0.5A; +3V3=120mA" (Einheit A oder mA, ohne Einheit A). Mehrere
    Bauteile am selben Netz werden addiert (jedes Bauteil nennt seine Last).
 3. Sonst Schaetzung aus der Bauteil-DB: Summe der Spitzenstroeme I_peak_A aller Teile mit Versorgungspin am Netz; Regler geben
    ihren Ausgangsstrom an den Eingang weiter (LDO/Lader: I_in = I_out + I_q, Schaltregler: P_out/(eta*V_in,min), eta 0,8 angenommen).
 Sind 1 und 2 gegeben, zaehlt das Maximum. Geschaetzte Stroeme sind Spitzenwerte: Waermepruefungen (E3, E4) melden dann bei
 Ueberschreitung nur 'warnung' (konservativ, aber kein 'fehler' aus einer Spitze), Spannungsfall/Brownout (E2, E8) voll.

KONVENTION Spannung je Netz (V_min..V_max): 1. _projekt.elektronik.netze, 2. Reglerausgang aus der DB (Pinrolle vout, V_out_V
 oder aus FB-Teiler mit V_fb_V), 3. Akku: Pinrolle 'bat' eines LiPo-Laders -> V_min = Firmware-Abschaltung, sonst Schutz-IC
 (DW01A 2,4 V), sonst Chemie; V_max = Ladeschluss; Batteriehalter aus der DB (Zellen aus "2x" im Wert), 4. Netzname (+3V3, 5V,
 1V8 ... +-5 %), 5. Netz ohne eigene Quelle, das ueber <= 1 kOhm an einer bekannten Schiene haengt (RC-Filter vor VCC),
 6. Logiknetze: 0..VDD des treibenden Bauteils.

Externe Grenzwerte (nicht OCW) sind im Feld 'quelle' als "extern" gekennzeichnet: IPC-2221B/2152 (Leiterbahnerwaermung),
Hammerstad-Jensen (Microstrip), NXP UM10204 (I2C), LiPo-C-Rate, WPC Qi (Resonanz).
"""
import glob
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from . import ergebnis, projekt_soll, uebersprungen
from .. import realterme as rt

MODUL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PFAD = os.path.join(MODUL_DIR, 'bauteile.json')

RHO_CU = 1.72e-5          # Ohm*mm (1,72e-8 Ohm*m, 20 C) -> 35 um: 0,49 mOhm/Quadrat (Katalog E2: ~0,5)
ALPHA_CU = 0.00393        # 1/K
MU0 = 4e-7 * math.pi * 1e-3   # H/mm
EPS0 = 8.854e-15          # F/mm
C0 = 2.998e11             # mm/s
VIA_HUELSE_MM = 0.020     # Kupfer in der Bohrung, IPC-6012 Klasse 2 Mittelwert (angenommen)

Q = {
    'E1': '6.002 L4, 6.012 L14 (OCW); I2C-V_OL 0,4 V NXP UM10204 (extern)',
    'E2': '6.622 L12 (OCW): R = rho*l/(w*t)',
    'E3': '6.622 L12/16 (OCW) P = I^2 R; Grenze IPC-2221B-Naeherung der IPC-2152-Kurven (extern)',
    'E4': '6.622 L16, 6.111 L16 (OCW): T_j = T_a + P*RthJA',
    'E5': '6.002 L22, 6.012 L8 (OCW)',
    'E6': '6.002 L22 (OCW): t = C_eff/I_bat; Abschlaege mb2/realterme.py (Zellendatenblaetter)',
    'E7': '6.002 L3/L12 (OCW)',
    'E8': '10.626 L3, 6.101 (OCW): V = V0 - I*R_eff; R_int-Abschlaege mb2/realterme.py',
    'E9': '6.622 L38, 6.101 (OCW): L_loop = mu0*h*l/w',
    'E10': '6.622 L38 (OCW)',
    'E11': '6.002 L13 (OCW); t_r = 0,8473*R*C und Grenzen NXP UM10204 (extern)',
    'E12': '6.002 L18, 6.101 (OCW): f_c = 1/(2 pi R C)',
    'E13': '6.013 L11 (OCW): l > lambda/8',
    'E14': '6.013 L11-14 (OCW); Microstrip Hammerstad-Jensen (extern)',
    'E15': '6.013 L18/19 (OCW)',
    'E16': '6.013 L17 (OCW): Friis',
    'E17': '6.622 L38 (OCW): L = mu0*h*l/w',
    'E18': '6.002 L13, 6.622 L38 (OCW): C = eps*A/d',
    'E19': '6.622 L28-30 (OCW): f0 <= f_sw/10',
    'E20': '6.002 L22, 6.101 (OCW): P = V^2/(2R_L), I = V/R_L (BTL, Amplitude V_DD)',
    'E21': 'C-Rate LiPo (extern, Zellenhersteller: Standardladung 0,5 C, max 1 C; Laden 0-10 C nur <= 0,5 C, unter 0 C '
           'unzulaessig, JEITA); Waerme 6.622 L16',
    'E22': '6.622 L9/L12, 6.013 L14 (OCW); Qi-Band WPC (extern)',
    'E23': '6.622 L38 (OCW): P = Q_g*V*f',
    'E24': '6.101 (OCW)',
    'E25': '6.302 (OCW)',
}
TITEL = {
    'E1': 'Logikpegel', 'E2': 'Spannungsfall', 'E3': 'Leiterbahnerwaermung', 'E4': 'Sperrschichttemperatur',
    'E5': 'Widerstand/LED', 'E6': 'Akkulaufzeit', 'E7': 'Spannungsteiler', 'E8': 'Brownout bei Funkspitze',
    'E9': 'Entkopplung', 'E10': 'Hot Loop Schaltregler', 'E11': 'I2C-Pull-up', 'E12': 'RC-Grenzfrequenz',
    'E13': 'Lange Leitung', 'E14': 'Wellenwiderstand Z0', 'E15': 'Antennen-Keepout', 'E16': 'Link-Budget',
    'E17': 'Rueckstrompfad', 'E18': 'Uebersprechen', 'E19': 'EMI-Filter', 'E20': 'Verstaerker vs. Lautsprecher',
    'E21': 'LiPo-Ladestrom', 'E22': 'Qi-Resonanz', 'E23': 'Gate-Ansteuerung', 'E24': 'Zener-Regler',
    'E25': 'OpAmp-Stabilitaet',
}

# --------------------------------------------------------------------------------------------- KiCad lesen

_PCBNEW = r'''
import sys, json, pcbnew
b = pcbnew.LoadBoard(sys.argv[1])
MM = 1e-6
def xy(p): return [round(p.x * MM, 4), round(p.y * MM, 4)]
def ln(l): return b.GetLayerName(l)
def polys(ps):
    out = []
    for i in range(ps.OutlineCount()):
        o = ps.Outline(i)
        e = {'aussen': [xy(o.CPoint(j)) for j in range(o.PointCount())], 'loecher': []}
        for k in range(ps.HoleCount(i)):
            h = ps.Hole(i, k)
            e['loecher'].append([xy(h.CPoint(j)) for j in range(h.PointCount())])
        out.append(e)
    return out
def zone(z, fp=None):
    e = {'netz': z.GetNetname(), 'regel': bool(z.GetIsRuleArea()), 'lagen': [ln(l) for l in z.GetLayerSet().CuStack()], 'fp': fp}
    if e['regel']:
        for k, f in (('kein_kupfer', 'GetDoNotAllowZoneFills'), ('kein_kupfer', 'GetDoNotAllowCopperPour'),
                     ('keine_bahnen', 'GetDoNotAllowTracks'), ('keine_vias', 'GetDoNotAllowVias'), ('keine_pads', 'GetDoNotAllowPads')):
            if hasattr(z, f) and k not in e:
                e[k] = bool(getattr(z, f)())
        e['umriss'] = polys(z.Outline())
    else:
        e['flaechen'] = {}
        for l in z.GetLayerSet().CuStack():
            try: e['flaechen'][ln(l)] = polys(z.GetFilledPolysList(l))
            except Exception: pass
    return e
ds = b.GetDesignSettings()
out = {'version': pcbnew.GetBuildVersion(), 'kupferlagen': b.GetCopperLayerCount(),
       'lagen': [ln(l) for l in b.GetEnabledLayers().CuStack()], 'dicke_mm': ds.GetBoardThickness() * MM}
bb = b.GetBoardEdgesBoundingBox(); out['rand'] = [xy(bb.GetOrigin()), xy(bb.GetEnd())]
nk = {}
for name, net in b.GetNetsByName().items():
    try: nk[str(name)] = net.GetNetClassName()
    except Exception:
        try: nk[str(name)] = net.GetNetClass().GetName()
        except Exception: nk[str(name)] = ''
out['netzklassen'] = nk
fps, zs = [], []
for fp in b.GetFootprints():
    f = {'ref': fp.GetReference(), 'wert': fp.GetValue(), 'fp': fp.GetFPIDAsString(), 'pos': xy(fp.GetPosition()),
         'rot': fp.GetOrientationDegrees(), 'seite': 'B' if fp.IsFlipped() else 'F', 'felder': {}, 'pads': []}
    for fl in fp.GetFields():
        if fl.GetName() not in ('Reference', 'Value', 'Footprint', 'Datasheet', 'Description'):
            f['felder'][fl.GetName()] = fl.GetText()
    try:
        cy = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd)
        if cy.OutlineCount():
            bx = cy.BBox(); f['huelle'] = [xy(bx.GetOrigin()), xy(bx.GetEnd())]
    except Exception: pass
    if 'huelle' not in f:
        bx = fp.GetBoundingBox(False, False); f['huelle'] = [xy(bx.GetOrigin()), xy(bx.GetEnd())]
    for p in fp.Pads():
        try: gr = p.GetSize(pcbnew.F_Cu)
        except Exception: gr = p.GetSize()
        f['pads'].append({'nr': p.GetNumber(), 'netz': p.GetNetname(), 'pos': xy(p.GetPosition()), 'gr': xy(gr),
                          'rot': p.GetOrientationDegrees(), 'typ': p.GetPinType(), 'fkt': p.GetPinFunction(),
                          'lagen': [ln(l) for l in p.GetLayerSet().CuStack()],
                          'bohr_mm': p.GetDrillSize().x * MM})
    for z in fp.Zones():
        zs.append(zone(z, fp.GetReference()))
    fps.append(f)
out['bauteile'] = fps
tr = []
for t in b.GetTracks():
    c = t.GetClass()
    if c == 'PCB_VIA':
        tr.append({'art': 'via', 'pos': xy(t.GetPosition()), 'netz': t.GetNetname(), 'bohr_mm': t.GetDrillValue() * MM})
    else:
        tr.append({'art': 'bogen' if c == 'PCB_ARC' else 'bahn', 'a': xy(t.GetStart()), 'b': xy(t.GetEnd()),
                   'w': t.GetWidth() * MM, 'lage': ln(t.GetLayer()), 'netz': t.GetNetname(), 'l': t.GetLength() * MM})
out['bahnen'] = tr
for z in b.Zones():
    zs.append(zone(z))
out['zonen'] = zs
json.dump(out, open(sys.argv[2], 'w', encoding='utf-8'))
print('OK')
'''


def _kicad_bin(name):
    from ..werkzeuge import kicad_home
    return os.path.join(kicad_home(), 'bin', name)


def finde_platine(pdir):
    """Haupt-.kicad_pcb in <pdir>/electronics (ohne Sicherungen/Zwischenstaende)."""
    ed = os.path.join(pdir, 'electronics')
    if not os.path.isdir(ed):
        return None
    kand = [f for f in glob.glob(os.path.join(ed, '*.kicad_pcb'))
            if not re.search(r'\.(vor-|lauf|unplaced|best|platz|v\d)', os.path.basename(f))]
    if not kand:
        return None
    pros = {os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(ed, '*.kicad_pro'))}
    kand.sort(key=lambda f: (os.path.splitext(os.path.basename(f))[0] not in pros, -os.path.getsize(f)))
    return kand[0]


_KICAD_CACHE = {}


def _kicad_stempel(pcb):
    ed = os.path.dirname(pcb)
    fs = [pcb] + sorted(glob.glob(os.path.join(ed, '*.kicad_sch')) + glob.glob(os.path.join(ed, '*.kicad_pro')))
    return tuple((f, os.path.getmtime(f), os.path.getsize(f)) for f in fs if os.path.exists(f))


def lese_kicad(pcb):
    """Wie _lese_kicad, aber je Dateistand nur einmal (merkmale_platine und pruefe lesen dieselbe Platine)."""
    import copy
    key = _kicad_stempel(pcb)
    if key not in _KICAD_CACHE:
        if len(_KICAD_CACHE) >= 4:
            _KICAD_CACHE.clear()
        _KICAD_CACHE[key] = _lese_kicad(pcb)
    return copy.deepcopy(_KICAD_CACHE[key])


def _lese_kicad(pcb):
    """Layout (pcbnew) + Netzliste (kicad-cli) aus Kopien in einem Temp-Ordner. Rueckgabe dict."""
    ed = os.path.dirname(pcb)
    name = os.path.splitext(os.path.basename(pcb))[0]
    tmp = tempfile.mkdtemp(prefix='mb2_el_')
    try:
        shutil.copy(pcb, tmp)
        for f in glob.glob(os.path.join(ed, '*.kicad_pro')) + glob.glob(os.path.join(ed, '*.kicad_sch')):
            shutil.copy(f, tmp)
        skript = os.path.join(tmp, '_lies.py')
        open(skript, 'w', encoding='utf-8').write(_PCBNEW)
        oj = os.path.join(tmp, 'layout.json')
        r = subprocess.run([_kicad_bin('python.exe'), skript, os.path.join(tmp, os.path.basename(pcb)), oj],
                           capture_output=True, text=True, timeout=600, stdin=subprocess.DEVNULL)
        if not os.path.exists(oj):
            raise RuntimeError('pcbnew-Auszug fehlgeschlagen: ' + (r.stdout + r.stderr)[-600:])
        lay = json.load(open(oj, encoding='utf-8'))
        lay['stackup_sexpr'] = _stackup_sexpr(pcb)
        netz = None
        sch = os.path.join(tmp, name + '.kicad_sch')
        if os.path.exists(sch):
            ox = os.path.join(tmp, 'netz.xml')
            subprocess.run([_kicad_bin('kicad-cli.exe'), 'sch', 'export', 'netlist', '--format', 'kicadxml', '-o', ox, sch],
                           capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
            if os.path.exists(ox):
                netz = _lies_netzliste_xml(ox)
        return {'pcb': pcb, 'layout': lay, 'netzliste': netz}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _stackup_sexpr(pcb):
    from ..sexpr import child, children, num, parse
    txt = open(pcb, encoding='utf-8').read()
    i = txt.find('(stackup')
    if i < 0:
        return None
    tiefe, j = 0, i
    while j < len(txt):
        if txt[j] == '(':
            tiefe += 1
        elif txt[j] == ')':
            tiefe -= 1
            if tiefe == 0:
                break
        j += 1
    node = parse(txt[i:j + 1])
    out = []
    for l in children(node, 'layer'):
        typ = child(l, 'type')
        d = child(l, 'thickness')
        er = child(l, 'epsilon_r')
        t = str(typ[1]) if typ else ''
        out.append({'name': l[1], 'typ': 'copper' if t == 'copper' else ('dielectric' if t in ('core', 'prepreg') else t),
                    'dicke_mm': num(d[1]) if d else None, 'er': num(er[1]) if er else None})
    return out


def _lies_netzliste_xml(pfad):
    root = ET.parse(pfad).getroot()
    teile = {}
    for c in root.iter('comp'):
        felder = {}
        for f in c.iter('field'):
            felder[f.get('name')] = (f.text or '').strip()
        lib = c.find('libsource')
        teile[c.get('ref')] = {'wert': c.findtext('value') or '', 'fp': c.findtext('footprint') or '', 'felder': felder,
                               'lib': (lib.get('lib') + ':' + lib.get('part')) if lib is not None else '',
                               'dnp': any(p.get('name') == 'dnp' for p in c.iter('property'))}
    netze = {}
    for n in root.iter('net'):
        knoten = []
        for nd in n.iter('node'):
            pin = nd.get('pin') or ''
            fkt = nd.get('pinfunction') or ''
            if fkt.endswith('_' + pin):
                fkt = fkt[:-len(pin) - 1]
            knoten.append({'ref': nd.get('ref'), 'pin': pin, 'name': fkt, 'typ': (nd.get('pintype') or '').split('+')[0]})
        netze[n.get('name')] = knoten
    return {'teile': teile, 'netze': netze}


# --------------------------------------------------------------------------------------------- Werte, DB

_SI = {'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'µ': 1e-6, 'm': 1e-3, 'k': 1e3, 'K': 1e3, 'M': 1e6, 'G': 1e9, 'R': 1.0, '': 1.0}


def wert_si(text, art='R'):
    """'4k7' -> 4700, '100n' -> 1e-7, '2.2uH' -> 2.2e-6, '1M' -> 1e6, '4R7' -> 4.7, '0' -> 0. Ferrit '220R@100MHz' -> None."""
    if text is None:
        return None
    s = str(text).strip()
    if '@' in s:
        return None
    m = re.match(r'^(\d+(?:[.,]\d+)?)\s*([pnuµmkKMGR]?)(\d*)\s*(?:Ohm|Ω|F|H|R)?\s*(?:\s|$|[A-Za-z])', s + ' ')
    if not m:
        return None
    zahl, pref, rest = m.group(1).replace(',', '.'), m.group(2), m.group(3)
    if rest and pref:
        zahl = zahl + '.' + rest if '.' not in zahl else zahl + rest
    if art == 'C' and pref == 'M':
        return None
    return float(zahl) * _SI[pref]


def _norm(s):
    return re.sub(r'[\s\-_]', '', str(s or '')).upper()


def lade_db(pdir=None):
    db = json.load(open(DB_PFAD, encoding='utf-8'))
    if pdir:
        p = os.path.join(pdir, 'electronics', 'bauteile.json')
        if os.path.exists(p):
            extra = json.load(open(p, encoding='utf-8'))
            db['teile'].update(extra.get('teile', {}))
            for k in ('generisch_led', 'chemie'):
                db.setdefault(k, {}).update(extra.get(k, {}))
    idx = {}
    for key, e in db['teile'].items():
        for a in [key] + e.get('mpn', []) + e.get('werte', []):
            idx.setdefault(('M', _norm(a)), key)
        for a in e.get('lcsc', []):
            idx[('L', _norm(a))] = key
    db['_idx'] = idx
    return db


def db_eintrag(db, teil):
    f = teil.get('felder', {})
    for k in ('LCSC', 'LCSC Part', 'JLCPCB'):
        if f.get(k) and ('L', _norm(f[k])) in db['_idx']:
            return db['teile'][db['_idx'][('L', _norm(f[k]))]]
    for k in ('MPN', 'Manufacturer Part Number'):
        if f.get(k) and ('M', _norm(f[k])) in db['_idx']:
            return db['teile'][db['_idx'][('M', _norm(f[k]))]]
    w = _norm(teil.get('wert'))
    if ('M', w) in db['_idx']:
        return db['teile'][db['_idx'][('M', w)]]
    return None


def ausdruck(expr, vdd):
    """'0.75*VDD' / 'VDD-0.4' / Zahl -> V. Nur Zahlen, VDD und + - * / ( ) erlaubt."""
    if expr is None:
        return None
    if isinstance(expr, (int, float)):
        return float(expr)
    if vdd is None:
        return None
    s = str(expr).replace(' ', '')
    if not re.fullmatch(r'[0-9.+\-*/()VD]*', s):
        raise ValueError('Ausdruck nicht erlaubt: ' + s)
    return float(eval(s.replace('VDD', repr(float(vdd))), {'__builtins__': {}}, {}))  # noqa: S307 - gefiltert


def _vf_diode(e, I):
    """V_F bei Strom I aus der DB-Tabelle [[I, V], ...] (linear in log I), None = unbekannt."""
    tab = (e or {}).get('V_f_tabelle')
    if not tab:
        return (e or {}).get('V_f_V')
    if I <= tab[0][0]:
        return tab[0][1]
    for (i0, v0), (i1, v1) in zip(tab, tab[1:]):
        if i0 <= I <= i1:
            return v0 + (v1 - v0) * (math.log(I) - math.log(i0)) / (math.log(i1) - math.log(i0))
    return tab[-1][1]


def _strom_text(t):
    m = re.fullmatch(r'\s*(\d+(?:[.,]\d+)?)\s*(mA|A|uA|µA)?\s*', t)
    if not m:
        return None
    v = float(m.group(1).replace(',', '.'))
    return v * {'mA': 1e-3, 'uA': 1e-6, 'µA': 1e-6}.get(m.group(2), 1.0)


# --------------------------------------------------------------------------------------------- Geometrie

def _in_poly(x, y, pts):
    inn = False
    n = len(pts)
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inn = not inn
        j = i
    return inn


def in_flaeche(x, y, polys):
    for p in polys:
        if _in_poly(x, y, p['aussen']) and not any(_in_poly(x, y, h) for h in p['loecher']):
            return True
    return False


def _bbox(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _schneiden(a, b, c, d):
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return (o(a, b, c) * o(a, b, d) < 0) and (o(c, d, a) * o(c, d, b) < 0)


def _abst_seg(p, a, b):
    """Abstand Punkt p zur Strecke ab und Lage s (0..1) des Fusspunkts."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dy * dy
    s = 0.0 if l2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
    return math.dist(p, (a[0] + s * dx, a[1] + s * dy)), s


def _rand_abst(p, pts):
    return min(_abst_seg(p, pts[i], pts[(i + 1) % len(pts)])[0] for i in range(len(pts)))


def flaechen_ueberlapp(poly_a, polys_b, tol=0.05):
    """Ueberlappt das Polygon poly_a (Liste Punkte) eine der Fuellflaechen polys_b mehr als tol (mm)? Punkte, die nur
    auf dem Rand liegen (Fuellung endet an der Sperrflaeche), zaehlen nicht."""
    ax0, ay0, ax1, ay1 = _bbox(poly_a)
    for p in polys_b:
        bx0, by0, bx1, by1 = _bbox(p['aussen'])
        if bx1 < ax0 or bx0 > ax1 or by1 < ay0 or by0 > ay1:
            continue
        if any(_in_poly(x, y, poly_a) and _rand_abst((x, y), poly_a) > tol for x, y in p['aussen']):
            return True
        if any(in_flaeche(x, y, [p]) and _rand_abst((x, y), p['aussen']) > tol for x, y in poly_a):
            return True
        n, m = len(poly_a), len(p['aussen'])
        for i in range(n):
            for j in range(m):
                if _schneiden(poly_a[i], poly_a[(i + 1) % n], p['aussen'][j], p['aussen'][(j + 1) % m]):
                    return True
    return False


def _abtasten(a, b, schritt):
    l = math.dist(a, b)
    n = max(1, int(l / schritt))
    return [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n + 1)]


def _pad_ecken(p):
    w, h = p['gr'][0] / 2, p['gr'][1] / 2
    a = math.radians(p.get('rot', 0))
    out = [tuple(p['pos'])]
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        lx, ly = sx * w, sy * h
        out.append((p['pos'][0] + lx * math.cos(a) + ly * math.sin(a), p['pos'][1] - lx * math.sin(a) + ly * math.cos(a)))
    return out


# --------------------------------------------------------------------------------------------- Mikrostreifen

def microstrip_z0(w, h, t, er):
    """Hammerstad-Jensen (vereinfachte geschlossene Form, extern) mit Dickenkorrektur. mm, Ohm. -> (Z0, eps_eff)."""
    if t and t > 0:
        w = w + (t / math.pi) * (1 + math.log(2 * h / t))
    u = w / h
    if u <= 1:
        ee = (er + 1) / 2 + (er - 1) / 2 * ((1 + 12 / u) ** -0.5 + 0.04 * (1 - u) ** 2)
        z0 = 60 / math.sqrt(ee) * math.log(8 / u + u / 4)
    else:
        ee = (er + 1) / 2 + (er - 1) / 2 * (1 + 12 / u) ** -0.5
        z0 = 120 * math.pi / (math.sqrt(ee) * (u + 1.393 + 0.667 * math.log(u + 1.444)))
    return z0, ee


def microstrip_breite(z_soll, h, t, er):
    """Breite fuer Z0 = z_soll (Bisektion ueber microstrip_z0, Z0 faellt mit w)."""
    lo, hi = 0.01, 20.0 * h
    for _ in range(60):
        m = (lo + hi) / 2
        if microstrip_z0(m, h, t, er)[0] > z_soll:
            lo = m
        else:
            hi = m
    return (lo + hi) / 2


def ipc2221_dT(I, w_mm, t_mm, aussen=True):
    """IPC-2221B: I = k*dT^0.44*A^0.725 (A in mil^2, k 0,048 aussen / 0,024 innen) -> dT in K (extern)."""
    A = (w_mm / 0.0254) * (t_mm / 0.0254)
    k = 0.048 if aussen else 0.024
    return (I / (k * A ** 0.725)) ** (1 / 0.44)


# --------------------------------------------------------------------------------------------- Modell

I2C_RE = re.compile(r'(?<![A-Z])(SDA|SCL)(?![A-Z])')
GND_RE = re.compile(r'^/?(GND|AGND|DGND|PGND|GNDA|GNDD|VSS|0V|EARTH)\b', re.I)


class Platine:
    """Netzliste + Layout + DB + soll-Felder, daraus Spannungen, Stroeme, Graphen."""

    def __init__(self, k, db, psoll):
        self.k = k
        self.db = db
        self.ps = psoll or {}
        self.el = self.ps.get('elektronik', {}) or {}
        self.module = [m for m in (self.el.get('module') or []) if isinstance(m, dict)]
        self.ohne_kicad = False     # True: Stellvertreter fuer Kaufmodule (nur soll-Daten, siehe platine_ohne_kicad)
        self.pdir = None            # setzt platine_laden; ohne pdir (Tests) kein Blick in Gehaeuse/merkmale
        self._kontext = None
        self.lay = k['layout']
        self.annahmen = []
        nl = k.get('netzliste')
        self.bt = {f['ref']: f for f in self.lay['bauteile']}
        if nl:
            self.teile = nl['teile']
            self.netze = {n: [x for x in kn if x['ref'] in self.teile] for n, kn in nl['netze'].items()}
            for ref, t in self.teile.items():   # Felder der Platine ergaenzen (LCSC dort, wenn im Schaltplan fehlt)
                if ref in self.bt:
                    for kk, vv in self.bt[ref]['felder'].items():
                        t['felder'].setdefault(kk, vv)
        else:
            self.teile, self.netze = {}, {}
            for f in self.lay['bauteile']:
                self.teile[f['ref']] = {'wert': f['wert'], 'fp': f['fp'], 'felder': f['felder'], 'dnp': f.get('dnp', False)}
                for p in f['pads']:
                    if p['netz']:
                        self.netze.setdefault(p['netz'], []).append({'ref': f['ref'], 'pin': p['nr'], 'name': p['fkt'],
                                                                     'typ': p['typ']})
            self.annahmen.append('kein Schaltplan: Netze aus den Pads, ohne Pin-Typen')
        self.netze = {n: kn for n, kn in self.netze.items() if not n.startswith('unconnected-')}
        self.dbe = {ref: db_eintrag(db, t) for ref, t in self.teile.items()}
        self.pins_von = {}
        for n, kn in self.netze.items():
            for x in kn:
                x['netz'] = n
                self.pins_von.setdefault(x['ref'], []).append(x)
        self.pads = {}
        for f in self.lay['bauteile']:
            for p in f['pads']:
                self.pads.setdefault((f['ref'], p['nr']), []).append(p)
        self._stackup()
        self._spannungen()
        self._stroeme()

    # ---- Grundbegriffe
    def art(self, ref):
        t = self.teile.get(ref, {})
        fp = t.get('fp', '') or self.bt.get(ref, {}).get('fp', '')
        m = re.match(r'[A-Z]+', ref or '')
        p = m.group(0) if m else ''
        if p == 'R' or (p == 'RN'):
            return 'R'
        if p == 'C':
            return 'C'
        if p == 'FB' or (p == 'L' and '@' in t.get('wert', '')):
            return 'FB'
        if p == 'L':
            return 'L'
        if p in ('D', 'LED'):
            return 'LED' if 'LED' in fp.upper() else 'D'
        return p

    def rolle(self, x):
        e = self.dbe.get(x['ref']) or {}
        name = re.sub(r'[~{}]', '', x.get('name') or '').upper()
        r = (e.get('pins') or {}).get(name)
        if r is None and name:
            for k, v in (e.get('pins') or {}).items():
                if name.split('/')[0] == k:
                    r = v
        if r is None:
            r = (e.get('pins_nr') or {}).get(x['pin'])
        if r is None:
            if x.get('typ') == 'power_out':
                r = 'vout'
            elif x.get('typ') == 'power_in':
                r = 'gnd' if GND_RE.match(name) or name in ('GND', 'VSS', 'PGND') else 'vdd'
        return r

    def ist_gnd(self, n):
        return bool(n) and bool(GND_RE.match(n))

    def andere_seite(self, ref, netz):
        """Fuer Zweipole (R, C, L, D): Netz am anderen Pin."""
        ps = self.pins_von.get(ref, [])
        if len(ps) != 2:
            return None
        a, b = ps
        return b['netz'] if a['netz'] == netz else (a['netz'] if b['netz'] == netz else None)

    def zweipole(self, netz, art):
        out = []
        for x in self.netze.get(netz, []):
            if self.art(x['ref']) == art and not self.teile[x['ref']].get('dnp'):
                o = self.andere_seite(x['ref'], netz)
                if o is not None:
                    out.append((x['ref'], o))
        return out

    def wert(self, ref, art):
        return wert_si(self.teile.get(ref, {}).get('wert'), art)

    # ---- Lagenaufbau
    def _stackup(self):
        st = self.lay.get('stackup_sexpr') or self.el.get('lagenaufbau')
        n = self.lay['kupferlagen']
        quelle = 'Platine (setup/stackup)' if self.lay.get('stackup_sexpr') else 'soll.json lagenaufbau'
        if not st:
            if n == 2:
                st = [{'typ': 'copper', 'dicke_mm': 0.035}, {'typ': 'dielectric', 'dicke_mm': max(0.1, self.lay['dicke_mm'] - 0.07), 'er': 4.5},
                      {'typ': 'copper', 'dicke_mm': 0.035}]
                quelle = 'angenommen: JLC 2 Lagen, 35 um Cu, FR4 er 4,5'
            elif n == 4:
                st = [{'typ': 'copper', 'dicke_mm': 0.035}, {'typ': 'dielectric', 'dicke_mm': 0.2104, 'er': 4.4},
                      {'typ': 'copper', 'dicke_mm': 0.0152}, {'typ': 'dielectric', 'dicke_mm': 1.065, 'er': 4.6},
                      {'typ': 'copper', 'dicke_mm': 0.0152}, {'typ': 'dielectric', 'dicke_mm': 0.2104, 'er': 4.4},
                      {'typ': 'copper', 'dicke_mm': 0.035}]
                quelle = 'angenommen: JLC7628 4 Lagen'
            else:
                st = []
                d = 1.6 / max(1, n - 1)
                for i in range(n):
                    st.append({'typ': 'copper', 'dicke_mm': 0.035 if i in (0, n - 1) else 0.0175})
                    if i < n - 1:
                        st.append({'typ': 'dielectric', 'dicke_mm': d, 'er': 4.4})
                quelle = f'angenommen: {n} Lagen gleichmaessig, Lagenaufbau unbekannt (Ergebnisse fuer h unsicher)'
        self.stackup_quelle = quelle
        cu = [s for s in st if s['typ'] == 'copper']
        lagen = self.lay['lagen']
        self.cu_dicke = {}
        self.h_ref = {}   # Lage -> (Abstand zur naechsten Kupferlage, er, Nachbarlage)
        for i, ln in enumerate(lagen):
            self.cu_dicke[ln] = (cu[i]['dicke_mm'] if i < len(cu) and cu[i].get('dicke_mm') else 0.035)
        idx = [i for i, s in enumerate(st) if s['typ'] == 'copper']
        for i, ln in enumerate(lagen):
            if i >= len(idx):
                continue
            nb = i + 1 if i == 0 else (i - 1 if i == len(lagen) - 1 else i + 1)
            if nb >= len(idx) or nb < 0:
                continue
            lo, hi = sorted((idx[i], idx[nb]))
            diel = [s for s in st[lo + 1:hi] if s['typ'] == 'dielectric']
            h = sum(s.get('dicke_mm') or 0 for s in diel)
            er = max((s.get('er') or 4.5) for s in diel) if diel else 4.5
            self.h_ref[ln] = (h, er, lagen[nb])
        if 'angenommen' in quelle:
            self.annahmen.append('Lagenaufbau ' + quelle)

    # ---- Spannungen
    def _spannungen(self):
        V = {}
        herkunft = {}

        self.akku_netze = set()     # Netze, die direkt (ohne Regler) am Akku/an der Batterie haengen
        self.quelle_pins = {}       # Netz -> [(ref, pin)] der speisenden Bauteile bei Weitergabe ueber FET/Diode

        def setze(n, lo, hi, wie, von=None, akku=False, pins=None):
            if n and n not in V:
                V[n] = (lo, hi)
                herkunft[n] = wie
                if akku or (von and von in self.akku_netze):
                    self.akku_netze.add(n)
                if pins:
                    self.quelle_pins[n] = pins
        for n in self.netze:
            if self.ist_gnd(n):
                setze(n, 0.0, 0.0, 'Masse')
        for n, d in (self.el.get('netze') or {}).items():
            V[n] = (d.get('V_min', d.get('V')), d.get('V_max', d.get('V')))
            herkunft[n] = 'soll.json'
        # Akku/Batterie
        schutz = [e for e in self.dbe.values() if e and e.get('typ') == 'akkuschutz']
        for ref, e in self.dbe.items():
            if not e:
                continue
            for x in self.pins_von.get(ref, []):
                if self.rolle(x) != 'bat':
                    continue
                if e.get('typ') == 'batterie':
                    nz = 1
                    m = re.match(r'\s*(\d+)\s*x', self.teile[ref]['wert'], re.I)
                    if m:
                        nz = int(m.group(1))
                    lo, hi = e['zelle_V']
                    wie = f'Batterie {ref} ({nz} Zellen, Entladeschluss DB)'
                    if self.el.get('V_abschalt_V'):
                        lo = float(self.el['V_abschalt_V']) / nz
                        wie = f'Batterie {ref} ({nz} Zellen, Firmware-Abschaltung soll.json)'
                    setze(x['netz'], nz * lo, nz * hi, wie, akku=True)
                    self.akku = {'ref': ref, 'netz': x['netz'], 'mAh': e.get('kapazitaet_mAh'),
                                 'R_int': (e.get('R_int_Ohm_zelle') or 0) * nz if e.get('R_int_Ohm_zelle') else None,
                                 'V_min': nz * lo, 'V_max': nz * hi, 'quelle': 'DB ' + ref}
                elif e.get('chemie'):
                    ch = self.db.get('chemie', {}).get(e['chemie'], {})
                    lo = ch.get('V_min', 3.0)
                    wie = f'{e["chemie"]}-Chemie'
                    if schutz:
                        lo = min(s.get('V_ueberentladung_V', lo) for s in schutz)
                        wie = 'Schutz-IC trennt bei %.2f V' % lo
                    if self.el.get('V_abschalt_V'):
                        lo = float(self.el['V_abschalt_V'])
                        wie = 'Firmware-Abschaltung (soll.json)'
                    hi = e.get('V_bat_reg_V', ch.get('V_max', 4.2))
                    setze(x['netz'], lo, hi, f'Akku an {ref}.{x["name"]} ({wie})', akku=True)
                    if not hasattr(self, 'akku'):
                        self.akku = {'ref': ref, 'netz': x['netz'], 'mAh': self.ps.get('akku_mAh'),
                                     'R_int': self.el.get('R_int_Ohm'), 'V_min': lo, 'V_max': hi,
                                     'chemie': e['chemie'], 'quelle': 'Lader ' + ref}
        # Reglerausgaenge (mehrfach, weil Eingaenge von Ausgaengen abhaengen koennen)
        for _ in range(3):
            for ref, e in self.dbe.items():
                if not e:
                    continue
                vo = e.get('V_out_V')
                for x in self.pins_von.get(ref, []):
                    if self.rolle(x) != 'vout':
                        continue
                    v = vo if vo else self._v_fb(ref, e, x['netz'])
                    if v:
                        tol = 0.03
                        lo, wie, von = v * (1 - tol), f'Ausgang {ref} ({v:.2f} V, DB +-3 %)', None
                        if e.get('V_out_folgt_bat'):
                            # Power-Path-Lader (Befund E2): ohne Eingang haengt OUT ueber den Akku-FET am Akku
                            bat = [y['netz'] for y in self.pins_von.get(ref, []) if self.rolle(y) == 'bat']
                            if bat and bat[0] in V:
                                lo = min(lo, V[bat[0]][0])
                                von = bat[0]
                                wie = (f'Ausgang {ref} ({v:.2f} V +-3 % mit Eingang; ohne Eingang = Akku {bat[0]} '
                                       f'ab {V[bat[0]][0]:.2f} V ueber Akku-FET, Spannungsfall vernachlaessigt)')
                            else:
                                wie += ' - ACHTUNG Akkubetrieb: OUT folgt dem Akku, Akkunetz unbekannt (zu guenstig)'
                        setze(x['netz'], lo, v * (1 + tol), wie, von=von)
        # Netzname
        for n in self.netze:
            if n in V:
                continue
            nn = n.lstrip('/').upper()
            m = re.search(r'(?<![0-9A-Z])\+?(\d{1,2})V(\d{1,2})(?![0-9])', nn) or None
            v = None
            if m:
                v = float(m.group(1) + '.' + m.group(2))
            else:
                m = re.search(r'(?<![0-9A-Z.])\+?(\d{1,2}(?:\.\d+)?)V(?![0-9A-Z])', nn)
                if m:
                    v = float(m.group(1))
            if v:
                setze(n, v * 0.95, v * 1.05, 'Netzname (+-5 %)')
        # VBUS von USB
        for n in self.netze:
            if re.fullmatch(r'/?VBUS', n, re.I):
                setze(n, 4.75, 5.25, 'USB VBUS (USB 2.0: 4,75-5,25 V, extern)')
        # P-Kanal-Lastschalter/Verpolschutz (D-S) und Dioden (A -> K) reichen die Schiene weiter
        for _ in range(3):
            for ref, e in self.dbe.items():
                ps = {re.sub(r'[~{}]', '', x.get('name') or '').upper(): x['netz'] for x in self.pins_von.get(ref, [])}
                if e and e.get('typ') == 'pmos' and 'D' in ps and 'S' in ps:
                    for a, b in ((ps['S'], ps['D']), (ps['D'], ps['S'])):
                        if a in V and b not in V and not self.ist_gnd(a) and not self._hat_quelle(b):
                            setze(b, V[a][0], V[a][1], f'ueber P-FET {ref} aus {a} (Spannungsfall I*R_DS(on) vernachlaessigt)', von=a,
                                  pins=[(ref, x['pin']) for x in self.pins_von[ref] if x['netz'] == b])
            for ref in self.teile:
                if self.art(ref) != 'D':
                    continue
                ps = {(x.get('name') or '').upper(): x['netz'] for x in self.pins_von.get(ref, [])}
                a, kk = ps.get('A'), ps.get('K')
                if a in V and kk and kk not in V and not self._hat_quelle(kk) and not self.ist_gnd(a):
                    quellen = [x['netz'] for d in self.teile if self.art(d) == 'D'
                               for x in self.pins_von.get(d, []) if (x.get('name') or '').upper() == 'A'
                               and self.andere_seite(d, x['netz']) == kk and x['netz'] in V]
                    vf = _vf_diode(self.dbe.get(ref), 0.1)
                    lo = min(V[q][0] for q in quellen) - (vf if vf is not None else 0.6)
                    hi = max(V[q][1] for q in quellen)
                    setze(kk, max(0.0, lo), hi, f'ueber Diode(n) aus {", ".join(sorted(set(quellen)))} (V_f '
                          + (f'{vf:.2f} V DB' if vf is not None else '0,6 V angenommen') + ')',
                          von=quellen[0] if all(q in self.akku_netze for q in quellen) else None,
                          pins=[(d, x['pin']) for d in self.teile if self.art(d) == 'D' for x in self.pins_von.get(d, [])
                                if x['netz'] == kk])
        # ueber kleine Widerstaende angebundene Versorgungsnetze (RC vor VCC)
        for _ in range(2):
            for n in self.netze:
                if n in V:
                    continue
                kn = self.netze[n]
                if any(x.get('typ') in ('output', 'bidirectional', 'power_out', 'open_collector', 'tri_state') for x in kn):
                    continue
                for ref, o in self.zweipole(n, 'R'):
                    r = self.wert(ref, 'R')
                    if r is not None and r <= 1000 and o in V and not self.ist_gnd(o):
                        if any(self.rolle(x) == 'vdd' for x in kn):
                            setze(n, V[o][0], V[o][1], f'ueber {ref} ({r:g} Ohm) an {o}', von=o)
        self.V = V
        self.V_her = herkunft
        if not hasattr(self, 'akku'):
            self.akku = None
            if self.ps.get('akku_mAh'):
                self.akku = {'ref': None, 'netz': None, 'mAh': self.ps.get('akku_mAh'), 'R_int': self.el.get('R_int_Ohm'),
                             'V_min': None, 'V_max': None, 'quelle': 'soll.json'}
        elif self.ps.get('akku_mAh'):
            self.akku['mAh'] = self.ps['akku_mAh']

    def _hat_quelle(self, n):
        return any(x.get('typ') == 'power_out' or self.rolle(x) in ('vout', 'bat') for x in self.netze.get(n, []))

    def _v_fb(self, ref, e, vout_netz):
        """V_out aus dem FB-Teiler: V_out = V_fb*(1 + R_oben/R_unten)."""
        if not e.get('V_fb_V'):
            return None
        for x in self.pins_von.get(ref, []):
            if self.rolle(x) != 'fb':
                continue
            if self.ist_gnd(x['netz']):
                return None
            oben = [self.wert(r, 'R') for r, o in self.zweipole(x['netz'], 'R') if o == vout_netz]
            unten = [self.wert(r, 'R') for r, o in self.zweipole(x['netz'], 'R') if self.ist_gnd(o)]
            if len(oben) == 1 and len(unten) == 1 and oben[0] and unten[0]:
                return e['V_fb_V'] * (1 + oben[0] / unten[0])
        return None

    def vdd(self, ref):
        """(V_min, V_max, Netz) der Logikversorgung eines Bauteils."""
        e = self.dbe.get(ref) or {}
        if e.get('logik_ausgang'):
            for x in self.pins_von.get(ref, []):
                if (x.get('name') or '').upper() == e['logik_ausgang'] and x['netz'] in self.V:
                    return self.V[x['netz']] + (x['netz'],)
        kand = [x['netz'] for x in self.pins_von.get(ref, []) if self.rolle(x) == 'vdd' and x['netz'] in self.V
                and not self.ist_gnd(x['netz'])]
        if not kand:
            return None
        n = max(kand, key=lambda k: self.V[k][1])
        return self.V[n] + (n,)

    # ---- Stroeme
    def _stroeme(self):
        I = {}
        her = {}
        klasse = self.lay.get('netzklassen', {})
        for n in self.netze:
            m = re.search(r'(\d+(?:[.,]\d+)?)\s*(mA|A)(?![a-z])', klasse.get(n, '') or '')
            if m:
                I[n] = float(m.group(1).replace(',', '.')) * (1e-3 if m.group(2) == 'mA' else 1.0)
                her[n] = f'Netzklasse "{klasse[n]}"'
        feld = {}
        for ref, t in self.teile.items():
            s = t.get('felder', {}).get('Strom')
            if not s:
                continue
            for teil in re.split(r'[;,]\s*(?=[^;,]*=)', s):
                if '=' in teil:
                    nn, vv = teil.rsplit('=', 1)
                    v = _strom_text(vv)
                    if v is not None:
                        nn = nn.strip()
                        if nn not in self.netze and '/' + nn in self.netze:
                            nn = '/' + nn
                        feld[nn] = feld.get(nn, 0) + v
        for n, v in feld.items():
            if n not in I or v > I[n]:
                I[n] = v
                her[n] = 'Symbolfeld Strom'
        self.I_gegeben = dict(I)
        # Schaetzung aus der DB
        est = {}
        lasten = {}
        for ref, e in self.dbe.items():
            if not e or self.teile[ref].get('dnp'):
                continue
            ip = e.get('I_peak_A')
            if ip and e.get('typ') not in ('ldo', 'buck', 'boost', 'buckboost', 'lader_linear', 'qi_lader'):
                vn = [x['netz'] for x in self.pins_von.get(ref, []) if self.rolle(x) == 'vdd' and not self.ist_gnd(x['netz'])]
                for n in set(vn):
                    est[n] = est.get(n, 0) + ip / len(set(vn))
                    lasten.setdefault(n, []).append((ref, ip / len(set(vn))))
        for _ in range(3):
            for ref, e in self.dbe.items():
                if not e or e.get('typ') not in ('ldo', 'buck', 'boost', 'buckboost', 'lader_linear'):
                    continue
                vin = [x['netz'] for x in self.pins_von.get(ref, []) if self.rolle(x) == 'vin']
                vout = [x['netz'] for x in self.pins_von.get(ref, []) if self.rolle(x) == 'vout']
                if not vin or not vout:
                    continue
                io = sum(I.get(n, est.get(n, 0)) for n in set(vout))
                if not io:
                    continue
                if e['typ'] in ('ldo', 'lader_linear'):
                    ii = io + (e.get('I_q_A') or 0)
                else:
                    vo = max((self.V.get(n, (0, 0))[1] for n in vout), default=0)
                    vi = min((self.V.get(n, (0, 0))[0] for n in vin if n in self.V), default=0)
                    ii = io * vo / ((e.get('eta') or 0.8) * vi) if vi else None
                    if ii is None:
                        continue
                for n in set(vin):
                    if n not in I:
                        alt = [l for l in lasten.get(n, []) if l[0] != ref]
                        est[n] = sum(a[1] for a in alt) + ii
                        lasten[n] = alt + [(ref, ii)]
        for n, v in est.items():
            if n not in I and v > 0:
                I[n] = v
                her[n] = 'geschaetzt aus DB (Spitzenstroeme: ' + ', '.join(f'{r} {i * 1e3:.0f} mA' for r, i in lasten.get(n, [])) + ')'
        self.I = I
        self.I_her = her
        self.lasten = {n: l for n, l in lasten.items() if n not in self.I_gegeben}

    def strom_explizit(self, n):
        return n in self.I_gegeben

    # ---- Layout-Hilfen
    def bahnen(self, netz=None):
        return [t for t in self.lay['bahnen'] if t['art'] != 'via' and (netz is None or t['netz'] == netz)]

    def vias(self, netz=None):
        return [t for t in self.lay['bahnen'] if t['art'] == 'via' and (netz is None or t['netz'] == netz)]

    def fuellungen(self, netz, lage):
        out = []
        for z in self.lay['zonen']:
            if not z['regel'] and z['netz'] == netz:
                out += z.get('flaechen', {}).get(lage, [])
        return out

    def gnd_fuellung(self, lage):
        out = []
        for z in self.lay['zonen']:
            if not z['regel'] and self.ist_gnd(z['netz']):
                out += z.get('flaechen', {}).get(lage, [])
        return out

    def pad_pos(self, ref, pin):
        p = self.pads.get((ref, pin))
        return p[0]['pos'] if p else None

    def T_a(self):
        if self.el.get('T_a_C') is not None:
            return float(self.el['T_a_C']), 'soll.json T_a_C'
        if self.ps.get('T_max_C') is not None:
            return float(self.ps['T_max_C']), 'soll.json T_max_C'
        return 40.0, 'angenommen 40 C (Gehaeuse innen)'

    # ---- Realterme (mb2/realterme.py), einmal je Platine
    def modul_wert(self, feld, quelle='el'):
        """soll-Feld: _projekt.elektronik (quelle 'el') bzw. _projekt ('ps') vor dem ersten Kaufmodul, das es nennt."""
        d = self.el if quelle == 'el' else self.ps
        if d.get(feld) is not None:
            return d[feld]
        return next((m[feld] for m in self.module if m.get(feld) is not None), None)

    def akku_chemie(self):
        """Chemie-Schluessel fuer realterme.KAELTE_KAPAZITAET aus soll, Modul, Lader (DB chemie) oder Batterie (DB)."""
        ch = self.ps.get('akku_chemie') or self.modul_wert('chemie')
        ak = self.akku or {}
        if not ch and ak.get('chemie'):
            ch = ak['chemie']
        if not ch and ak.get('ref'):
            w = _norm((self.teile.get(ak['ref']) or {}).get('wert', '')).lower()
            ch = 'li_fes2' if ('l91' in w or 'lithium' in w) else ('alkali' if ('alkali' in w or 'mn1500' in w) else None)
        if not ch:
            return None
        ch = str(ch).lower().replace('-', '').replace(' ', '')
        return {'lipo': 'lipo', 'liion': 'lipo', 'lipolymer': 'lipo', 'lifepo4': 'lifepo4', 'nimh': 'nimh',
                'alkali': 'alkali', 'lifes2': 'li_fes2', 'li_fes2': 'li_fes2', 'l91': 'li_fes2'}.get(ch, ch)

    def kontext(self):
        if self._kontext is None:
            extra = {'kuehlflaeche': self.el.get('kuehlflaeche'), 'elektronik': True}
            ch = self.akku_chemie()
            if ch and not self.ps.get('akku_chemie'):
                extra['akku_chemie'] = ch
            self._kontext = rt.kontext(self.pdir, soll={'_projekt': self.ps},
                                       merkmale=None if self.pdir else {}, **extra)
        return self._kontext

    def gehaeuse_da(self):
        """Gehaeuse/Platinen-3D vorhanden (board.step oder STEP/Skript unter cad/) -> Metall darin wird nicht geprueft."""
        if not self.pdir:
            return None
        for d, muster in (('electronics', ('board.step',)), ('cad', ('*.step', '*.stp', '*.py')),
                          ('mechanics', ('*.step', '*.stp', '*.f3d', '*.py'))):
            for m in muster:
                if glob.glob(os.path.join(self.pdir, d, m)):
                    return os.path.join(d, m)
        return None

    # ---- Widerstandsgraph eines Netzes (E2)
    def netz_widerstand(self, netz, von, nach):
        """Kleinster Kupferwiderstand (Ohm) von Pad-Liste 'von' zu Pad 'nach' ueber Bahnen/Vias; Zonen gleichen Netzes
        werden als widerstandslos angenommen (optimistisch, im Hinweis genannt). None = keine Verbindung gefunden."""
        import heapq
        kanten = {}

        def add(a, b, r):
            kanten.setdefault(a, []).append((b, r))
            kanten.setdefault(b, []).append((a, r))

        def k(lage, p):
            return (lage, round(p[0], 3), round(p[1], 3))
        T, _ = self.T_a()
        rho = RHO_CU * (1 + ALPHA_CU * (T - 20))
        enden = []
        segs = []
        for t in self.bahnen(netz):
            tcu = self.cu_dicke.get(t['lage'], 0.035)
            r = rho * t['l'] / (t['w'] * tcu) if t['w'] > 0 else 0
            add(k(t['lage'], t['a']), k(t['lage'], t['b']), r)
            enden.append((t['lage'], t['a'], t['w']))
            enden.append((t['lage'], t['b'], t['w']))
            segs.append((t, r))
        # Bahnenden, die eine andere Bahn nur ueberlappen (KiCad verbindet ueber die Breite): an deren Enden anteilig anbinden
        for lage, p, w in enden:
            for t, r in segs:
                if t['lage'] != lage or p == t['a'] or p == t['b']:
                    continue
                d, s = _abst_seg(p, t['a'], t['b'])
                if d <= (w + t['w']) / 2 * 0.999:
                    add(k(lage, p), k(lage, t['a']), r * s)
                    add(k(lage, p), k(lage, t['b']), r * (1 - s))
        h = self.lay['dicke_mm']
        lagen = self.lay['lagen']
        for v in self.vias(netz):
            d = v['bohr_mm'] or 0.3
            r = rho * h / (math.pi * d * VIA_HUELSE_MM)
            for i in range(len(lagen) - 1):
                add(k(lagen[i], v['pos']), k(lagen[i + 1], v['pos']), r / (len(lagen) - 1))
            for lage, p, w in enden:
                if lage in lagen and math.dist(p, v['pos']) <= max(d / 2 + 0.15, w / 2):
                    add(k(lage, p), k(lage, v['pos']), 0.0)
        zonen = {}
        for lage in lagen:
            f = self.fuellungen(netz, lage)
            if f:
                zonen[lage] = f
        knoten_pad = {}
        for x in self.netze.get(netz, []):
            for p in self.pads.get((x['ref'], x['pin']), []):
                pk = ('pad', x['ref'], x['pin'])
                knoten_pad[pk] = p
                for lage in p['lagen']:
                    for el, ep, w in enden:
                        if el != lage:
                            continue
                        dx, dy = abs(ep[0] - p['pos'][0]), abs(ep[1] - p['pos'][1])
                        rr = max(p['gr']) / 2 + 0.01
                        if dx <= rr and dy <= rr:
                            add(pk, k(el, ep), 0.0)
                    if lage in zonen and in_flaeche(p['pos'][0], p['pos'][1], zonen[lage]):
                        add(pk, ('zone', lage), 0.0)
        for el, ep, w in enden:
            if el in zonen and in_flaeche(ep[0], ep[1], zonen[el]):
                add(k(el, ep), ('zone', el), 0.0)
        for v in self.vias(netz):
            for lage in zonen:
                if in_flaeche(v['pos'][0], v['pos'][1], zonen[lage]):
                    add(k(lage, v['pos']), ('zone', lage), 0.0)
        start = [('pad',) + s for s in von]
        dist = {s: 0.0 for s in start if s in kanten}
        heap = [(0.0, s) for s in dist]
        ziel = ('pad',) + nach
        while heap:
            d, u = heapq.heappop(heap)
            if u == ziel:
                return d, bool(zonen)
            if d > dist.get(u, 1e99):
                continue
            for v, r in kanten.get(u, []):
                nd = d + r
                if nd < dist.get(v, 1e99):
                    dist[v] = nd
                    heapq.heappush(heap, (nd, v))
        return None, bool(zonen)

    def r_gegen_masse(self, netz, tiefe=6):
        """Ersatzwiderstand (Ohm) vom Netz nach GND nur ueber Widerstaende (Knotenanalyse). None = kein Pfad."""
        import numpy as np
        knoten = {netz}
        rs = []
        rand = [netz]
        for _ in range(tiefe):
            neu = []
            for n in rand:
                if self.ist_gnd(n):
                    continue
                for ref, o in self.zweipole(n, 'R'):
                    r = self.wert(ref, 'R')
                    if r is None:
                        return None
                    if (ref, ) not in [(x[0],) for x in rs]:
                        rs.append((ref, n, o, r))
                    if o not in knoten:
                        knoten.add(o)
                        neu.append(o)
            rand = neu
        g = [n for n in knoten if self.ist_gnd(n)]
        if not g:
            return None
        frei = [n for n in knoten if not self.ist_gnd(n)]
        ix = {n: i for i, n in enumerate(frei)}
        Gm = np.zeros((len(frei), len(frei)))
        for ref, a, b, r in rs:
            gg = 1 / max(r, 1e-6)
            for p, q in ((a, b), (b, a)):
                if p in ix:
                    Gm[ix[p], ix[p]] += gg
                    if q in ix:
                        Gm[ix[p], ix[q]] -= gg
        Gm += np.eye(len(frei)) * 1e-15
        rhs = np.zeros(len(frei))
        rhs[ix[netz]] = 1.0
        try:
            v = np.linalg.solve(Gm, rhs)
        except np.linalg.LinAlgError:
            return None
        return float(v[ix[netz]])


# --------------------------------------------------------------------------------------------- Ergebnis-Helfer

def _e(id, stufe, hinweis, wert=None, grenze=None, einheit='', daten=None, titel=None):
    return ergebnis(id, titel or TITEL[id], stufe, wert=wert, grenze=grenze, einheit=einheit, quelle=Q[id],
                    hinweis=hinweis, daten=daten)


def _u(id, grund):
    return uebersprungen(id, TITEL[id], grund, quelle=Q[id])


def _stufe(wert, ok, warn, groesser_besser=False):
    """Schwellwerte: kleiner ist besser (Standard) -> ok bis 'ok', warnung bis 'warn', sonst fehler."""
    if groesser_besser:
        return 'ok' if wert >= ok else ('warnung' if wert >= warn else 'fehler')
    return 'ok' if wert <= ok else ('warnung' if wert <= warn else 'fehler')


def _zusammen(id, liste, leer_grund):
    """ok-Ergebnisse je ID zu einem Eintrag zusammenfassen; Warnungen/Fehler einzeln."""
    if not liste:
        return [_u(id, leer_grund)]
    ok = [x for x in liste if x['stufe'] in ('ok', 'info')]
    rest = [x for x in liste if x['stufe'] not in ('ok', 'info')]
    out = list(rest)
    if ok:
        if len(ok) == 1:
            out.append(ok[0])
        else:
            st = 'ok' if all(x['stufe'] == 'ok' for x in ok) else 'info'
            out.append(_e(id, st, f'{len(ok)} Stellen in Ordnung: ' + '; '.join(x['hinweis'] for x in ok)[:1500],
                          daten={'einzeln': [x.get('daten') for x in ok][:40]}))
    return out


# --------------------------------------------------------------------------------------------- E1 Logikpegel

def _od_pin(pl, x):
    r = pl.rolle(x)
    if r == 'od' or x.get('typ') == 'open_collector':
        return True
    nm = (x.get('name') or '').upper()
    return bool(I2C_RE.search(nm)) or bool(I2C_RE.search(x['netz'].upper()))


def _pullup(pl, netz):
    """[(ref, R, V_min, V_max, Schiene)] Widerstaende vom Netz zu einer Schiene bekannter Spannung."""
    out = []
    for ref, o in pl.zweipole(netz, 'R'):
        r = pl.wert(ref, 'R')
        if r and o in pl.V and not pl.ist_gnd(o) and pl.V[o][1] > 0:
            out.append((ref, r, pl.V[o][0], pl.V[o][1], o))
    return out


def pruefe_e1(pl):
    res = []
    ohne_db = set()
    for n, kn in pl.netze.items():
        if pl.ist_gnd(n) or n in pl.V and pl.V_her.get(n, '').startswith(('Ausgang', 'Akku', 'Netzname', 'Batterie', 'soll')):
            continue
        logik = [x for x in kn if x.get('typ') in ('input', 'output', 'bidirectional', 'tri_state', 'open_collector')
                 and pl.rolle(x) not in ('vdd', 'gnd', 'vin', 'vout', 'bat', 'gate', 'rf', 'ac', 'sense', 'prog', 'fb')]
        teile = {x['ref'] for x in logik}
        if len(teile) < 2:
            continue
        mit = [x for x in logik if (pl.dbe.get(x['ref']) or {}).get('logik') and pl.vdd(x['ref'])]
        for x in logik:
            if x not in mit:
                ohne_db.add(x['ref'])
        if len({x['ref'] for x in mit}) < 2:
            continue
        pu = _pullup(pl, n)
        for d in mit:
            if d.get('typ') == 'input':
                continue
            ld = pl.dbe[d['ref']]['logik']
            vd_lo, vd_hi, vd_netz = pl.vdd(d['ref'])
            od = _od_pin(pl, d)
            if od and not pu:
                continue
            for rx in mit:
                if rx['ref'] == d['ref'] or rx.get('typ') in ('output', 'open_collector'):
                    continue
                lr = pl.dbe[rx['ref']]['logik']
                vr_lo, vr_hi, vr_netz = pl.vdd(rx['ref'])
                quell_netze = {p[4] for p in pu} if od else {vd_netz}
                gleich = quell_netze == {vr_netz}
                # gleiche Schiene: beide Seiten sehen dieselbe Spannung -> an beiden Enden des Bereichs auswerten;
                # verschiedene Schienen: unabhaengig, schlimmste Kombination
                faelle = [(v, v, v) for v in (vr_lo, vr_hi)] if gleich else [(None, None, None)]
                nmh = nml = None
                vol_ber = q_ol = None
                for vq, vdrv, vrx in faelle:
                    if od:
                        voh = vq if vq is not None else min(p[2] for p in pu)
                        i_sink = sum((vq if vq is not None else p[3]) / p[1] for p in pu)
                        vol_spec = ausdruck(ld.get('V_OL'), vdrv if vdrv is not None else vd_hi)
                        iol = ld.get('I_OL_A') or 0.003
                        q_ol = 'DB'
                        if vol_spec is None:
                            vol_spec, iol, q_ol = 0.4, 0.003, 'UM10204 0,4 V @ 3 mA (extern)'
                        vol = vol_spec * min(1.0, i_sink / iol)
                    else:
                        voh = ausdruck(ld.get('V_OH'), vdrv if vdrv is not None else vd_lo)
                        vol = ausdruck(ld.get('V_OL'), vdrv if vdrv is not None else vd_hi)
                        i_sink = None
                    vih = ausdruck(lr.get('V_IH'), vrx if vrx is not None else vr_hi)
                    vil = ausdruck(lr.get('V_IL'), vrx if vrx is not None else vr_lo)
                    if voh is not None and vih is not None:
                        nmh = voh - vih if nmh is None else min(nmh, voh - vih)
                    if vil is not None and vol is not None:
                        if nml is None or vil - vol < nml:
                            nml, vol_ber = vil - vol, (vol, i_sink)
                txt = f'{n}: {d["ref"]}.{d["name"] or d["pin"]} -> {rx["ref"]}.{rx["name"] or rx["pin"]}'
                werte = [w for w in (nmh, nml) if w is not None]
                if not werte:
                    res.append(_e('E1', 'uebersprungen', txt + ': Pegel unvollstaendig in der DB'))
                    continue
                nm = min(werte)
                st = 'ok' if nm >= 0.4 else ('warnung' if nm > 0 else 'fehler')
                hin = f'{txt}: NM_H = {nmh:.2f} V, NM_L = {nml:.2f} V' if nmh is not None and nml is not None else \
                    f'{txt}: NM = {nm:.2f} V (nur eine Seite bekannt)'
                if gleich:
                    hin += f' (gleiche Schiene {vr_netz})'
                if od and vol_ber:
                    hin += (f' (Open-Drain, Pull-up {", ".join(p[0] for p in pu)}, V_OL {vol_ber[0]:.2f} V bei '
                            f'{vol_ber[1] * 1e3:.2f} mA, {q_ol})')
                # Ueberspannung am Eingang nur moeglich, wenn die Hoch-Quelle eine andere Schiene ist
                vhoch = max(p[3] for p in pu) if od else max([vd_hi] + [p[3] for p in pu])
                hoch_netze = quell_netze | ({p[4] for p in pu} if not od else set())
                vmax = 5.5 if lr.get('fuenf_v_tolerant') else ausdruck(lr.get('V_in_max', 'VDD+0.3'), vr_lo)
                if hoch_netze != {vr_netz} and vmax is not None and vhoch > vmax + 1e-9:
                    st = 'fehler'
                    hin += f'; Eingang ueberspannt: {vhoch:.2f} V > {vmax:.2f} V (nicht 5-V-tolerant)'
                elif nmh is None or nml is None:
                    st = 'warnung' if st == 'ok' else st
                res.append(_e('E1', st, hin, wert=round(nm, 3), grenze=0.4, einheit='V',
                              daten={'netz': n, 'treiber': d['ref'], 'empfaenger': rx['ref'], 'NM_H': nmh, 'NM_L': nml}))
    out = _zusammen('E1', res, 'kein Netz mit zwei Logikbauteilen bekannter Pegel (Bauteil-DB) gefunden')
    if ohne_db:
        out.append(_e('E1', 'uebersprungen', 'Logikpins ohne Pegel in der Bauteil-DB (bauteile.json ergaenzen): '
                      + ', '.join(sorted(ohne_db))))
    return out


# --------------------------------------------------------------------------------------------- E2/E3 Strom auf Bahnen

def _quellen_lasten(pl, n):
    """Quellen: am Akkunetz der Akku (Stecker/Halter), sonst Reglerausgang/Lader, sonst Stecker. Lasten: Versorgungspins."""
    kn = pl.netze.get(n, [])
    stecker = [(x['ref'], x['pin']) for x in kn if pl.art(x['ref']) in ('J', 'BT', 'P', 'CN')]
    if pl.akku and pl.akku.get('netz') == n and stecker:
        q = stecker
    elif n in pl.quelle_pins:
        q = pl.quelle_pins[n]
    else:
        q = [(x['ref'], x['pin']) for x in kn if pl.rolle(x) in ('vout', 'bat')] or stecker
    lasten = [(x['ref'], x['pin']) for x in kn if pl.rolle(x) in ('vdd', 'vin') and (x['ref'], x['pin']) not in q]
    return q, lasten


def pruefe_e2(pl):
    """dV an jeder Last l. Strom je Last bekannt (DB-Schaetzung): Baum-Schranke dV_l <= sum_k I_k*min(R_l, R_k)
    (gemeinsamer Pfad von l und k ist hoechstens der kuerzere). Sonst I_gesamt*R_l (konservativ)."""
    res = []
    for n, I in sorted(pl.I.items()):
        if pl.ist_gnd(n) or n not in pl.V or pl.V[n][0] <= 0:
            continue
        q, lasten = _quellen_lasten(pl, n)
        if not q or not lasten:
            res.append(_e('E2', 'uebersprungen', f'{n}: Quelle oder Last im Netz nicht erkennbar'))
            continue
        R = {}
        zone = False
        for l in lasten:
            r, z = pl.netz_widerstand(n, q, l)
            zone = zone or z
            if r is not None:
                R[l] = r
        if not R:
            res.append(_e('E2', 'warnung', f'{n}: keine Kupferverbindung Quelle -> Last im Layout gefunden (ungeroutet?)'))
            continue
        ik = {}
        for ref, i in pl.lasten.get(n, []):
            pins = [l for l in R if l[0] == ref]
            for l in pins:
                ik[l] = ik.get(l, 0) + i / len(pins)
        schlimm = None
        for l, rl in R.items():
            rest = max(0.0, I - sum(ik.values()))
            dv = sum(i * min(rl, R[k]) for k, i in ik.items()) + rest * rl
            wie = 'Baum-Schranke je Last' if ik else 'Gesamtstrom bis zur Last'
            if ik and rest > 1e-9:
                wie += f', Rest {rest * 1e3:.0f} mA ohne Lastzuordnung voll bis zur Last'
            if schlimm is None or dv > schlimm[0]:
                schlimm = (dv, l, rl, wie)
        dv, l, r, wie = schlimm
        rel = dv / pl.V[n][0] * 100
        st = _stufe(rel, 2.0, 3.0)
        hin = (f'{n}: I = {I * 1e3:.0f} mA ({pl.I_her[n]}), Quelle {", ".join(a + "." + b for a, b in q)}, schlimmste Last '
               f'{l[0]}.{l[1]} mit R = {r * 1e3:.1f} mOhm, dV = {dv * 1e3:.1f} mV ({wie}) = {rel:.2f} % von {pl.V[n][0]:.2f} V')
        if zone:
            hin += ' (Zonen gleichen Netzes als widerstandslos gerechnet)'
        hin += '; Rueckweg ueber GND nicht mitgerechnet'
        res.append(_e('E2', st, hin, wert=round(rel, 3), grenze=2.0, einheit='%',
                      daten={'netz': n, 'I_A': I, 'R_Ohm': r, 'dV_V': dv}))
    return _zusammen('E2', res, 'kein Netz mit Strom (Netzklasse/Symbolfeld Strom/DB-Schaetzung) und Spannung')


def pruefe_e3(pl):
    res = []
    aussen = {pl.lay['lagen'][0], pl.lay['lagen'][-1]} if pl.lay['lagen'] else set()
    T, tq = pl.T_a()
    for n, I in sorted(pl.I.items()):
        bs = pl.bahnen(n)
        if not bs:
            continue
        rho = RHO_CU * (1 + ALPHA_CU * (T - 20))
        schlimm = max(bs, key=lambda t: ipc2221_dT(I, t['w'], pl.cu_dicke.get(t['lage'], 0.035), t['lage'] in aussen))
        tcu = pl.cu_dicke.get(schlimm['lage'], 0.035)
        dT = ipc2221_dT(I, schlimm['w'], tcu, schlimm['lage'] in aussen)
        P = sum(I ** 2 * rho * t['l'] / (t['w'] * pl.cu_dicke.get(t['lage'], 0.035)) for t in bs if t['w'] > 0)
        st = _stufe(dT, 10.0, 20.0)
        if st == 'fehler' and not pl.strom_explizit(n):
            st = 'warnung'
        res.append(_e('E3', st, f'{n}: I = {I * 1e3:.0f} mA ({pl.I_her[n]}), schmalste Bahn {schlimm["w"]:.2f} mm auf '
                      f'{schlimm["lage"]} ({tcu * 1e3:.0f} um) -> dT = {dT:.1f} K (IPC-2221B), P_Bahnen = {P * 1e3:.2f} mW'
                      + ('' if pl.strom_explizit(n) else '; Spitzenstrom als Dauerstrom = konservativ'),
                      wert=round(dT, 2), grenze=10.0, einheit='K', daten={'netz': n, 'P_W': P, 'fuer_fem_waerme': P > 0.05}))
    return _zusammen('E3', res, 'keine Bahn mit bekanntem Strom')


# --------------------------------------------------------------------------------------------- E4 Sperrschicht

RTH_GEHAEUSE_K_W = 15.0   # kleines geschlossenes Gehaeuse ~70x40x20 mm: A ~ 0,008 m2, h ~ 8 W/m2K -> 1/(h*A) ~ 15 K/W


def pruefe_e4(pl):
    """T_j = T_teil + P * RthJA * f_rthja. T_teil aus realterme.teil_temperatur: Luft (T_a_C bzw. T_max_C) + Sonne
    (aussen) + Eigenerwaermung P_ges * Rth_gehaeuse (entfaellt bei T_a_C, das die Luft an der Platine schon nennt)."""
    teile, vorab = [], []
    for ref, e in pl.dbe.items():
        if not e or pl.teile[ref].get('dnp'):
            continue
        typ = e.get('typ')
        P = None
        txt = ''
        explizit = False
        if typ == 'ldo':
            vin = [x['netz'] for x in pl.pins_von[ref] if pl.rolle(x) == 'vin']
            vout = [x['netz'] for x in pl.pins_von[ref] if pl.rolle(x) == 'vout']
            if not vin or not vout or vin[0] not in pl.V or vout[0] not in pl.V:
                vorab.append(_e('E4', 'uebersprungen', f'{ref}: Ein-/Ausgangsspannung unbekannt'))
                continue
            io = pl.I.get(vout[0])
            if io is None:
                vorab.append(_e('E4', 'uebersprungen', f'{ref}: Ausgangsstrom unbekannt (Netzklasse/Symbolfeld Strom)'))
                continue
            vi = pl.V[vin[0]][1]
            vo = pl.V[vout[0]][0]
            P = max(0.0, vi - vo) * io + vi * (e.get('I_q_A') or 0)
            explizit = pl.strom_explizit(vout[0])
            txt = f'{ref} (LDO): P = ({vi:.2f} - {vo:.2f}) V * {io * 1e3:.0f} mA + V_in*I_q = {P * 1e3:.0f} mW'
        elif typ in ('nmos', 'pmos') and e.get('R_DS_on_Ohm'):
            ds = [x['netz'] for x in pl.pins_von[ref] if pl.rolle(x) in ('drain', 'source')]
            ii = [pl.I[n] for n in ds if n in pl.I and not pl.ist_gnd(n)]
            if not ii:
                continue
            i = max(ii)
            r = max(e['R_DS_on_Ohm'].values())
            P = i * i * r
            explizit = any(pl.strom_explizit(n) for n in ds)
            txt = f'{ref} (MOSFET): P = I^2*R_DS(on) = ({i * 1e3:.0f} mA)^2 * {r * 1e3:.0f} mOhm = {P * 1e3:.1f} mW'
        elif typ == 'lader_linear':
            ich = _ladestrom(pl, ref, e)
            vin = [x['netz'] for x in pl.pins_von[ref] if pl.rolle(x) == 'vin']
            if not ich or not vin or vin[0] not in pl.V:
                continue
            vbat = max((pl.akku or {}).get('V_min') or 3.0, 3.0)
            P = (pl.V[vin[0]][1] - vbat) * ich[0]
            explizit = True
            txt = (f'{ref} (Linearlader): P = (V_in,max {pl.V[vin[0]][1]:.2f} - V_bat {vbat:.2f}) V * {ich[0] * 1e3:.0f} mA = '
                   f'{P * 1e3:.0f} mW (Schnellladung erst ab ca. 3,0 V, darunter Vorladung mit kleinem Strom)')
        else:
            continue
        teile.append((ref, e, P, txt, explizit))
    if not teile:
        return _zusammen('E4', vorab, 'kein Regler/Lader/MOSFET mit DB-Kennwerten und bekanntem Strom')
    # eine Teiltemperatur fuer alle Bauteile der Platine
    k = dict(pl.kontext())
    P_ges = sum(P for _, _, P, _, _ in teile)
    ang_eigen = False
    if pl.el.get('T_a_C') is not None:
        k['T_max_C'] = float(pl.el['T_a_C'])
        dT_eigen = 0.0
        eigen_txt = 'T_a_C = Luft an der Platine (Eigenerwaermung enthalten)'
    else:
        rth_g = pl.el.get('Rth_gehaeuse_K_W')
        if rth_g is None:
            rth_g, ang_eigen = RTH_GEHAEUSE_K_W, True
        dT_eigen = P_ges * float(rth_g)
        eigen_txt = (f'Eigenerwaermung P_ges {P_ges * 1e3:.0f} mW * {float(rth_g):.0f} K/W'
                     + (' (Rth_gehaeuse angenommen)' if ang_eigen else ''))
    T, terme, ang_T = rt.teil_temperatur(k, dT_eigen_K=dT_eigen)
    if dT_eigen:
        terme = [t + f' ({eigen_txt})' if t.startswith('Eigenerwaermung') else t for t in terme]
    else:
        terme.append(eigen_txt)
    f_rth, t_rth, ang_rth = rt.abminderung('rthja', k)
    ang = ang_T or ang_rth or ang_eigen
    real = rt.hinweis(terme + t_rth)
    res = vorab
    for ref, e, P, txt, explizit in teile:
        if not e.get('RthJA_K_W'):
            res.append(_e('E4', 'uebersprungen', txt + '; RthJA fehlt in der DB', wert=round(P, 4), einheit='W'))
            continue
        rth = e['RthJA_K_W'] * f_rth
        tj = T + P * rth
        gr = (e.get('Tj_max_C') or 125) - 20
        st = _stufe(tj, gr, gr + 20)
        if st == 'fehler' and not explizit:
            st = 'warnung'
            txt += ' (mit geschaetztem Spitzenstrom als Dauerstrom - Dauerstrom angeben)'
        st = rt.deckel(st, ang)
        res.append(_e('E4', st, txt + f'; T_j = T_teil {T:.1f} C + P*{e["RthJA_K_W"]:.0f} K/W*{f_rth:.2f} = {tj:.0f} C; '
                      + real + ('; Annahmen -> hoechstens warnung' if ang and st == 'warnung' else ''),
                      wert=round(tj, 1), grenze=gr, einheit='C',
                      daten={'ref': ref, 'P_W': P, 'T_teil_C': T, 'RthJA_eff_K_W': rth, 'angenommen': ang}))
    return _zusammen('E4', res, 'kein Regler/Lader/MOSFET mit DB-Kennwerten und bekanntem Strom')


# --------------------------------------------------------------------------------------------- E5 Widerstand/LED

def _netzbereich(pl, n):
    if pl.ist_gnd(n):
        return (0.0, 0.0)
    if n in pl.V:
        return pl.V[n]
    hoch = []
    for x in pl.netze.get(n, []):
        if x.get('typ') in ('output', 'bidirectional', 'tri_state', 'open_collector') and pl.vdd(x['ref']):
            hoch.append(pl.vdd(x['ref'])[1])
    return (0.0, max(hoch)) if hoch else None


def _led_vf(pl, ref):
    e = pl.dbe.get(ref) or {}
    if e.get('V_f_V'):
        return e['V_f_V'], 'DB'
    w = _norm(pl.teile[ref]['wert']).lower()
    g = pl.db.get('generisch_led', {})
    for k in sorted(g, key=len, reverse=True):
        if not k.startswith('_') and k != 'I_max_A' and k.lower() in w:
            return g[k], 'Typklasse'
    return None, None


def _r(R):
    return f'{R / 1e6:g} MOhm' if R >= 1e6 else (f'{R / 1e3:g} kOhm' if R >= 1e3 else f'{R:g} Ohm')


def _p_nenn(pl, ref):
    fp = pl.teile[ref].get('fp', '')
    for k, v in pl.db.get('widerstand_nennleistung_W', {}).items():
        if not k.startswith('_') and re.search(r'(?<!\d)' + k + r'(?!\d)', fp):
            return v
    return None


def pruefe_e5(pl):
    res = []
    for ref in sorted(pl.teile):
        if pl.art(ref) != 'R' or pl.teile[ref].get('dnp'):
            continue
        ps = pl.pins_von.get(ref, [])
        if len(ps) != 2:
            continue
        R = pl.wert(ref, 'R')
        pn = _p_nenn(pl, ref)
        if R is None:
            continue
        a, b = ps[0]['netz'], ps[1]['netz']
        # LED in Reihe?
        led = None
        for seite, ander in ((a, b), (b, a)):
            leds = pl.zweipole(seite, 'LED')
            if leds and len([x for x in pl.netze[seite]]) == 2:
                led = (leds[0][0], seite, leds[0][1], ander)
        if led:
            lref, mitte, jenseits, quelle = led
            vf, vq = _led_vf(pl, lref)
            vs = _netzbereich(pl, quelle)
            vj = _netzbereich(pl, jenseits)
            if vf is None or vs is None:
                res.append(_e('E5', 'uebersprungen', f'{ref}+{lref}: V_f oder Quellspannung unbekannt'))
                continue
            # LED-Anode an der Quelle? (Kathode zu GND/Schalter) - Richtung egal fuer die Spannungsbilanz
            v_unten = vj[0] if vj else 0.0
            vs_max = vs[1]
            reserve = vs_max - v_unten - vf
            if R == 0:
                res.append(_e('E5', 'info', f'{ref} = 0 Ohm vor {lref}: Strombegrenzung muss in der LED/im Taster stecken '
                              f'(Quelle {quelle} bis {vs_max:.2f} V)', daten={'ref': ref}))
                continue
            i = max(0.0, reserve) / R
            P = i * i * R
            imax = (pl.dbe.get(lref) or {}).get('I_max_A')
            imax_typ = imax is None
            if imax_typ:
                imax = pl.db.get('generisch_led', {}).get('I_max_A', 0.02)
            st = 'ok'
            hin = (f'{ref} {_r(R)} + {lref} (V_f {vf:.1f} V {vq}): I = ({vs_max:.2f} - {v_unten:.2f} - {vf:.1f}) V / R = '
                   f'{i * 1e3:.2f} mA, P_R = {P * 1e3:.2f} mW')
            if reserve < 0.3:
                st = 'warnung'
                hin += f'; Reserve V_s - V_f = {reserve:.2f} V < 0,3 V (Helligkeit streut stark)'
            if i > imax:
                st = 'warnung' if imax_typ else 'fehler'
                hin += f'; I > I_max {imax * 1e3:.0f} mA' + (' (Typklasse Anzeige-LED - Datenblatt-I_max in bauteile.json eintragen)'
                                                            if imax_typ else '')
            if pn and P > 0.5 * pn:
                st = 'fehler' if P > pn else 'warnung'
                hin += f'; P > 0,5*P_nenn ({pn * 1e3:.0f} mW)'
            src = [x for x in pl.netze.get(quelle, []) if x.get('typ') in ('output', 'bidirectional')]
            for x in src:
                lg = (pl.dbe.get(x['ref']) or {}).get('logik') or {}
                if lg.get('I_OH_A') and i > lg['I_OH_A']:
                    st = 'fehler'
                    hin += f'; GPIO {x["ref"]}.{x["name"]} liefert hoechstens {lg["I_OH_A"] * 1e3:.0f} mA'
            res.append(_e('E5', st, hin, wert=round(P, 6), grenze=0.5 * pn if pn else None, einheit='W',
                          daten={'ref': ref, 'led': lref, 'I_A': i}))
            continue
        va, vb = _netzbereich(pl, a), _netzbereich(pl, b)
        if va is None or vb is None:
            continue
        if f'ueber {ref} ' in pl.V_her.get(a, '') + pl.V_her.get(b, ''):
            res.append(_e('E5', 'ok', f'{ref} {_r(R)} speist {a if f"ueber {ref} " in pl.V_her.get(a, "") else b} '
                          '(RC-Filter vor VCC, nur Versorgungsstrom des ICs - P vernachlaessigbar)', daten={'ref': ref}))
            continue
        dv = max(abs(va[1] - vb[0]), abs(vb[1] - va[0]))
        if R <= 0:
            continue
        P = dv * dv / R
        fest = [n for n in (a, b) if n in pl.V]
        if not fest:
            # Serienwiderstand zwischen zwei Logiknetzen: im Betrieb nur Eingangs-/Umladestrom; P nur bei Treiberkonflikt
            treiber = [n for n in (a, b) if any(x.get('typ') in ('output', 'bidirectional', 'tri_state')
                                                  and pl.art(x['ref']) not in ('R', 'C') for x in pl.netze.get(n, []))]
            res.append(_e('E5', 'info', f'{ref} {_r(R)} in Reihe zwischen Logiknetzen {a} / {b}: kein Gleichstrom im Betrieb'
                          + (f'; nur bei Treiberkonflikt (beide Seiten treiben) P = {P * 1e3:.0f} mW' if len(treiber) == 2 else ''),
                          daten={'ref': ref}))
            continue
        if pn is None:
            res.append(_e('E5', 'uebersprungen', f'{ref}: P = {P * 1e3:.2f} mW, Bauform/Nennleistung unbekannt'))
            continue
        st = 'ok' if P <= 0.5 * pn else ('warnung' if P <= pn else 'fehler')
        res.append(_e('E5', st, f'{ref} {_r(R)} zwischen {a} und {b}: dV_max {dv:.2f} V -> P = {P * 1e3:.3f} mW '
                      f'(P_nenn {pn * 1e3:.0f} mW)', wert=round(P, 6), grenze=0.5 * pn, einheit='W', daten={'ref': ref}))
    return _zusammen('E5', res, 'keine Widerstaende mit bekannten Spannungen')


# --------------------------------------------------------------------------------------------- E7 Teiler, E6 Laufzeit

def teiler(pl):
    out = []
    for n, kn in pl.netze.items():
        if pl.ist_gnd(n) or n in pl.V:
            continue
        rs = pl.zweipole(n, 'R')
        if len(rs) != 2:
            continue
        oben = [(r, o) for r, o in rs if o in pl.V and not pl.ist_gnd(o)]
        unten = [(r, o) for r, o in rs if pl.ist_gnd(o)]
        if len(oben) != 1 or len(unten) != 1:
            continue
        r1, r2 = pl.wert(oben[0][0], 'R'), pl.wert(unten[0][0], 'R')
        if not r1 or not r2:
            continue
        caps = [pl.wert(c, 'C') for c, o in pl.zweipole(n, 'C') if pl.ist_gnd(o)]
        out.append({'netz': n, 'R1': oben[0][0], 'R2': unten[0][0], 'r1': r1, 'r2': r2, 'schiene': oben[0][1],
                    'V': pl.V[oben[0][1]][1], 'C': sum(c for c in caps if c) or None})
    return out


def pruefe_e7(pl):
    res = []
    akku = pl.akku is not None
    for t in teiler(pl):
        I = t['V'] / (t['r1'] + t['r2'])
        rth = t['r1'] * t['r2'] / (t['r1'] + t['r2'])
        hin = (f'{t["netz"]}: {t["R1"]} {_r(t["r1"])} / {t["R2"]} {_r(t["r2"])} an {t["schiene"]} ({t["V"]:.2f} V): '
               f'I = {I * 1e6:.2f} uA, R_th = {rth / 1e3:.1f} kOhm')
        if t['C']:
            hin += f', C {t["C"] * 1e9:.0f} nF puffert den ADC-Abtastkondensator'
        fb = any(pl.rolle(x) == 'fb' for x in pl.netze.get(t['netz'], []))
        if fb:
            st = 'info'
            hin += ' (Rueckkopplungsteiler eines Reglers: fliesst nur, solange der Regler laeuft; in E6 mitgezaehlt)'
        elif akku:
            st = _stufe(I * 1e6, 1.0, 5.0)
            if st == 'fehler':
                st = 'warnung'
            hin += ' (Akkubetrieb: Ziel <= 1 uA, Dauerverlust zaehlt in E6)'
        else:
            st = 'info'
        res.append(_e('E7', st, hin, wert=round(I * 1e6, 3), grenze=1.0 if akku else None, einheit='uA',
                      daten={'netz': t['netz'], 'I_A': I, 'R_th_Ohm': rth}))
    return _zusammen('E7', res, 'keine Spannungsteiler (zwei Widerstaende Schiene -> Knoten -> GND) gefunden')


CHEMIE_V = {'lipo': (3.0, 4.2), 'lifepo4': (2.5, 3.6), 'li_fes2': (0.9, 1.8), 'alkali': (0.9, 1.6), 'nimh': (1.0, 1.4)}
ETA_STANDARD = 0.8


def _v_bat(pl):
    """(V_min, V_max) des Akkus: Platine, sonst Firmware-Abschaltung/Chemie (1 Zelle), sonst None."""
    ak = pl.akku or {}
    if ak.get('V_min') and ak.get('V_max'):
        return ak['V_min'], ak['V_max']
    lo, hi = CHEMIE_V.get(pl.akku_chemie() or 'lipo', CHEMIE_V['lipo'])
    va = pl.modul_wert('V_abschalt_V')
    return (float(va) if va else lo), hi


def _wandler(pl):
    """(faktor, text, angenommen) fuer I_bat = I_last * V_out / (eta * V_bat) (Kopf-KONVENTION Strom, eta 0,8).
    V_bat = Abschaltspannung (ungunstigster Fall: groesster Akkustrom). LDO/direkt: Faktor 1 (I_q im Ruhestrom-Boden)."""
    lo, hi = _v_bat(pl)
    vb = lo
    if pl.ohne_kicad:
        w = pl.modul_wert('wandler')
        if w in ('ldo', 'keiner'):
            return 1.0, f'Wandler {w}: I_bat = I_last', False
        eta = pl.modul_wert('eta')
        vo = pl.modul_wert('V_out_V') or 3.3
        ang = w is None or eta is None or pl.modul_wert('V_out_V') is None
        eta = float(eta or ETA_STANDARD)
        f = max(1.0, vo / (eta * vb))
        return f, (f'Wandler {w or "unbekannt -> Schaltregler"}: I_bat = I*{vo:.2f} V/({eta:.2f}*{vb:.2f} V) = '
                   f'I*{f:.3f}' + (' (angenommen)' if ang else '')), ang
    schalt = [(r, e) for r, e in pl.dbe.items() if e and e.get('typ') in ('buck', 'boost', 'buckboost')
              and not pl.teile[r].get('dnp')]
    if pl.akku_netze:
        schalt = [(r, e) for r, e in schalt
                  if any(pl.rolle(x) == 'vin' and x['netz'] in pl.akku_netze for x in pl.pins_von.get(r, []))]
    if not schalt:
        return 1.0, 'kein Schaltregler am Akku: I_bat = I_last (LDO/direkt)', False
    best = None
    for r, e in schalt:
        vo = max((pl.V[x['netz']][1] for x in pl.pins_von.get(r, []) if pl.rolle(x) == 'vout' and x['netz'] in pl.V),
                 default=e.get('V_out_V'))
        ang = vo is None or not e.get('eta')
        eta = float(e.get('eta') or ETA_STANDARD)
        f = (vo / (eta * vb)) if vo else 1 / eta
        if best is None or f > best[0]:
            best = (f, f'{r} ({e["typ"]}): I_bat = I*{(vo or 0):.2f} V/({eta:.2f}*{vb:.2f} V) = I*{f:.3f}'
                    + (' (eta/V_out angenommen)' if ang else ''), ang)
    return best


def pruefe_e6(pl):
    """t = C_eff / I_bat. C_eff = C_nenn / realterme.abminderung('kapazitaet') (nutzbar 0,85, Kaelte, Alterung,
    Selbstentladung); I_bat = Ruhestrom-Boden (Akkuseite) + (Lastruhe + Modi) * Wandlerfaktor. 'ok' erst ab 1,25 x Ziel."""
    ak = pl.akku
    if not ak or not ak.get('mAh'):
        return [_u('E6', 'Akkukapazitaet fehlt (soll.json _projekt.akku_mAh, elektronik.module[].akku_mAh oder Batterie '
                         'in der DB)')]
    boden_bat = []      # schon Akkustrom: I_q der Regler/Schutz-ICs, Teiler am Akku
    boden_last = []     # Lastseite: Ruhestrom MCU/Sensoren
    unbekannt = []
    for ref, e in pl.dbe.items():
        if pl.teile[ref].get('dnp'):
            continue
        if e is None:   # nicht in der DB: mit Versorgungspin ist der Ruhestrom unbekannt, nie 0 A
            if any(pl.rolle(x) == 'vdd' for x in pl.pins_von.get(ref, [])):
                unbekannt.append(f'{ref} (nicht in bauteile.json)')
            continue
        if e.get('typ') in ('ldo', 'boost', 'buck', 'buckboost', 'akkuschutz'):
            if e.get('I_q_A') is not None:
                boden_bat.append((ref + ' I_q', e['I_q_A']))
            else:
                unbekannt.append(ref)
        elif e.get('typ') in ('mcu', 'sensor'):
            if e.get('I_sleep_A') is not None:
                boden_last.append((ref + ' Ruhe', e['I_sleep_A']))
            else:
                unbekannt.append(ref)
    for t in teiler(pl):
        (boden_bat if t['schiene'] in pl.akku_netze or not pl.akku_netze else boden_last).append(
            (f'Teiler {t["R1"]}/{t["R2"]}', t['V'] / (t['r1'] + t['r2'])))
    for m in pl.module:
        if m.get('I_ruhe_uA') is not None:
            boden_last.append((f'{m.get("name", "Modul")} Ruhe', float(m['I_ruhe_uA']) * 1e-6))
    modi = pl.el.get('modi') or []
    if pl.ohne_kicad and not modi and not boden_last:
        return [_u('E6', 'Kaufmodul ohne Verbrauchsangabe: soll.json elektronik.modi [{name, I_mA, anteil}] oder '
                         'elektronik.module[].I_ruhe_uA fehlt')]
    f_w, t_w, ang_w = _wandler(pl)
    I_bat0 = sum(i for _, i in boden_bat)
    I_last = sum(i for _, i in boden_last) + sum(m['I_mA'] * 1e-3 * m['anteil'] for m in modi)
    Im = I_bat0 + I_last * f_w
    f_c, t_c, ang_c = rt.abminderung('kapazitaet', pl.kontext())
    C_eff = ak['mAh'] / f_c
    t_h = C_eff * 1e-3 / Im if Im > 0 else float('inf')
    ziel = pl.ps.get('laufzeit_ziel_h')
    boden = boden_bat + boden_last
    hin = (f'Ruhestrom-Boden {sum(i for _, i in boden) * 1e6:.2f} uA (' + ', '.join(f'{n} {i * 1e6:.2f}' for n, i in boden)
           + ' uA)' + (f' + Modi {", ".join(m["name"] for m in modi)}' if modi else '')
           + f'; {t_w} -> I_bat {Im * 1e6:.2f} uA; C_eff = {ak["mAh"]:.0f} mAh / {f_c:.3f} = {C_eff:.0f} mAh'
           + f' -> t = {t_h:.0f} h; ' + rt.hinweis(t_c))
    if unbekannt:
        hin += '; ohne Ruhestrom in der DB: ' + ', '.join(sorted(unbekannt))
    daten = {'C_eff_mAh': C_eff, 'f_kapazitaet': f_c, 'f_wandler': f_w, 'I_bat_A': Im}
    if not ziel:
        return [_e('E6', 'warnung', hin + '; Laufzeitziel fehlt (soll.json _projekt.laufzeit_ziel_h) - ohne Ziel kein ok',
                   wert=round(t_h, 1), einheit='h', daten=daten)]
    st = 'ok' if t_h >= 1.25 * ziel else ('warnung' if t_h >= ziel else 'fehler')
    if st == 'warnung':
        hin += f'; Reserve unter 25 % (ok ab 1,25 x {ziel:g} h = {1.25 * ziel:g} h)'
    if st == 'ok' and (unbekannt or not modi):
        st = 'warnung'
        hin += '; nur Untergrenze des Verbrauchs bekannt (Modi/Ruhestroeme fehlen) - Laufzeit kann kuerzer sein'
    st2 = rt.deckel(st, ang_c or ang_w)
    if st2 != st:
        hin += '; Bedingungen angenommen (Chemie/T_min/Wandler) -> hoechstens warnung'
    return [_e('E6', st2, hin, wert=round(t_h, 1), grenze=1.25 * ziel, einheit='h', daten=daten)]


# --------------------------------------------------------------------------------------------- E8 Brownout

E8_RESERVE_V = 0.15     # Regel-/Messreserve ueber VDD_min (Audit 15.11.2026: 0,1 V war zu knapp)


def _rint_eff(pl, rint):
    """(R_eff, text, angenommen): R_int * realterme.abminderung('rint') (Kaelte bei T_min, Alterung/Kontakte)."""
    if not rint:
        return rint, '', False
    f, terme, ang = rt.abminderung('rint', pl.kontext())
    return rint * f, f'R_eff = {rint:g} Ohm * {f:.2f} = {rint * f:.3f} Ohm ({rt.hinweis(terme)})', ang


def pruefe_e8(pl):
    """Brownout bei der Funkspitze: V_krit = VDD_min + 0,15 V + Dropout + I_peak * R_eff, R_eff = R_int * f_rint."""
    if pl.ohne_kicad:
        return _pruefe_e8_modul(pl)
    res = []
    ak = pl.akku
    for ref, e in pl.dbe.items():
        if not e or e.get('typ') not in ('mcu',) or not e.get('VDD_V'):
            continue
        vd = pl.vdd(ref)
        if not vd:
            res.append(_e('E8', 'uebersprungen', f'{ref}: Versorgungsspannung unbekannt'))
            continue
        ip = e.get('I_peak_A')
        if not ip:
            res.append(_e('E8', 'uebersprungen', f'{ref}: Spitzenstrom fehlt in der DB'))
            continue
        vnetz = vd[2]
        vdd_min = e['VDD_V'][0]
        reserve = E8_RESERVE_V
        # Regler vor der MCU?
        reg = None
        for x in pl.netze.get(vnetz, []):
            if pl.rolle(x) == 'vout' and (pl.dbe.get(x['ref']) or {}).get('typ') in ('ldo', 'boost', 'buck', 'buckboost'):
                reg = x['ref']
        I_netz = max(pl.I.get(vnetz, 0), ip)
        if reg and pl.dbe[reg]['typ'] == 'ldo':
            re_ = pl.dbe[reg]
            vins = [x['netz'] for x in pl.pins_von[reg] if pl.rolle(x) == 'vin']
            if not vins:
                res.append(_e('E8', 'uebersprungen', f'{ref}: Eingang des Reglers {reg} nicht erkannt (Pinrolle vin)'))
                continue
            vin = vins[0]
            do = (re_.get('dropout_V') or 0) * I_netz / (re_.get('dropout_bei_A') or re_.get('I_max_A') or 1)
            rint, r_txt, r_ang = _rint_eff(pl, (ak or {}).get('R_int') if ak and vin in pl.akku_netze else None)
            v_krit = vdd_min + reserve + do + (I_netz * rint if rint else 0)
            vq = pl.V.get(vin)
            hin = (f'{ref}: VDD_min {vdd_min:.2f} V + Reserve {reserve:.2f} V + Dropout {reg} {do:.2f} V '
                   f'(linear auf {I_netz * 1e3:.0f} mA)' + (f' + I*R_int {I_netz * rint:.2f} V' if rint else '')
                   + f' -> {vin} muss >= {v_krit:.2f} V bleiben' + (f'; {r_txt}' if r_txt else ''))
            if not rint and vin in pl.akku_netze:
                hin += '; R_int des Akkus unbekannt (soll.json elektronik.R_int_Ohm) - Einbruch an der Zelle nicht gerechnet'
            if vq is None:
                res.append(_e('E8', 'uebersprungen', hin + f'; Spannung an {vin} unbekannt', wert=round(v_krit, 3), einheit='V'))
                continue
            vmin = vq[0]
            st = 'ok' if vmin >= v_krit else ('warnung' if vin in pl.akku_netze and not pl.el.get('V_abschalt_V') else 'fehler')
            hin += f'; {vin} faellt bis {vmin:.2f} V ({pl.V_her.get(vin)})'
            if st == 'warnung':
                hin += f' -> Firmware muss bei >= {v_krit:.2f} V abschalten (soll.json elektronik.V_abschalt_V eintragen)'
            if not rint and st == 'ok':
                st = 'warnung'
            st = rt.deckel(st, r_ang)
            res.append(_e('E8', st, hin, wert=round(vmin, 3), grenze=round(v_krit, 3), einheit='V',
                          daten={'ref': ref, 'regler': reg, 'V_krit': v_krit}))
        else:
            vq = pl.V.get(vnetz)
            rint = (ak or {}).get('R_int') if ak and ak.get('netz') == vnetz else None
            if vq is None:
                res.append(_e('E8', 'uebersprungen', f'{ref}: Spannung an {vnetz} unbekannt'))
                continue
            if reg:
                # Eingangsseite (Akkueinbruch I*R_int am Reglereingang, dessen Unterspannungsabschaltung) ist hier nicht
                # gerechnet -> hoechstens 'warnung', nie 'ok'
                st = 'warnung' if vq[0] >= vdd_min + reserve else 'fehler'
                res.append(_e('E8', st, f'{ref} an Schaltregler {reg}: {vnetz} min {vq[0]:.2f} V vs. VDD_min {vdd_min:.2f} V + '
                              f'{reserve} V; Akkueinbruch am Reglereingang und dessen Abschaltung NICHT gerechnet '
                              f'(Regelreserve bei {I_netz * 1e3:.0f} mA nicht modelliert)',
                              wert=round(vq[0], 3), grenze=vdd_min + reserve, einheit='V'))
                continue
            am_akku = vnetz in pl.akku_netze
            if am_akku and ak:
                rint = ak.get('R_int')
            rint, r_txt, r_ang = _rint_eff(pl, rint)
            einbruch = I_netz * rint if rint else 0
            vmin = vq[0] - einbruch
            v_krit = vdd_min + reserve + einbruch
            st = _stufe(vmin, vdd_min + reserve, vdd_min, groesser_besser=True)
            hin = (f'{ref} direkt an {vnetz}: V_min {vq[0]:.2f} V ({pl.V_her.get(vnetz)}) - I_peak {I_netz * 1e3:.0f} mA * '
                   f'R_eff {f"{rint:.3f}" if rint else "?"} Ohm = {vmin:.2f} V vs. VDD_min {vdd_min:.2f} V + {reserve} V'
                   + (f'; {r_txt}' if r_txt else ''))
            if am_akku and st != 'ok' and not pl.el.get('V_abschalt_V'):
                st = 'warnung'
                hin += (f' -> Entladeschluss der Zelle liegt unter VDD_min: Firmware muss bei Akku >= {v_krit:.2f} V '
                        f'(Leerlauf, vor der Funkspitze) abschalten (soll.json elektronik.V_abschalt_V); Restkapazitaet darunter ungenutzt')
            if not rint:
                st = 'warnung' if st == 'ok' else st
                hin += ' (R_int unbekannt)'
            st = rt.deckel(st, r_ang)
            res.append(_e('E8', st, hin, wert=round(vmin, 3), grenze=round(v_krit, 3), einheit='V', daten={'ref': ref, 'V_krit': v_krit}))
    return _zusammen('E8', res, 'keine MCU/kein Funkmodul mit Spitzenstrom in der DB')


def _pruefe_e8_modul(pl):
    """Kaufmodul ohne KiCad: V_krit am Akku = VDD_min + 0,15 V + Dropout (LDO) + I_peak * R_eff;
    mit Schaltregler V_in_min_V + 0,15 V + I_peak * V_out/(eta*V_bat) * R_eff. Vergleich mit V_abschalt_V."""
    ak = pl.akku
    if not ak:
        return [_u('E8', 'Kaufmodul ohne Akku (elektronik.module[].akku_mAh bzw. _projekt.akku_mAh fehlt)')]
    w = pl.modul_wert('wandler')
    ip = pl.modul_wert('I_peak_mA')
    fehlt = ['I_peak_mA'] if ip is None else []
    if w is None:
        fehlt.append('wandler')
    elif w in ('ldo', 'keiner'):
        if pl.modul_wert('VDD_min_V') is None:
            fehlt.append('VDD_min_V')
        if w == 'ldo' and pl.modul_wert('dropout_V') is None:
            fehlt.append('dropout_V')
    elif pl.modul_wert('V_in_min_V') is None:
        fehlt.append('V_in_min_V')
    if fehlt:
        return [_u('E8', 'Kaufmodul: ' + ', '.join(f'elektronik.module[].{f}' for f in fehlt)
                   + ' fehlt - Brownout bei der Funkspitze nicht rechenbar')]
    I = float(ip) * 1e-3
    rint, r_txt, r_ang = _rint_eff(pl, ak.get('R_int'))
    R = E8_RESERVE_V
    if w in ('ldo', 'keiner'):
        vdd = float(pl.modul_wert('VDD_min_V'))
        do = float(pl.modul_wert('dropout_V') or 0) if w == 'ldo' else 0.0
        I_bat = I
        v_krit = vdd + R + do + I_bat * (rint or 0)
        hin = (f'Kaufmodul ({w}): VDD_min {vdd:.2f} V + Reserve {R:.2f} V + Dropout {do:.2f} V + I_peak {I * 1e3:.0f} mA'
               f' * R_eff {f"{rint:.3f}" if rint else "?"} Ohm -> Akku muss >= {v_krit:.2f} V bleiben')
    else:
        f_w, t_w, _ = _wandler(pl)
        vin = float(pl.modul_wert('V_in_min_V'))
        I_bat = I * f_w
        v_krit = vin + R + I_bat * (rint or 0)
        hin = (f'Kaufmodul ({w}): V_in_min {vin:.2f} V + Reserve {R:.2f} V + I_bat {I_bat * 1e3:.0f} mA ({t_w}) * R_eff '
               f'{f"{rint:.3f}" if rint else "?"} Ohm -> Akku muss >= {v_krit:.2f} V bleiben')
    if r_txt:
        hin += '; ' + r_txt
    va = pl.modul_wert('V_abschalt_V')
    if va is None:
        st = 'warnung'
        hin += (f'; Firmware-Abschaltung fehlt (elektronik.V_abschalt_V): Firmware muss bei Akku >= {v_krit:.2f} V '
                '(Leerlauf, vor der Funkspitze) abschalten')
        vmin = ak.get('V_min')
    else:
        vmin = float(va)
        st = 'ok' if vmin >= v_krit else 'fehler'
        hin += f'; Abschaltung {vmin:.2f} V'
    if not rint:
        st = 'warnung' if st == 'ok' else st
        hin += ' (R_int unbekannt: elektronik.R_int_Ohm)'
    st = rt.deckel(st, r_ang)
    return [_e('E8', st, hin, wert=round(vmin, 3) if vmin else None, grenze=round(v_krit, 3), einheit='V',
               daten={'V_krit': v_krit, 'R_eff_Ohm': rint, 'I_bat_A': I_bat})]


# --------------------------------------------------------------------------------------------- E9/E10 Entkopplung

def _masse_von(pl, ref):
    """Bezugsnetze eines Bauteils: Netze seiner gnd-Pins (z. B. BATN beim DW01A), sonst die GND-Namen."""
    g = {x['netz'] for x in pl.pins_von.get(ref, []) if pl.rolle(x) in ('gnd', 'pgnd')}
    return g


def _naechster_c(pl, ref, pin, netz):
    pp = pl.pad_pos(ref, pin)
    if pp is None:
        return None
    best = None
    masse = _masse_von(pl, ref)
    for c, o in pl.zweipole(netz, 'C'):
        if not (o in masse or (not masse and pl.ist_gnd(o)) or (pl.ist_gnd(o) and any(pl.ist_gnd(m) for m in masse))):
            continue
        cpin = [x for x in pl.pins_von[c] if x['netz'] == netz][0]['pin']
        cp = pl.pad_pos(c, cpin)
        if cp is None:
            continue
        d = math.dist(pp, cp)
        if best is None or d < best[1]:
            best = (c, d)
    return best


def pruefe_e9(pl):
    """Abstand Versorgungspin -> naechster C zur eigenen Masse des ICs (<= 3 mm) und L_loop = mu0*h*l/w (<= 5 nH).
    h = Abstand zur Nachbarlage (Masse dort), w = Padbreite des Versorgungspins."""
    res = []
    nur_L = []
    for ref in sorted(pl.teile):
        if pl.art(ref) not in ('U', 'IC') or pl.teile[ref].get('dnp'):
            continue
        for x in pl.pins_von.get(ref, []):
            if pl.rolle(x) not in ('vdd', 'vin', 'vin_a') or pl.ist_gnd(x['netz']):
                continue
            b = _naechster_c(pl, ref, x['pin'], x['netz'])
            if b is None:
                res.append(_e('E9', 'fehler', f'{ref}.{x["name"]} ({x["netz"]}): kein Kondensator zur Masse des Bauteils '
                              f'({", ".join(sorted(_masse_von(pl, ref))) or "GND"}) an diesem Netz', daten={'ref': ref, 'pin': x['pin']}))
                continue
            c, d = b
            pads = pl.pads.get((ref, x['pin'])) or [{'gr': [0.3, 0.3], 'lagen': pl.lay['lagen'][:1]}]
            lage = pads[0]['lagen'][0] if pads[0]['lagen'] else pl.lay['lagen'][0]
            h = pl.h_ref.get(lage, (1.5, 4.5, None))[0]
            w = max(0.2, min(pads[0]['gr']))
            L = MU0 * h * d / w * 1e9
            st = _stufe(d, 3.0, 10.0)
            hin = (f'{ref}.{x["name"]} ({x["netz"]}): naechster C {c} in {d:.1f} mm, L_loop ~ mu0*{h:.2f} mm*{d:.1f} mm/'
                   f'{w:.2f} mm = {L:.1f} nH')
            e = _e('E9', st, hin, wert=round(d, 2), grenze=3.0, einheit='mm', daten={'ref': ref, 'pin': x['pin'], 'C': c, 'L_nH': L})
            if st == 'ok' and L > 5:
                nur_L.append(e)
            else:
                res.append(e)
    if nur_L:
        res.append(_e('E9', 'warnung', f'{len(nur_L)} Versorgungspins mit C <= 3 mm, aber L_loop > 5 nH (Masse erst auf der '
                      'Nachbarlage im Abstand h - GND-Via direkt an jedes C-Pad, duennere Platine/4 Lagen): '
                      + '; '.join(x['hinweis'] for x in nur_L), wert=round(max(x['daten']['L_nH'] for x in nur_L), 1),
                      grenze=5.0, einheit='nH'))
    return _zusammen('E9', res, 'keine ICs mit Versorgungspins')


def pruefe_e10(pl):
    res = []
    for ref, e in pl.dbe.items():
        if not e or e.get('typ') not in ('buck', 'boost', 'buckboost'):
            continue
        for rolle in e.get('heiss', ['vin']):
            for x in [x for x in pl.pins_von[ref] if pl.rolle(x) == rolle]:
                b = _naechster_c(pl, ref, x['pin'], x['netz'])
                if b is None:
                    res.append(_e('E10', 'fehler', f'{ref}.{x["name"]}: kein Kondensator nach GND im heissen Pfad'))
                    continue
                st = _stufe(b[1], 3.0, 5.0)
                res.append(_e('E10', st, f'{ref}.{x["name"]} ({x["netz"]}): C {b[0]} in {b[1]:.1f} mm (Masche klein halten)',
                              wert=round(b[1], 2), grenze=3.0, einheit='mm'))
        sw = {x['netz'] for x in pl.pins_von[ref] if pl.rolle(x) == 'sw'}
        for n in sw:
            A = sum(t['l'] * t['w'] for t in pl.bahnen(n))
            l = sum(t['l'] for t in pl.bahnen(n))
            res.append(_e('E10', 'info', f'{ref} SW-Netz {n}: Kupfer {A:.1f} mm^2, Bahnlaenge {l:.1f} mm (klein = weniger Abstrahlung)',
                          wert=round(A, 2), einheit='mm^2'))
    return _zusammen('E10', res, 'kein Schaltregler (DB-Typ buck/boost/buckboost)')


# --------------------------------------------------------------------------------------------- E11 I2C

def _bahn_c(pl, netz):
    """Leiterbahnkapazitaet (F): max(Plattenkondensator eps*w*l/h (Katalog), Microstrip sqrt(eps_eff)/(c*Z0)*l)."""
    C = 0.0
    for t in pl.bahnen(netz):
        h, er, _ = pl.h_ref.get(t['lage'], (1.5, 4.5, None))
        tcu = pl.cu_dicke.get(t['lage'], 0.035)
        cp = EPS0 * er * t['w'] * t['l'] / h
        z0, ee = microstrip_z0(t['w'], h, tcu, er)
        cm = math.sqrt(ee) / (C0 * z0) * t['l']
        C += max(cp, cm)
    return C


def i2c_netze(pl):
    out = {}
    for n, kn in pl.netze.items():
        nm = n.upper()
        if I2C_RE.search(nm) or any(I2C_RE.search((x.get('name') or '').upper()) for x in kn):
            out[n] = kn
    return out


def pruefe_e11(pl):
    res = []
    f = float(pl.el.get('i2c_kHz', 400))
    tr_max = 1000e-9 if f <= 100 else (300e-9 if f <= 400 else 120e-9)
    for n, kn in sorted(i2c_netze(pl).items()):
        geraete = {x['ref'] for x in kn if pl.art(x['ref']) not in ('R', 'C')}
        pu = _pullup(pl, n)
        if not pu:
            st = 'warnung'
            res.append(_e('E11', st, f'{n}: kein Pull-up auf der Platine gefunden (auf Modul/extern? sonst fehlt er)'))
            continue
        R = 1 / sum(1 / p[1] for p in pu)
        vdd = max(p[3] for p in pu)
        Cpins = 0.0
        for g in geraete:
            cp = (pl.dbe.get(g) or {}).get('C_pin_pF')
            Cpins += (cp if cp else 10.0) * 1e-12
        Cb = _bahn_c(pl, n)
        C = Cpins + Cb
        tr = 0.8473 * R * C
        rmin = (vdd - 0.4) / 0.003
        st = 'ok' if tr <= tr_max and R >= rmin else ('fehler' if R < rmin * 0.8 or tr > 1.5 * tr_max else 'warnung')
        res.append(_e('E11', st, f'{n}: R_p {R:.0f} Ohm ({", ".join(p[0] for p in pu)}), C_b = {len(geraete)} Pins x 10 pF '
                      f'(UM10204 C_i max, wo DB leer) + Bahn {Cb * 1e12:.1f} pF = {C * 1e12:.1f} pF -> t_r = 0,8473*R*C = '
                      f'{tr * 1e9:.0f} ns (Grenze {tr_max * 1e9:.0f} ns bei {f:.0f} kHz), R_min = (V_DD - 0,4)/3 mA = {rmin:.0f} Ohm',
                      wert=round(tr * 1e9, 1), grenze=tr_max * 1e9, einheit='ns', daten={'netz': n, 'R': R, 'C_F': C}))
    return _zusammen('E11', res, 'keine I2C-Netze (SDA/SCL) gefunden')


# --------------------------------------------------------------------------------------------- E12 RC

def pruefe_e12(pl):
    res = []
    fs = pl.el.get('abtastrate_Hz')
    gesehen = set()
    for t in teiler(pl):
        if t['C']:
            rth = t['r1'] * t['r2'] / (t['r1'] + t['r2'])
            fc = 1 / (2 * math.pi * rth * t['C'])
            gesehen.add(t['netz'])
            res.append((t['netz'], rth, t['C'], fc, f'Teiler {t["R1"]}/{t["R2"]}'))
    for n, kn in pl.netze.items():
        if n in gesehen or pl.ist_gnd(n) or n in pl.V:
            continue
        caps = [pl.wert(c, 'C') for c, o in pl.zweipole(n, 'C') if pl.ist_gnd(o)]
        rs = pl.zweipole(n, 'R')
        eing = [x for x in kn if x.get('typ') in ('input', 'bidirectional')]
        if len(rs) == 1 and caps and all(caps) and eing:
            R = pl.wert(rs[0][0], 'R')
            if R:
                C = sum(caps)
                res.append((n, R, C, 1 / (2 * math.pi * R * C), f'Reihen-R {rs[0][0]}'))
    out = []
    for n, R, C, fc, wie in res:
        hin = f'{n}: {wie}, R = {R / 1e3:.2f} kOhm, C = {C * 1e9:.1f} nF -> f_c = {fc:.3g} Hz'
        if fs:
            st = 'ok' if fc <= fs / 2 else 'warnung'
            hin += f' (Nyquist {fs / 2:.3g} Hz)'
        else:
            st = 'info'
        out.append(_e('E12', st, hin, wert=round(fc, 4), grenze=fs / 2 if fs else None, einheit='Hz', daten={'netz': n}))
    return _zusammen('E12', out, 'keine RC-Glieder vor Eingaengen gefunden')


# --------------------------------------------------------------------------------------------- E13/E14 Leitungen

def netz_frequenzen(pl):
    f = {}
    for n, v in (pl.el.get('frequenzen') or {}).items():
        f[n] = (float(v), 'soll.json')
    for n in i2c_netze(pl):
        f.setdefault(n, (float(pl.el.get('i2c_kHz', 400)) * 1e3, 'I2C'))
    for n in pl.netze:
        nm = n.upper()
        if re.search(r'USB.*D[PNM+-]|^/?D[PN+-]$|USB_D', nm):
            f.setdefault(n, (12e6, 'USB Full-Speed angenommen'))
    for n in rf_netze(pl):
        f.setdefault(n, (rf_netze(pl)[n] * 1e6, 'Funk (DB)'))
    for ref, e in pl.dbe.items():
        if e and e.get('f_sw_Hz'):
            for x in pl.pins_von.get(ref, []):
                if pl.rolle(x) == 'sw':
                    f.setdefault(x['netz'], (e['f_sw_Hz'], f'Schaltfrequenz {ref}'))
    for ref in pl.teile:
        if pl.art(ref) == 'Y':
            fq = re.match(r'\s*(\d+(?:\.\d+)?)\s*(k|M)?Hz', pl.teile[ref]['wert'])
            if fq:
                v = float(fq.group(1)) * {'k': 1e3, 'M': 1e6}.get(fq.group(2), 1)
                for x in pl.pins_von.get(ref, []):
                    if not pl.ist_gnd(x['netz']):
                        f.setdefault(x['netz'], (v, f'Quarz {ref}'))
    return f


def rf_netze(pl):
    """Netz -> f_MHz fuer HF-Zuleitungen: Pinrolle 'rf' eines Funkmoduls, Netz an Koax-Buchse/Antenne."""
    out = {}
    fdef = None
    for ref, e in pl.dbe.items():
        if e and e.get('antenne'):
            fdef = e['antenne'].get('f_MHz')
            for x in pl.pins_von.get(ref, []):
                if pl.rolle(x) == 'rf':
                    out[x['netz']] = e['antenne'].get('f_MHz')
    for ref, t in pl.teile.items():
        fp = t.get('fp', '')
        if fp.startswith(('Connector_Coaxial', 'RF_Antenna')) or pl.art(ref) == 'AE':
            for x in pl.pins_von.get(ref, []):
                if not pl.ist_gnd(x['netz']) and fdef:
                    out.setdefault(x['netz'], fdef)
    return out


def pruefe_e13(pl):
    res = []
    for n, (f, wie) in sorted(netz_frequenzen(pl).items()):
        bs = pl.bahnen(n)
        if not bs:
            continue
        l = sum(t['l'] for t in bs)
        er = max((pl.h_ref.get(t['lage'], (1, 4.5, None))[1] for t in bs), default=4.5)
        lam = C0 / (f * math.sqrt(er))
        st = 'ok' if l <= lam / 8 else 'warnung'
        res.append(_e('E13', st, f'{n} ({wie}, {f:.4g} Hz): Bahnlaenge {l:.1f} mm vs. lambda/8 = {lam / 8:.0f} mm '
                      f'(eps_r {er} als obere Schranke)' + ('' if st == 'ok' else ' -> Z0-gefuehrt + Abschluss/Serien-R'),
                      wert=round(l, 1), grenze=round(lam / 8, 1), einheit='mm'))
    return _zusammen('E13', res, 'keine Netze mit bekannter Frequenz (I2C/USB/Funk/Quarz/soll.json frequenzen)')


def pruefe_e14(pl):
    res = []
    for n, fmhz in sorted(rf_netze(pl).items()):
        bs = pl.bahnen(n)
        if not bs:
            res.append(_e('E14', 'info', f'{n}: keine Bahn (Antenne direkt am Pin)'))
            continue
        l = sum(t['l'] for t in bs)
        h, er, nb = pl.h_ref.get(bs[0]['lage'], (1.5, 4.5, None))
        lam = C0 / (fmhz * 1e6 * math.sqrt(er))
        schlimm = None
        for t in bs:
            h, er, nb = pl.h_ref.get(t['lage'], (1.5, 4.5, None))
            z0, ee = microstrip_z0(t['w'], h, pl.cu_dicke.get(t['lage'], 0.035), er)
            gnd = pl.gnd_fuellung(nb) if nb else []
            bedeckt = all(in_flaeche(x, y, gnd) for x, y in _abtasten(t['a'], t['b'], 0.5)) if gnd else False
            if schlimm is None or abs(z0 - 50) > abs(schlimm[0] - 50):
                schlimm = (z0, t, bedeckt, h, er)
        z0, t, bedeckt, h, er = schlimm
        gamma = (z0 - 50) / (z0 + 50)
        hin = (f'{n} ({fmhz} MHz): Bahn {t["w"]:.2f} mm auf {t["lage"]}, h {h:.2f} mm, er {er}: Z0 = {z0:.0f} Ohm '
               f'(Hammerstad, Microstrip ohne Koplanar-Masse), Gamma = {gamma:.2f}, Laenge {l:.1f} mm = {l / lam:.3f} lambda')
        if l < lam / 20:
            st = 'ok'
            hin += ' -> elektrisch kurz (< lambda/20), Fehlanpassung unkritisch'
        else:
            st = 'ok' if abs(z0 - 50) <= 5 and bedeckt else 'warnung'
            if not bedeckt:
                hin += '; keine durchgehende GND-Flaeche darunter'
            if abs(z0 - 50) > 5:
                w50 = microstrip_breite(50, h, pl.cu_dicke.get(t['lage'], 0.035), er)
                hin += f'; 50 Ohm braeuchten w = {w50:.2f} mm (oder koplanar mit GND seitlich)'
        res.append(_e('E14', st, hin, wert=round(z0, 1), grenze=50, einheit='Ohm', daten={'netz': n, 'l_mm': l}))
    return _zusammen('E14', res, 'keine HF-Zuleitung (Funkmodul-RF-Pin/Koaxbuchse/Antenne) gefunden')


# --------------------------------------------------------------------------------------------- E15 Antenne

def _rechteck(h):
    (x0, y0), (x1, y1) = h
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def fp_nach_platine(f, x, y):
    """Punkt in Footprint-Koordinaten (mm, KiCad: y nach unten, unrotiert, Oberseite) -> Platinenkoordinaten.
    KiCad-Drehung positiv = gegen den Uhrzeigersinn auf dem Bildschirm; Unterseite spiegelt x. Die Richtung wird mit
    'kontrolle_pad' am echten Board gegengeprueft (pruefe_e15)."""
    if f.get('seite') == 'B':
        x = -x
    a = math.radians(f.get('rot', 0) or 0)
    return (f['pos'][0] + x * math.cos(a) + y * math.sin(a), f['pos'][1] - x * math.sin(a) + y * math.cos(a))


def _keepout_geometrie(pl, ref):
    """Pflicht-Sperrzone aus soll.json _projekt.elektronik.keepout[ref] oder bauteile.json antenne.keepout (dict):
    {"rechteck_mm": [x0, y0, x1, y1] (Footprint-Koordinaten), "kontrolle_pad": {"nr": "1", "pos_mm": [x, y]},
     "ueber_kante_erlaubt": true, "quelle": "Datenblatt S. .."}. True/fehlend -> None."""
    p = (((pl.ps or {}).get('elektronik') or {}).get('keepout') or {}).get(ref)
    if p is None:
        p = ((pl.dbe.get(ref) or {}).get('antenne') or {}).get('keepout')
    return p if isinstance(p, dict) and p.get('rechteck_mm') else None


def _keepout_abdeckung(pl, ref, geo, sperr):
    """(Anteil der Pflichtzone auf der Platine, der auf JEDER Kupferlage von Sperrflaechen abgedeckt ist, Text,
    Fehler der Transformationskontrolle oder None)."""
    f = next(b for b in pl.lay['bauteile'] if b['ref'] == ref)
    kp, kontrolle = geo.get('kontrolle_pad'), None
    if kp:
        pad = next((p for p in f['pads'] if str(p['nr']) == str(kp['nr'])), None)
        if pad is None:
            kontrolle = f'Kontrollpad {kp["nr"]} fehlt am Footprint'
        else:
            soll = fp_nach_platine(f, *kp['pos_mm'])
            d = math.dist(soll, pad['pos'])
            if d > 0.2:
                kontrolle = (f'Kontrollpad {kp["nr"]}: erwartet {soll[0]:.2f}/{soll[1]:.2f}, Board {pad["pos"][0]:.2f}/'
                             f'{pad["pos"][1]:.2f} mm ({d:.2f} mm daneben) - Footprint-Koordinaten oder Drehung pruefen')
    x0, y0, x1, y1 = geo['rechteck_mm']
    (bx0, by0), (bx1, by1) = pl.lay['rand']
    lagen = [l for l in pl.lay.get('lagen', ['F.Cu', 'B.Cu']) if l.endswith('.Cu')]
    n = 24
    innen = gedeckt = 0
    for i in range(n + 1):
        for j in range(n + 1):
            px, py = fp_nach_platine(f, x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * j / n)
            if not (bx0 <= px <= bx1 and by0 <= py <= by1):
                if not geo.get('ueber_kante_erlaubt', True):
                    innen += 1      # ausserhalb der Platine ist nicht erlaubt -> zaehlt als nicht gedeckt
                continue
            innen += 1
            if all(any(lage in z['lagen'] and in_flaeche(px, py, [{'aussen': p['aussen'], 'loecher': p['loecher']}])
                       for z in sperr for p in z['umriss']) for lage in lagen):
                gedeckt += 1
    anteil = gedeckt / innen if innen else 1.0
    return anteil, f'Pflicht-Sperrzone ({geo.get("quelle", "Quelle fehlt")}) zu {anteil * 100:.0f} % auf allen ' \
                   f'Kupferlagen ({", ".join(lagen)}) abgedeckt', kontrolle


def pruefe_e15(pl):
    if pl.ohne_kicad:
        fm = [m for m in pl.module if m.get('funk')]
        if not fm:
            return [_u('E15', 'Kaufmodul ohne Funk (elektronik.module[].funk)')]
        return [_e('E15', 'warnung', ', '.join(m.get('name', 'Modul') for m in fm) + ': Antennen-Keepout liegt beim '
                   'Modulhersteller (keine KiCad-Daten); Metall im Gehaeuse (Akku, Display, Schrauben, Inserts) im Radius '
                   'lambda/10 um die Antenne ist nicht geprueft -> hoechstens warnung')]
    res = []
    ant = [ref for ref, e in pl.dbe.items() if e and (e.get('antenne') or {}).get('keepout')]
    ant += [ref for ref, t in pl.teile.items() if (t.get('fp', '').startswith('RF_Antenna') or pl.art(ref) == 'AE')
            and ref not in ant]
    for ref in ant:
        if ref not in pl.bt:
            continue
        hull = _rechteck(pl.bt[ref]['huelle'])
        sperr = [z for z in pl.lay['zonen'] if z['regel'] and z.get('kein_kupfer')
                 and any(flaechen_ueberlapp(hull, z['umriss']) or flaechen_ueberlapp(p['aussen'], [{'aussen': hull, 'loecher': []}])
                         for p in z['umriss'])]
        if not sperr:
            res.append(_e('E15', 'warnung', f'{ref}: keine Sperrflaeche (Keepout, kein Kupfer) am Antennenbereich - '
                          'Masse unter der Antenne loescht die Abstrahlung; Bereich aus dem Datenblatt als Sperrflaeche anlegen'))
            continue
        treffer = []
        for z in sperr:
            for p in z['umriss']:
                umr = [{'aussen': p['aussen'], 'loecher': p['loecher']}]
                for lage in z['lagen']:
                    for zz in pl.lay['zonen']:
                        if zz['regel']:
                            continue
                        f = zz.get('flaechen', {}).get(lage, [])
                        if f and flaechen_ueberlapp(p['aussen'], f):
                            treffer.append(f'Zone {zz["netz"]} auf {lage}')
                    for t in pl.bahnen():
                        if t['lage'] == lage and any(in_flaeche(x, y, umr) for x, y in _abtasten(t['a'], t['b'], 0.25)):
                            treffer.append(f'Bahn {t["netz"]} auf {lage}')
                    for v in pl.vias():
                        if in_flaeche(v['pos'][0], v['pos'][1], umr):
                            treffer.append(f'Via {v["netz"]}')
                    for f in pl.lay['bauteile']:
                        if f['ref'] == ref:
                            continue
                        for pd in f['pads']:
                            if lage in pd['lagen'] and any(in_flaeche(x, y, umr) and _rand_abst((x, y), p['aussen']) > 0.05
                                                           for x, y in _pad_ecken(pd)):
                                treffer.append(f'Pad {f["ref"]}.{pd["nr"]} auf {lage}')
        treffer = sorted(set(treffer))
        (bx0, by0), (bx1, by1) = pl.lay['rand']
        st = 'fehler' if treffer else 'ok'
        hin = (f'{ref}: {len(sperr)} Sperrflaeche(n) am Antennenbereich, ' +
               ('Kupfer darin: ' + ', '.join(treffer[:12]) if treffer else 'kein Kupfer darin')
               + '; Metall im Gehaeuse >= lambda/10 Abstand nicht geprueft (Gehaeuse-3D)')
        # Groesse und Lage (seit 19.11.2026): ohne Pflichtzone aus dem Datenblatt hoechstens warnung
        geo = _keepout_geometrie(pl, ref)
        if geo is None:
            if st == 'ok':
                st = 'warnung'
            hin += ('; Groesse/Lage der Sperrflaeche NICHT geprueft: Pflichtzone fehlt (antenne.keepout.rechteck_mm in '
                    'bauteile.json oder _projekt.elektronik.keepout aus dem Datenblatt)')
        else:
            anteil, txt, kontrolle = _keepout_abdeckung(pl, ref, geo, sperr)
            hin += '; ' + txt
            if kontrolle:
                st = 'fehler'
                hin += '; ' + kontrolle
            elif anteil < 0.999:
                st = 'fehler'
                hin += ' - Sperrflaeche vergroessern/verschieben, bis die Pflichtzone voll abgedeckt ist'
            if not geo.get('quelle') and st == 'ok':
                st = 'warnung'
        geh = pl.gehaeuse_da()
        if st == 'ok' and geh:
            st = 'warnung'
            hin += (f' -> hoechstens warnung: Gehaeuse/Platinen-3D liegt vor ({geh}), Akku, Display, Schrauben, Inserts '
                    'im Radius lambda/10 um die Antenne sind ungeprueft')
        res.append(_e('E15', st, hin, wert=len(treffer), grenze=0, einheit='Treffer', daten={'ref': ref, 'treffer': treffer}))
    return _zusammen('E15', res, 'keine Antenne/kein Funkmodul mit Antennen-Keepout in der DB')


# --------------------------------------------------------------------------------------------- E16 Link-Budget

# Ausbreitungsexponent n (log-distance, Bezug 1 m Freiraum). Freiraum allein (n = 2) unterschaetzt jede Strecke
# am Boden drastisch. 'dorf' = bebaut, keine Sichtlinie: n = 3,5, kalibriert an Bodenklima 15.11.2026 (868 MHz, 830 m
# durchs Dorf, gemessen ~ -134 dBm bei 14 dBm, Freiraum haette -103 dBm versprochen). Literatur: suburban 2,7-3,5,
# abgeschattet/urban 3-5 (Rappaport, Wireless Communications, Tab. 4.2).
FUNK_UMGEBUNG_N = {'frei': 2.0, 'sicht': 2.5, 'land': 3.0, 'dorf': 3.5, 'stadt': 4.0, 'innen': 4.0}
# Einzelverluste in dB (Mittelwerte bei 868 MHz; nass eher mehr)
FUNK_HINDERNIS_DB = {'holz': 3, 'ziegel_dach': 8, 'ziegel_nass': 15, 'mauer': 10, 'beton': 15, 'glas': 3,
                     'metallisiertes_glas': 25, 'baeume': 6, 'alu_gehaeuse_antenne_innen': 30}
FUNK_KABEL_DB_PRO_M = {'rg174': 1.0, 'rg316': 0.9, 'rg58': 0.5, 'h155': 0.25, 'lmr195': 0.35, 'lmr400': 0.13,
                       'ecoflex10': 0.15}
FUNK_RESERVE_DB = 10      # Fading/Wetter/Laub/Alterung: darunter Warnung, unter 0 Fehler


def funk_im_entwurf(pl):
    """True, wenn die Platine erkennbar funkt (Funkmodul mit Antennenangabe, HF-Netz, Koax-/Antennen-Footprint)."""
    return (bool(rf_netze(pl)) or any(e and e.get('antenne') for e in pl.dbe.values())
            or any(m.get('funk') for m in getattr(pl, 'module', [])))


def pruefe_e16(pl):
    fu = pl.el.get('funk')
    if not fu or not fu.get('r_m'):
        if funk_im_entwurf(pl):
            return [_e('E16', 'fehler', 'Platine funkt, aber soll.json elektronik.funk fehlt: Linkbudget ist Pflicht '
                       '{r_m, umgebung, hindernisse, kabel, P_t_dBm, P_rx_min_dBm, G_t_dBi, G_r_dBi}')]
        return [_u('E16', 'kein Funk im Entwurf und soll.json elektronik.funk fehlt')]
    fmhz = fu.get('f_MHz') or next(iter(rf_netze(pl).values()), None) or next(
        ((e.get('antenne') or {}).get('f_MHz') for e in pl.dbe.values() if e and e.get('antenne')), None) or next(
        (m.get('f_MHz') for m in pl.module if m.get('funk') and m.get('f_MHz')), None)
    if not fmhz or fu.get('P_t_dBm') is None or fu.get('P_rx_min_dBm') is None:
        return [_e('E16', 'fehler', 'Linkbudget unvollstaendig: Frequenz, P_t_dBm oder P_rx_min_dBm fehlt')]
    lam = 299.792458 / fmhz
    r = max(float(fu['r_m']), 1.0)
    umg = fu.get('umgebung')
    annahmen = []
    if umg not in FUNK_UMGEBUNG_N:
        annahmen.append(f'umgebung {umg!r} unbekannt/fehlt -> "dorf" angenommen ({"/".join(FUNK_UMGEBUNG_N)})')
        umg = 'dorf'
    n = FUNK_UMGEBUNG_N[umg]
    pl_1m = 20 * math.log10(4 * math.pi / lam)
    pfad = pl_1m + 10 * n * math.log10(r)
    fspl = 20 * math.log10(4 * math.pi * r / lam)
    hind = 0.0
    for h in fu.get('hindernisse', []):
        if isinstance(h, (int, float)):
            hind += h
        elif h in FUNK_HINDERNIS_DB:
            hind += FUNK_HINDERNIS_DB[h]
        else:
            annahmen.append(f'Hindernis {h!r} unbekannt -> 10 dB')
            hind += 10
    kabel = 0.0
    for k in fu.get('kabel', []):            # [{"typ": "rg174", "m": 3}, ...]
        dbm = FUNK_KABEL_DB_PRO_M.get(str(k.get('typ', '')).lower())
        if dbm is None:
            annahmen.append(f'Kabel {k.get("typ")!r} unbekannt -> 1 dB/m')
            dbm = 1.0
        kabel += dbm * float(k.get('m', 0)) + 0.3   # + Steckerpaar
    antenne = 0.0
    if fu.get('magnetfuss_ohne_blech'):
        antenne += 4
    if fu.get('polarisation_gekreuzt'):
        antenne += 15
    for g in ('G_t_dBi', 'G_r_dBi'):
        if fu.get(g) is None:
            annahmen.append(f'{g} fehlt -> 0 dBi angenommen (kleine 868-MHz-Antennen oft darunter)')
    prx = (fu['P_t_dBm'] + (fu.get('G_t_dBi') or 0) + (fu.get('G_r_dBi') or 0) - pfad - hind - kabel - antenne
           - fu.get('verluste_dB', 0))
    m = prx - fu['P_rx_min_dBm']
    st = 'fehler' if m < 0 else ('warnung' if m < FUNK_RESERVE_DB else 'ok')
    if annahmen and st == 'ok':
        st = 'warnung'
    hin = (f'{fmhz} MHz, {r:.0f} m, Umgebung {umg} (n = {n}): Pfad {pfad:.1f} dB (Freiraum waere {fspl:.1f} dB), '
           f'Hindernisse {hind:.0f} dB, Kabel {kabel:.1f} dB, Antenne {antenne:.0f} dB -> P_rx = {prx:.1f} dBm, '
           f'Reserve {m:.1f} dB (Ziel >= {FUNK_RESERVE_DB} dB)')
    if annahmen:
        hin += '; Annahmen: ' + '; '.join(annahmen)
    return [_e('E16', st, hin, wert=round(m, 1), grenze=FUNK_RESERVE_DB, einheit='dB',
               daten={'pfad_dB': round(pfad, 1), 'freiraum_dB': round(fspl, 1), 'n': n, 'hindernisse_dB': hind,
                      'kabel_dB': round(kabel, 1), 'antenne_dB': antenne, 'P_rx_dBm': round(prx, 1)})]


# --------------------------------------------------------------------------------------------- E17 Rueckstrom

def schnelle_netze(pl):
    f = netz_frequenzen(pl)
    out = {n for n, (v, _) in f.items() if v >= 1e6 and not pl.ist_gnd(n)}
    for n in pl.netze:
        if re.search(r'SCK|SCLK|CLK|BCLK|LRCLK|MCLK|I2S|USB_D|^/?D[PN]$', n.upper()) and not pl.ist_gnd(n):
            out.add(n)
    return out


def pruefe_e17(pl):
    if pl.lay['kupferlagen'] < 2:
        return [_u('E17', 'einlagige Platine')]
    if not any(not pl.ist_gnd(t['netz']) for t in pl.bahnen()):
        return [_u('E17', 'keine Signalbahnen auf der Platine (noch nicht geroutet?)')]
    if not any(not z['regel'] and pl.ist_gnd(z['netz']) for z in pl.lay['zonen']):
        return [_e('E17', 'warnung', 'keine GND-Flaeche auf der Platine - Rueckstrom laeuft ueber Bahnen (grosse Schleifen)')]
    schnell = schnelle_netze(pl)
    res = []
    for n in sorted(schnell):
        bs = pl.bahnen(n)
        if not bs:
            continue
        tot = 0.0
        frei = 0.0
        for t in bs:
            h, er, nb = pl.h_ref.get(t['lage'], (1.5, 4.5, None))
            gnd = pl.gnd_fuellung(nb) if nb else []
            pts = _abtasten(t['a'], t['b'], 0.5)
            seg = t['l'] / max(1, len(pts))
            for x, y in pts:
                tot += seg
                if not in_flaeche(x, y, gnd):
                    frei += seg
        anteil = 100 * (1 - frei / tot) if tot else 100
        st = 'ok' if anteil >= 99.5 else 'warnung'
        h = pl.h_ref.get(bs[0]['lage'], (1.5, 4.5, None))[0]
        res.append(_e('E17', st, f'{n}: {anteil:.0f} % der Bahnlaenge ueber GND der Nachbarlage, {frei:.1f} mm ohne '
                      f'Bezugsflaeche (L ~ mu0*h*l/w, h {h:.2f} mm)', wert=round(anteil, 1), grenze=100, einheit='%'))
    return _zusammen('E17', res, 'keine schnellen Netze (>= 1 MHz, Takt/USB/I2S/SW/HF) mit Bahnen')


# --------------------------------------------------------------------------------------------- E18 Uebersprechen

def _ist_schiene(pl, n):
    """Versorgungsschiene (feste Spannung, kein Logiknetz) - als 'Opfer' von Uebersprechen wechselstrommaessig Masse."""
    return n in pl.V and pl.V[n][1] > 0   # Logiknetze stehen nie in pl.V (nur in _netzbereich)


def pruefe_e18(pl):
    res = []
    schnell = schnelle_netze(pl)
    alle = pl.bahnen()
    gitter = {}
    for i, t in enumerate(alle):
        for x, y in (t['a'], t['b']):
            gitter.setdefault((t['lage'], int(x // 5), int(y // 5)), set()).add(i)
    for n in sorted(schnell):
        kopp = {}
        for t in pl.bahnen(n):
            ax, ay = t['b'][0] - t['a'][0], t['b'][1] - t['a'][1]
            la = math.hypot(ax, ay)
            if la < 0.5:
                continue
            ux, uy = ax / la, ay / la
            kand = set()
            for x, y in _abtasten(t['a'], t['b'], 4):
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        kand |= gitter.get((t['lage'], int(x // 5) + dx, int(y // 5) + dy), set())
            for j in kand:
                o = alle[j]
                if o['netz'] == n or pl.ist_gnd(o['netz']) or o['lage'] != t['lage'] or _ist_schiene(pl, o['netz']):
                    continue
                bx, by = o['b'][0] - o['a'][0], o['b'][1] - o['a'][1]
                lb = math.hypot(bx, by)
                if lb < 0.5 or abs(ux * by - uy * bx) / lb > 0.17:   # > 10 Grad nicht parallel
                    continue
                d = abs((o['a'][0] - t['a'][0]) * uy - (o['a'][1] - t['a'][1]) * ux)
                spalt = d - t['w'] / 2 - o['w'] / 2
                if spalt > 2 * max(t['w'], o['w']) or spalt <= 0:
                    continue
                s0 = (o['a'][0] - t['a'][0]) * ux + (o['a'][1] - t['a'][1]) * uy
                s1 = (o['b'][0] - t['a'][0]) * ux + (o['b'][1] - t['a'][1]) * uy
                ueber = max(0.0, min(la, max(s0, s1)) - max(0.0, min(s0, s1)))
                if ueber <= 0:
                    continue
                k = kopp.setdefault(o['netz'], [0.0, spalt])
                k[0] += ueber
                k[1] = min(k[1], spalt)
        for opfer, (l, spalt) in sorted(kopp.items(), key=lambda kv: -kv[1][0]):
            er = 4.5
            tcu = 0.035
            C = EPS0 * er * tcu * l / spalt
            st = 'warnung' if l > 10 else 'ok'
            res.append(_e('E18', st, f'{n} -> {opfer}: {l:.1f} mm parallel, Spalt {spalt:.2f} mm, C_m >= eps*t*l/d = '
                          f'{C * 1e15:.1f} fF (Seitenwand, Streufeld nicht gerechnet)', wert=round(l, 1), grenze=10, einheit='mm'))
    # Serien-R an schnellen MCU-Ausgaengen (nicht an Debug-Eingaengen SWD/JTAG, die der Programmer treibt)
    for n in sorted(schnell):
        if re.search(r'SWCLK|SWDIO|TCK|TMS|JTAG', n.upper()):
            continue
        for x in pl.netze.get(n, []):
            if (pl.dbe.get(x['ref']) or {}).get('typ') == 'mcu' and x.get('typ') in ('output', 'bidirectional'):
                rs = [(r, pl.wert(r, 'R')) for r, o in pl.zweipole(n, 'R') if not pl.ist_gnd(o) and o not in pl.V]
                ok = [r for r, v in rs if v is not None and 15 <= v <= 100]
                st = 'ok' if ok else 'warnung'
                res.append(_e('E18', st, f'{n} an {x["ref"]}.{x["name"]}: Serien-R ' + (', '.join(ok) if ok else
                              'fehlt (22-33 Ohm bremst die Flanke)'), daten={'netz': n}))
    return _zusammen('E18', res, 'keine schnellen Netze mit benachbarten Bahnen')


# --------------------------------------------------------------------------------------------- E19 EMI-Filter

def pruefe_e19(pl):
    res = []
    for ref, e in pl.dbe.items():
        if not e or e.get('typ') not in ('buck', 'boost', 'buckboost'):
            continue
        for x in [x for x in pl.pins_von[ref] if pl.rolle(x) == 'vin']:
            fil = [(l, o) for art in ('L', 'FB') for l, o in pl.zweipole(x['netz'], art)
                   if not any(pl.rolle(y) == 'sw' for y in pl.netze.get(o, []))]
            if not fil:
                res.append(_e('E19', 'info', f'{ref}.{x["name"]}: kein LC-Eingangsfilter (nur noetig bei empfindlicher Quelle/Leitung)'))
                continue
            for l, o in fil:
                L = pl.wert(l, 'L')
                Cs = [pl.wert(c, 'C') for c, g in pl.zweipole(x['netz'], 'C') if pl.ist_gnd(g)]
                if L is None or not Cs or not all(Cs) or not e.get('f_sw_Hz'):
                    res.append(_e('E19', 'uebersprungen', f'{ref}: Filter {l} - L (Ferrit ohne L-Wert?), C oder f_sw unbekannt'))
                    continue
                C = sum(Cs)
                f0 = 1 / (2 * math.pi * math.sqrt(L * C))
                st = 'ok' if f0 <= e['f_sw_Hz'] / 10 else 'warnung'
                res.append(_e('E19', st, f'{ref}: Filter {l} {L * 1e6:.2f} uH + {C * 1e6:.1f} uF -> f0 = {f0 / 1e3:.1f} kHz vs. '
                              f'f_sw/10 = {e["f_sw_Hz"] / 10e3:.0f} kHz', wert=round(f0, 0), grenze=e['f_sw_Hz'] / 10, einheit='Hz'))
    return _zusammen('E19', res, 'kein Schaltregler in der DB')


# --------------------------------------------------------------------------------------------- E20 Verstaerker

def pruefe_e20(pl):
    res = []
    for ref, e in pl.dbe.items():
        if not e or e.get('typ') != 'verstaerker_btl':
            continue
        vn = [x['netz'] for x in pl.pins_von.get(ref, []) if pl.rolle(x) == 'vdd']
        if not vn or vn[0] not in pl.V:
            res.append(_e('E20', 'uebersprungen', f'{ref}: Versorgung unbekannt'))
            continue
        vdd = pl.V[vn[0]][1]
        rl = pl.el.get('lautsprecher_Ohm')
        rmin = e.get('R_L_min_Ohm')
        if not rl:
            if rmin:
                ip = vdd / rmin
                res.append(_e('E20', 'uebersprungen', f'{ref}: Lautsprecherimpedanz fehlt (soll.json elektronik.lautsprecher_Ohm); '
                              f'schlimmster Fall R_L,min {rmin} Ohm: P = V^2/(2R) = {vdd ** 2 / (2 * rmin):.2f} W, '
                              f'I_peak = V/R = {ip:.2f} A an {vn[0]} (fuer E2/E8 als Symbolfeld Strom eintragen)',
                              wert=round(ip, 3), einheit='A'))
            continue
        P = vdd ** 2 / (2 * rl)
        ip = vdd / rl                     # BTL: Amplitude V_DD am Lastwiderstand (passt zu P = V^2/2R, Befund E3)
        st = 'ok' if not rmin or rl >= rmin else 'fehler'
        res.append(_e('E20', st, f'{ref}: R_L {rl} Ohm (min {rmin}), V_DD {vdd:.2f} V -> P = {P:.2f} W, I_peak = {ip:.2f} A an {vn[0]}',
                      wert=rl, grenze=rmin, einheit='Ohm', daten={'I_peak_A': ip}))
    return _zusammen('E20', res, 'kein Verstaerker in der DB')


# --------------------------------------------------------------------------------------------- E21 LiPo-Ladestrom

def _ladestrom(pl, ref, e):
    if not e.get('K_prog_AOhm'):
        return None
    for x in pl.pins_von.get(ref, []):
        nm = re.sub(r'[~{}]', '', x.get('name') or '').upper()
        if nm in [p.upper() for p in e.get('prog_pins', [])]:
            r = pl.r_gegen_masse(x['netz'])
            if r:
                return e['K_prog_AOhm'] / r, r, x['netz']
    return None


TS_PIN_RE = re.compile(r'^(TS|NTC|TEMP|THERM|TH|TS[-/_]?CTRL)$')


def _ntc_am_lader(pl, ref):
    """('ja'|'pack'|'nein', text): NTC am TS/NTC/TEMP-Pin des Laders. 'pack' = Netz geht an einen Stecker (NTC im
    Akkupack, am Bauteil nicht pruefbar)."""
    ts = [x for x in pl.pins_von.get(ref, []) if pl.rolle(x) == 'ts'
          or TS_PIN_RE.match(re.sub(r'[~{}]', '', x.get('name') or '').upper())]
    if not ts:
        return 'nein', f'{ref}: kein TS/NTC-Pin in der Netzliste (Lader ohne Temperaturfuehler)'
    for x in ts:
        n = x['netz']
        if pl.ist_gnd(n):
            return 'nein', f'{ref}.{x["name"]} liegt an {n} (Temperaturueberwachung abgeschaltet)'
        for y in pl.netze.get(n, []):
            r = y['ref']
            if r == ref:
                continue
            t = pl.teile.get(r, {})
            kenn = (t.get('wert', '') + ' ' + t.get('fp', '')).upper()
            if re.match(r'(TH|RT|NTC)\d', r) or 'NTC' in kenn or 'THERMISTOR' in kenn:
                return 'ja', f'NTC {r} ({t.get("wert", "")}) an {ref}.{x["name"]}'
        for y in pl.netze.get(n, []):
            if re.match(r'(J|CN|P|X|BT)\d', y['ref']):
                return 'pack', f'{ref}.{x["name"]} geht an Stecker {y["ref"]} (NTC im Akkupack angenommen, am Bauteil pruefen)'
    return 'nein', f'{ref}.{ts[0]["name"]} ({ts[0]["netz"]}) ohne Thermistor (nur Festwiderstand/offen)'


def _e21_bewerten(pl, kopf, I, mah, ntc, ntc_txt, daten):
    """C-Rate + Temperatur: ok bis 0,5 C, 0,5-1 C warnung, > 1 C fehler. Bei T_min_C < 10 oder aussen ist ein NTC am
    TS-Pin Pflicht (Laden unter 0 C unzulaessig, 0-10 C nur <= 0,5 C, JEITA), sonst fehler."""
    crate = I / (mah * 1e-3)
    st = 'ok' if crate <= 0.5 else ('warnung' if crate <= 1.0 else 'fehler')
    hin = kopf + f' = {crate:.2f} C bei {mah:.0f} mAh (ok <= 0,5 C, Grenze 1 C)'
    if st == 'warnung':
        hin += '; 0,5-1 C: Lebensdauer leidet, nur mit Zellendatenblatt (Standardladung meist 0,5 C)'
    k = pl.kontext()
    Tmin, aussen = k.get('T_min_C'), k.get('aussen')
    kalt = (Tmin is not None and Tmin < 10) or bool(aussen)
    wo = (f'T_min {Tmin:g} C' if Tmin is not None and Tmin < 10 else '') + (' aussen' if aussen else '')
    hin += '; ' + ntc_txt
    if kalt:
        if ntc == 'nein':
            st = 'fehler'
            hin += (f'; {wo.strip()}: NTC am TS-Pin ist Pflicht (Laden unter 0 C unzulaessig, 0-10 C nur <= 0,5 C, '
                    'JEITA/Zellendatenblatt)')
        elif ntc == 'pack':
            st = rt.deckel(st, True)
        if crate > 0.5 and st == 'ok':
            st = 'warnung'
    elif Tmin is None and aussen is None and ntc != 'ja':
        if st == 'ok':
            st = 'warnung'
        hin += '; Einsatztemperatur unbekannt (soll.json T_min_C/aussen) und kein NTC -> hoechstens warnung'
    elif ntc == 'pack':
        st = rt.deckel(st, True)
    daten = dict(daten, ntc=ntc, kalt=kalt)
    return _e('E21', st, hin, wert=round(crate, 3), grenze=0.5, einheit='C', daten=daten)


PRIMAERZELLEN = ('li_fes2', 'alkali')


def pruefe_e21(pl):
    if pl.akku_chemie() in PRIMAERZELLEN:
        return [_e('E21', 'info', f'Primaerzelle ({pl.akku_chemie()}): kein Laden vorgesehen - Ladestrom nicht relevant')]
    if pl.ohne_kicad:
        ich = pl.modul_wert('I_chg_mA')
        mah = (pl.akku or {}).get('mAh')
        if not pl.akku:
            return [_u('E21', 'Kaufmodul ohne Akku (elektronik.module[].akku_mAh bzw. _projekt.akku_mAh fehlt)')]
        if ich is None or not mah:
            return [_u('E21', 'Kaufmodul: Ladestrom fehlt (elektronik.module[].I_chg_mA, laut Moduldoku/Ladewiderstand)')]
        n = pl.modul_wert('ntc')
        ntc, txt = (('ja', 'NTC am Lader laut soll.json') if n else
                    ('nein', 'kein NTC am Lader (soll.json module[].ntc false)') if n is False else
                    ('nein', 'NTC am Lader unbekannt (module[].ntc fehlt) -> wie ohne NTC'))
        return [_e21_bewerten(pl, f'Kaufmodul: I_chg {float(ich):.0f} mA (soll.json)', float(ich) * 1e-3, mah, ntc, txt,
                              {'I_A': float(ich) * 1e-3})]
    res = []
    for ref, e in pl.dbe.items():
        if not e or e.get('typ') not in ('lader_linear', 'qi_lader'):
            continue
        r = _ladestrom(pl, ref, e)
        if not r:
            res.append(_e('E21', 'uebersprungen', f'{ref}: Programmierwiderstand nach GND nicht gefunden'))
            continue
        I, R, n = r
        mah = (pl.akku or {}).get('mAh') or pl.ps.get('akku_mAh')
        hin = f'{ref}: I_chg = K {e["K_prog_AOhm"]} A*Ohm / R {R:.0f} Ohm ({n} nach GND) = {I * 1e3:.0f} mA'
        if e.get('I_chg_max_A') and I > e['I_chg_max_A']:
            res.append(_e('E21', 'fehler', hin + f' > Bauteilgrenze {e["I_chg_max_A"]} A', wert=round(I, 4), einheit='A'))
            continue
        if not mah:
            res.append(ergebnis('E21', TITEL['E21'], 'uebersprungen', wert=round(I, 4), einheit='A', quelle=Q['E21'],
                                hinweis=hin + '; Akkukapazitaet fehlt (soll.json _projekt.akku_mAh)'))
            continue
        ntc, txt = _ntc_am_lader(pl, ref)
        res.append(_e21_bewerten(pl, hin, I, mah, ntc, txt, {'I_A': I, 'R_Ohm': R}))
    return _zusammen('E21', res, 'kein LiPo-Lader in der DB')


# --------------------------------------------------------------------------------------------- E22 Qi

def pruefe_e22(pl):
    res = []
    for ref, e in pl.dbe.items():
        if not e or not e.get('qi_f_s_Hz'):
            continue
        ac = [x['netz'] for x in pl.pins_von.get(ref, []) if pl.rolle(x) == 'ac']
        if len(set(ac)) != 2:
            continue
        a1, a2 = sorted(set(ac))
        # Serien-C: Kondensatoren zwischen einem AC-Netz und einem Netz, das kein AC-Netz ist (Spulenseite)
        reihen = {}
        dual = []
        for a in (a1, a2):
            for c, o in pl.zweipole(a, 'C'):
                if o in (a1, a2):
                    dual.append(c)
                elif not pl.ist_gnd(o) and not any(pl.rolle(y) for y in pl.netze.get(o, []) if pl.art(y['ref']) == 'U'):
                    reihen.setdefault((a, o), []).append(c)
        if not reihen:
            res.append(_e('E22', 'uebersprungen', f'{ref}: Serienresonanz-C nicht erkannt'))
            continue
        (an, spn), cs = max(reihen.items(), key=lambda kv: len(kv[1]))
        werte = [(c, pl.wert(c, 'C')) for c in cs]
        offen = [c for c, v in werte if v is None]
        Cs = sum(v for c, v in werte if v)
        Cd = sum(pl.wert(c, 'C') or 0 for c in set(dual))
        L = pl.el.get('qi_spule_uH')
        f0 = e['qi_f_s_Hz']
        delta = math.sqrt(RHO_CU * 1e-3 / (math.pi * 150e3 * 4e-7 * math.pi)) * 1e3
        if not L:
            Lsoll = 1 / ((2 * math.pi * f0) ** 2 * Cs) * 1e6
            res.append(_e('E22', 'uebersprungen', f'{ref}: C_s = {Cs * 1e9:.1f} nF ({", ".join(cs)}) braucht L = {Lsoll:.2f} uH '
                          f'fuer {f0 / 1e3:.0f} kHz; Spuleninduktivitaet fehlt (soll.json elektronik.qi_spule_uH)'
                          + (f'; unbestueckt/ohne Wert: {", ".join(offen)}' if offen else ''), wert=round(Lsoll, 3), einheit='uH'))
            continue
        Lh = L * 1e-6
        fs = 1 / (2 * math.pi * math.sqrt(Lh * Cs))
        abw = (fs - f0) / f0 * 100
        st = 'ok' if abs(abw) <= 5 else 'warnung'
        hin = (f'{ref}: L {L} uH, C_s = {Cs * 1e9:.1f} nF ({", ".join(cs)}) -> f_s = 1/(2 pi sqrt(LC)) = {fs / 1e3:.1f} kHz, '
               f'{abw:+.1f} % von {f0 / 1e3:.0f} kHz (Band +-5 %)')
        if abs(abw) > 5:
            c_soll = 1 / ((2 * math.pi * f0) ** 2 * Lh)
            hin += f'; fuer {f0 / 1e3:.0f} kHz braucht es C_s = {c_soll * 1e9:.1f} nF ({(c_soll - Cs) * 1e9:+.1f} nF'
            hin += (f', z. B. ueber {", ".join(offen)})' if offen else ')')
        if Cd:
            fd = 1 / (2 * math.pi * math.sqrt(Lh * Cd))
            hin += f'; Parallelresonanz C_d {Cd * 1e9:.2f} nF -> f_d = {fd / 1e6:.2f} MHz (Soll 1 MHz +-10 %, mit L statt L\')'
            if abs(fd - 1e6) > 0.1e6:
                st = 'warnung'
        hin += f'; Skintiefe Cu bei 150 kHz {delta:.2f} mm (Litze unter {2 * delta:.2f} mm Ader)'
        res.append(_e('E22', st, hin, wert=round(abw, 2), grenze=5.0, einheit='%', daten={'f_s_Hz': fs, 'C_s_F': Cs}))
    return _zusammen('E22', res, 'kein Qi-Empfaenger in der DB')


# --------------------------------------------------------------------------------------------- E23-E25

def pruefe_e23(pl):
    res = []
    for ref, e in pl.dbe.items():
        if not e or e.get('typ') not in ('nmos', 'pmos'):
            continue
        g = [x for x in pl.pins_von.get(ref, []) if pl.rolle(x) == 'gate']
        if not g:
            continue
        gn = g[0]['netz']
        quelle = None
        for x in pl.netze.get(gn, []):
            if x['ref'] != ref and x.get('typ') in ('output', 'bidirectional', 'open_collector') and pl.vdd(x['ref']):
                quelle = (x['ref'], pl.vdd(x['ref']))
        if quelle is None:
            for r, o in pl.zweipole(gn, 'R'):
                if o in pl.V and not pl.ist_gnd(o):
                    quelle = (r, pl.V[o])
        if quelle is None:
            continue
        vg = quelle[1][0]
        src = [x['netz'] for x in pl.pins_von[ref] if pl.rolle(x) == 'source']
        vs = 0.0
        if src and src[0] in pl.V:
            # unguenstigster Fall (Befund E1): pmos kleinste Source-Spannung (Gate auf 0 V), nmos groesste
            vs = pl.V[src[0]][0] if e['typ'] == 'pmos' else pl.V[src[0]][1]
        vgs = abs(vg - vs) if e['typ'] == 'nmos' else abs(vs)   # pmos: Gate auf 0 V gezogen
        rds = e.get('R_DS_on_Ohm') or {}
        spez = min((float(k) for k in rds), default=None)
        th = e.get('V_GS_th_max_V')
        hin = f'{ref}: V_GS,min = {vgs:.2f} V (Gate von {quelle[0]})'
        if th and vgs < th:
            st = 'fehler'
            hin += f' < V_GS(th),max {th} V - schaltet nicht sicher ein'
        elif spez and vgs < spez:
            st = 'warnung'
            hin += f' < {spez} V (kleinste V_GS mit spezifiziertem R_DS(on)) - R_DS(on) unspezifiziert hoeher'
            if 'Schutz-IC' in ' '.join(pl.V_her.values()):
                hin += ' (tritt erst kurz vor der Unterspannungsabschaltung auf; dort P = I^2*R_DS(on) gegenpruefen)'
        else:
            st = 'ok'
            if spez:
                hin += f' >= {spez} V (R_DS(on) {rds[str(spez) if str(spez) in rds else next(iter(rds))] * 1e3:.0f} mOhm spezifiziert)'
        f = None
        for kk, vv in pl.teile[ref].get('felder', {}).items():
            if kk.lower() in ('f_pwm', 'pwm_hz'):
                f = wert_si(re.sub(r'\s*Hz\s*$', '', vv), 'f')
        if f and e.get('Q_g_C'):
            hin += f'; P_gate = Q_g*V*f = {e["Q_g_C"] * vgs * f * 1e3:.2f} mW'
        res.append(_e('E23', st, hin, wert=round(vgs, 3), grenze=spez or th, einheit='V', daten={'ref': ref}))
    return _zusammen('E23', res, 'kein MOSFET mit bekannter Gate-Ansteuerung')


def pruefe_e24(pl):
    z = [ref for ref, e in pl.dbe.items() if e and e.get('typ') == 'zener']
    if not z:
        return [_u('E24', 'kein Zener-Regler (DB-Typ zener) auf der Platine')]
    res = []
    for ref in z:
        e = pl.dbe[ref]
        k = [x['netz'] for x in pl.pins_von[ref] if (x.get('name') or '').upper() in ('K', 'KATHODE')]
        if not k:
            continue
        rs = [(r, pl.wert(r, 'R'), o) for r, o in pl.zweipole(k[0], 'R') if o in pl.V]
        if not rs or not e.get('V_z_V') or not e.get('I_z_min_A'):
            res.append(_e('E24', 'uebersprungen', f'{ref}: Vorwiderstand/V_z/I_z,min unbekannt'))
            continue
        r, R, o = rs[0]
        il = pl.I.get(k[0], 0)
        iz = (pl.V[o][0] - e['V_z_V']) / R - il
        st = 'ok' if iz >= e['I_z_min_A'] else 'fehler'
        res.append(_e('E24', st, f'{ref}: I_Z,min = (V_in,min - V_Z)/R - I_L = {iz * 1e3:.2f} mA (min {e["I_z_min_A"] * 1e3:.2f})',
                      wert=round(iz, 5), grenze=e['I_z_min_A'], einheit='A'))
    return _zusammen('E24', res, 'keine pruefbaren Zener-Regler')


def pruefe_e25(pl):
    ops = [ref for ref, e in pl.dbe.items() if e and e.get('typ') == 'opamp']
    if not ops:
        return [_u('E25', 'kein OpAmp mit DB-Eintrag (typ opamp, C_last_max_pF) auf der Platine')]
    res = []
    for ref in ops:
        e = pl.dbe[ref]
        out = [x['netz'] for x in pl.pins_von[ref] if x.get('typ') == 'output']
        if not out or not e.get('C_last_max_pF'):
            res.append(_e('E25', 'uebersprungen', f'{ref}: Ausgang oder C_last_max_pF unbekannt'))
            continue
        C = sum(pl.wert(c, 'C') or 0 for c, o in pl.zweipole(out[0], 'C') if pl.ist_gnd(o))
        st = 'ok' if C * 1e12 <= e['C_last_max_pF'] else 'warnung'
        res.append(_e('E25', st, f'{ref}: kapazitive Last direkt am Ausgang {C * 1e12:.0f} pF (max {e["C_last_max_pF"]} pF '
                      f'ohne Isolationswiderstand; sonst Phasenreserve < 45 Grad)', wert=C * 1e12, grenze=e['C_last_max_pF'], einheit='pF'))
    return _zusammen('E25', res, 'keine pruefbaren OpAmps')


# --------------------------------------------------------------------------------------------- Einstieg

PRUEFUNGEN = [pruefe_e1, pruefe_e2, pruefe_e3, pruefe_e4, pruefe_e5, pruefe_e6, pruefe_e7, pruefe_e8, pruefe_e9, pruefe_e10,
              pruefe_e11, pruefe_e12, pruefe_e13, pruefe_e14, pruefe_e15, pruefe_e16, pruefe_e17, pruefe_e18, pruefe_e19,
              pruefe_e20, pruefe_e21, pruefe_e22, pruefe_e23, pruefe_e24, pruefe_e25]


def platine_laden(pdir, projekt=None, pcb=None):
    pcb = pcb or finde_platine(pdir)
    if not pcb:
        return None
    ps = dict(projekt_soll(pdir)) if projekt is None else projekt
    pl = Platine(lese_kicad(pcb), lade_db(pdir), ps)
    pl.pdir = pdir
    return pl


def _leeres_layout():
    return {'version': 'ohne KiCad', 'kupferlagen': 2, 'lagen': ['F.Cu', 'B.Cu'], 'dicke_mm': 1.6, 'rand': [[0, 0], [0, 0]],
            'netzklassen': {}, 'bauteile': [], 'bahnen': [], 'zonen': [], 'stackup_sexpr': None}


def platine_ohne_kicad(pdir, ps, db=None):
    """Stellvertreter ohne .kicad_pcb (Kaufmodule, nur soll-Daten): leere Netzliste, Akku aus _projekt/module.
    Die Platinen-Pruefungen laufen darauf ohne Absturz durch; genutzt werden nur E6, E8, E15, E16, E21."""
    pl = Platine({'pcb': '', 'layout': _leeres_layout(), 'netzliste': {'teile': {}, 'netze': {}}},
                 db or lade_db(pdir), ps)
    pl.pdir = pdir
    pl.ohne_kicad = True
    mah = pl.modul_wert('akku_mAh', 'ps')
    if mah is None and any(m.get('akku') for m in pl.module):
        mah = next((m.get('akku_mAh') for m in pl.module if m.get('akku')), None)
    if mah or any(m.get('akku') for m in pl.module):
        lo, hi = CHEMIE_V.get(pl.akku_chemie() or 'lipo', CHEMIE_V['lipo'])
        pl.akku = {'ref': None, 'netz': None, 'mAh': mah, 'R_int': pl.modul_wert('R_int_Ohm'), 'V_min': lo, 'V_max': hi,
                   'chemie': pl.akku_chemie(), 'quelle': 'soll.json (Kaufmodul)'}
    return pl


def merkmale_platine(pdir):
    """Billige Merkmale aus der KiCad-Platine fuer merkmale.py: {'funk', 'akku', 'lautsprecher'}; {} ohne .kicad_pcb.
    Wirft nie (unlesbare Platine -> {}; der Lesefehler erscheint in pruefe als eigener Befund)."""
    try:
        pl = platine_laden(pdir)
    except Exception:  # noqa: BLE001
        return {}
    if pl is None:
        return {}
    ls = any(e and e.get('typ') == 'verstaerker_btl' for e in pl.dbe.values()) or any(
        re.search(r'speaker|buzzer|lautsprecher|summer|piezo', (t.get('fp', '') + ' ' + t.get('wert', '')), re.I)
        or re.match(r'(LS|BZ|SP)\d', ref) for ref, t in pl.teile.items())
    return {'funk': funk_im_entwurf(pl), 'akku': pl.akku is not None, 'lautsprecher': bool(ls)}


NUR_SOLL = (pruefe_e6, pruefe_e8, pruefe_e15, pruefe_e16, pruefe_e21)


def pruefe(pdir, projekt=None, pcb=None):
    """Alle Elektronik-Pruefungen. ``projekt`` ersetzt _projekt aus soll.json (fuer Tests/fremde Projekte)."""
    try:
        pl = platine_laden(pdir, projekt, pcb)
    except Exception as ex:  # noqa: BLE001 - KiCad fehlt o. ae. -> sichtbar, aber kein Absturz
        return [ergebnis('E', 'Elektronik einlesen', 'warnung', hinweis=f'Platine nicht lesbar, E1-E25 nicht geprueft: {type(ex).__name__}: {ex}',
                         quelle='mb2/kicad (pcbnew)')]
    if pl is not None:
        return pruefe_platine(pl)
    ps = dict(projekt_soll(pdir)) if projekt is None else projekt
    el = ps.get('elektronik') or {}
    if not (el.get('module') or ps.get('akku_mAh') or el.get('funk') or el.get('modi')):
        return [uebersprungen('E1-E25', 'Elektronik', 'keine .kicad_pcb unter electronics/ und keine soll-Daten '
                              '(Kaufmodul: _projekt.elektronik.module)', quelle='OCW_PRUEFKATALOG 3.7')]
    return pruefe_ohne_kicad(platine_ohne_kicad(pdir, ps))


def pruefe_ohne_kicad(pl):
    """Nur die Pruefungen, die mit soll-Daten auskommen; der Rest als EIN Eintrag 'E-Rest' (nicht 'E1-E25', sonst
    stuft der Ausloeser ihn trotz gerechneter E6/E16 zu 'fehler' hoch)."""
    out = [ergebnis('E0', 'Annahmen Elektronik', 'info', quelle='mb2/pruefungen/elektronik.py Docstring',
                    hinweis='keine .kicad_pcb: Kaufmodul(e) ' + (', '.join(m.get('name', '?') for m in pl.module) or '-')
                            + ' aus soll.json; nur E6, E8, E15, E16, E21 gerechnet')]
    for f in NUR_SOLL:
        id = 'E' + f.__name__.split('_e')[-1]
        try:
            out += f(pl)
        except Exception as ex:  # noqa: BLE001
            out.append(ergebnis(id, TITEL.get(id, id), 'fehler', hinweis=f'Pruefung abgestuerzt: {type(ex).__name__}: {ex}',
                                quelle=Q.get(id, '')))
    rest = [f'E{i}' for i in range(1, 26) if f'E{i}' not in ('E6', 'E8', 'E15', 'E16', 'E21')]
    out.append(uebersprungen('E-Rest', 'Elektronik ohne KiCad', ', '.join(rest) + ': brauchen eine .kicad_pcb '
                             '(Kaufmodul: Verantwortung des Herstellers)', quelle='OCW_PRUEFKATALOG 3.7'))
    return out


def pruefe_platine(pl):
    out = []
    if pl.annahmen:
        out.append(ergebnis('E0', 'Annahmen Elektronik', 'info', hinweis='; '.join(pl.annahmen),
                            quelle='mb2/pruefungen/elektronik.py Docstring'))
    for f in PRUEFUNGEN:
        id = 'E' + f.__name__.split('_e')[-1]
        try:
            out += f(pl)
        except Exception as ex:  # noqa: BLE001 - eine Pruefung faellt aus, die anderen laufen weiter
            out.append(ergebnis(id, TITEL.get(id, id), 'fehler', hinweis=f'Pruefung abgestuerzt: {type(ex).__name__}: {ex}',
                                quelle=Q.get(id, '')))
    return out
