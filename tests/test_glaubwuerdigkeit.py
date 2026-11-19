"""Glaubwuerdigkeit nach V&V 40: abgestufte Faktoren, Pflichten wachsen mit dem Modellrisiko (17.11.2026).
Aufruf aus maker-bridge-2/:  .venv/Scripts/python.exe tests/test_glaubwuerdigkeit.py"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mb2 import glaubwuerdigkeit as gw, sensitivitaet   # noqa: E402

TMP = tempfile.mkdtemp(prefix='mb2_glaub_')
LINEAR = {'loeser': 'CalculiX linear', 'bewertung': {'ok': True, 'min_sicherheit_z': 3.0}, '_cache': 'k1'}
M = {'frage': 'Haelt der Haken die Montage?', 'einsatz': 'FEM ersetzt den Zyklentest'}
F20_OK = {'fem_plausi': [{'id': 'F20', 'stufe': 'ok', 'teil': 'haken/grat'}]}
F21_OK = {'fem_plausi': F20_OK['fem_plausi'] + [{'id': 'F21', 'stufe': 'info', 'teil': 'haken/grat'}]}


def projekt(erg, sens=None):
    os.makedirs(os.path.join(TMP, 'fem', 'sens'), exist_ok=True)
    json.dump(erg, open(os.path.join(TMP, 'fem', 'haken.erg.json'), 'w', encoding='utf-8'))
    sp = os.path.join(TMP, 'fem', 'sens', 'haken.sens.json')
    if sens is None:
        if os.path.exists(sp):
            os.remove(sp)
    else:
        json.dump(sens, open(sp, 'w', encoding='utf-8'))
    return TMP


def sens(robust=True, vollstaendig=True, cache='k1'):
    return {'rel': 0.2, 'robust': robust, 'vollstaendig': vollstaendig, 'basis_cache': cache, 'empfindlichste': 'last_grat',
            'parameter': [{'parameter': 'last_grat', 'minus': {'ok': True}, 'plus': {'ok': robust}}]}


KONV = {**LINEAR, 'konvergenz': {}}


def test_ohne_einstufung_nie_bewiesen():
    assert gw.bewerte(projekt(LINEAR), 'haken', None)['status'] == 'vorbehalt'


def test_geringes_risiko_reicht_code_verifikation():
    g = gw.bewerte(projekt(LINEAR), 'haken', {**M, 'einfluss': 'gering', 'folge': 'mittel'})
    assert g['risiko'] == 2 and g['status'] == 'bewiesen', g


def test_mittleres_risiko_braucht_konvergenz_und_sensitivitaet():
    m = {**M, 'einfluss': 'mittel', 'folge': 'mittel'}
    assert gw.bewerte(projekt(LINEAR), 'haken', m)['status'] == 'vorbehalt'
    assert gw.bewerte(projekt(KONV), 'haken', m, F20_OK)['status'] == 'vorbehalt'          # Sensitivitaet fehlt
    assert gw.bewerte(projekt(KONV, sens(vollstaendig=False)), 'haken', m, F20_OK)['status'] == 'bewiesen'


def test_veraltete_oder_kippende_sensitivitaet_zaehlt_nicht():
    m = {**M, 'einfluss': 'gering', 'folge': 'gering'}
    g = gw.bewerte(projekt(KONV, sens(robust=False)), 'haken', m, F20_OK)
    assert g['status'] == 'vorbehalt' and 'nicht robust' in g['text'], g          # Befund auch bei Risiko 1
    g = gw.bewerte(projekt(KONV, sens(cache='alt')), 'haken', {**m, 'einfluss': 'mittel', 'folge': 'mittel'}, F20_OK)
    assert g['status'] == 'vorbehalt' and 'veraltet' in json.dumps(g['faktoren']), g


def test_hohes_risiko_braucht_messung_mit_differenz():
    m = {**M, 'einfluss': 'hoch', 'folge': 'mittel'}
    p = projekt(KONV, sens())
    assert gw.bewerte(p, 'haken', m, F20_OK)['status'] == 'unbewiesen'
    m['anwendbarkeit'] = 'gleiches PETG, Lastbereich wie im Modell'
    m['validierung'] = {'beleg': 'messung.json', 'strenge': 'sicht'}
    assert gw.bewerte(p, 'haken', m, F20_OK)['status'] == 'unbewiesen'                # Sichtvergleich reicht nicht
    m['validierung'] = {'beleg': 'messung.json', 'strenge': 'differenz', 'abweichung': 4.0, 'grenze': 10.0}
    assert gw.bewerte(p, 'haken', m, F20_OK)['status'] == 'bewiesen'
    m['validierung']['abweichung'] = 15.0
    assert gw.bewerte(p, 'haken', m, F20_OK)['status'] == 'unbewiesen'


def test_hoechstes_risiko_verlangt_hoechste_stufen():
    m = {**M, 'einfluss': 'hoch', 'folge': 'hoch', 'anwendbarkeit': 'ja',
         'validierung': {'beleg': 'x', 'strenge': 'differenz', 'abweichung': 1, 'grenze': 5}}
    p = projekt(KONV, sens())
    assert gw.bewerte(p, 'haken', m, F21_OK, herkunft='gemessen')['status'] == 'unbewiesen'   # Strenge 2 < 4
    m['validierung']['strenge'] = 'unsicherheit_beidseitig'
    assert gw.bewerte(p, 'haken', m, F20_OK, herkunft='gemessen')['status'] == 'unbewiesen'   # F21 fehlt
    assert gw.bewerte(p, 'haken', m, F21_OK, herkunft='geschaetzt')['status'] == 'unbewiesen'
    assert gw.bewerte(p, 'haken', m, F21_OK, herkunft='gemessen')['status'] == 'bewiesen'


def test_unbekannter_loeser_hat_keine_code_verifikation():
    g = gw.bewerte(projekt({'loeser': 'Eigenbau', 'bewertung': {'ok': True}}), 'haken',
                   {**M, 'einfluss': 'gering', 'folge': 'gering'})
    assert g['status'] == 'vorbehalt', g


def test_sensitivitaet_standardsatz_und_festigkeit_analytisch():
    os.makedirs(os.path.join(TMP, 'fem'), exist_ok=True)
    spec = {'koerper': [{'step': 'x.step', 'material': 'PETG'}, {'box': [0] * 6, 'material': 'STARR'}],
            'lagerung': [{'wo': {}, 'fest': 'xyz'}, {'wo': {}, 'fest': 'xy', 'weg': {'z': -1.0}}],
            'lasten': [{'name': 'a', 'wo': {}, 'kraft_N': [0, 0, 5.0]}]}
    namen = [n for n, *_ in sensitivitaet.standard(spec, 'mechanik')]
    assert namen == ['last_a', 'weg_1', 'E_PETG', 'festigkeit_PETG'], namen
    json.dump(spec, open(os.path.join(TMP, 'fem', 'f.json'), 'w', encoding='utf-8'))
    laeufe = []

    def rechne(projekt_, fall, art):     # Ersatzloeser: Sicherheit ~ 1 / Last
        laeufe.append(fall)
        s = spec if fall == 'f' else json.load(open(os.path.join(TMP, 'fem', fall + '.json'), encoding='utf-8'))
        S = 2.2 * 5.0 / abs(s['lasten'][0]['kraft_N'][2])
        return {'bewertung': {'ok': S >= 2, 'min_sicherheit_z': S}, '_cache': 'b'}
    erg = sensitivitaet.studie('p', TMP, 'f', 'mechanik', rechne, rel=0.2, nur=['last_a', 'festigkeit_PETG'])
    assert not erg['robust'] and not erg['vollstaendig'], erg                  # +20 % Last: S = 1,83 < 2
    assert erg['parameter'][1]['minus']['kennzahl'] == 1.76                     # Festigkeit -20 %: 2,2 * 0,8
    assert len(laeufe) == 3                                                     # Grundfall + 2 Lastvarianten


if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_'):
            f()
            print('ok', n)
