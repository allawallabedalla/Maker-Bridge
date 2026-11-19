"""Fragen-Warteschlange in projekt.md (seit 19.11.2026, Regel des Nutzers: alle Fragen stellen, aber nur EINE je
Nachricht).

Abschnitt ``## Offene Fragen`` in projekt.md, eine Zeile je Frage:
    - [ ] (widerspruch) X3: Budget 0,5 °C ist so gross wie die Toleranz - Toleranz lockern oder genaueren ADC?
    - [x] (ziel) Stueckzahl? -> 1 (Nutzer 19.11.2026)
Reihenfolge (wichtigste zuerst): widerspruch (X-fehler) -> sicherheit (Folgen fuer Sicherheit/Messung, X-warnung)
-> ziel (Ziele/KPIs) -> komfort. Innerhalb einer Art bleibt die Reihenfolge des Einreihens.
Nichts faellt weg: eine beantwortete Frage wird abgehakt, nicht geloescht. Doppelte Fragen werden nicht neu eingereiht.
"""
import os
import re

ARTEN = ('widerspruch', 'sicherheit', 'ziel', 'komfort')
KOPF = '## Offene Fragen'
_ZEILE = re.compile(r'^- \[( |x)\] \((\w+)\) (.*?)(?: -> (.*))?$')


def _pfad(pdir):
    return os.path.join(pdir, 'projekt.md')


def _lesen(pdir):
    p = _pfad(pdir)
    text = open(p, encoding='utf-8').read() if os.path.exists(p) else ''
    zeilen = text.split('\n')
    if KOPF not in zeilen:
        return zeilen, None, None, []
    a = zeilen.index(KOPF)
    e = next((i for i in range(a + 1, len(zeilen)) if zeilen[i].startswith('## ')), len(zeilen))
    fragen = []
    for z in zeilen[a + 1:e]:
        m = _ZEILE.match(z.strip())
        if m:
            fragen.append({'offen': m.group(1) == ' ', 'art': m.group(2), 'frage': m.group(3), 'antwort': m.group(4)})
    return zeilen, a, e, fragen


def _schreiben(pdir, zeilen, a, e, fragen):
    rang = {k: i for i, k in enumerate(ARTEN)}
    offen = sorted([f for f in fragen if f['offen']], key=lambda f: rang.get(f['art'], len(ARTEN)))   # stabil
    erledigt = [f for f in fragen if not f['offen']]
    block = [KOPF, ''] + [f'- [ ] ({f["art"]}) {f["frage"]}' for f in offen] + \
        [f'- [x] ({f["art"]}) {f["frage"]} -> {f["antwort"]}' for f in erledigt] + ['']
    if a is None:
        neu = zeilen + ([''] if zeilen and zeilen[-1] else []) + block
    else:
        neu = zeilen[:a] + block + zeilen[e:]
    open(_pfad(pdir), 'w', encoding='utf-8').write('\n'.join(neu).rstrip('\n') + '\n')


def liste(pdir):
    """Alle Fragen, offene zuerst in Reihenfolge der Wichtigkeit."""
    return _lesen(pdir)[3]


def einreihen(pdir, frage, art):
    """Frage anhaengen (art aus ARTEN). Gleicher Text bereits vorhanden (offen oder beantwortet) -> nichts tun."""
    if art not in ARTEN:
        raise ValueError(f'art {art!r} unbekannt, erlaubt: {ARTEN}')
    frage = ' '.join(str(frage).split()).replace(' -> ', ' - ')
    zeilen, a, e, fragen = _lesen(pdir)
    if any(f['frage'] == frage for f in fragen):
        return {'neu': False, 'offen': sum(f['offen'] for f in fragen)}
    fragen.append({'offen': True, 'art': art, 'frage': frage, 'antwort': None})
    _schreiben(pdir, zeilen, a, e, fragen)
    return {'neu': True, 'offen': sum(f['offen'] for f in fragen)}


def naechste(pdir):
    """Die EINE Frage fuer die naechste Nachricht (oder None) und wie viele danach noch warten."""
    offen = [f for f in liste(pdir) if f['offen']]
    return {'frage': offen[0] if offen else None, 'danach_noch': max(len(offen) - 1, 0)}


def beantworten(pdir, frage, antwort):
    """Frage abhaken (Text oder Anfang des Texts) und die Antwort daneben schreiben."""
    zeilen, a, e, fragen = _lesen(pdir)
    treffer = [f for f in fragen if f['offen'] and f['frage'].startswith(' '.join(str(frage).split()))]
    if len(treffer) != 1:
        raise ValueError(f'{len(treffer)} offene Fragen passen zu {frage!r} - eindeutigen Anfang angeben')
    treffer[0].update(offen=False, antwort=' '.join(str(antwort).split()))
    _schreiben(pdir, zeilen, a, e, fragen)
    return naechste(pdir)


def aus_katalog(pdir, katalog):
    """Jeden Widerspruch (X-fehler -> widerspruch, X-warnung -> sicherheit) einreihen. Rueckgabe: Zahl neuer Fragen."""
    n = 0
    for e in (katalog or {}).get('widerspruch', []):
        if e.get('stufe') in ('fehler', 'warnung'):
            art = 'widerspruch' if e['stufe'] == 'fehler' else 'sicherheit'
            n += einreihen(pdir, f'{e["id"]} {e.get("titel", "")}: {e.get("hinweis", "")}'.strip(), art)['neu']
    return n
