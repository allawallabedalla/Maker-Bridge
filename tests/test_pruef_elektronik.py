"""Gegentests fuer mb2/pruefungen/elektronik.py (Katalog E1-E25).

Aufruf (ohne pytest): .venv\\Scripts\\python.exe tests/test_pruef_elektronik.py
Teil 1: Formeln gegen Handrechnung. Teil 2: synthetische Platinen (ohne KiCad), Ergebnis von Hand nachgerechnet.
Teil 3: echte Platinen (KiCad 10 noetig) - die alten maker-bridge-Projekte werden NUR gelesen (Kopie im Temp-Ordner)."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _nachweis import beispielprojekt, lang  # noqa: E402,F401

from mb2.pruefungen import elektronik as el  # noqa: E402

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALT = os.path.join(os.path.dirname(HIER), 'maker-bridge', 'projects')
MB2 = os.path.join(HIER, 'projects')


def nahe(a, b, rel=1e-3, abs_=1e-12):
    return abs(a - b) <= max(abs_, rel * abs(b))


def eintrag(res, id, stufe=None, enthaelt=None):
    for e in res:
        if e['id'] == id and (stufe is None or e['stufe'] == stufe) and (enthaelt is None or enthaelt in e['hinweis']):
            return e
    raise AssertionError(f'{id}/{stufe}/{enthaelt} fehlt: ' + '\n'.join(f'{e["id"]} {e["stufe"]} {e["hinweis"][:150]}'
                                                                       for e in res if e['id'] == id))


# ------------------------------------------------------------------ Teil 1: Formeln

def test_wert_si():
    assert el.wert_si('4k7') == 4700
    assert el.wert_si('6k8') == 6800
    assert el.wert_si('1M') == 1e6
    assert nahe(el.wert_si('100n', 'C'), 1e-7)
    assert nahe(el.wert_si('2n2', 'C'), 2.2e-9)
    assert nahe(el.wert_si('47n C0G', 'C'), 47e-9)
    assert nahe(el.wert_si('2.2uH', 'L'), 2.2e-6)
    assert el.wert_si('4R7') == 4.7
    assert el.wert_si('0') == 0
    assert el.wert_si('220R@100MHz', 'L') is None     # Ferrit: kein L-Wert
    assert el.wert_si('Abgleich', 'C') is None


def test_microstrip_hammerstad_hand():
    # Handrechnung w/h = 2, er = 4,4, t = 0: eps_eff = 2,7 + 1,7*(1+6)^-0,5 = 3,3426
    # Z0 = 120 pi / (sqrt(3,3426)*(2 + 1,393 + 0,667*ln(3,444))) = 376,99/7,7114 = 48,89 Ohm
    z0, ee = el.microstrip_z0(2.0, 1.0, 0.0, 4.4)
    assert nahe(ee, 3.3426, 1e-3), ee
    assert nahe(z0, 48.89, 2e-3), z0
    # u < 1: w/h = 0,5, er 4,4: eps = 2,7 + 1,7*((1+24)^-0,5 + 0,04*0,25) = 2,7 + 1,7*0,21 = 3,057
    # Z0 = 60/sqrt(3,057)*ln(16 + 0,125) = 34,316*2,7804 = 95,41 Ohm
    z0, ee = el.microstrip_z0(0.5, 1.0, 0.0, 4.4)
    assert nahe(ee, 3.057, 1e-3), ee
    assert nahe(z0, 95.41, 2e-3), z0
    w = el.microstrip_breite(48.89, 1.0, 0.0, 4.4)
    assert nahe(w, 2.0, 2e-3), w


def test_ipc2221_hand():
    # 1 A, 10 mil x 1,378 mil = 13,78 mil^2; A^0,725 = 6,698; dT = (1/(0,048*6,698))^(1/0,44) = 3,110^2,2727 = 13,2 K
    dT = el.ipc2221_dT(1.0, 0.254, 0.035, aussen=True)
    assert nahe(dT, 13.19, 5e-3), dT
    assert el.ipc2221_dT(1.0, 0.254, 0.035, aussen=False) > dT   # innen schlechter


def test_ausdruck_und_diode():
    assert nahe(el.ausdruck('0.75*VDD', 3.3), 2.475)
    assert nahe(el.ausdruck('VDD-0.4', 3.3), 2.9)
    assert el.ausdruck(0.4, None) == 0.4
    try:
        el.ausdruck('__import__("os")', 3.3)
        raise AssertionError('unsicherer Ausdruck angenommen')
    except ValueError:
        pass
    e = {'V_f_tabelle': [[0.001, 0.32], [0.01, 0.40]]}
    # log-linear: bei 3,162 mA (Mitte in log) -> 0,36 V
    assert nahe(el._vf_diode(e, math.sqrt(0.001 * 0.01)), 0.36, 1e-6)


# ------------------------------------------------------------------ Teil 2: synthetische Platinen

def _platine(teile, netze, bahnen=(), zonen=(), pads=None, klassen=None, projekt=None, lagen=2):
    """Netzliste {ref: (wert, fp, felder)}, netze {netz: [(ref, pin, name, typ)]}, pads {(ref, pin): (x, y)}."""
    pads = pads or {}
    bt = []
    for ref, (wert, fp, felder) in teile.items():
        ps = []
        for n, kn in netze.items():
            for r, pin, name, typ in kn:
                if r == ref:
                    ps.append({'nr': pin, 'netz': n, 'pos': list(pads.get((ref, pin), (0.0, 0.0))), 'gr': [0.6, 0.6], 'rot': 0,
                               'typ': typ, 'fkt': name, 'lagen': ['F.Cu'], 'bohr_mm': 0})
        bt.append({'ref': ref, 'wert': wert, 'fp': fp, 'pos': [0, 0], 'rot': 0, 'seite': 'F', 'felder': dict(felder),
                   'pads': ps, 'huelle': [[-1, -1], [1, 1]]})
    lay = {'version': 'test', 'kupferlagen': lagen, 'lagen': ['F.Cu', 'B.Cu'] if lagen == 2 else ['F.Cu', 'In1.Cu', 'In2.Cu', 'B.Cu'],
           'dicke_mm': 1.6, 'rand': [[0, 0], [50, 50]], 'netzklassen': klassen or {}, 'bauteile': bt, 'bahnen': list(bahnen),
           'zonen': list(zonen), 'stackup_sexpr': None}
    nl = {'teile': {ref: {'wert': w, 'fp': fp, 'felder': dict(f), 'lib': '', 'dnp': False} for ref, (w, fp, f) in teile.items()},
          'netze': {n: [{'ref': r, 'pin': p, 'name': nm, 'typ': t} for r, p, nm, t in kn] for n, kn in netze.items()}}
    return el.Platine({'pcb': '', 'layout': lay, 'netzliste': nl}, el.lade_db(), projekt or {})


R0603 = 'Resistor_SMD:R_0603_1608Metric'
C0603 = 'Capacitor_SMD:C_0603_1608Metric'


def _i2c_platine(r_pu='4k7', projekt=None):
    teile = {'U1': ('ESP32-C6-MINI-1-H4', 'RF_Module:ESP32-C6-MINI-1', {'LCSC': 'C6553337'}),
             'U2': ('SHT45-AD1B', 'x', {'LCSC': 'C5221601'}),
             'R1': (r_pu, R0603, {}), 'R2': (r_pu, R0603, {}), 'C1': ('100n', C0603, {})}
    netze = {'+3V3': [('U1', '3', '3V3', 'power_in'), ('U2', '3', 'VDD', 'power_in'), ('R1', '1', '', 'passive'),
                      ('R2', '1', '', 'passive'), ('C1', '1', '', 'passive')],
             'GND': [('U1', '1', 'GND', 'power_in'), ('U2', '4', 'VSS', 'power_in'), ('C1', '2', '', 'passive')],
             '/SDA': [('U1', '15', 'IO6', 'bidirectional'), ('U2', '1', 'SDA', 'bidirectional'), ('R1', '2', '', 'passive')],
             '/SCL': [('U1', '16', 'IO7', 'bidirectional'), ('U2', '2', 'SCL', 'input'), ('R2', '2', '', 'passive')]}
    bahnen = [{'art': 'bahn', 'a': [0, 0], 'b': [20, 0], 'w': 0.2, 'lage': 'F.Cu', 'netz': '/SDA', 'l': 20.0}]
    return _platine(teile, netze, bahnen=bahnen, projekt=projekt)


def test_e1_i2c_pegel_hand():
    pl = _i2c_platine()
    res = el.pruefe_e1(pl)
    # +3V3 aus Netzname: 3,135..3,465 V; Pull-up und ESP32 an derselben Schiene -> gleiche Spannung v auf beiden Seiten.
    # U1 (ESP32) liest SDA von U2 (SHT45, Open-Drain): NM_H = min_v (v - 0,75 v) = 0,25*3,135 = 0,784 V
    # V_OL(SHT45) fehlt -> UM10204 0,4 V @ 3 mA, skaliert auf I_sink = v/4700:
    # NM_L = min_v (0,25 v - 0,4*(v/4700)/0,003) -> bei v = 3,135: 0,7838 - 0,0889 = 0,6948 V -> ok
    alle = [e for e in res if e['id'] == 'E1' and e['stufe'] != 'uebersprungen']
    einzel = [d for e in alle for d in ([e.get('daten')] + (e.get('daten', {}) or {}).get('einzeln', [])) if d and 'NM_H' in d]
    x = [d for d in einzel if d['netz'] == '/SDA' and d['treiber'] == 'U2' and d['empfaenger'] == 'U1'][0]
    assert nahe(x['NM_H'], 0.25 * 3.135, 1e-3), x
    assert nahe(x['NM_L'], 0.25 * 3.135 - 0.4 * (3.135 / 4700) / 0.003, 1e-3), x
    assert all(e['stufe'] == 'ok' for e in alle), alle


def test_e1_ueberspannung_fehler():
    # Pull-up an +5V auf ESP32-Eingang: 5,25 V > VDD_min + 0,3 = 3,435 V -> fehler
    pl = _i2c_platine()
    pl.netze['+5V'] = [{'ref': 'R1', 'pin': '1', 'name': '', 'typ': 'passive', 'netz': '+5V'}]
    pl.netze['+3V3'] = [x for x in pl.netze['+3V3'] if x['ref'] != 'R1']
    pl.pins_von['R1'] = [x for x in pl.pins_von['R1'] if x['pin'] != '1'] + pl.netze['+5V']
    pl._spannungen()
    res = el.pruefe_e1(pl)
    e = eintrag(res, 'E1', 'fehler', 'ueberspannt')
    assert '5.25 V > 3.43 V' in e['hinweis'], e['hinweis']


def test_e11_i2c_anstieg_hand():
    pl = _i2c_platine(projekt={'elektronik': {'i2c_kHz': 400}})
    res = el.pruefe_e11(pl)
    sda = [e for e in res if e.get('daten', {}) and e['daten'].get('netz') == '/SDA'] or \
          [d for e in res for d in (e.get('daten') or {}).get('einzeln', []) if d and d.get('netz') == '/SDA']
    d = sda[0] if 'R' in sda[0] else sda[0]['daten']
    # Bahn 20 mm x 0,2 mm, h = 1,53 mm, er 4,5: Platte eps0*4,5*0,2*20/1,53 = 0,104 pF; Microstrip groesser -> max
    z0, ee = el.microstrip_z0(0.2, 1.53, 0.035, 4.5)
    c_ms = math.sqrt(ee) / (el.C0 * z0) * 20
    C = 2 * 10e-12 + max(c_ms, el.EPS0 * 4.5 * 0.2 * 20 / 1.53)
    assert nahe(d['C_F'], C, 1e-6), (d, C)
    tr = 0.8473 * 4700 * C
    assert tr < 300e-9
    assert all(e['stufe'] == 'ok' for e in res if e['id'] == 'E11')
    # 470 Ohm: R_min = (3,465 - 0,4)/3 mA = 1022 Ohm -> zu klein -> fehler
    res2 = el.pruefe_e11(_i2c_platine('470'))
    assert any(e['stufe'] == 'fehler' for e in res2), res2


def _ldo_platine(projekt=None, klasse=None, ntc=False):
    teile = {'U1': ('RT9080-33GJ5', 'x', {'LCSC': 'C841192'}), 'U2': ('ESP32-C6-MINI-1-H4', 'x', {'LCSC': 'C6553337'}),
             'U3': ('BQ24073RGTR', 'x', {'LCSC': 'C15220'}), 'R1': ('1M', R0603, {}), 'R2': ('1M', R0603, {}),
             'C1': ('100n', C0603, {}), 'R3': ('2k4', R0603, {}), 'J1': ('AKKU', 'Connector_JST:x', {}),
             'C2': ('1u', C0603, {}), 'C3': ('1u', C0603, {})}
    netze = {'/VBAT': [('U1', '1', 'VIN', 'power_in'), ('U3', '2', 'BAT', 'power_out'), ('R1', '1', '', 'passive'),
                       ('J1', '1', 'Pin_1', 'passive'), ('C2', '1', '', 'passive')],
             '+3V3': [('U1', '5', 'VOUT', 'power_out'), ('U2', '3', '3V3', 'power_in'), ('C3', '1', '', 'passive')],
             'GND': [('U1', '2', 'GND', 'power_in'), ('U2', '1', 'GND', 'power_in'), ('R2', '2', '', 'passive'),
                     ('C1', '2', '', 'passive'), ('R3', '2', '', 'passive'), ('J1', '2', 'Pin_2', 'passive'),
                     ('C2', '2', '', 'passive'), ('C3', '2', '', 'passive'), ('U3', '8', 'VSS', 'power_in')],
             '/ADC': [('R1', '2', '', 'passive'), ('R2', '1', '', 'passive'), ('C1', '1', '', 'passive'),
                      ('U2', '9', 'IO4', 'bidirectional')],
             '/ISET': [('U3', '16', 'ISET', 'passive'), ('R3', '1', '', 'passive')]}
    if ntc:                                   # 10k-NTC am TS-Pin des BQ24073
        teile['TH1'] = ('10k NTC B3380', 'Resistor_SMD:R_0603_1608Metric', {})
        netze['/TS'] = [('U3', '1', 'TS', 'input'), ('TH1', '1', '', 'passive')]
        netze['GND'].append(('TH1', '2', '', 'passive'))
    pads = {('U2', '3'): (0, 0), ('C3', '1'): (2.0, 0), ('U1', '1'): (10, 0), ('C2', '1'): (10, 4.0), ('U1', '5'): (12, 0),
            ('J1', '1'): (30, 0)}
    bahnen = [{'art': 'bahn', 'a': [30, 0], 'b': [10, 0], 'w': 0.2, 'lage': 'F.Cu', 'netz': '/VBAT', 'l': 20.0}]
    return _platine(teile, netze, bahnen=bahnen, pads=pads, projekt=projekt, klassen=klasse)


def test_e2_spannungsfall_hand():
    # 20 mm x 0,2 mm x 35 um bei 20 C: R = 1,72e-5*20/(0,2*0,035) = 49,14 mOhm; I = 1 A aus Netzklasse "Leistung_1A"
    # dV = 49,1 mV; V_min /VBAT = 2,4 V (LiPo + kein Schutz-IC -> Chemie 3,0 V) -> 3,0: 1,64 %
    pl = _ldo_platine({'elektronik': {'T_a_C': 20}}, klasse={'/VBAT': 'Leistung_1A'})
    assert pl.V['/VBAT'] == (3.0, 4.2), pl.V['/VBAT']
    res = el.pruefe_e2(pl)
    e = eintrag(res, 'E2', enthaelt='/VBAT')
    R = 1.72e-5 * 20 / (0.2 * 0.035)
    assert nahe(e['daten']['R_Ohm'], R, 1e-6), e
    assert nahe(e['wert'], round(R * 1.0 / 3.0 * 100, 3), 1e-3), e
    assert e['stufe'] == 'ok'


def test_e4_ldo_hand():
    # +3V3 explizit 100 mA (Symbolfeld Strom an U2): P = (4,2 - 3,3*0,97) V * 0,1 A + 4,2 V * 2 uA = 0,07990 W
    # T_a_C 25 (Luft an der Platine, keine Eigenerwaermung dazu), kuehlflaeche false -> RthJA x1,5 (realterme)
    # T_j = 25 + 0,0799*230,6*1,5 = 25 + 27,64 = 52,6 C <= 105 -> ok
    pl = _ldo_platine({'elektronik': {'T_a_C': 25, 'kuehlflaeche': False}})
    pl.teile['U2']['felder']['Strom'] = '+3V3=100mA'
    pl._stroeme()
    res = el.pruefe_e4(pl)
    e = eintrag(res, 'E4', enthaelt='U1 (LDO)')
    P = (4.2 - 3.3 * 0.97) * 0.1 + 4.2 * 2e-6
    assert nahe(e['daten']['P_W'], P, 1e-6), e
    assert nahe(e['wert'], round(25 + P * 230.6 * 1.5, 1), 1e-3), e
    assert e['stufe'] == 'ok', e
    # kuehlflaeche nicht angegeben -> x1,5 angenommen -> hoechstens warnung (nie ok auf Annahmen)
    pl2 = _ldo_platine({'elektronik': {'T_a_C': 25}})
    pl2.teile['U2']['felder']['Strom'] = '+3V3=100mA'
    pl2._stroeme()
    assert eintrag(el.pruefe_e4(pl2), 'E4', enthaelt='U1 (LDO)')['stufe'] == 'warnung'


def test_e4_sonne_und_eigenerwaermung_hand():
    # T_max_C 30, aussen, weiss (alpha 0,25): Sonne = 0,25*1000/25 = 10 K; Eigenerwaermung P_ges*Rth_gehaeuse
    # P = 0,07990 W (nur U1 rechnet; U3 ohne IN-Pin) -> 0,0799*20 = 1,598 K; T_teil = 30 + 10 + 1,598 = 41,60 C
    # T_j = 41,60 + 0,0799*230,6*1,5 = 41,60 + 27,64 = 69,2 C -> ok
    pl = _ldo_platine({'T_max_C': 30, 'aussen': True, 'farbe': 'weiss',
                       'elektronik': {'Rth_gehaeuse_K_W': 20, 'kuehlflaeche': False}})
    pl.teile['U2']['felder']['Strom'] = '+3V3=100mA'
    pl._stroeme()
    e = eintrag(el.pruefe_e4(pl), 'E4', enthaelt='U1 (LDO)')
    P = (4.2 - 3.3 * 0.97) * 0.1 + 4.2 * 2e-6
    T = 30 + 0.25 * 1000 / 25 + P * 20
    assert nahe(e['daten']['T_teil_C'], T, 1e-6), e
    assert nahe(e['wert'], round(T + P * 230.6 * 1.5, 1), 1e-3) and e['stufe'] == 'ok', e
    assert 'Sonne +10 K' in e['hinweis'], e['hinweis']


def test_e4_geschaetzt_nur_warnung():
    # ohne Stromangabe: ESP32 0,5 A Spitze -> P = 0,5 W -> 155 C -> nur 'warnung' (Spitze, kein Dauerstrom)
    res = el.pruefe_e4(_ldo_platine({'elektronik': {'T_a_C': 40}}))
    e = eintrag(res, 'E4', enthaelt='U1 (LDO)')
    assert e['stufe'] == 'warnung', e


def test_e7_e6_teiler_laufzeit_hand():
    # Teiler 1M/1M an /VBAT (4,2 V): I = 2,1 uA -> Akku -> warnung (> 1 uA). R_th = 500 kOhm, f_c = 1/(2 pi 500k 100n) = 3,183 Hz
    pl = _ldo_platine({'akku_mAh': 1000, 'laufzeit_ziel_h': 100000})
    e = eintrag(el.pruefe_e7(pl), 'E7')
    assert e['stufe'] == 'warnung' and nahe(e['wert'], 2.1, 1e-3), e
    f = eintrag(el.pruefe_e12(pl), 'E12')
    assert nahe(f['wert'], 1 / (2 * math.pi * 5e5 * 1e-7), 1e-3), f
    # E6 (Realterme): Boden = RT9080 2 uA + Teiler 2,1 uA = 4,1 uA (ESP32-Ruhe unbekannt), nur LDO -> Wandler x1.
    # Ziel 100000 h (11 Jahre): Selbstentladung LiPo 3 %/Monat * 100000/730 = 411 % -> Faktor 1/0,05 -> fehler
    g = eintrag(el.pruefe_e6(pl), 'E6')
    assert g['stufe'] == 'fehler', g
    # Ziel 8760 h: f = 1/0,85 (nutzbar) / 0,95 (T_min 15 C angenommen: 0,8 + 0,2*15/20) / 0,8 (Alterung)
    #             / (1 - 0,03*8760/730 = 0,64) = 2,4188 -> C_eff = 1000/2,4188 = 413,4 mAh
    # t = 0,4134 Ah / 4,1 uA = 100837 h >= 1,25*8760 -> ok, aber Unbekannte/Annahmen -> warnung
    pl.ps['laufzeit_ziel_h'] = 8760
    pl._kontext = None
    g = eintrag(el.pruefe_e6(pl), 'E6')
    f = 1 / 0.85 / 0.95 / 0.8 / (1 - 0.03 * 8760 / 730)
    assert nahe(g['daten']['f_kapazitaet'], f, 1e-9), g
    assert nahe(g['wert'], round(1.0 / f / 4.1e-6, 1), 1e-4), g
    assert g['stufe'] == 'warnung', g
    # Ziel 90000 h: Selbstentladung 0,03*90000/730 = 3,70 -> Faktor 1/0,05 -> C_eff 1000*0,85*0,95*0,8*0,05 = 32,3 mAh
    # -> 7878 h < 90000 -> fehler
    pl.ps['laufzeit_ziel_h'] = 90000
    pl._kontext = None
    assert eintrag(el.pruefe_e6(pl), 'E6')['stufe'] == 'fehler'


def test_e6_ohne_ziel_warnung():
    # Akku bekannt, Ziel fehlt -> rechnen und 'warnung' (frueher 'info')
    e = eintrag(el.pruefe_e6(_ldo_platine({'akku_mAh': 1000})), 'E6')
    assert e['stufe'] == 'warnung' and 'Laufzeitziel fehlt' in e['hinweis'], e


def test_e8_brownout_hand():
    # LiPo 3,0..4,2 V, LDO RT9080: Dropout 0,53 V @ 0,6 A linear -> bei 0,5 A 0,4417 V
    # V_krit = 3,0 + 0,15 (Reserve) + 0,4417 = 3,5917 V > 3,0 -> Akkunetz ohne Abschaltspannung -> warnung
    pl = _ldo_platine()
    e = eintrag(el.pruefe_e8(pl), 'E8')
    assert nahe(e['daten']['V_krit'], 3.0 + 0.15 + 0.53 * 0.5 / 0.6, 1e-6), e
    assert e['stufe'] == 'warnung'
    # R_int 0,1 Ohm bei T_min 20 C: f = (2 + (1-2)*20/25 = 1,2) * 1,5 Alterung = 1,8 -> R_eff 0,18 Ohm
    # V_krit = 3,5917 + 0,5 A*0,18 = 3,6817 V; Abschaltung 3,7 V -> ok
    pl2 = _ldo_platine({'T_min_C': 20, 'elektronik': {'V_abschalt_V': 3.7, 'R_int_Ohm': 0.1}})
    e2 = eintrag(el.pruefe_e8(pl2), 'E8')
    assert nahe(e2['daten']['V_krit'], 3.0 + 0.15 + 0.53 * 0.5 / 0.6 + 0.5 * 0.18, 1e-6) and e2['stufe'] == 'ok', e2
    # Abschaltung 3,6 V (frueher ok mit R_int roh und 0,1 V Reserve) -> 3,6817 > 3,6 -> fehler
    pl3 = _ldo_platine({'T_min_C': 20, 'elektronik': {'V_abschalt_V': 3.6, 'R_int_Ohm': 0.1}})
    assert eintrag(el.pruefe_e8(pl3), 'E8')['stufe'] == 'fehler'
    # Kaelte: T_min -10 C -> f = 3,0*1,5 = 4,5 -> R_eff 0,45 Ohm -> V_krit 3,5917 + 0,225 = 3,8167 > 3,7 -> fehler
    pl4 = _ldo_platine({'T_min_C': -10, 'elektronik': {'V_abschalt_V': 3.7, 'R_int_Ohm': 0.1}})
    e4 = eintrag(el.pruefe_e8(pl4), 'E8')
    assert nahe(e4['daten']['V_krit'], 3.5917 + 0.225, 1e-4) and e4['stufe'] == 'fehler', e4
    # T_min unbekannt -> 15 C angenommen (f = 1,4*1,5 = 2,1): V_krit 3,5917 + 0,105; Abschaltung 4,0 V reicht -> nur warnung
    pl5 = _ldo_platine({'elektronik': {'V_abschalt_V': 4.0, 'R_int_Ohm': 0.1}})
    e5 = eintrag(el.pruefe_e8(pl5), 'E8')
    assert nahe(e5['daten']['V_krit'], 3.5917 + 0.5 * 0.21, 1e-4) and e5['stufe'] == 'warnung', e5


def test_e9_entkopplung_abstand():
    pl = _ldo_platine()
    res = el.pruefe_e9(pl)
    # U2 3V3 bei (0,0), C3 bei (2,0): 2 mm -> ok (L-Kriterium ggf. gesammelte Warnung); U1 VIN -> C2 4 mm -> warnung
    a = [e for e in res if 'U1.VIN' in e['hinweis']][0]
    assert a['stufe'] == 'warnung' and nahe(a['wert'], 4.0), a
    assert any('U2.3V3' in e['hinweis'] and '2.0 mm' in e['hinweis'] for e in res)
    # L = mu0*h*l/w = 4e-7*pi*1e-3 H/mm * 1,53 mm * 2 mm / 0,6 mm = 6,41 nH (Padbreite 0,6)
    L = 4e-7 * math.pi * 1e-3 * 1.53 * 2.0 / 0.6 * 1e9
    assert any(f'{L:.1f} nH' in e['hinweis'] for e in res), [e['hinweis'] for e in res]


def test_e21_ladestrom_hand():
    # BQ24073: I = 890 / 2400 = 0,3708 A; 725 mAh -> 0,511 C -> 0,5-1 C = warnung (ok nur bis 0,5 C)
    pl = _ldo_platine({'akku_mAh': 725})
    e = eintrag(el.pruefe_e21(pl), 'E21')
    assert nahe(e['daten']['I_A'], 890 / 2400, 1e-9) and nahe(e['wert'], 890 / 2400 / 0.725, 1e-3), e
    assert e['stufe'] == 'warnung', e
    pl2 = _ldo_platine({'akku_mAh': 300})          # 1,24 C -> fehler
    assert eintrag(el.pruefe_e21(pl2), 'E21')['stufe'] == 'fehler'
    # 1000 mAh -> 0,371 C; innen (T_min 15 C, aussen false), kein NTC noetig -> ok
    assert eintrag(el.pruefe_e21(_ldo_platine({'akku_mAh': 1000, 'T_min_C': 15, 'aussen': False})), 'E21')['stufe'] == 'ok'
    # Temperatur unbekannt und kein NTC -> hoechstens warnung
    assert eintrag(el.pruefe_e21(_ldo_platine({'akku_mAh': 1000})), 'E21')['stufe'] == 'warnung'


def test_e21_ntc_pflicht_bei_kaelte():
    # T_min 5 C < 10 C: Laden unter 0 C unzulaessig -> NTC am TS-Pin Pflicht; ohne -> fehler (auch bei 0,37 C)
    e = eintrag(el.pruefe_e21(_ldo_platine({'akku_mAh': 1000, 'T_min_C': 5})), 'E21')
    assert e['stufe'] == 'fehler' and 'NTC am TS-Pin ist Pflicht' in e['hinweis'], e
    # aussen ohne T_min -> ebenso fehler
    assert eintrag(el.pruefe_e21(_ldo_platine({'akku_mAh': 1000, 'aussen': True})), 'E21')['stufe'] == 'fehler'
    # mit 10k-NTC TH1 an U3.TS: 0,371 C <= 0,5 C -> ok
    e2 = eintrag(el.pruefe_e21(_ldo_platine({'akku_mAh': 1000, 'T_min_C': 5}, ntc=True)), 'E21')
    assert e2['stufe'] == 'ok' and e2['daten']['ntc'] == 'ja' and 'TH1' in e2['hinweis'], e2
    # mit NTC, aber 0,511 C bei Kaelte -> warnung
    assert eintrag(el.pruefe_e21(_ldo_platine({'akku_mAh': 725, 'T_min_C': 5}, ntc=True)), 'E21')['stufe'] == 'warnung'


def test_e15_gehaeuse_hoechstens_warnung():
    # Antenne AE1 mit Sperrflaeche, kein Kupfer darin -> ohne Gehaeuse 'ok'; liegt board.step vor -> 'warnung'
    import tempfile
    teile = {'AE1': ('ANT', 'RF_Antenna:Test', {})}
    netze = {'/RF': [('AE1', '1', 'A', 'passive')]}
    zone = {'netz': '', 'regel': True, 'kein_kupfer': True, 'lagen': ['F.Cu'], 'fp': None,
            'umriss': [{'aussen': [[-3, -3], [3, -3], [3, 3], [-3, 3]], 'loecher': []}]}
    pl = _platine(teile, netze, zonen=[zone])
    assert eintrag(el.pruefe_e15(pl), 'E15')['stufe'] == 'ok'
    d = tempfile.mkdtemp(prefix='mb2_e15_')
    os.makedirs(os.path.join(d, 'electronics'))
    open(os.path.join(d, 'electronics', 'board.step'), 'w').write('ISO-10303-21;')
    pl.pdir = d
    e = eintrag(el.pruefe_e15(pl), 'E15')
    assert e['stufe'] == 'warnung' and 'hoechstens warnung' in e['hinweis'], e


def _modul_projekt(projekt):
    import json
    import tempfile
    d = tempfile.mkdtemp(prefix='mb2_modul_')
    os.makedirs(os.path.join(d, 'electronics'))
    os.makedirs(os.path.join(d, 'cad'))
    open(os.path.join(d, 'electronics', 't3_v161.step'), 'w').write('ISO-10303-21;')
    json.dump({'_projekt': projekt}, open(os.path.join(d, 'cad', 'soll.json'), 'w'))
    return d


def test_kaufmodul_ohne_kicad():
    # LILYGO T3 als Kaufmodul, nur STEP: E6/E8/E15/E16/E21 laufen aus soll-Daten, Rest ein Eintrag 'E-Rest'
    t3 = {'name': 'LILYGO T3', 'funk': True, 'f_MHz': 868, 'akku': True, 'akku_mAh': 2000, 'chemie': 'lipo',
          'R_int_Ohm': 0.1, 'V_abschalt_V': 3.5, 'I_ruhe_uA': 100, 'wandler': 'ldo', 'dropout_V': 0.2,
          'I_peak_mA': 200, 'VDD_min_V': 3.0, 'I_chg_mA': 500, 'ntc': False}
    funk = {'r_m': 1000, 'f_MHz': 868, 'P_t_dBm': 14, 'P_rx_min_dBm': -120, 'umgebung': 'frei', 'G_t_dBi': 0,
            'G_r_dBi': 0}
    d = _modul_projekt({'T_min_C': 20, 'aussen': False, 'laufzeit_ziel_h': 1000,
                        'elektronik': {'module': [t3], 'funk': funk}})
    assert el.merkmale_platine(d) == {}                  # keine .kicad_pcb -> leer, kein Absturz
    res = el.pruefe(d)
    ids = {e['id'] for e in res}
    assert {'E6', 'E8', 'E15', 'E16', 'E21', 'E-Rest'} <= ids and 'E1-E25' not in ids, ids
    assert not any('abgestuerzt' in e['hinweis'] for e in res), res
    # E6: Ziel 1000 h -> Selbstentladung 0,03*1000/730 = 4,1 %; f = 1/0,85 / 1,0 (20 C) / 0,8 / 0,9589 = 1,5336
    # C_eff = 2000/1,5336 = 1304,1 mAh; I = 100 uA (LDO x1) -> t = 13041 h >= 1250 h, aber Modi fehlen -> warnung
    e6 = eintrag(res, 'E6')
    f = 1 / 0.85 / 0.8 / (1 - 0.03 * 1000 / 730)
    assert nahe(e6['wert'], round(2000 / f * 1e-3 / 100e-6, 1), 1e-4) and e6['stufe'] == 'warnung', e6
    # E8: V_krit = 3,0 + 0,15 + 0,2 + 0,2 A * 0,1*1,8 (20 C: 1,2*1,5) = 3,386 V <= 3,5 -> ok
    e8 = eintrag(res, 'E8')
    assert nahe(e8['daten']['V_krit'], 3.0 + 0.15 + 0.2 + 0.2 * 0.18, 1e-6) and e8['stufe'] == 'ok', e8
    # E21: 0,5 A / 2 Ah = 0,25 C, innen 20 C -> ok trotz ntc false
    assert eintrag(res, 'E21')['stufe'] == 'ok'
    assert eintrag(res, 'E15')['stufe'] == 'warnung'     # Keepout beim Hersteller, Gehaeusemetall ungeprueft
    assert eintrag(res, 'E16')['stufe'] == 'ok'
    assert eintrag(res, 'E-Rest')['stufe'] == 'uebersprungen'


def test_kaufmodul_wandler_und_luecken():
    # Modus am Buck (eta 0,9, 3,3 V) an LiPo ohne V_abschalt: V_bat = Abschaltung 3,0 V (ungunstigster Fall, seit
    # 19.11.2026; vorher Mitte 3,6 V). Faktor 3,3/(0,9*3,0) = 1,22222; Modus 10 mA * 0,1 = 1 mA
    # T_min 20, Ziel 100 h (Selbstentladung 0,4 % < 1 % -> entfaellt): C_eff = 1000*0,85*0,8 = 680 mAh
    # -> t = 0,68/1,22222e-3 = 556,4 h >= 125 h, nichts unbekannt -> ok
    m = {'name': 'M', 'akku': True, 'akku_mAh': 1000, 'chemie': 'lipo', 'wandler': 'buck', 'eta': 0.9, 'V_out_V': 3.3}
    d = _modul_projekt({'T_min_C': 20, 'aussen': False, 'laufzeit_ziel_h': 100,
                        'elektronik': {'module': [m], 'modi': [{'name': 'mess', 'I_mA': 10, 'anteil': 0.1}]}})
    res = el.pruefe(d)
    e6 = eintrag(res, 'E6')
    fw = 3.3 / (0.9 * 3.0)
    assert nahe(e6['daten']['f_wandler'], fw, 1e-9), e6
    assert nahe(e6['wert'], round(0.68 / (1e-3 * fw), 1), 1e-4) and e6['stufe'] == 'ok', e6
    # E8/E21 ohne Angaben -> 'uebersprungen' mit Grund (alle() stuft bei Merkmal akku zu fehler hoch)
    assert 'I_peak_mA' in eintrag(res, 'E8', 'uebersprungen')['hinweis']
    assert 'I_chg_mA' in eintrag(res, 'E21', 'uebersprungen')['hinweis']
    # Funk am Modul ohne elektronik.funk -> E16 fehler
    r2 = el.pruefe(_modul_projekt({'elektronik': {'module': [dict(m, funk=True)]}}))
    assert eintrag(r2, 'E16')['stufe'] == 'fehler'


def test_e5_led_hand():
    # LED rot (Typklasse 2,0 V) an +3V3 (max 3,465 V) ueber 1 kOhm nach GND: I = (3,465 - 0 - 2,0)/1000 = 1,465 mA
    teile = {'R1': ('1k', R0603, {}), 'D1': ('rot', 'LED_SMD:LED_0603_1608Metric', {})}
    netze = {'+3V3': [('R1', '1', '', 'passive')], '/LA': [('R1', '2', '', 'passive'), ('D1', '2', 'A', 'passive')],
             'GND': [('D1', '1', 'K', 'passive')]}
    pl = _platine(teile, netze)
    e = eintrag(el.pruefe_e5(pl), 'E5', 'ok')
    assert nahe(e['daten']['I_A'], (3.465 - 2.0) / 1000, 1e-6), e
    # 47 Ohm: I = 31 mA > 20 mA (Typklasse) -> warnung, P = 45 mW < 50 mW
    teile['R1'] = ('47', R0603, {})
    e2 = eintrag(el.pruefe_e5(_platine(teile, netze)), 'E5')
    assert e2['stufe'] == 'warnung' and 'I_max' in e2['hinweis'], e2


def test_e22_qi_hand():
    # 4 x 47 nF = 188 nF, L = 12 uH: f_s = 1/(2 pi sqrt(12e-6*188e-9)) = 106,05 kHz -> +6,05 % -> warnung
    # C fuer 100 kHz: 1/((2 pi 1e5)^2 * 12e-6) = 211,1 nF
    teile = {'U1': ('BQ51050B', 'x', {'LCSC': 'C133307'})}
    netze = {'/AC1': [('U1', '2', 'AC1', 'input')], '/AC2': [('U1', '19', 'AC2', 'input')], '/COIL': []}
    for i in range(1, 5):
        teile[f'C{i}'] = ('47n', C0603, {})
        netze['/COIL'].append((f'C{i}', '1', '', 'passive'))
        netze['/AC1'].append((f'C{i}', '2', '', 'passive'))
    teile['C5'] = ('2n2', C0603, {})
    netze['/AC1'].append(('C5', '1', '', 'passive'))
    netze['/AC2'].append(('C5', '2', '', 'passive'))
    pl = _platine(teile, netze, projekt={'elektronik': {'qi_spule_uH': 12}})
    e = eintrag(el.pruefe_e22(pl), 'E22')
    fs = 1 / (2 * math.pi * math.sqrt(12e-6 * 188e-9))
    assert nahe(e['daten']['f_s_Hz'], fs, 1e-9) and e['stufe'] == 'warnung', e
    assert '211.1 nF' in e['hinweis'], e['hinweis']


def test_e16_friis_hand():
    # 868 MHz, 1000 m, Freiraum: lambda = 0,3454 m, FSPL = 20 log10(4 pi 1000/0,3454) = 91,22 dB; 14 dBm -> -77,2 dBm;
    # Empf. -120 -> 42,8 dB
    pl = _platine({}, {}, projekt={'elektronik': {'funk': {'r_m': 1000, 'f_MHz': 868, 'P_t_dBm': 14, 'P_rx_min_dBm': -120,
                                                            'umgebung': 'frei', 'G_t_dBi': 0, 'G_r_dBi': 0}}})
    e = eintrag(el.pruefe_e16(pl), 'E16')
    fspl = 20 * math.log10(4 * math.pi * 1000 / (299.792458 / 868))
    assert nahe(e['wert'], round(14 - fspl + 120, 1), 1e-3) and e['stufe'] == 'ok', e


def test_e16_bodenklima_nachgerechnet():
    # Feldfall 15.11.2026: 830 m durchs Dorf, Basis hinter Dachziegeln, Magnetfuss auf Unterlegscheibe, 3 m RG174,
    # 14 dBm, SF10 (-132 dBm). Gemessen: SNR -17 dB, also unter der Grenze -> E16 muss 'fehler' liefern.
    funk = {'r_m': 830, 'f_MHz': 868, 'P_t_dBm': 14, 'P_rx_min_dBm': -132, 'G_t_dBi': 2, 'umgebung': 'dorf',
            'hindernisse': ['ziegel_dach'], 'kabel': [{'typ': 'rg174', 'm': 3}], 'magnetfuss_ohne_blech': True}
    e = eintrag(el.pruefe_e16(_platine({}, {}, projekt={'elektronik': {'funk': funk}})), 'E16')
    assert e['stufe'] == 'fehler', e
    assert e['daten']['pfad_dB'] - e['daten']['freiraum_dB'] > 30, e   # Dorf kostet bei 830 m > 30 dB mehr als Freiraum


def test_e16_antennengewinn_fehlt_ist_annahme():
    funk = {'r_m': 1000, 'f_MHz': 868, 'P_t_dBm': 14, 'P_rx_min_dBm': -120, 'umgebung': 'frei'}
    e = eintrag(el.pruefe_e16(_platine({}, {}, projekt={'elektronik': {'funk': funk}})), 'E16')
    assert e['stufe'] == 'warnung' and 'G_t_dBi fehlt' in e['hinweis'], e


def test_e16_umgebung_fehlt_konservativ():
    funk = {'r_m': 100, 'f_MHz': 868, 'P_t_dBm': 14, 'P_rx_min_dBm': -132}
    e = eintrag(el.pruefe_e16(_platine({}, {}, projekt={'elektronik': {'funk': funk}})), 'E16')
    assert e['daten']['n'] == 3.5 and e['stufe'] == 'warnung' and 'dorf' in e['hinweis'], e


def test_fehlende_eingaben_uebersprungen():
    pl = _platine({}, {})
    res = el.pruefe_platine(pl)
    ids = {e['id'] for e in res}
    assert {f'E{i}' for i in range(1, 26)} <= ids, ids
    assert all(e['stufe'] in ('uebersprungen', 'info') for e in res if e['id'] != 'E0'), \
        [(e['id'], e['stufe']) for e in res if e['stufe'] not in ('uebersprungen', 'info')]


# ------------------------------------------------------------------ Teil 3: echte Platinen (nur lesen)

def _echt(name, projekt=None, basis=ALT):
    pdir = os.path.join(basis, name)
    beispielprojekt(pdir, 'electronics')
    vorher = {f: os.path.getmtime(os.path.join(pdir, 'electronics', f)) for f in os.listdir(os.path.join(pdir, 'electronics'))}
    res = el.pruefe(pdir, projekt)
    nachher = {f: os.path.getmtime(os.path.join(pdir, 'electronics', f)) for f in os.listdir(os.path.join(pdir, 'electronics'))}
    assert vorher == nachher, 'Projektordner wurde veraendert!'
    assert not any(e['stufe'] == 'fehler' and 'abgestuerzt' in e['hinweis'] for e in res), res
    return res


def test_echt_klimalogger():
    res = _echt('klimalogger', {'akku_mAh': 1000, 'elektronik': {'qi_spule_uH': 12}})
    if res is None:
        return
    e = eintrag(res, 'E21')                               # 314 / (390 + 200) = 0,532 A -> 0,53 C > 0,5 C: warnung
    assert nahe(e['daten']['I_A'], 314 / 590, 1e-9) and e['stufe'] == 'warnung' and e['daten']['ntc'] == 'ja', e
    q = eintrag(res, 'E22')
    assert q['stufe'] == 'warnung' and nahe(q['daten']['f_s_Hz'], 1 / (2 * math.pi * math.sqrt(12e-6 * 188e-9)), 1e-6), q
    b = eintrag(res, 'E8')
    assert b['stufe'] == 'warnung' and '3.59 V' in b['hinweis'], b   # 3,0 + 0,15 Reserve + 0,44 Dropout
    eintrag(res, 'E15', 'warnung', 'kein Kupfer darin')    # Sperrflaechen frei, aber Gehaeuse (mechanics/) ungeprueft
    m = el.merkmale_platine(os.path.join(ALT, 'klimalogger'))
    assert m == {'funk': True, 'akku': True, 'lautsprecher': False}, m
    eintrag(res, 'E7', 'warnung', '/VBAT_ADC')             # 1M/1M -> 2,1 uA Dauerverlust


def test_echt_evolve_kiesel():
    res = _echt('evolve-kiesel', {'akku_mAh': 725})
    if res is None:
        return
    e = eintrag(res, 'E21')
    assert nahe(e['daten']['I_A'], 890 / 2400, 1e-9) and e['stufe'] == 'warnung', e   # 0,37 A / 0,725 Ah = 0,51 C
    pl = el.platine_laden(os.path.join(ALT, 'evolve-kiesel'), {})
    lo, hi = pl.V['/5V_BB']                                  # FB-Teiler 180k/20k: 0,5*(1+9) = 5,0 V
    assert nahe((lo + hi) / 2, 5.0, 1e-6), (lo, hi)


def test_echt_rad_warnknopf():
    res = _echt('rad-warnknopf')
    if res is None:
        return
    z = eintrag(res, 'E14', 'warnung', '/ANT')               # 0,5 mm auf 0,21 mm Prepreg -> ~42 Ohm
    assert 35 < z['wert'] < 48, z
    eintrag(res, 'E15', 'warnung', 'AE1')


def test_echt_bodenklima():
    res = _echt('bodenklima')
    if res is None:
        return
    b = eintrag(res, 'E8')                                    # 2 x L91 bis 1,8 V < 2,0 V RAK3172
    assert b['stufe'] == 'warnung' and 'Firmware muss' in b['hinweis'], b
    e6 = eintrag(res, 'E6', 'warnung', 'Laufzeitziel fehlt')  # 3500 mAh aus der DB, kein Ziel -> warnung (frueher info)
    assert e6['daten']['f_kapazitaet'] > 1.1, e6            # L91 (li_fes2) mit Abschlaegen statt Nennkapazitaet


def test_echt_mb2_projekte():
    for name in ('testdose', 'schnapphaken', 'stifthalter-fem', 'frag-mich-alles-gehaeuse', 'bodenklima-sondenkopf'):
        pdir = beispielprojekt(os.path.join(MB2, name))
        res = el.pruefe(pdir)
        assert res and not any('abgestuerzt' in e['hinweis'] for e in res), (name, res)
        assert not any(e['stufe'] == 'fehler' for e in res), (name, [e for e in res if e['stufe'] == 'fehler'])


if __name__ == '__main__':
    n = 0
    for name, f in list(globals().items()):
        if name.startswith('test_'):
            f()
            n += 1
            print('ok', name)
    print(f'{n} Tests bestanden')
