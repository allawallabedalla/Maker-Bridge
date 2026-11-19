"""Kriterium 3 (19.11.2026): Jede Regel aus VMODELL.md und dem Skill hat mindestens einen Test.

Jede Regel traegt in der Doku eine Marke ``<!-- R:V01 -->`` (VMODELL.md) bzw. ``<!-- R:S01 -->`` (Skill).
REGELN ordnet jeder Marke Tests zu (``datei::funktion``) oder ``VERHALTEN`` mit Grund: Regeln fuer das Verhalten der KI
im Gespraech (Ton, Fragen, Kritik) lassen sich nicht mit Code pruefen - sie stehen hier ausdruecklich, damit keine Regel
stillschweigend ungetestet bleibt. Dazu die Tests fuer Regeln, die vorher keinen hatten.
Aufruf aus maker-bridge-2/:  uv run python tests/test_regeln.py"""
import ast
import json
import os
import re
import sys
import tempfile

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASIS)

from mb2 import anforderungen as an, befehle, cache, cad, fragen  # noqa: E402

TMP = tempfile.mkdtemp(prefix='mb2_regeln_')
VERHALTEN = 'verhalten'
DOKU = {'V': 'VMODELL.md', 'S': os.path.join('claude', 'skills', 'idee-zu-druck-2', 'SKILL.md')}

