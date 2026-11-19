"""Auftragskarten, Hochstufen, Laufsperre und kurzer Stand (Kriterium 6, seit 19.11.2026).

Vorbild: grenzland-forschung (Dirigent + Karten, gemessen: Opus-Anteil 93 % -> ~50 %). Grundsaetze:
- Der Leit-Agent entscheidet und gibt Karten aus; die Arbeit macht ein frischer Fachagent mit genau EINER Karte.
- Die ABNAHME prueft die Bridge selbst (audit), nicht der Agent: eine Karte ist erst erledigt, wenn ihr Mangel im
  naechsten audit fehlt. Was der Agent meldet, ist nur Notiz.
- Hochstufen statt wiederholen: jeder Fehlversuch geht eine Stufe hoeher (haiku -> sonnet -> opus). Nach der
  hoechsten Stufe kommt keine weitere Variante, sondern die Karte "Grundannahme pruefen" an den Leit-Agenten; scheitert
  auch die, ist der Nutzer dran. Nie zweimal dieselbe Karte auf derselben Stufe.
- Laufsperre (pruef/lauf.json) verhindert zwei gleichzeitige Laeufe; Bremse nach max_karten bzw. max_tokens je Lauf.
- Uebergabe zwischen Iterationen/Sitzungen nur ueber pruef/stand.md (hoechstens 5 KB), nie ueber den Chatverlauf.

Dateien: pruef/karten.json (Protokoll aller Karten), pruef/lauf.json (Sperre + Bremse), pruef/stand.md.
Tokens: die Bridge kann den Verbrauch eines Agenten nicht selbst messen. Meldet der Host ihn (Agent-Ergebnis), wird er
mit karte_ergebnis(..., tokens=) eingetragen und zaehlt fuer die Bremse; sonst steht er als unbekannt da, nie als 0.
"""
import datetime
import hashlib
import json
import os

STUFEN = ('haiku', 'sonnet', 'opus')
STAND_MAX = 5000
SPERRE_H = 3.0

# Mangel-Anfang -> (Agent, Startstufe, Auftrag). Reihenfolge = Vorrang (vorne zuerst abarbeiten).
REGELN = (
    ('Katalog-Pruefungen laufen nicht', 'leit', 'opus', 'Absturz der Pruefungen beheben (Code-Fehler, kein Projektfehler)'),
    ('V-Matrix laeuft nicht', 'leit', 'opus', 'Absturz der V-Matrix beheben'),
    ('Teil ', 'mb2-cad', 'sonnet', 'Teil so aendern, dass cad_build ok ist und alle Kaufteile eine Quelle haben'),
    ('board.step', 'mb2-elektronik', 'sonnet', 'kicad_board neu, danach cad_build'),
    ('DRC', 'mb2-elektronik', 'sonnet', 'DRC-Fehler beheben'),
    ('Keine Katze', 'mb2-elektronik', 'haiku', 'kicad_cat ausfuehren'),
    ('FEM ', 'mb2-fem', 'sonnet', 'FEM-Mangel beheben: nie gerechnet -> fem_mech/fem_waerme; Bewertung nicht ok -> Ursache '
                                  'und konkreten Konstruktionsvorschlag in projekt.md, Umsetzung als eigene Karte mb2-cad'),
    ('Katalog E', 'mb2-elektronik', 'sonnet', 'Katalog-Fehler der Elektronik beheben (Eingabe oder Entwurf)'),
    ('Katalog MK', 'mb2-elektronik', 'sonnet', 'Messkette: fehlende Eingabe mit Datenblatt-Beleg oder Entwurf aendern'),
    ('Katalog FW', 'mb2-elektronik', 'haiku', 'Firmware-Konstante an soll angleichen (oder soll begruenden)'),
    ('Katalog W', 'mb2-fem', 'sonnet', 'Waerme-Mangel beheben (Eingabe nachtragen oder Entwurf aendern)'),
    ('Katalog K', 'nutzer', None, 'Ziel- oder Kostenangabe fehlt bzw. widerspricht: als EINE Frage an den Nutzer (fragen)'),
    ('Katalog X', 'nutzer', None, 'Widerspruch in den Angaben: als EINE Frage an den Nutzer (fragen)'),
    ('Katalog ', 'mb2-cad', 'sonnet', 'Katalog-Fehler der Mechanik beheben (Eingabe nach FELDER.md oder Entwurf)'),
    ('Keine Druckplatte', 'mb2-cad', 'haiku', 'cad_plate mit allen Druckteilen'),
    ('Druckplatte aelter', 'mb2-cad', 'haiku', 'cad_plate neu'),
    ('Slicer-Profilpruefung', 'mb2-slicer', 'haiku', 'Profilproblem beheben und neu slicen'),
    ('Kein G-Code', 'mb2-slicer', 'haiku', 'slice_plate'),
    ('G-Code aelter', 'mb2-slicer', 'haiku', 'slice_plate neu'),
    ('bricklayers', 'mb2-slicer', 'haiku', 'slice_plate neu'),
    ('V-Matrix: ', 'leit', 'sonnet', 'Lastenheft-Mangel beheben (anforderungen.json: Herkunft, Eltern, Nachweis, Ebene)'),
)
# Anforderungs-Maengel sind Folgen; offen bleiben am Ende nur Abnahme/Feld -> Nutzer am Geraet
FOLGE = 'Anforderung '


