"""Glaubwuerdigkeit von Rechenmodellen, risikobasiert nach ASME V&V 40-2018 / FDA-Leitfaden 2023 (seit 17.11.2026).

Grundlagen: oeffentlicher FDA-Leitfaden "Assessing the Credibility of Computational Modeling and Simulation in Medical
Device Submissions" (Nov. 2023) und die Vortragsfolien des V&V-40-Ausschusses (IMAG-Wiki, um 2014). Der Normtext lag
nicht vor. Wie in den Folien hat jeder Faktor Stufen (niedrige -> hohe Glaubwuerdigkeit); das Risiko legt fest, welche
Stufe je Faktor verlangt ist. Mehrere Faktoren der Norm sind zusammengefasst (Rechenmodell, Vergleichsgroesse).

Je FEM-Nachweis in anforderungen.json ein Block "modell":
    {"frage": "Haelt der Haken 50 Montagezyklen?",              # Question of Interest
     "einsatz": "FEM ersetzt den Zyklentest vor dem Druck",     # Context of Use: was das Modell entscheidet
     "einfluss": "gering|mittel|hoch",   # wie stark die Entscheidung am Modell haengt (hoch = einziger Beleg)
     "folge": "gering|mittel|hoch",      # was eine falsche Entscheidung anrichtet
     "validierung": {"beleg": "Pfad/Messprotokoll", "strenge": "differenz", "abweichung": 4.0, "grenze": 10.0,
                     "einheit": "%"},
     "anwendbarkeit": "Messung am gleichen Material, Lastbereich 0-60 N wie im Modell"}

Modellrisiko = 1 + Einfluss + Folge (1..5). Faktoren und Stufen:
    code           0 keine | 1 Abgleich des Loesers gegen bekannte Loesung (tests/)
    loesung        0 keine | 1 Netzkonvergenz, F20 ok | 2 zusaetzlich Richardson-Fehlerband (F21) im Rahmen
    vergleich      0 keine Messung | 1 Sichtvergleich | 2 Differenz gepaarter Werte | 3 mit Unsicherheit einer Seite
                   | 4 mit Unsicherheit beider Seiten (validierung.strenge: sicht|differenz|unsicherheit_einseitig|
                   unsicherheit_beidseitig); ab Stufe 2 muss die Abweichung innerhalb der Grenze liegen
    sensitivitaet  0 keine | 1 Studie (fem_sensitivitaet mit nur=[...]) robust | 2 Standardsatz aller Eingaben robust
    anwendbarkeit  0 | 1 begruendet;   herkunft  0 | 1 alle Eingaben stark (gemessen/datenblatt/norm/berechnet)
Verlangt je Risiko (PFLICHT): 1-2 code 1 | 3 + loesung 1, sensitivitaet 1 | 4 + vergleich 2, anwendbarkeit 1 |
5 loesung 2, vergleich 4, sensitivitaet 2, herkunft 1.
Fehlt eine Stufe: Risiko <= 3 -> 'vorbehalt', Risiko >= 4 -> 'unbewiesen' (sperrt druckfertig).
Eine Sensitivitaetsstudie, in der eine Variante nicht mehr ok ist, ist ein Befund: mindestens 'vorbehalt'.
Kein "modell"-Block: 'vorbehalt' - ein nicht eingestuftes Modell ist nie 'bewiesen'.
Leitsatz V&V 40: Ist der Plan nicht erfuellbar, den Einsatzzweck enger fassen (geringerer Einfluss -> geringeres Risiko).
"""
import json
import os

