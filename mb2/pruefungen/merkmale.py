"""Projektmerkmale fuer den Ausloeser-Mechanismus (Audit Scheinsicherheit 15.11.2026, Muster A).

Eine Pruefung, die wegen fehlender Eingabe 'uebersprungen' meldet, waehrend der Entwurf das Merkmal erkennbar enthaelt
(Funk, Akku, aussen, Schrauben, ...), taeuscht Sicherheit vor. ``merkmale(pdir)`` sammelt einmal je Projekt, welche
Merkmale vorliegen und woran sie erkannt wurden. ``AUSLOESER`` (in ``__init__``) ordnet jedem Merkmal die Pruef-IDs zu,
deren Ueberspringen dann ein 'fehler' ist (Verzicht nur ausdruecklich ueber ``_projekt.nicht_relevant``).

Quellen, je billig und ohne Rechnung: cad/soll.json, projekt.md (Stichworte), Dateinamen unter electronics/ (Kaufmodule
als STEP), bauteile.json, die KiCad-Platine (ueber elektronik.merkmale_platine), fem/*.json, print/slice.json.
Ein explizites soll-Feld geht immer vor (z. B. ``aussen: false`` schaltet die Stichwortsuche ab).
"""
import json
import os
import re

from . import soll as _soll

# Stichworte (klein, ohne Umlaute verglichen). Nur eindeutige Begriffe, damit nicht jedes Projekt alles ausloest.
STICHWORTE = {
    'funk': r'\blora\b|sx12[67]\d|sx127\d|rak3172|rak\d{4}|esp32|esp8266|\bwlan\b|\bwifi\b|bluetooth|\bble\b|zigbee|'
            r'\bthread\b|\bmatter\b|nrf52|cc1101|rfm9\d|\bantenne\b|\bsma\b|ipex|u\.fl|868 ?mhz|433 ?mhz|2[,.]4 ?ghz|\bt3\b',
    'akku': r'\bakku|\blipo\b|li-?ion|li-?po|18650|14500|\bbatterie|\bl91\b|\bcr2032|\bcr123|lifepo|\bknopfzelle',
    # NICHT bloss "aussen" (Aussenmass, aussen liegend ...): nur Einsatzorte
    'aussen': r'aussenbereich|aussenmontage|aussen montiert|draussen|outdoor|im freien|\bgarten|\bbeet\b|balkon|'
              r'wetterfest|\bregen\b|fahrrad|dachrinne|\bgiebel|\bwald\b|\bwiese|terrasse|briefkasten|\bip6[5-8]',
    'schrauben': r'schraube|\bm2\b|\bm3\b|\bm4\b|\bm5\b|einschmelz|ruthex|\binsert',
    'schnapper': r'schnapp|rastnase|clip\b|klipp',
    'handgeraet': r'handgeraet|tragbar|in der hand|fernbedienung|hosentasche|schluesselanhaenger|wearable',
    'anregung': r'\bmotor|luefter|vibration|fahrrad|\brad\b|\bauto\b|kfz|schrittmotor|pumpe',
    'lautsprecher': r'lautsprecher|speaker|buzzer|\bsummer\b|piezo',
    'dauerlast': r'vorspann|presssitz|pressitz|dauerlast|dauerhaft belastet|traegt dauerhaft',
    'fluid': r'durchfluss|volumenstrom|\bschlauch|mikrofluid|\bkanal\b.*\b(wasser|fluessig|gas)|leckage|\bpumpe|ventil\b',
    'daten': r'datenlogger|\blogger\b|aufzeichn|sd-?karte|speichert die (mess)?daten|messdaten speichern|\bflash-?speicher',
    'firmware': r'firmware|\.ino|arduino|platformio|esp-idf|micropython',
}


