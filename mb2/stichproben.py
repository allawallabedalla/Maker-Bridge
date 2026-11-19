"""Stichproben-Validierung: einzelne Realmessungen gegen Modellvorhersagen einstreuen (seit 19.11.2026).

Begriff (VVUQ.md): Abgleich mit der Wirklichkeit ist VALIDIERUNG (nicht Verifikation).

Datei ``stichproben.json`` im Projekt:
    {"modelle": {"<modell_id>": {
        "art": "katalog|fem", "ref": "E16" | "<fem-fall>", "groesse": "P_rx_dBm",
        "merkmale": ["elektronik.funk.r_m"],          # Bedingungen, die den Gueltigkeitsbereich aufspannen (soll-Pfade)
        "k": 2,
        "punkte": [{"bedingungen": {"elektronik.funk.r_m": 830}, "S": -132.7, "D": -134.0,
                    "u_D": 1.5, "u_num": 0.0, "u_input": 3.0, "datum": "2026-11-15", "quelle": "...",
                    "datenstatus": "gemessen|rueckfuehrbar_gemessen|demonstrationsdaten_nicht_rueckfuehrbar|simuliert"}]}}}
    S = Modellvorhersage bei genau diesen Bedingungen. Fehlt S und gleichen die Bedingungen dem aktuellen Entwurf, nimmt
    die Bridge die aktuelle Katalog-Vorhersage (wert bzw. daten[groesse]).

Regeln je Modell:
    1. Jeder Punkt einzeln nach V&V 20: E = S - D, u_val = sqrt(u_num^2 + u_input^2 + u_D^2), ok bei |E| <= k u_val.
       Ohne u_D zaehlt der Punkt nicht (Messunsicherheit ist Pflicht).
    2. Nur echte Messungen zaehlen (gemessen / rueckfuehrbar_gemessen); Demo- und Simulationsdaten werden gezeigt,
       aber ignoriert.
    3. EIN durchgefallener Punkt -> 'widerlegt': das Modell verliert seine Beweiskraft, bis es nachkalibriert ist.
    4. Validiert ist nur der gemessene Bereich (je Merkmal min ... max der Punkte). Liegt der aktuelle Entwurf ausserhalb
       -> 'extrapolation' (hoechstens vorbehalt).
    5. Alle Punkte ok und Entwurf im Bereich -> 'validiert'.
Messpunkte vorschlagen: Pruefungen mit der kleinsten Reserve (wert/grenze) und ohne Stichprobe, FEM-Eingaben mit der
groessten Empfindlichkeit (fem/sens), Ecken des Einsatzbereichs - so bringt die naechste Messung am meisten.
"""
import json
import math
import os

ECHT = ('gemessen', 'rueckfuehrbar_gemessen')


def lade(pdir):
    p = os.path.join(pdir, 'stichproben.json')
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {'modelle': {}}


def _feldwert(d, pfad):
    for t in pfad.split('.'):
        if not isinstance(d, dict) or t not in d:
            return None
        d = d[t]
    return d


def _vorhersage(mdl, katalog):
    if mdl.get('art') != 'katalog' or not katalog:
        return None
    for l in katalog.values():
        for e in l:
            if e.get('id') == mdl.get('ref'):
                g = mdl.get('groesse')
                v = (e.get('daten') or {}).get(g) if g else e.get('wert')
                if isinstance(v, (int, float)):
                    return v
    return None


def bewerte_modell(mdl, projekt, katalog=None):
    """{'status': validiert|widerlegt|extrapolation|ohne_punkte, 'text', 'punkte': [...], 'bereich': {...}}."""
    k = float(mdl.get('k', 2.0))
    aktuell = {m: _feldwert(projekt, m) for m in mdl.get('merkmale', [])}
    zeilen, gueltig = [], []
    for p in mdl.get('punkte', []):
        z = {'bedingungen': p.get('bedingungen', {}), 'datum': p.get('datum'), 'datenstatus': p.get('datenstatus')}
        S = p.get('S')
        if S is None and all(p.get('bedingungen', {}).get(m) == v for m, v in aktuell.items()):
            S = _vorhersage(mdl, katalog)
            z['S_aus'] = 'aktuelle Katalog-Vorhersage'
        if not isinstance(S, (int, float)) or not isinstance(p.get('D'), (int, float)):
            z['bewertung'] = 'ohne S oder D - nicht gewertet'
        elif not isinstance(p.get('u_D'), (int, float)):
            z['bewertung'] = 'ohne Messunsicherheit u_D - nicht gewertet'
        elif p.get('datenstatus') not in ECHT:
            z['bewertung'] = f'{p.get("datenstatus") or "datenstatus fehlt"} - nicht gewertet'
        else:
            u = math.sqrt(sum(float(p.get(n) or 0.0) ** 2 for n in ('u_num', 'u_input', 'u_D')))
            E = S - p['D']
            ok = abs(E) <= k * u
            z.update({n: p.get(n) for n in ('u_num', 'u_input', 'u_D')})
            z.update(S=S, D=p['D'], E=round(E, 6), u_val=round(u, 6), verhaeltnis=round(abs(E) / (k * u), 3) if u else
                     math.inf, bewertung='ok' if ok else 'durchgefallen')
            gueltig.append(z)
        zeilen.append(z)
    if not gueltig:
        return {'status': 'ohne_punkte', 'text': 'keine gewertete Stichprobe', 'punkte': zeilen, 'bereich': {}}
    bereich = {}
    for m in mdl.get('merkmale', []):
        werte = [z['bedingungen'].get(m) for z in gueltig if isinstance(z['bedingungen'].get(m), (int, float))]
        if werte:
            bereich[m] = [min(werte), max(werte)]
    schlecht = [z for z in gueltig if z['bewertung'] == 'durchgefallen']
    if schlecht:
        w = max(schlecht, key=lambda z: z['verhaeltnis'])
        return {'status': 'widerlegt', 'punkte': zeilen, 'bereich': bereich,
                'text': f'{len(schlecht)}/{len(gueltig)} Stichproben durchgefallen (schlechteste |E|/(k u_val) = '
                        f'{w["verhaeltnis"]}) - Modell nachkalibrieren'}
    aus = [f'{m} = {v} ausserhalb {bereich.get(m)}' for m, v in aktuell.items()
           if isinstance(v, (int, float)) and m in bereich and not (bereich[m][0] <= v <= bereich[m][1])]
    fehlt = [m for m, v in aktuell.items() if m not in bereich]
    if aus or fehlt:
        return {'status': 'extrapolation', 'punkte': zeilen, 'bereich': bereich,
                'text': f'{len(gueltig)} Stichproben ok, aber Entwurf ausserhalb des gemessenen Bereichs: '
                        + '; '.join(aus + [f'{m}: kein Punkt mit dieser Bedingung' for m in fehlt])}
    return {'status': 'validiert', 'punkte': zeilen, 'bereich': bereich,
            'text': f'an {len(gueltig)} Stichproben validiert (V&V 20, k = {k:g}), Entwurf im gemessenen Bereich'}