STUFE = {'gering': 0, 'mittel': 1, 'hoch': 2}
STRENGE = {'sicht': 1, 'differenz': 2, 'unsicherheit_einseitig': 3, 'unsicherheit_beidseitig': 4}
PFLICHT = {   # Risiko -> verlangte Stufe je Faktor
    1: {'code': 1}, 2: {'code': 1},
    3: {'code': 1, 'loesung': 1, 'sensitivitaet': 1},
    4: {'code': 1, 'loesung': 1, 'sensitivitaet': 1, 'vergleich': 2, 'anwendbarkeit': 1},
    5: {'code': 1, 'loesung': 2, 'sensitivitaet': 2, 'vergleich': 4, 'anwendbarkeit': 1, 'herkunft': 1},
}
NAMEN = {'code': 'Code-Verifikation', 'loesung': 'Loesungsverifikation (Netz)', 'vergleich': 'Validierung (Strenge)',
         'sensitivitaet': 'Sensitivitaet', 'anwendbarkeit': 'Anwendbarkeit', 'herkunft': 'Herkunft der Eingaben'}
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Code-Verifikation je Physik: Abgleich gegen eine bekannte Loesung (Datei im Repo, Ergebnis in ARCHITEKTUR.md)
CODE_VERIFIKATION = {
    'calculix_linear': ('tests/fem_abgleich.py',
                        'Stifthalter gegen scikit-fem, gleiches Netz: Federrate 0,6438 vs 0,644 N/mm'),
    'calculix_nichtlinear': ('tests/schnapphaken_abgleich.py',
                             'Kontakt-Lauf gegen Kraft-Lauf ohne Kontakt: Steifigkeit -0,1 %'),
    'elmer_waerme': ('tests/test_pruef_waerme.py',
                     'Platte mit Quelle gegen qL^2/2k: 27,55 vs 27,5 degC; Strahlung Hand vs. Elmer < 0,1 %'),
}


def physik(erg):
    l = (erg or {}).get('loeser', '')
    if l.startswith('Elmer'):
        return 'elmer_waerme'
    if 'nichtlinear' in l or 'Kontakt' in l:
        return 'calculix_nichtlinear'
    if l.startswith('CalculiX'):
        return 'calculix_linear'
    return None


def risiko(modell):
    e, f = STUFE.get((modell or {}).get('einfluss')), STUFE.get((modell or {}).get('folge'))
    return None if e is None or f is None else 1 + e + f


def _katalog(katalog, id, fall):
    return [e for l in (katalog or {}).values() for e in l
            if e.get('id') == id and (e.get('teil') in (None, fall) or str(e.get('teil', '')).startswith(fall + '/'))]