REGELN = {
    # ---------------------------------------------------------------- VMODELL.md
    'V01': ['test_keine_scheinsicherheit.py::test_jede_nachweisart_ohne_daten_unbewiesen',
            'test_anforderungen.py::test_beweispflicht_und_freigabe'],
    'V02': ['test_regeln.py::test_eltern_erben_schlechtestes_kind', 'test_anforderungen.py::test_beweispflicht_und_freigabe'],
    'V03': ['test_regeln.py::test_freigabestufen'],
    'V04': ['test_anforderungen.py::test_stakeholder_wunsch_und_herleitung',
            'test_regeln.py::test_obere_ebenen_brauchen_herkunft_und_abnahme'],
    'V05': ['test_anforderungen.py::test_stakeholder_wunsch_und_herleitung'],
    'V06': ['test_anforderungen.py::test_stakeholder_wunsch_und_herleitung'],
    'V07': ['test_glaubwuerdigkeit.py::test_relative_abweichung_bridge_grenzen'],
    'V08': ['test_regeln.py::test_obere_ebenen_brauchen_herkunft_und_abnahme'],
    'V09': ['test_regeln.py::test_kind_ohne_eltern_ist_mangel'],
    'V10': ['test_regeln.py::test_warnung_nur_mit_begruendung'],
    'V11': ['test_anforderungen.py::test_herkunft_vorbehalt', 'test_anforderungen.py::test_reserve_gegen_unsicherheit'],
    'V12': ['test_anforderungen.py::test_abnahme_lageunabhaengig'],
    'V13': ['test_anforderungen.py::test_firmware_konstante_gegen_soll', 'test_review_19_11.py::test_fw1_parser_hex_exponent_endung'],
    'V14': ['test_glaubwuerdigkeit.py::test_vv20_metrik'],
    'V15': ['test_anforderungen.py::test_ml_modell_nachweis'],
    'V16': ['test_anforderungen.py::test_feldmessung_hebt_modellnachweis_auf'],
    'V17': ['test_stichproben.py::test_einzelpunkt_metrik_und_regeln', 'test_stichproben.py::test_wirkung_in_der_v_matrix_und_vorschlag'],
    'V18': ['test_glaubwuerdigkeit.py::test_geringes_risiko_reicht_code_verifikation',
            'test_glaubwuerdigkeit.py::test_mittleres_risiko_braucht_konvergenz_und_sensitivitaet',
            'test_glaubwuerdigkeit.py::test_hohes_risiko_braucht_messung_mit_differenz',
            'test_glaubwuerdigkeit.py::test_hoechstes_risiko_verlangt_hoechste_stufen'],
    'V19': ['test_glaubwuerdigkeit.py::test_hohes_risiko_braucht_messung_mit_differenz', 'test_regeln.py::test_freigabestufen'],
    'V20': ['test_glaubwuerdigkeit.py::test_veraltete_oder_kippende_sensitivitaet_zaehlt_nicht'],
    'V21': ['test_glaubwuerdigkeit.py::test_ohne_einstufung_nie_bewiesen'],
    'V22': ['test_glaubwuerdigkeit.py::test_veraltete_oder_kippende_sensitivitaet_zaehlt_nicht'],
    'V23': ['test_messkette.py::test_zweipunktkalibrierung_beweist_keine_linearitaet',
            'test_messkette.py::test_hysterese_braucht_auf_und_ab', 'test_messkette.py::test_drift_braucht_zeitraum_und_rechnet_auf_jahr',
            'test_messkette.py::test_wiederholbarkeit_mindestanzahl', 'test_messkette.py::test_linearitaet_mehrpunkt_in_fs',
            'test_regeln.py::test_messbereich_braucht_beide_grenzen'],
    'V24': ['test_messkette.py::test_ohne_reihe_unbewiesen', 'test_messkette.py::test_referenz_ohne_rueckfuehrung_oder_unsicherheit',
            'test_messkette.py::test_bedingungen_abweichend', 'test_messkette.py::test_einheit_unpassend'],
    'V25': ['test_messkette.py::test_vmatrix_fehlende_messnachweise_sind_maengel'],
    'V26': ['test_messkette.py::test_genauigkeit_schutzband'],
    'V27': ['test_messkette.py::test_katalog_mk_und_ausloeser'],
    'V28': ['test_temp_demonstrator.py::test_negativ_ohne_kalibrierschein_keine_freigabe',
            'test_temp_demonstrator.py::test_demonstrator_ehrlicher_stand'],
    'V29': ['test_messkette.py::test_genauigkeit_einzelwert_ist_voreinstellung'],
    'V30': ['test_messkette.py::test_genauigkeit_schutzband'],
    'V31': ['test_temp_demonstrator.py::test_freigabe_nur_durch_mensch_und_an_stand_gebunden', 'test_temp_demonstrator.py::test_demonstrator_ehrlicher_stand'],
    'V32': ['test_temp_demonstrator.py::test_freigabe_nur_durch_mensch_und_an_stand_gebunden',
            'test_regeln.py::test_kein_druck_und_keine_freigabe_ueber_mcp'],
    'V33': ['test_regeln.py::test_ausloeser_unbewiesen_nicht_verletzt'],
    'V34': ['test_temp_demonstrator.py::test_kalibrierreihe_ist_kein_nachweis'],
    'V35': ['test_temp_demonstrator.py::test_freigabe_nur_durch_mensch_und_an_stand_gebunden'],
    'V36': ['test_temp_demonstrator.py::test_fehlende_adc_daten_kein_budget', 'test_temp_demonstrator.py::test_uebersteuerung_und_grenzen'],
    'V37': ['test_anforderungen.py::test_feldabgleich_schreibt_feldfall', 'test_feldfaelle.py::test_feldfaelle'],
    'V38': ['test_erweiterungen.py::test_fehlerinjektion_und_dichtheit_als_abnahme'],
    'V39': ['test_erweiterungen.py::test_x10_beobachtbarkeit'],
    'V40': ['test_erweiterungen.py::test_fehlerinjektion_und_dichtheit_als_abnahme'],
    'V41': ['test_erweiterungen.py::test_modulprofil_budget_hand', 'test_erweiterungen.py::test_modulprofil_ohne_angaben_kein_ok'],
    # ---------------------------------------------------------------- Skill idee-zu-druck-2
    'S01': ['test_regeln.py::test_kein_druck_und_keine_freigabe_ueber_mcp'],
    'S02': (VERHALTEN, 'Ton und Form der Antworten - Pruefung durch den Nutzer'),
    'S03': (VERHALTEN, 'Verstaendlichkeit einer Rueckfrage - Pruefung durch den Nutzer'),
    'S04': ['test_regeln.py::test_fragen_warteschlange'],
    'S05': (VERHALTEN, 'Kritische Haltung im Gespraech; die rechenbaren Widersprueche pruefen X1-X9 (S12)'),
    'S06': (VERHALTEN, 'Klaerung der Systemgrenze im Gespraech'),
    'S07': ['test_widerspruch.py::test_x7_bus_und_x8_kalibrierung'],
    'S08': ['test_anforderungen.py::test_stakeholder_wunsch_und_herleitung'],
    'S09': ['test_widerspruch.py::test_x2_messbereich'],
    'S10': (VERHALTEN, 'Einbau als Teil der Messkette - je Projekt im Budget (MK1) einzutragen'),
    'S11': ['test_widerspruch.py::test_x4_bis_x6_ziele', 'test_widerspruch.py::test_x9_seriennachweis_mit_einem_geraet'],
    'S12': ['test_widerspruch.py::test_demonstrator_findet_budget_gleich_toleranz', 'test_regeln.py::test_fragen_warteschlange'],
    'S13': ['test_temp_demonstrator.py::test_freigabe_nur_durch_mensch_und_an_stand_gebunden'],
    'S14': ['test_ziele.py::test_project_new_fragt_ziele_ab', 'test_ziele.py::test_luecken_zaehlen_nicht_als_null',
            'test_ziele.py::test_unbekannt_ist_risiko_und_prioritaet_eindeutig'],
    'S15': ['test_stichproben.py::test_wirkung_in_der_v_matrix_und_vorschlag'],
    'S16': (VERHALTEN, 'Wann nach einem Datenblatt gefragt wird; dass fehlende Bauteile unbekannt statt 0 zaehlen, '
                       'prueft test_keine_scheinsicherheit'),
    'S17': (VERHALTEN, 'Bestellliste und Vorrat liegen ausserhalb des Repositorys'),
    'S18': ['test_regeln.py::test_platzhalter_ohne_quelle_ungeprueft'],
    'S19': ['test_pruef_katalog.py::test_project_new_einsatz_und_eingaben_offen',
            'test_pruef_katalog.py::test_ausloeser_stilles_ueberspringen_wird_fehler'],
    'S20': (VERHALTEN, 'Ehrlichkeit beim Eintragen (nichts schoenen) - der Code kann eine geschoente Angabe nicht '
                       'von einer echten unterscheiden'),
    'S21': ['test_regeln.py::test_cache_schluessel_umfasst_alle_quellen',
            'test_glaubwuerdigkeit.py::test_veraltete_oder_kippende_sensitivitaet_zaehlt_nicht'],
    'S22': (VERHALTEN, 'Ruecksprung im Ablauf (FEM kritisch -> Gehaeuse) steuert die KI'),
    'S23': ['test_regeln.py::test_freigabestufen'],
    'S24': ['test_anforderungen.py::test_abnahme_eintragen_beweist'],
    'S25': ['test_feldfaelle.py::test_feldfaelle'],
    'S27': ['test_karten.py::test_laufsperre_und_bremse'],
    'S28': ['test_karten.py::test_abnahme_entscheidet_das_audit_nicht_der_agent', 'test_durchlauf.py::test_durchlauf_idee_bis_freigabe'],
    'S29': ['test_karten.py::test_hochstufen_statt_wiederholen'],
    'S30': ['test_karten.py::test_laufsperre_und_bremse', 'test_karten.py::test_vorrang_und_nutzer'],
    'S31': ['test_karten.py::test_stand_kurz_und_vollstaendig'],
    'S32': ['test_erweiterungen.py::test_x10_beobachtbarkeit'],
    'S33': ['test_pruef_dauer_toleranz.py::test_t1_t4_messung'],
    'S26': (VERHALTEN, 'Grundannahme pruefen nach zwei gescheiterten Varianten - Urteil der KI'),
}