def _p(pdir, f):
    return os.path.join(pdir, 'pruef', f)


def _lade(pdir, f, leer):
    p = _p(pdir, f)
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else leer


def _speichere(pdir, f, d):
    os.makedirs(os.path.join(pdir, 'pruef'), exist_ok=True)
    json.dump(d, open(_p(pdir, f), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)


def _jetzt():
    return datetime.datetime.now().isoformat(timespec='seconds')


def _schluessel(mangel):
    """Gleicher Mangel -> gleiche Karte, auch wenn sich Zahlen im Text aendern (Wert 1,12 -> 1,31)."""
    kopf = mangel.split(':')[0].strip()
    return hashlib.sha1(kopf.encode()).hexdigest()[:8], kopf


def regel(mangel):
    for anfang, agent, stufe, auftrag in REGELN:
        if mangel.startswith(anfang):
            return agent, stufe, auftrag
    return None


# ---------------------------------------------------------------------------------------------- Laufsperre/Bremse

def lauf_start(pdir, max_karten=20, max_tokens=None, sperre_h=SPERRE_H, jetzt=None):
    """Sperre setzen. Laeuft schon ein Lauf (Sperre juenger als sperre_h), -> {'ok': False}: sofort enden."""
    t = jetzt or datetime.datetime.now()
    l = _lade(pdir, 'lauf.json', {})
    if l.get('belegt_seit'):
        alt = datetime.datetime.fromisoformat(l['belegt_seit'])
        if (t - alt).total_seconds() < sperre_h * 3600:
            return {'ok': False, 'grund': f'Lauf seit {l["belegt_seit"]} aktiv (Sperre {sperre_h} h) - sofort enden'}
    nr = int(l.get('nr', 0)) + 1
    _speichere(pdir, 'lauf.json', {'nr': nr, 'belegt_seit': t.isoformat(timespec='seconds'), 'max_karten': max_karten,
                                   'max_tokens': max_tokens, 'karten': 0, 'tokens': 0, 'tokens_unbekannt': 0})
    return {'ok': True, 'lauf': nr}


def lauf_ende(pdir, grund=''):
    l = _lade(pdir, 'lauf.json', {})
    l.update(belegt_seit=None, ende=_jetzt(), ende_grund=grund)
    _speichere(pdir, 'lauf.json', l)
    stand(pdir)
    return {'ok': True, 'lauf': l.get('nr'), 'karten': l.get('karten'), 'tokens': l.get('tokens'),
            'tokens_unbekannt': l.get('tokens_unbekannt')}


def _bremse(pdir):
    l = _lade(pdir, 'lauf.json', {})
    if not l.get('belegt_seit'):
        return 'kein Lauf aktiv - erst lauf_start'
    if l.get('max_karten') and l.get('karten', 0) >= l['max_karten']:
        return f'Bremse: {l["karten"]} Karten in diesem Lauf (Grenze {l["max_karten"]})'
    if l.get('max_tokens') and l.get('tokens', 0) >= l['max_tokens']:
        return f'Bremse: {l["tokens"]} Tokens in diesem Lauf (Grenze {l["max_tokens"]})'
    return None


# ---------------------------------------------------------------------------------------------- Karten

def _naechste_stufe(agent, start, versuche):
    """Stufe fuer den naechsten Versuch: Start, dann je Fehlversuch eine hoeher; danach 'grundannahme', dann 'nutzer'."""
    fehl = [v for v in versuche if v['status'] == 'fehler']
    if not fehl:
        return start
    i = STUFEN.index(start) + len([v for v in fehl if v['stufe'] in STUFEN])
    if i < len(STUFEN):
        return STUFEN[i]
    return 'grundannahme' if not any(v['stufe'] == 'grundannahme' for v in fehl) else 'nutzer'


def karte_text(k):
    """Der ganze Auftrag an einen frischen Agenten (in sich vollstaendig, keine Vorgeschichte)."""
    return '\n'.join([
        f'KARTE {k["id"]} · {k["agent"]} · {k["stufe"]}',
        f'PROJEKT: {k["projekt"]}',
        f'ZIEL: {k["auftrag"]}',
        f'MANGEL (aus audit): {k["mangel"]}',
        'REGELN: Nur diesen Mangel bearbeiten. Nur Dateien des Projekts aendern, die dafuer noetig sind. Keine '
        'Installation, nichts loeschen, nicht drucken, keine weiteren Agenten. Fehlt eine Angabe: aufhoeren und sie in '
        'der Rueckgabe nennen (nicht raten, nicht schoenen). Werte nur mit Quelle (_herkunft).',
        'ABNAHME (prueft die Bridge, nicht du): im naechsten audit gibt es keinen Mangel, der so beginnt: '
        f'"{k["kopf"]}"',
        'RUECKGABE (hoechstens 10 Zeilen): OK|FEHLER · geaenderte Dateien · fehlende Angabe oder Grund',
    ] + ([f'VORVERSUCHE: {k["vorversuche"]}'] if k.get('vorversuche') else []))


def naechste(pdir, audit_erg, projekt=None):
    """Aus dem audit die EINE naechste Karte. Rueckgabe {'stop': fertig|nutzer|bremse|...} oder {'karte': {...}}."""
    b = _bremse(pdir)
    if b:
        return {'stop': 'bremse', 'grund': b}
    maengel = audit_erg.get('maengel') or []
    log = _lade(pdir, 'karten.json', {'karten': []})
    offen = [k for k in log['karten'] if k['status'] == 'ausgegeben']
    if offen:
        return {'stop': 'karte_offen', 'grund': f'Karte {offen[-1]["id"]} ist ausgegeben, erst karte_ergebnis', 'karte': offen[-1]}
    arbeit = []
    for m in maengel:
        r = regel(m)
        if r:
            arbeit.append((REGELN.index(next(x for x in REGELN if m.startswith(x[0]))), m, r))
    if not arbeit:
        rest = [m for m in maengel if m.startswith(FOLGE)]
        if audit_erg.get('freigabe') == 'fertig' and not maengel:
            return {'stop': 'fertig', 'grund': 'freigabe fertig, keine Maengel'}
        if audit_erg.get('freigabe') == 'druckfertig' and not [m for m in maengel if not m.startswith(FOLGE)]:
            return {'stop': 'nutzer', 'grund': 'druckfertig - jetzt drucken, Abnahme am Geraet und Feldwerte durch den '
                                               'Nutzer (abnahme_eintragen, feld_eintragen)', 'offen': rest[:5]}
        return {'stop': 'nutzer', 'grund': 'nur noch Folge-Maengel ohne Karte - Leit-Agent prueft die Anforderungen',
                'offen': rest[:5]}
    arbeit.sort(key=lambda x: x[0])
    _, mangel, (agent, start, auftrag) = arbeit[0]
    kid, kopf = _schluessel(mangel)
    versuche = [k for k in log['karten'] if k['schluessel'] == kid]
    # nach einem erfolgreichen Versuch kehrt der Mangel zurueck -> neue Runde (Wippe), Zaehlung neu
    letzte_ok = max((i for i, k in enumerate(versuche) if k['status'] == 'ok'), default=-1)
    versuche = versuche[letzte_ok + 1:]
    if agent == 'nutzer':
        stufe = 'nutzer'
    else:
        stufe = _naechste_stufe(agent, start, versuche)
    if stufe == 'nutzer':
        return {'stop': 'nutzer', 'grund': f'{kopf}: {auftrag if agent == "nutzer" else "alle Stufen und die Grundannahme gescheitert"}'
                                           ' - EINE Frage an den Nutzer (fragen)', 'mangel': mangel}
    if stufe == 'grundannahme':
        agent, auftrag = 'leit', (f'Grundannahme pruefen: {len(versuche)} Versuche bis {STUFEN[-1]} ohne Erfolg. Nicht '
                                  'Variante 4 bauen - welche Annahme hinter dem Entwurf ist falsch? Neue Vorgabe schreiben.')
    k = {'id': f'{kid}-{len(versuche) + 1}', 'schluessel': kid, 'kopf': kopf, 'mangel': mangel, 'agent': agent,
         'stufe': stufe, 'modell': stufe if stufe in STUFEN else 'opus', 'auftrag': auftrag,
         'projekt': projekt or os.path.basename(pdir), 'status': 'ausgegeben', 'ausgegeben': _jetzt(),
         'vorversuche': '; '.join(f'{v["stufe"]}: {v.get("notiz") or v["status"]}' for v in versuche)}
    k['text'] = karte_text(k)
    log['karten'].append(k)
    _speichere(pdir, 'karten.json', log)
    l = _lade(pdir, 'lauf.json', {})
    l['karten'] = l.get('karten', 0) + 1
    _speichere(pdir, 'lauf.json', l)
    return {'karte': k}


def ergebnis(pdir, audit_erg, notiz='', tokens=None):
    """Ausgegebene Karte abschliessen. ok entscheidet das audit: Mangel mit gleichem Kopf noch da -> fehler."""
    log = _lade(pdir, 'karten.json', {'karten': []})
    offen = [k for k in log['karten'] if k['status'] == 'ausgegeben']
    if not offen:
        return {'ok': False, 'grund': 'keine Karte ausgegeben'}
    k = offen[-1]
    noch = [m for m in audit_erg.get('maengel') or [] if _schluessel(m)[0] == k['schluessel']]
    k.update(status='fehler' if noch else 'ok', ende=_jetzt(), notiz=' '.join(str(notiz).split())[:300],
             tokens=tokens, mangel_danach=noch[0] if noch else None)
    _speichere(pdir, 'karten.json', log)
    l = _lade(pdir, 'lauf.json', {})
    if isinstance(tokens, (int, float)):
        l['tokens'] = l.get('tokens', 0) + tokens
    else:
        l['tokens_unbekannt'] = l.get('tokens_unbekannt', 0) + 1
    _speichere(pdir, 'lauf.json', l)
    stand(pdir, audit_erg)
    return {'ok': not noch, 'karte': k['id'], 'status': k['status'], 'mangel_danach': k['mangel_danach']}


def kosten(pdir):
    """Kosten je Agent und Stufe aus dem Kartenprotokoll (Grundlage fuer die Modellwahl)."""
    out = {}
    for k in _lade(pdir, 'karten.json', {'karten': []})['karten']:
        z = out.setdefault(f'{k["agent"]}/{k["stufe"]}', {'karten': 0, 'ok': 0, 'tokens': 0, 'tokens_unbekannt': 0})
        z['karten'] += 1
        z['ok'] += k['status'] == 'ok'
        if isinstance(k.get('tokens'), (int, float)):
            z['tokens'] += k['tokens']
        else:
            z['tokens_unbekannt'] += 1
    return out


# ---------------------------------------------------------------------------------------------- Stand (Uebergabe)

def stand(pdir, audit_erg=None):
    """pruef/stand.md, hoechstens 5 KB: alles, was die naechste Iteration oder Sitzung braucht - und nichts sonst."""
    from . import fragen
    v = _lade(pdir, 'v_matrix.json', {})
    maengel = (audit_erg or {}).get('maengel')
    log = _lade(pdir, 'karten.json', {'karten': []})['karten']
    l = _lade(pdir, 'lauf.json', {})
    fr = fragen.naechste(pdir)
    z = [f'# Stand {os.path.basename(pdir)} ({_jetzt()})', '',
         f'- Freigabe: **{(audit_erg or {}).get("freigabe") or v.get("freigabe") or "unbekannt"}**',
         f'- Lauf: {"aktiv seit " + l["belegt_seit"] if l.get("belegt_seit") else "frei"} '
         f'(Lauf {l.get("nr", 0)}, {l.get("karten", 0)} Karten, Tokens {l.get("tokens", 0)}'
         f'{", " + str(l.get("tokens_unbekannt")) + " ohne Angabe" if l.get("tokens_unbekannt") else ""})']
    if maengel is not None:
        z += ['', f'## Maengel ({len(maengel)})'] + [f'- {m[:160]}' for m in maengel[:5]]
        if len(maengel) > 5:
            z.append(f'- ... {len(maengel) - 5} weitere (audit)')
    offen = [k for k in log if k['status'] == 'ausgegeben']
    z += ['', '## Karten'] + ([f'- AUSGEGEBEN {offen[-1]["id"]} {offen[-1]["agent"]}/{offen[-1]["stufe"]}: '
                               f'{offen[-1]["kopf"][:100]}'] if offen else []) + \
        [f'- {k["status"]} {k["id"]} {k["agent"]}/{k["stufe"]}: {k["kopf"][:80]}' for k in log[-5:] if k not in offen]
    z += ['', '## Naechste Frage an den Nutzer',
          f'- {fr["frage"]["frage"][:200]} (danach noch {fr["danach_noch"]})' if fr['frage'] else '- keine']
    text = '\n'.join(z) + '\n'
    if len(text.encode('utf-8')) > STAND_MAX:
        text = text.encode('utf-8')[:STAND_MAX - 40].decode('utf-8', 'ignore') + '\n... (gekuerzt auf 5 KB)\n'
    os.makedirs(os.path.join(pdir, 'pruef'), exist_ok=True)
    open(_p(pdir, 'stand.md'), 'w', encoding='utf-8').write(text)
    return text