def stufen(pdir, fall, erg, modell, katalog=None, herkunft=None):
    """{faktor: (stufe, beleg)} - was fuer diesen Fall tatsaechlich vorliegt."""
    s = {}
    cv = CODE_VERIFIKATION.get(physik(erg))
    s['code'] = (1, f'{cv[0]}: {cv[1]}') if cv and os.path.exists(os.path.join(BASE, cv[0])) else \
        (0, f'keine Verifikation fuer Loeser {erg.get("loeser")!r}')
    f20, f21 = _katalog(katalog, 'F20', fall), _katalog(katalog, 'F21', fall)
    schlecht20 = [e for e in f20 if e.get('stufe') not in ('ok', 'info')]
    if 'konvergenz' not in erg:
        s['loesung'] = (0, '"konvergenz" im Lastfall fehlt')
    elif not f20:
        s['loesung'] = (0, 'F20 fehlt im Katalog - Netzkonvergenz nicht bewertet')
    elif schlecht20:
        s['loesung'] = (0, f'F20 {schlecht20[0].get("stufe")}: {schlecht20[0].get("hinweis", "")}')
    elif f21 and all(e.get('stufe') in ('ok', 'info') for e in f21):
        s['loesung'] = (2, 'Netzkonvergenz und Richardson-Fehlerband (F20, F21) im Rahmen')
    else:
        s['loesung'] = (1, 'Netzkonvergenz gerechnet, F20 ok' + ('; F21 mit Warnung' if f21 else '; F21 fehlt'))
    v = modell.get('validierung') or {}
    st = STRENGE.get(v.get('strenge'), 2 if v.get('beleg') else 0) if v else 0
    ab, gr = v.get('abweichung'), v.get('grenze')
    # Stufen 3/4 ("mit Unsicherheit") nur mit gerechneter Validierungsmetrik (V&V 20, seit 19.11.2026)
    metrik = vv20_metrik(v) if v else None
    if st >= 3:
        if metrik is None or (st == 4 and not metrik['beidseitig']):
            st = min(st, 2) if metrik is None else 3
            if metrik is None:
                v = dict(v, _hinweis='Unsicherheiten (S, D, u_num, u_input, u_D) fehlen - nur Differenz gewertet')
        if metrik is not None:
            ab, gr = metrik['E_max_rel'], 1.0          # |E| / (k u_val) <= 1
            v = dict(v, einheit='', _hinweis=metrik['text'])
    # Bridge-weite Obergrenze fuer relative Abweichungen (seit 19.11.2026, nach Liu et al. 2025: < 5 % zuverlaessig,
    # 5-10 % brauchbar mit Nachjustieren, > 15 % gescheitert; die Luecke 10-15 % schliessen wir konservativ bei 10 %)
    relativ = str(v.get('einheit', '')).strip() == '%'
    if relativ and isinstance(gr, (int, float)) and gr > 10:
        gr = 10.0
    if st >= 2 and not (isinstance(ab, (int, float)) and isinstance(gr, (int, float)) and abs(ab) <= gr):
        s['vergleich'] = (0, f'{v.get("beleg")}: Abweichung {ab} ueber Grenze {gr}'
                             f'{" (Bridge-Obergrenze 10 %)" if relativ else ""} oder nicht angegeben')
    elif relativ and isinstance(ab, (int, float)) and 5 < abs(ab) <= 10:
        s['vergleich'] = (min(st, 2), f'{v.get("beleg")}: Abweichung {ab} % zwischen 5 und 10 % - brauchbar, aber '
                                      f'nachjustieren; hoechstens Stufe 2')
    else:
        s['vergleich'] = (st, f'{v.get("beleg")}: {v.get("strenge", "differenz")}, Abweichung {ab} '
                              f'{v.get("einheit", "")} bei Grenze {gr}' if v else 'keine Messung zum Vergleich')
    if v and v.get('_hinweis'):
        s['vergleich'] = (s['vergleich'][0], s['vergleich'][1] + '; ' + v['_hinweis'])
    sp = os.path.join(pdir, 'fem', 'sens', fall + '.sens.json')
    sens = json.load(open(sp, encoding='utf-8')) if os.path.exists(sp) else None
    if not sens:
        s['sensitivitaet'] = (0, 'keine Studie (fem_sensitivitaet)')
    elif sens.get('basis_cache') != erg.get('_cache'):
        s['sensitivitaet'] = (0, 'Studie veraltet: Grundfall hat sich seither geaendert')
    elif not sens.get('robust'):
        kipp = [z['parameter'] for z in sens['parameter'] if not (z['minus']['ok'] and z['plus']['ok'])]
        s['sensitivitaet'] = (0, f'nicht robust bei +/-{sens["rel"] * 100:.0f} %: {", ".join(kipp) or "Grundfall"}')
        s['_nicht_robust'] = True
    else:
        s['sensitivitaet'] = (2 if sens.get('vollstaendig') else 1,
                              f'robust bei +/-{sens["rel"] * 100:.0f} %, {len(sens["parameter"])} Parameter, '
                              f'empfindlichste: {sens.get("empfindlichste")}')
    s['anwendbarkeit'] = (1, modell['anwendbarkeit']) if modell.get('anwendbarkeit') else (0, 'nicht begruendet')
    stark = herkunft in ('gemessen', 'datenblatt', 'norm', 'berechnet')
    s['herkunft'] = (1 if stark else 0, f'schwaechste Herkunft: {herkunft or "offen"}')
    return s


def vv20_metrik(v):
    """Validierungsmetrik nach ASME V&V 20 (Begriffe aus der Literatur, Normtext nicht eingesehen):
    Vergleichsfehler E = S - D (Simulation minus Messung), Validierungsunsicherheit
    u_val = sqrt(u_num^2 + u_input^2 + u_D^2) (Numerik: Netzkonvergenz/F21; Eingaben: Sensitivitaet/UQ; Messung).
    Validiert, wenn |E| <= k u_val (k Standard 2). Mehrere Groessen (validierung.groessen = [{name, S, D, u_num,
    u_input, u_D}]): jede einzeln - konservative Einzelpruefung, KEINE multivariate Metrik nach VVUQ 20.1.
    Rueckgabe None, wenn S oder D fehlen. 'beidseitig' = u_num, u_input und u_D angegeben (Simulation UND Messung)."""
    import math
    gr = v.get('groessen') or ([v] if 'S' in v or 'D' in v else [])
    if not gr or any(not isinstance(g.get('S'), (int, float)) or not isinstance(g.get('D'), (int, float)) for g in gr):
        return None
    k = float(v.get('k', 2.0))
    zeilen, beid = [], True
    for g in gr:
        us = [g.get(n) for n in ('u_num', 'u_input', 'u_D')]
        beid = beid and all(isinstance(u, (int, float)) for u in us)
        uval = math.sqrt(sum(float(u) ** 2 for u in us if isinstance(u, (int, float))))
        E = g['S'] - g['D']
        rel = abs(E) / (k * uval) if uval > 0 else math.inf
        zeilen.append({'name': g.get('name', 'Groesse'), 'E': E, 'u_val': uval, 'verhaeltnis': rel})
    worst = max(zeilen, key=lambda z: z['verhaeltnis'])
    text = 'V&V 20: ' + '; '.join(f'{z["name"]} E = {z["E"]:.4g}, u_val = {z["u_val"]:.4g}, |E|/(k u_val) = '
                                  f'{z["verhaeltnis"]:.2f}' for z in zeilen)
    if len(zeilen) > 1:
        text += ' (jede Groesse einzeln, keine multivariate Metrik nach VVUQ 20.1)'
    return {'zeilen': zeilen, 'E_max_rel': worst['verhaeltnis'], 'beidseitig': beid, 'text': text}


