"""Kriterium 1 (19.11.2026): Ohne Eingaben meldet KEINE Pruefung 'ok' und KEIN Nachweis 'bewiesen'.

"Gruen heisst bewiesen" - nicht "nichts gefunden". Der Test zaehlt die Module aus pruefungen.MODULE und die Nachweisarten
selbst auf, damit neue Module und Arten automatisch mitgeprueft werden.
Aufruf aus maker-bridge-2/:  uv run python tests/test_keine_scheinsicherheit.py"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mb2 import anforderungen as an, pruefungen   # noqa: E402

TMP = tempfile.mkdtemp(prefix='mb2_schein_')
ERLAUBT_OHNE_EINGABE = ('uebersprungen', 'info', 'warnung', 'fehler')
NACHWEISARTEN = ('katalog', 'cad', 'fem', 'slice', 'kicad', 'abnahme', 'feld', 'manuell', 'messung', 'ml_modell')


def _projekt(name, soll):
    d = os.path.join(TMP, name)
    for sub in ('cad', 'out', 'fem', 'print', 'electronics'):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    json.dump(soll, open(os.path.join(d, 'cad', 'soll.json'), 'w', encoding='utf-8'))
    return d


def _ok_ohne_eingaben(d):
    """Alle Katalogergebnisse mit Stufe 'ok' (Modulabsturz zaehlt als Fehler, nicht als ok)."""
    erg = pruefungen.alle(d)['module']
    fehlende = set(pruefungen.MODULE) - set(erg)
    assert not fehlende, f'Module ohne Ergebnis: {fehlende}'
    return [(m, e['id'], e.get('teil'), e['titel']) for m, l in erg.items() for e in l
            if e['stufe'] not in ERLAUBT_OHNE_EINGABE]


def test_leeres_projekt_kein_ok():
    schlecht = _ok_ohne_eingaben(_projekt('leer', {}))
    assert not schlecht, f'ok ohne jede Eingabe: {schlecht}'


def test_teil_ohne_angaben_kein_ok():
    """Ein Teil ist angelegt, aber ohne Werte, Geometrie oder Rechnung: nichts darf gruen sein."""
    schlecht = _ok_ohne_eingaben(_projekt('teil', {'_projekt': {}, 'gehaeuse': {}}))
    assert not schlecht, f'ok ohne Eingaben am Teil: {schlecht}'


def test_jede_nachweisart_ohne_daten_unbewiesen():
    d = _projekt('nachweise', {'_projekt': {}})
    anf = [{'id': f'A-{art}', 'ebene': 'system', 'herkunft': 'Test',
            'messtechnik': {'messbereich': {'min': 0, 'max': 1, 'einheit': 'x'}, 'genauigkeit': {'max_abs': 1},
                            'bedingungen': {'T': 1}} if art == 'messung' else None,
            'nachweise': [{'art': art, 'ref': 'X', 'stufe': 'abnahme', 'eigenschaft': 'genauigkeit',
                           'kriterium': {'groesse': 'x', 'op': '>=', 'wert': 1}}]}
           for art in NACHWEISARTEN]
    for a in anf:
        if a['messtechnik'] is None:
            del a['messtechnik']
    json.dump({'anforderungen': anf}, open(os.path.join(d, 'anforderungen.json'), 'w', encoding='utf-8'))
    v = an.pruefen(d, katalog={})
    schlecht = [(z['id'], n['status']) for z in v['anforderungen'] for n in z['nachweise'] if n['status'] == 'bewiesen']
    assert not schlecht, f'bewiesen ohne Daten: {schlecht}'
    assert v['freigabe'] == 'nicht_druckfertig' and v['messtechnische_freigabe']['status'] != 'freigegeben', v['freigabe']
    assert {z['id'] for z in v['anforderungen']} == {f'A-{a}' for a in NACHWEISARTEN}


def test_messkette_ohne_daten_kein_ok():
    from mb2.pruefungen import messkette
    d = _projekt('mk', {'_projekt': {'messkette': {'profil': 'rtd_ratiometrisch_3leiter'}}})
    schlecht = [e['id'] for e in messkette.pruefe(d) if e['stufe'] not in ERLAUBT_OHNE_EINGABE]
    assert not schlecht, schlecht


# ---------------------------------------------------------------- Weglass-Probe (teilweise gefuellte Projekte)
# Regel: Wird EINE Eingabe entfernt, darf kein Ergebnis besser werden. Wird aus warnung/fehler/uebersprungen ein 'ok',
# nur weil eine Angabe fehlt, ist das Scheinsicherheit (Muster aller Review-Funde vom 19.11.2026).

SCHLECHTER = ('warnung', 'fehler', 'uebersprungen')
# Zielfelder sind Anforderungen, keine Eingaben: wer ein strengeres eigenes Ziel loescht, bekommt zu Recht das mildere
# Bridge-Minimum. Sie gehoeren nicht in die Weglass-Probe.
ZIELFELDER = {'sicherheit', 'zuverlaessigkeit', 'lastfaktor', 'ziel_U', 'ziel_aufloesung', 'ziele',
              'zielkosten_eur_stueck', 'aufwand_h_stueck', 'termin', 'zeit_h_pro_woche', 'prioritaet', 'fehlerfolge',
              'stueckzahl', 'klemmkraft_min_N', 'abstand_mm', 'laufzeit_ziel_h'}

MECH_SOLL = {
    '_projekt': {'material': 'PETG', 'streuung_xy': 0.08, 'streuung_z': 0.08, 'T_max_C': 23, 'T_min_C': 20,
                 'aussen': False, 'sicherheit': 2.5},
    'teil': {
        'schnapper': [{'name': 'a', 'L_mm': 12, 'b_mm': 6, 't_mm': 1.6, 'hinterschnitt_mm': 0.8, 'winkel_grad': 30,
                       'mu': 0.3, 'achse': 'x', 'eps_zul': 0.02, 'zyklen': 10}],
        'knicken': [{'name': 'stift', 'L_mm': 50, 'd_mm': 4, 'lagerung': 'frei', 'kraft_N': 20, 'achse': 'x'}],
        'rippen': [{'name': 'steg', 'h_mm': 20, 't_mm': 2, 'rand': 'gelenkig', 'druck_MPa': 10}],
        'schrauben': [{'d_mm': 3, 'vorspannung_N': 300, 'kopf_d_mm': 5.5, 'loch_d_mm': 3.2, 'klemmlaenge_mm': 6,
                       'last_N': 100, 'klemmkraft_min_N': 100, 'einschraub_mm': 4, 'achse': 'x'}],
        'inserts': [{'d_aussen_mm': 4.0, 'laenge_mm': 5.7}],
        'pressitze': [{'d_mm': 8, 'D_aussen_mm': 12, 'uebermass_mm': 0.05, 'achse': 'z'}],
        'scharniere': [{'L_mm': 1.5, 't_mm': 0.6, 'b_mm': 10, 'winkel_grad': 90, 'achse': 'x', 'eps_zul': 0.04}],
        'torsion': [{'art': 'rund', 'T_Nmm': 100, 'd_mm': 10}],
        'deckelbiegung': [{'a_mm': 50, 'b_mm': 50, 't_mm': 2, 'last_N': 10, 'last_art': 'punkt', 'abstand_mm': 0.15}],
        'zahnraeder': [{'m_mm': 1, 'z': 20, 'b_mm': 5, 'F_t_N': 50, 'achse': 'z', 'dauerlast': False}],
    }}

ELEK_SOLL = {'_projekt': {
    'T_min_C': -10, 'aussen': False, 'laufzeit_ziel_h': 1000,
    'elektronik': {'module': [{'name': 'Modul', 'funk': True, 'f_MHz': 868, 'akku': True, 'akku_mAh': 2000,
                               'chemie': 'lipo', 'R_int_Ohm': 0.1, 'V_abschalt_V': 3.5, 'I_ruhe_uA': 100,
                               'wandler': 'ldo', 'dropout_V': 0.2, 'I_peak_mA': 200, 'VDD_min_V': 3.0,
                               'I_chg_mA': 500, 'ntc': True}],
                   'funk': {'r_m': 300, 'f_MHz': 868, 'P_t_dBm': 14, 'P_rx_min_dBm': -132, 'G_t_dBi': 2,
                            'G_r_dBi': 2, 'umgebung': 'dorf', 'hindernisse': [], 'kabel': []},
                   'modi': [{'name': 'mess', 'I_mA': 10, 'anteil': 0.01}]}}}


def _blaetter(o, pfad=()):
    if isinstance(o, dict):
        for k, v in o.items():
            yield pfad + (k,)
            yield from _blaetter(v, pfad + (k,))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _blaetter(v, pfad + (i,))


def _ohne(o, pfad):
    import copy
    o = copy.deepcopy(o)
    x = o
    for t in pfad[:-1]:
        x = x[t]
    del x[pfad[-1]]
    return o


def _weglassprobe(name, soll, module, vorbereiten=None):
    """Fuer jede einzelne Angabe (Dict-Schluessel) im soll: entfernen, Module neu rechnen, Verbesserungen sammeln."""
    import importlib
    mods = [importlib.import_module(f'mb2.pruefungen.{m}') for m in module]

    def lauf(s):
        d = _projekt(name, s)
        if vorbereiten:
            vorbereiten(d)
        return {(e['id'], e.get('teil'), e['titel']): e['stufe'] for m in mods for e in m.pruefe(d)}
    basis = lauf(soll)
    funde = []
    for pfad in _blaetter(soll):
        if isinstance(pfad[-1], int) or pfad[-1] in ZIELFELDER:
            continue
        neu = lauf(_ohne(soll, pfad))
        for k, alt in basis.items():
            if alt in SCHLECHTER and neu.get(k) == 'ok':
                funde.append(('/'.join(map(str, pfad)), k, alt))
    return funde


def test_weglassprobe_mechanik():
    funde = _weglassprobe('wp_mech', MECH_SOLL, ['mechanik'])
    assert not funde, f'Entfernte Angabe macht ein Ergebnis besser (Scheinsicherheit): {funde[:10]}'


def test_weglassprobe_elektronik():
    def step(d):
        open(os.path.join(d, 'electronics', 'modul.step'), 'w').write('ISO-10303-21;')
    funde = _weglassprobe('wp_elek', ELEK_SOLL, ['elektronik'], step)
    assert not funde, f'Entfernte Angabe macht ein Ergebnis besser (Scheinsicherheit): {funde[:10]}'


def test_weglassprobe_messkette_ziele_widerspruch():
    import copy
    demo = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'demonstratoren', 'MB2-TEMP-001')
    soll = json.load(open(os.path.join(demo, 'cad', 'soll.json'), encoding='utf-8'))
    soll = copy.deepcopy(soll)
    soll['_projekt'].pop('firmware', None)       # Firmware-Dateien liegen nicht im Testprojekt
    soll['_projekt']['ziele'] = {'stueckzahl': 2, 'aufwand_h_stueck': 3, 'termin': '2027-06-30', 'zeit_h_pro_woche': 5,
                                 'fehlerfolge': 'mittel', 'prioritaet': ['qualitaet', 'kosten', 'zeit'],
                                 'zielkosten_eur_stueck': 50}

    def anf(d):
        shutil.copy(os.path.join(demo, 'anforderungen.json'), d)
    funde = _weglassprobe('wp_mk', soll, ['messkette', 'kpi', 'widerspruch'], anf)
    assert not funde, f'Entfernte Angabe macht ein Ergebnis besser (Scheinsicherheit): {funde[:10]}'


DAUER_SOLL = {
    '_projekt': {'material': 'PETG', 'T_max_C': 35, 'T_min_C': 5, 'T_mittel_C': 25, 'T_tagesgang_K': 10,
                 'lebensdauer_h': 1000, 'aussen': False,
                 'kennwerte': {'PETG': {'kriech_E_inf_zu_E0': [0.5, 'Test'], 'kriech_tau_h': [1000, 'Test'],
                                        'alpha_1_K': [70e-6, 'Test'], 'S_e_MPa': [15, 'Test'], 'mu': [0.3, 'Test'],
                                        'eps_dauer': [0.01, 'Test']}}},
    'teil': {'dauerlast': {'dauer_h': 1000, 'durchbiegung_mm': 0.2, 'durchbiegung_zul_mm': 0.3, 'sigma_MPa': 8},
             'schrauben': [{'d_mm': 3, 'vorspannung_N': 300, 'klemmkraft_min_N': 150}],
             'wechsellast': {'sigma_a_MPa': 3, 'sigma_m_MPa': 2, 'zyklen': 1e6},
             'masse_g': 50, 'anregung_Hz': 30}}


def test_weglassprobe_dauer_toleranz_schwingung():
    def teil(d):
        json.dump({'ok': True, 'bbox_mm': [40, 30, 20], 'druck_drehung': [0, 0, 0]},
                  open(os.path.join(d, 'out', 'teil.pruefung.json'), 'w'))
    funde = _weglassprobe('wp_dauer', DAUER_SOLL, ['dauer', 'toleranz', 'schwingung'], teil)
    assert not funde, f'Entfernte Angabe macht ein Ergebnis besser (Scheinsicherheit): {funde[:10]}'


def _fem_projekt():
    """Oeffentliches FEM-Projekt (Wandhaken wie tests/test_durchlauf.py), einmal gebaut und gerechnet."""
    fertig = os.path.join(TMP, 'fem_basis', 'haken')
    if os.path.exists(os.path.join(fertig, 'fem', 'haken.erg.json')):
        return fertig
    from mb2 import befehle as B, werkzeuge
    if not werkzeuge.ccx():
        from _nachweis import NichtAusgefuehrt
        raise NichtAusgefuehrt('werkzeug_fehlt', 'CalculiX (ccx) fehlt')
    from test_durchlauf import HAKEN
    alt = B.PROJEKTE
    B.PROJEKTE = os.path.join(TMP, 'fem_basis')
    try:
        B.project_new('haken', 'Haken an der Innenwand', '',
                      einsatz={'aussen': False, 'T_min_C': 15, 'T_max_C': 30, 'material': 'PETG', 'lebensdauer_h': 20000})
        d = os.path.join(B.PROJEKTE, 'haken')
        open(os.path.join(d, 'cad', 'haken.py'), 'w', encoding='utf-8').write(HAKEN.format(b=14, h=10))
        s = json.load(open(os.path.join(d, 'cad', 'soll.json'), encoding='utf-8'))
        s['haken'] = FEM_TEIL
        json.dump(s, open(os.path.join(d, 'cad', 'soll.json'), 'w', encoding='utf-8'))
        assert B.cad_build('haken', 'haken')['ok']
        json.dump(FEM_FALL, open(os.path.join(d, 'fem', 'haken.json'), 'w', encoding='utf-8'))
        B.fem_mech('haken', 'haken')
    finally:
        B.PROJEKTE = alt
    return d


FEM_TEIL = {'material': 'PETG', 'druckrichtung': 'x',
            'balken': [{'fall': 'haken', 'last': 'jacke', 'art': 'kragarm', 'L_mm': 30, 'a_mm': 21, 'b_mm': 14, 'h_mm': 10}],
            'dauerlast': {'dauer_h': 20000, 'sigma_MPa': 2, 'durchbiegung_mm': 0.05, 'durchbiegung_zul_mm': 0.5},
            'wechsellast': {'sigma_a_MPa': 1, 'sigma_m_MPa': 1, 'zyklen': 1e4}, 'masse_g': 10, 'anregung_Hz': 50}
FEM_FALL = {'koerper': [{'step': 'out/haken.step', 'material': 'PETG'}], 'netz': {'groesse': 1.5},
            'lagerung': [{'wo': {'ebene': ['y', 0.0]}, 'fest': 'xyz'}],
            'lasten': [{'name': 'jacke', 'wo': {'ebene': ['z', 10.0], 'box': [-14, 20, 9, 14, 30.5, 11]},
                        'kraft_N': [0, 0, -20]}], 'schwerkraft': True}
FEM_MODULE = ('mechanik', 'fem_plausi', 'dauer', 'toleranz', 'schwingung')


def test_weglassprobe_fem():
    """FEM-gestuetzte Pruefungen (M3, M7, M9, F23-F25, D*, T*, S*): jede Angabe in soll.json (Teil und _projekt) und
    im Lastfall einzeln entfernen - kein Ergebnis darf dadurch von warnung/fehler auf ok springen."""
    import importlib
    basis_dir = _fem_projekt()
    mods = [importlib.import_module(f'mb2.pruefungen.{m}') for m in FEM_MODULE]
    soll = json.load(open(os.path.join(basis_dir, 'cad', 'soll.json'), encoding='utf-8'))

    def lauf(neu_soll=None, neu_fall=None):
        d = os.path.join(TMP, 'fem_probe')
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(basis_dir, d)
        if neu_soll is not None:
            json.dump(neu_soll, open(os.path.join(d, 'cad', 'soll.json'), 'w', encoding='utf-8'))
        if neu_fall is not None:
            json.dump(neu_fall, open(os.path.join(d, 'fem', 'haken.json'), 'w', encoding='utf-8'))
        return {(e['id'], e.get('teil'), e['titel']): e['stufe'] for m in mods for e in m.pruefe(d)}
    basis = lauf()
    aktiv = sorted({k[0] for k, v in basis.items() if v != 'uebersprungen'})
    assert {'M3', 'M7', 'M9', 'F23'} <= set(aktiv), aktiv          # die Probe muss die FEM-Pruefungen wirklich treffen
    funde = []
    for quelle, daten in (('soll', soll), ('fall', FEM_FALL)):
        for pfad in _blaetter(daten):
            if isinstance(pfad[-1], int) or pfad[-1] in ZIELFELDER:
                continue
            neu = lauf(**({'neu_soll': _ohne(daten, pfad)} if quelle == 'soll' else {'neu_fall': _ohne(daten, pfad)}))
            for k, alt in basis.items():
                if alt in SCHLECHTER and neu.get(k) == 'ok':
                    funde.append((quelle + ':' + '/'.join(map(str, pfad)), k, alt))
    assert not funde, f'Entfernte Angabe macht ein Ergebnis besser (Scheinsicherheit): {funde[:10]}'
    # Randwert: anregung_Hz = 0 liess das Modul schwingung abstuerzen (Division durch null, 19.11.2026)
    import copy
    null = copy.deepcopy(soll)
    null['haken']['anregung_Hz'] = 0
    r = lauf(neu_soll=null)
    assert not [k for k, v in r.items() if k[0] == 'schwingung'], 'Modul schwingung abgestuerzt'
    assert r[('S2', 'haken', next(k[2] for k in r if k[0] == 'S2'))] == 'uebersprungen'

def _zahlen(o, pfad=()):
    if isinstance(o, bool):
        return
    if isinstance(o, (int, float)):
        yield pfad
    elif isinstance(o, dict):
        for k, v in o.items():
            yield from _zahlen(v, pfad + (k,))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _zahlen(v, pfad + (i,))


def _setze(o, pfad, wert):
    import copy
    o = copy.deepcopy(o)
    x = o
    for t in pfad[:-1]:
        x = x[t]
    x[pfad[-1]] = wert
    return o


def _randprobe(name, soll, module, vorbereiten=None, basis_dir=None, datei='cad/soll.json'):
    """Jede Zahl einzeln auf 0 und -1 setzen: kein Modul darf abstuerzen (ungueltige Eingabe -> uebersprungen/fehler
    mit Hinweis, nie ein Traceback)."""
    abstuerze = []
    for pfad in _zahlen(soll):
        for wert in (0, -1):
            neu = _setze(soll, pfad, wert)
            if basis_dir:
                d = os.path.join(TMP, name)
                shutil.rmtree(d, ignore_errors=True)
                shutil.copytree(basis_dir, d)
                json.dump(neu, open(os.path.join(d, datei), 'w', encoding='utf-8'))
            else:
                d = _projekt(name, neu)
                if vorbereiten:
                    vorbereiten(d)
            for e in (x for l in pruefungen.alle(d, module)['module'].values() for x in l):
                if e['id'] in pruefungen.MODULE:
                    abstuerze.append(('/'.join(map(str, pfad)), wert, e['hinweis'][:120]))
    return abstuerze


def test_randwerte_kein_absturz():
    funde = _randprobe('rp_mech', MECH_SOLL, ('mechanik',))
    funde += _randprobe('rp_elek', ELEK_SOLL, ('elektronik',))
    funde += _randprobe('rp_dauer', DAUER_SOLL, ('dauer', 'toleranz', 'schwingung'),
                        lambda d: json.dump({'ok': True, 'bbox_mm': [40, 30, 20], 'druck_drehung': [0, 0, 0]},
                                            open(os.path.join(d, 'out', 'teil.pruefung.json'), 'w')))
    assert not funde, f'{len(funde)} Abstuerze bei Randwerten: {funde[:12]}'


def test_randwerte_fem_kein_absturz():
    basis_dir = _fem_projekt()
    soll = json.load(open(os.path.join(basis_dir, 'cad', 'soll.json'), encoding='utf-8'))
    funde = _randprobe('rp_fem', soll, FEM_MODULE, basis_dir=basis_dir)
    funde += _randprobe('rp_fall', FEM_FALL, FEM_MODULE, basis_dir=basis_dir, datei='fem/haken.json')
    assert not funde, f'{len(funde)} Abstuerze bei Randwerten: {funde[:12]}'


if __name__ == '__main__':
    try:
        for n, f in list(globals().items()):
            if n.startswith('test_') and callable(f):
                f()
                print('ok', n)
        print('alle ok')
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