# ================================================================ Hilfen

def _projekt(name, anforderungen, soll=None, abnahme=None):
    d = os.path.join(TMP, name)
    os.makedirs(os.path.join(d, 'cad'), exist_ok=True)
    json.dump({'anforderungen': anforderungen}, open(os.path.join(d, 'anforderungen.json'), 'w', encoding='utf-8'))
    json.dump(soll or {'_projekt': {}}, open(os.path.join(d, 'cad', 'soll.json'), 'w', encoding='utf-8'))
    if abnahme is not None:
        json.dump({'schritte': abnahme}, open(os.path.join(d, 'abnahme.json'), 'w', encoding='utf-8'))
    return d


def _k(id_, stufe, **kw):
    return {'id': id_, 'titel': id_, 'stufe': stufe, 'hinweis': '', **kw}


def _z(v):
    return {z['id']: z for z in v['anforderungen']}


SYS = {'id': 'A-SYS', 'ebene': 'system', 'herkunft': 'Nutzer 19.11.2026', 'text': 'Geraet tut es',
       'nachweise': [{'art': 'abnahme', 'ref': 'AB-1', 'stufe': 'abnahme'}]}


def _sub(id_, eltern, ref):
    return {'id': id_, 'ebene': 'subsystem', 'eltern': eltern, 'text': id_,
            'nachweise': [{'art': 'katalog', 'ref': ref, 'stufe': 'integration'}]}