def bewerte(pdir, fall, modell, katalog=None, herkunft=None):
    """Glaubwuerdigkeit eines FEM-Falls fuer seinen Einsatzzweck. herkunft = schwaechste Herkunft der Eingaben."""
    p = os.path.join(pdir, 'fem', fall + '.erg.json')
    erg = json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}
    r = risiko(modell)
    out = {'fall': fall, 'loeser': erg.get('loeser'), 'physik': physik(erg), 'frage': (modell or {}).get('frage'),
           'einsatz': (modell or {}).get('einsatz'), 'einfluss': (modell or {}).get('einfluss'),
           'folge': (modell or {}).get('folge'), 'risiko': r, 'faktoren': []}
    if not modell:
        out.update(status='vorbehalt', text=f'fem {fall}: Modellrisiko nicht eingestuft (V&V 40) - '
                                             'Block "modell" mit frage, einsatz, einfluss, folge fehlt')
        return out
    if r is None:
        out.update(status='vorbehalt', text=f'fem {fall}: einfluss/folge muessen gering, mittel oder hoch sein')
        return out
    s = stufen(pdir, fall, erg, modell, katalog, herkunft)
    pflicht = PFLICHT[r]
    fehlt = [] if modell.get('frage') and modell.get('einsatz') else ['Frage und Einsatzzweck']
    for k, name in NAMEN.items():
        ist, beleg = s[k]
        soll = pflicht.get(k, 0)
        out['faktoren'].append({'faktor': name, 'stufe': ist, 'verlangt': soll, 'erfuellt': ist >= soll, 'beleg': beleg})
        if ist < soll:
            fehlt.append(f'{name} {ist}/{soll}')
    if not fehlt and not s.get('_nicht_robust'):
        out.update(status='bewiesen', text=f'fem {fall}: glaubwuerdig fuer Risiko {r}')
    elif not fehlt:
        out.update(status='vorbehalt', text=f'fem {fall}: {s["sensitivitaet"][1]}')
    else:
        out.update(status='vorbehalt' if r <= 3 else 'unbewiesen',
                   text=f'fem {fall}: Risiko {r}, fehlt {", ".join(fehlt)}'
                        + ('; Plan nicht erfuellbar? Einsatzzweck enger fassen' if r >= 4 else ''))
    return out


def bericht(pdir, eintraege):
    """pruef/glaubwuerdigkeit.json + .md (Credibility Assessment Report je Modell)."""
    os.makedirs(os.path.join(pdir, 'pruef'), exist_ok=True)
    json.dump({'modelle': eintraege}, open(os.path.join(pdir, 'pruef', 'glaubwuerdigkeit.json'), 'w',
                                           encoding='utf-8'), indent=1, ensure_ascii=False)
    z = ['# Glaubwuerdigkeit der Rechenmodelle (risikobasiert nach ASME V&V 40 / FDA 2023)', '',
         'Automatisch erzeugt von `anforderungen_pruefen`. Risiko = 1 + Einfluss + Folge (1-5); '
         'Stufen je Faktor siehe `mb2/glaubwuerdigkeit.py`.', '']
    for e in eintraege:
        z += [f'## {e["anforderung"]} - FEM {e["fall"]}', '',
              f'- Frage: {e.get("frage") or "-"}', f'- Einsatzzweck: {e.get("einsatz") or "-"}',
              f'- Loeser: {e.get("loeser") or "-"}',
              f'- Einfluss {e.get("einfluss") or "-"} x Folge {e.get("folge") or "-"} -> Risiko {e.get("risiko") or "-"}',
              f'- **Status: {e["status"]}** - {e["text"]}', '']
        if e['faktoren']:
            z += ['| Faktor | Stufe | verlangt | Beleg |', '|---|---|---|---|']
            z += [f'| {f["faktor"]} | {f["stufe"]} | {f["verlangt"]} | {f["beleg"]} |' for f in e['faktoren']]
            z.append('')
    open(os.path.join(pdir, 'pruef', 'glaubwuerdigkeit.md'), 'w', encoding='utf-8').write('\n'.join(z) + '\n')