def _norm(t):
    return (t.lower().replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss'))


def _text(pdir):
    teile = []
    for f in ('projekt.md', 'README.md'):
        p = os.path.join(pdir, f)
        if os.path.exists(p):
            # offene Vorlagenzeilen von project_new ("- akku_mAh: **offen** (...)") nennen Begriffe nur als Frage
            teile.append('\n'.join(z for z in open(p, encoding='utf-8', errors='replace').read().splitlines()
                                   if '**offen**' not in z))
    el = os.path.join(pdir, 'electronics')
    if os.path.isdir(el):
        teile.append(' '.join(os.listdir(el)))
        b = os.path.join(el, 'bauteile.json')
        if os.path.exists(b):
            teile.append(open(b, encoding='utf-8', errors='replace').read())
    return _norm('\n'.join(teile))


def _fem_mech(pdir):
    fd = os.path.join(pdir, 'fem')
    if not os.path.isdir(fd):
        return False
    for f in os.listdir(fd):
        if f.endswith('.erg.json'):
            try:
                if 'lastfaelle' in json.load(open(os.path.join(fd, f), encoding='utf-8')):
                    return True
            except (OSError, ValueError):
                continue
    return False


def _messtechnik(pdir):
    p = os.path.join(pdir, 'anforderungen.json')
    try:
        return any(a.get('messtechnik') for a in json.load(open(p, encoding='utf-8')).get('anforderungen', []))
    except (OSError, ValueError):
        return False


def merkmale(pdir):
    """{merkmal: {'aktiv': bool, 'quelle': str}} – nur aktive Merkmale tragen eine Quelle."""
    s = _soll(pdir)
    pj = s.get('_projekt', {})
    el = pj.get('elektronik', {}) or {}
    txt = _text(pdir)
    teile = {k: v for k, v in s.items() if k != '_projekt' and isinstance(v, dict)}
    m = {}

    def setze(name, aktiv, quelle):
        if aktiv and not m.get(name, {}).get('aktiv'):
            m[name] = {'aktiv': True, 'quelle': quelle}
        m.setdefault(name, {'aktiv': False, 'quelle': ''})

    def wort(name):
        t = re.search(STICHWORTE[name], txt)
        return f'Stichwort "{t.group(0)}" in projekt.md/electronics' if t else None

    # Platine (falls vorhanden): genaueste Quelle
    platine = {}
    try:
        from . import elektronik
        platine = elektronik.merkmale_platine(pdir) or {}
    except Exception:  # noqa: BLE001 - ohne lesbare Platine bleiben die anderen Quellen
        platine = {}

    module = [x for x in (el.get('module') or []) if isinstance(x, dict)]
    # Funk
    setze('funk', bool(el.get('funk')), 'soll.json elektronik.funk')
    setze('funk', any(x.get('funk') for x in module), 'soll.json elektronik.module[].funk')
    setze('funk', platine.get('funk'), 'KiCad: HF-Netz/Antenne/Funkmodul')
    setze('funk', bool(wort('funk')), wort('funk') or '')
    # Akku/Batterie
    setze('akku', pj.get('akku_mAh') is not None, 'soll.json akku_mAh')
    setze('akku', platine.get('akku'), 'KiCad: Lader/Schutz-IC/Batteriehalter')
    setze('akku', any(x.get('akku') for x in module), 'soll.json elektronik.module[].akku')
    setze('akku', bool(wort('akku')), wort('akku') or '')
    # Aussen: explizites soll geht vor
    if 'aussen' in pj:
        m['aussen'] = {'aktiv': bool(pj['aussen']), 'quelle': 'soll.json _projekt.aussen' if pj['aussen'] else ''}
    else:
        setze('aussen', pj.get('T_min_C') is not None and pj['T_min_C'] < 5, 'soll.json T_min_C < 5 C')
        setze('aussen', bool(wort('aussen')), wort('aussen') or '')
        r = (el.get('funk') or {}).get('r_m')
        setze('aussen', bool(r and r > 50 and (el.get('funk') or {}).get('umgebung') not in ('innen',)),
              'Funkstrecke > 50 m')
    # Elektronik im Gehaeuse (Verlustleistung -> Teiltemperatur ueber Raumluft)
    eld = os.path.join(pdir, 'electronics')
    hat_el = os.path.isdir(eld) and any(f.lower().endswith(('.kicad_pcb', '.step', '.stp')) for f in os.listdir(eld))
    setze('elektronik', hat_el or bool(platine), 'Dateien unter electronics/')
    # Mechanische Merkmale: soll oder Stichwort
    setze('schrauben', any(t.get('schrauben') for t in teile.values()), 'soll.json schrauben')
    setze('schrauben', bool(wort('schrauben')), wort('schrauben') or '')
    setze('schnapper', any(t.get('schnapper') for t in teile.values()), 'soll.json schnapper')
    setze('schnapper', bool(wort('schnapper')), wort('schnapper') or '')
    setze('dauerlast', any(t.get('dauerlast') for t in teile.values()) or bool(pj.get('dauerlast')), 'soll.json dauerlast')
    setze('dauerlast', bool(wort('dauerlast')), wort('dauerlast') or '')
    # Handgeraet: Stichwort oder Akku ohne Befestigungs-Hinweis
    setze('handgeraet', pj.get('fallhoehe_m') is not None, 'soll.json fallhoehe_m')
    setze('handgeraet', bool(wort('handgeraet')), wort('handgeraet') or '')
    setze('anregung', pj.get('anregung_Hz') is not None, 'soll.json anregung_Hz')
    setze('anregung', bool(wort('anregung')), wort('anregung') or '')
    setze('lautsprecher', bool(pj.get('lautsprecher') or el.get('lautsprecher_Ohm')), 'soll.json lautsprecher')
    setze('lautsprecher', platine.get('lautsprecher'), 'KiCad: Verstaerker/Lautsprecher')
    setze('lautsprecher', bool(wort('lautsprecher')), wort('lautsprecher') or '')
    setze('firmware', bool(pj.get('firmware')), 'soll.json _projekt.firmware')
    setze('firmware', bool(wort('firmware')), wort('firmware') or '')
    setze('ziele', bool(pj.get('ziele')), 'soll.json _projekt.ziele')
    setze('fluid', bool(pj.get('stroemung')) or any(t.get('stroemung') for t in teile.values()), 'soll.json stroemung')
    setze('fluid', bool(wort('fluid')), wort('fluid') or '')
    setze('daten', bool(pj.get('daten')), 'soll.json _projekt.daten')
    setze('daten', bool(wort('daten')), wort('daten') or '')
    # Messfunktion: Messkette im soll oder messtechnische Anforderung im Lastenheft
    setze('messung', bool(pj.get('messkette')), 'soll.json _projekt.messkette')
    setze('messung', _messtechnik(pdir), 'anforderungen.json messtechnik')
    # Rechenstand
    setze('fem_mech', _fem_mech(pdir), 'fem/*.erg.json mit Mechanik-Lastfaellen')
    setze('gesliced', os.path.exists(os.path.join(pdir, 'print', 'slice.json')), 'print/slice.json')
    return m


def aktiv(m, name):
    return bool((m.get(name) or {}).get('aktiv'))