# ================================================================ neue Regeltests

def test_eltern_erben_schlechtestes_kind():
    """Kette system <- subsystem <- komponente: vorbehalt und verletzt wandern bis ganz nach oben."""
    kom = {'id': 'K-1', 'ebene': 'komponente', 'eltern': ['B-1'], 'text': 'k',
           'nachweise': [{'art': 'katalog', 'ref': 'Q2', 'stufe': 'komponente', 'warnung_akzeptiert': 'Test'}]}
    d = _projekt('erben', [SYS, _sub('B-1', ['A-SYS'], 'Q1'), kom], abnahme=[{'id': 'AB-1', 'ist': 1, 'soll': {'wert': 0}}])
    z = _z(an.pruefen(d, katalog={'m': [_k('Q1', 'ok'), _k('Q2', 'warnung')]}))
    assert z['K-1']['status'] == 'vorbehalt' and z['B-1']['status'] == 'vorbehalt' and z['A-SYS']['status'] == 'vorbehalt', z
    z = _z(an.pruefen(d, katalog={'m': [_k('Q1', 'ok'), _k('Q2', 'fehler')]}))
    assert z['A-SYS']['status'] == 'verletzt' and 'B-1' in z['A-SYS']['wegen_kind'], z['A-SYS']


def test_freigabestufen():
    """nicht_druckfertig -> druckfertig (alles vor der Abnahme bewiesen) -> fertig (auch Abnahme bewiesen)."""
    ab = [{'id': 'AB-1', 'ist': None, 'soll': {'wert': 0, 'op': '>='}}]
    d = _projekt('stufen', [SYS, _sub('B-1', ['A-SYS'], 'Q1')], abnahme=ab)
    assert an.pruefen(d, katalog={'m': [_k('Q1', 'uebersprungen')]})['freigabe'] == 'nicht_druckfertig'
    v = an.pruefen(d, katalog={'m': [_k('Q1', 'ok')]})
    assert v['freigabe'] == 'druckfertig' and v['offen_abnahme'], v      # Abnahme fehlt noch
    an.abnahme_eintragen(d, 'AB-1', 1.0)
    assert an.pruefen(d, katalog={'m': [_k('Q1', 'ok')]})['freigabe'] == 'fertig'
    # ein unbewiesener Nachweis vor der Abnahme (z. B. FEM bei Risiko >= 4 ohne Messung) sperrt druckfertig
    assert an.pruefen(d, katalog={'m': [_k('Q1', 'warnung')]})['freigabe'] == 'nicht_druckfertig'