# ---------------------------------------------------------------------------------------------- KI/ML-Modelle

ML_PFLICHT = ('version', 'trainingsdaten', 'testdaten', 'metrik', 'eingaben')


def ml_bewerte(m):
    """Glaubwuerdigkeit eines KI/ML-Modells als Nachweis (seit 19.11.2026, SELBST ABGELEITET: ASME VVUQ 70 ist noch
    nicht veroeffentlicht; Logik wie V&V 40 - Einsatzzweck, Risiko, verlangte Belege - plus ML-typische Pruefungen).
    m = {"version": "Hash/Tag", "einsatz", "einfluss", "folge",
         "trainingsdaten": {"quelle", "n", "bereich": {"merkmal": [min, max]}},
         "testdaten": {"quelle", "n", "unabhaengig": true, "art": "messung|simulation"},
         "metrik": {"name", "wert", "grenze"}, "eingaben": {"merkmal": wert}, "uq": {"u": ..} (optional)}
    Regeln: kein Nachweis ohne Version (reproduzierbar), unabhaengige Testdaten (nicht im Training), Metrik in der
    Grenze und Eingaben im Trainingsbereich (keine Extrapolation). Ohne UQ hoechstens 'vorbehalt'. Ab Risiko 4 zusaetzlich
    Testdaten aus echten Messungen und UQ. Ausgaben eines KI-Agenten sind nie ein Nachweis.
    Rueckgabe (status, text)."""
    m = m or {}
    fehlt = [f for f in ML_PFLICHT if not m.get(f)]
    if fehlt:
        return 'unbewiesen', f'ML-Modell: {", ".join(fehlt)} fehlt'
    td, tr, me = m['testdaten'], m['trainingsdaten'], m['metrik']
    if not td.get('unabhaengig'):
        return 'unbewiesen', 'ML-Modell: Testdaten nicht als unabhaengig vom Training belegt'
    aus = []
    for k, v in m['eingaben'].items():
        b = (tr.get('bereich') or {}).get(k)
        if b is None:
            aus.append(f'{k}: Trainingsbereich unbekannt')
        elif not (b[0] <= v <= b[1]):
            aus.append(f'{k} = {v} ausserhalb {b}')
    if aus:
        return 'unbewiesen', 'ML-Modell extrapoliert: ' + '; '.join(aus)
    if not isinstance(me.get('wert'), (int, float)) or not isinstance(me.get('grenze'), (int, float)):
        return 'unbewiesen', 'ML-Modell: Metrik ohne Wert oder Grenze'
    if me['wert'] > me['grenze']:
        return 'verletzt', f'ML-Modell: {me.get("name")} {me["wert"]} > Grenze {me["grenze"]}'
    r = risiko(m)
    if r is None:
        return 'vorbehalt', 'ML-Modell: Risiko nicht eingestuft (einsatz, einfluss, folge)'
    if r >= 4 and (td.get('art') != 'messung' or not m.get('uq')):
        return 'unbewiesen', f'ML-Modell Risiko {r}: verlangt Testdaten aus Messungen und UQ'
    if not m.get('uq'):
        return 'vorbehalt', f'ML-Modell: {me.get("name")} {me["wert"]} <= {me["grenze"]}, aber ohne UQ'
    return 'bewiesen', f'ML-Modell {m["version"]}: {me.get("name")} {me["wert"]} <= {me["grenze"]}, im Trainingsbereich, mit UQ'