def bewerte(pdir, katalog=None):
    """{(art, ref): ergebnis} fuer alle Modelle mit Stichproben."""
    from .pruefungen import projekt_soll
    pj = projekt_soll(pdir)
    out = {}
    for mid, mdl in lade(pdir).get('modelle', {}).items():
        e = bewerte_modell(mdl, pj, katalog)
        e['modell'] = mid
        out[(mdl.get('art'), mdl.get('ref'))] = e
    return out


def eintragen(pdir, modell_id, punkt, art=None, ref=None, groesse=None, merkmale=None):
    """Stichprobe anhaengen; legt das Modell bei Bedarf an (art, ref, groesse, merkmale beim ersten Mal noetig)."""
    d = lade(pdir)
    mdl = d.setdefault('modelle', {}).setdefault(modell_id, {'punkte': []})
    for f, v in (('art', art), ('ref', ref), ('groesse', groesse), ('merkmale', merkmale)):
        if v is not None:
            mdl[f] = v
    if not mdl.get('art') or not mdl.get('ref'):
        raise ValueError('neues Modell braucht art (katalog|fem) und ref')
    mdl['punkte'].append(punkt)
    json.dump(d, open(os.path.join(pdir, 'stichproben.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    return {'modell': modell_id, 'punkte': len(mdl['punkte'])}


def vorschlagen(pdir, katalog, n=5):
    """Wo die naechste Messung am meisten bringt (sortiert): kleinste Reserve ohne Stichprobe, empfindlichste FEM-Eingabe."""
    sp = bewerte(pdir, katalog)
    kand = []
    for l in (katalog or {}).values():
        for e in l:
            w, g = e.get('wert'), e.get('grenze')
            if e.get('stufe') in ('ok', 'warnung') and isinstance(w, (int, float)) and isinstance(g, (int, float)) and g:
                reserve = abs(w - g) / abs(g)
                hat = ('katalog', e['id']) in sp and sp[('katalog', e['id'])]['status'] == 'validiert'
                if not hat:
                    kand.append((reserve, f'{e["id"]}{" [" + e["teil"] + "]" if e.get("teil") else ""}: Reserve '
                                          f'{reserve * 100:.0f} % ({w:g} gegen {g:g} {e.get("einheit", "")}), noch ohne '
                                          f'validierende Stichprobe - hier messen'))
    sd = os.path.join(pdir, 'fem', 'sens')
    if os.path.isdir(sd):
        for f in sorted(os.listdir(sd)):
            if f.endswith('.sens.json'):
                s = json.load(open(os.path.join(sd, f), encoding='utf-8'))
                for z in s.get('parameter', []):
                    el = z.get('elastizitaet')
                    if isinstance(el, (int, float)) and abs(el) > 0.5:
                        kand.append((1 / (1 + abs(el)), f'FEM {f[:-10]}: Ergebnis reagiert stark auf {z["parameter"]} '
                                                          f'(Elastizitaet {el:+.2f}) - diese Groesse real messen'))
    for (art, ref), e in sp.items():
        if e['status'] == 'extrapolation':
            kand.append((-1.0, f'{art} {ref}: {e["text"]} - Punkt bei den aktuellen Entwurfsbedingungen messen'))
        if e['status'] == 'widerlegt':
            kand.append((-2.0, f'{art} {ref}: {e["text"]}'))
    return [t for _, t in sorted(kand, key=lambda x: x[0])[:n]]