def test_obere_ebenen_brauchen_herkunft_und_abnahme():
    ohne = {'id': 'A-X', 'ebene': 'system', 'text': 'x', 'nachweise': [{'art': 'katalog', 'ref': 'Q1', 'stufe': 'integration'}]}
    wunsch = {'id': 'W-1', 'ebene': 'stakeholder', 'herkunft': 'Nutzer', 'text': 'w',
              'nachweise': [{'art': 'katalog', 'ref': 'Q1', 'stufe': 'integration'}]}
    d = _projekt('oben', [ohne, wunsch])
    z = _z(an.pruefen(d, katalog={'m': [_k('Q1', 'ok')]}))
    m = ' '.join(z['A-X']['matrix_maengel'])
    assert 'ohne Herkunft' in m and 'Abnahme am Geraet oder Feldmessung' in m and z['A-X']['status'] != 'bewiesen', m
    assert 'Abnahme am Geraet oder Feldmessung' in ' '.join(z['W-1']['matrix_maengel'])


def test_kind_ohne_eltern_ist_mangel():
    d = _projekt('waise', [SYS, _sub('B-1', [], 'Q1')], abnahme=[{'id': 'AB-1', 'ist': 1, 'soll': {'wert': 0}}])
    v = an.pruefen(d, katalog={'m': [_k('Q1', 'ok')]})
    z = _z(v)
    assert any('Elternanforderung' in x for x in z['B-1']['matrix_maengel']) and z['B-1']['status'] == 'unbewiesen', z['B-1']
    assert v['freigabe'] == 'nicht_druckfertig'


def test_warnung_nur_mit_begruendung():
    nw = {'art': 'katalog', 'ref': 'Q1', 'stufe': 'integration'}
    assert an._katalog_status(nw, {'m': [_k('Q1', 'warnung')]})[0] == 'unbewiesen'
    assert an._katalog_status(dict(nw, warnung_akzeptiert='Spalt 0,4 mm reicht, gemessen'),
                              {'m': [_k('Q1', 'warnung')]})[0] == 'vorbehalt'       # nie 'bewiesen'


def test_ausloeser_unbewiesen_nicht_verletzt():
    """Pflichteingabe fehlt -> Katalog meldet fehler (Ausloeser), V-Matrix sagt unbewiesen, nicht verletzt."""
    nw = {'art': 'katalog', 'ref': 'Q1', 'stufe': 'integration'}
    assert an._katalog_status(nw, {'m': [_k('Q1', 'fehler', ausloeser='funk')]})[0] == 'unbewiesen'
    assert an._katalog_status(nw, {'m': [_k('Q1', 'fehler')]})[0] == 'verletzt'


def test_messbereich_braucht_beide_grenzen():
    """Gleiche, vollstaendige Reihe: nur Mitte -> verfahren_unzureichend; beide Grenzen -> bewertet."""
    sys.path.insert(0, os.path.join(BASIS, 'tests'))
    from test_messkette import MT, reihe                 # vollstaendige TESTFIXTURE-Reihe (kein echter Nachweis)
    from mb2.pruefungen import messkette as mk
    mitte = mk.bewerte_reihe(reihe('messbereich', [{'ref': 50.0, 'ist': 50.1}]), 'messbereich', MT)
    assert mitte['grund'] == 'verfahren_unzureichend' and 'deckt' in json.dumps(mitte, ensure_ascii=False), mitte
    rand = mk.bewerte_reihe(reihe('messbereich', [{'ref': 0.0, 'ist': 0.1}, {'ref': 100.0, 'ist': 100.1}]), 'messbereich', MT)
    assert 'verfahren_unzureichend' not in rand['gruende'], rand


def test_kein_druck_und_keine_freigabe_ueber_mcp():
    """mb2 druckt nie und gibt nie selbst messtechnisch frei: kein Befehl dafuer im MCP-Server."""
    namen = set(befehle.BEFEHLE)
    assert not [n for n in namen if re.search(r'freigeb|upload|drucken|print_start|senden', n)], namen
    assert 'messtechnik_freigeben' not in namen and hasattr(an, 'messtechnik_freigeben')
    assert 'Schickt nichts an den Drucker' in befehle.slice_plate.__doc__


