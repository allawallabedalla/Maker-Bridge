"""Sensitivitaet eines FEM-Falls gegenueber seinen Eingaben (V&V-40-Faktor "Sensitivitaet", seit 17.11.2026).

Jede Eingabe wird um -rel und +rel verstellt und der Fall neu gerechnet (gecacht, Varianten in fem/sens/, damit audit
und die V-Matrix sie nicht als eigene Faelle zaehlen). Ergebnis fem/sens/<fall>.sens.json:
  parameter[]: Name, Kennzahl bei -rel / +rel, Elastizitaet (dK/K)/(dp/p), ok bei beiden Seiten
  robust: Bewertung bleibt bei jeder Variante ok;  vollstaendig: Standardsatz = alle Eingabegruppen verstellt
  basis_cache: Cache-Schluessel des Grundfalls - passt er nicht mehr, ist die Studie veraltet.
Standardsatz Mechanik: jede Last (kraft_N), jede Wegvorgabe, E-Modul und Festigkeit je Druckstoff.
Standardsatz Waerme: jede Waermequelle, Waermeuebergang h, Waermeleitung je Material.
Festigkeit wirkt nur auf die Bewertung (Sicherheit ~ Festigkeit) und wird ohne neue Rechnung ausgewertet.
"""
import copy
import json
import os

from .material import DRUCKSTOFFE


def _kennzahl(erg, art):
    bw = erg.get('bewertung') or {}
    if art == 'mechanik':   # wirksame Sicherheit (nach Realterm-Abminderung) - nur sie entscheidet ueber 'ok'
        w = bw.get('min_sicherheit_z_wirksam')
        return (w if w is not None else bw.get('min_sicherheit_z')), bool(bw.get('ok'))
    return erg.get('T_max_C'), bool(bw.get('ok'))


def standard(spec, art):
    """[(name, aenderung(spec, faktor) -> spec, analytisch)]"""
    out = []
    stoffe = sorted({k['material'].upper() for k in spec.get('koerper', []) if k.get('material')} - {'STARR'})
    if art == 'mechanik':
        for i, l in enumerate(spec.get('lasten', [])):
            out.append((f'last_{l.get("name", i)}', lambda s, f, i=i: _skal(s['lasten'][i], 'kraft_N', f), False))
        for i, l in enumerate(spec.get('lagerung', [])):
            if l.get('weg'):
                out.append((f'weg_{i}', lambda s, f, i=i: s['lagerung'][i].update(
                    weg={k: v * f for k, v in s['lagerung'][i]['weg'].items()}), False))
        for m in stoffe:
            out.append((f'E_{m}', lambda s, f, m=m: _mat(s, m, 'E_MPa', f), False))
        for m in stoffe:
            if m in DRUCKSTOFFE:
                out.append((f'festigkeit_{m}', None, True))
    else:
        for i, k in enumerate(spec.get('koerper', [])):
            if k.get('waerme_W'):
                out.append((f'quelle_{k.get("name", i)}', lambda s, f, i=i: _skal(s['koerper'][i], 'waerme_W', f),
                            False))
        if (spec.get('konvektion') or {}).get('h_W_m2K'):
            out.append(('h_konvektion', lambda s, f: _skal(s['konvektion'], 'h_W_m2K', f), False))
        for m in stoffe:
            out.append((f'k_{m}', lambda s, f, m=m: _mat(s, m, 'waermeleitung_W_mK', f), False))
    return out


def _skal(d, k, f):
    d[k] = [v * f for v in d[k]] if isinstance(d[k], list) else d[k] * f


def _mat(s, m, feld, f):
    from .material import MATERIAL
    s.setdefault('material_override', {}).setdefault(m, {})[feld] = MATERIAL[m][feld] * f


def studie(projekt, pdir, fall, art, rechne, rel=0.2, nur=None):
    """rechne(projekt, fall_pfad, art) -> erg (gecacht). nur = Liste von Parameternamen (sonst Standardsatz)."""
    spec_pfad = os.path.join(pdir, 'fem', fall + '.json')
    spec = json.load(open(spec_pfad, encoding='utf-8'))
    basis = rechne(projekt, fall, art)
    k0, ok0 = _kennzahl(basis, art)
    alle = standard(spec, art)
    wahl = [p for p in alle if not nur or p[0] in nur]
    os.makedirs(os.path.join(pdir, 'fem', 'sens'), exist_ok=True)
    zeilen = []
    for name, aendern, analytisch in wahl:
        z = {'parameter': name, 'rel': rel}
        for seite, f in (('minus', 1 - rel), ('plus', 1 + rel)):
            if analytisch:            # Sicherheit ~ Festigkeit, keine neue Rechnung noetig
                k = None if k0 is None else round(k0 * f, 3)
                ok = k is not None and k >= 2.0 if art == 'mechanik' else ok0
            else:
                s = copy.deepcopy(spec)
                aendern(s, f)
                vname = f'{fall}__{name}__{seite}'
                json.dump(s, open(os.path.join(pdir, 'fem', 'sens', vname + '.json'), 'w', encoding='utf-8'),
                          indent=1, ensure_ascii=False)
                k, ok = _kennzahl(rechne(projekt, 'sens/' + vname, art), art)
            z[seite] = {'kennzahl': k, 'ok': ok}
        km, kp = z['minus']['kennzahl'], z['plus']['kennzahl']
        z['elastizitaet'] = round((kp - km) / (2 * rel * k0), 3) if None not in (km, kp, k0) and k0 else None
        zeilen.append(z)
    erg = {'fall': fall, 'art': art, 'kennzahl': 'min_sicherheit_z' if art == 'mechanik' else 'T_max_C',
           'basis': {'kennzahl': k0, 'ok': ok0}, 'rel': rel, 'parameter': zeilen,
           'robust': ok0 and all(z['minus']['ok'] and z['plus']['ok'] for z in zeilen),
           'vollstaendig': not nur and bool(zeilen), 'basis_cache': basis.get('_cache'),
           'empfindlichste': max(zeilen, key=lambda z: abs(z['elastizitaet'] or 0))['parameter'] if zeilen else None}
    json.dump(erg, open(os.path.join(pdir, 'fem', 'sens', fall + '.sens.json'), 'w', encoding='utf-8'), indent=1,
              ensure_ascii=False)
    return erg