def test_fragen_warteschlange():
    d = os.path.join(TMP, 'fragen')
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, 'projekt.md'), 'w', encoding='utf-8').write('# P\n\n## Idee\nx\n')
    fragen.einreihen(d, 'Welche Farbe?', 'komfort')
    fragen.einreihen(d, 'Stueckzahl?', 'ziel')
    n = fragen.aus_katalog(d, {'widerspruch': [_k('X3', 'fehler', hinweis='Budget = Toleranz'), _k('X5', 'ok')]})
    assert n == 1
    assert fragen.einreihen(d, 'Stueckzahl?', 'ziel')['neu'] is False          # nichts doppelt
    r = fragen.naechste(d)
    assert r['frage']['art'] == 'widerspruch' and r['danach_noch'] == 2, r      # wichtigste zuerst, nur EINE
    r = fragen.beantworten(d, 'X3', 'Toleranz auf 1 °C')
    assert r['frage']['frage'] == 'Stueckzahl?', r
    fragen.beantworten(d, 'Stueckzahl?', '1')
    alle = fragen.liste(d)
    assert len(alle) == 3 and sum(f['offen'] for f in alle) == 1, alle         # nichts faellt weg
    text = open(os.path.join(d, 'projekt.md'), encoding='utf-8').read()
    assert '## Idee' in text and '- [x] (ziel) Stueckzahl? -> 1' in text, text
    try:
        fragen.einreihen(d, 'x', 'egal')
        raise AssertionError('unbekannte Art angenommen')
    except ValueError:
        pass


def test_platzhalter_ohne_quelle_ungeprueft():
    q, offen = cad.quellen_pruefen(TMP, ['Akku', 'Schraube', 'Modul', 'Luft'],
                                   {'Schraube': 'norm:DIN 912 M3x10', 'Modul': 'geschaetzt: aus altem Skript',
                                    'Luft': 'freiraum:3 mm ueber dem Chip'})
    assert sorted(o.split(':')[0] for o in offen) == ['Akku', 'Modul'], offen


def test_cache_schluessel_umfasst_alle_quellen():
    """Aenderung an einer Pruefung (mb2/pruefungen/) muss gecachte Ergebnisse ungueltig machen."""
    rel = {os.path.relpath(p, cache.MB2).replace(os.sep, '/') for p in cache.quelldateien()}
    assert {'fem.py', 'pruefungen/mechanik.py', 'sensorprofile/rtd.py'} <= rel, sorted(rel)[:10]


# ================================================================ Abgleich Doku <-> REGELN <-> Tests

def _marken():
    out = {}
    for pre, f in DOKU.items():
        for m in re.findall(r'<!-- R:([VS]\d{2}) -->', open(os.path.join(BASIS, f), encoding='utf-8').read()):
            assert m[0] == pre, f'{m} steht in {f}'
            assert m not in out, f'Marke {m} doppelt'
            out[m] = f
    return out


def _testfunktionen():
    out = set()
    for f in os.listdir(os.path.join(BASIS, 'tests')):
        if f.startswith('test_') and f.endswith('.py'):
            t = ast.parse(open(os.path.join(BASIS, 'tests', f), encoding='utf-8').read())
            out |= {f'{f}::{n.name}' for n in t.body if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')}
    return out


def test_jede_regel_hat_test():
    marken = _marken()
    assert set(marken) == set(REGELN), (f'ohne Eintrag in REGELN: {sorted(set(marken) - set(REGELN))}; '
                                        f'ohne Marke in der Doku: {sorted(set(REGELN) - set(marken))}')
    da = _testfunktionen()
    for rid, z in REGELN.items():
        if isinstance(z, tuple):
            assert z[0] == VERHALTEN and len(z[1]) > 10 and rid.startswith('S'), (rid, z)   # nur Skill-Verhalten
        else:
            assert z, rid
            fehlt = [t for t in z if t not in da]
            assert not fehlt, f'{rid}: Test gibt es nicht: {fehlt}'
    verh = [r for r, z in REGELN.items() if isinstance(z, tuple)]
    assert len(verh) <= 10, f'zu viele Regeln ohne Test: {verh}'


if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_') and callable(f):
            f()
            print('ok', n)
    print('alle ok')
