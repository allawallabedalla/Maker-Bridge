"""Anforderungen nach dem V-Modell, Beweispflicht, Herkunft, Abnahme am Geraet und Feldabgleich (seit 15.11.2026).

Kernproblem (audits/KERNPROBLEM_2026-11-15.md): Gruen hiess "keine Pruefung hat angeschlagen". Jetzt gilt:
**Ein Projekt ist erst frei, wenn jede Anforderung einen bestandenen, belegten Nachweis auf der passenden V-Ebene hat.**

V-Modell in mb2 (links Entwurf, rechts Nachweis auf derselben Hoehe):

    system      (Lastenheft: was das Geraet im Einsatz koennen muss)  <->  abnahme (am Geraet) + feld (im Einsatz)
    subsystem   (Pflichtenheft: Elektronik, Gehaeuse, Firmware, Montage) <->  integration (Katalog-Systempruefungen, FEM)
    komponente  (Teil, Platine, Firmware-Konstante)                     <->  komponente (cad_build, ERC/DRC, Katalog je Teil)

Dateien je Projekt (alle JSON, von Menschen und Agenten lesbar):
- ``anforderungen.json``  {"anforderungen": [Anforderung]}
- ``abnahme.json``        Abnahmeprotokoll: Schritte mit Soll, Ist, Datum (aus den Anforderungen erzeugt, Ist bleibt erhalten)
- ``feld.json``           Messungen im Einsatz {"messungen": [{groesse, wert, einheit, datum, ort, quelle}]}
- ``messung.json``        Referenzmessreihen (Kalibrierung, Pruefstand) {"reihen": [Reihe]} - Format in
                          ``mb2/pruefungen/messkette.py`` (seit 19.11.2026)

Anforderung:
    {"id": "A-FUNK", "ebene": "system|subsystem|komponente", "eltern": ["A-..."], "text": "...",
     "herkunft": "Nutzer 15.11.2026 | abgeleitet aus A-..",       # WER es verlangt (Rueckverfolgbarkeit nach oben)
     "eingaben": ["elektronik.funk.r_m", ...],                    # soll-Felder, auf denen der Nachweis beruht
     "nachweise": [Nachweis], "notiz": "..."}
Nachweis:
    {"art": "katalog|cad|fem|slice|kicad|abnahme|feld|manuell", "ref": "E16" | "<teil>" | "<fall>" | "alle" | "<schritt>",
     "teil": "..." (optional, katalog), "stufe": "komponente|integration|abnahme|feld",
     "kriterium": {"groesse": "snr_dB", "op": ">=", "wert": -5, "einheit": "dB"}   # abnahme/feld
     "warnung_akzeptiert": "Begruendung"   # sonst zaehlt eine Warnung als NICHT bewiesen
     "beleg": "Pfad/Foto", "geprueft_von": "..."}                   # manuell
     "modell": {"frage", "einsatz", "einfluss", "folge", "validierung", "anwendbarkeit"}  # fem: V&V 40, glaubwuerdigkeit.py
     "eigenschaft": "genauigkeit|linearitaet|hysterese|drift|wiederholbarkeit|messbereich"  # messung: ref = Reihen-ID
Messtechnische Anforderung (seit 19.11.2026): zusaetzlich ein Block ``messtechnik``
    {"messbereich": {"min": 0, "max": 100, "einheit": "°C"},
     "genauigkeit": {"max_abs": 0.5, "einheit": "°C", "bezug": "einzelwert|mittelwert"},   # Voreinstellung einzelwert
     "linearitaet": {"max_abs": 0.2, "einheit": "%FS"},
     "hysterese": {"max_abs": 0.2, "einheit": "%FS"}, "drift": {"max_abs": 0.1, "einheit": "°C/Jahr"},
     "wiederholbarkeit": {"max_abs": 0.05, "einheit": "°C"},         # Standardabweichung
     "definition_genauigkeit": "max. Betrag der Abweichung zur Referenz ueber den Messbereich",
     "bedingungen": {"T_umgebung_C": [20, 26], "U_V": 3.3, "einschwingzeit_s": 300, "messintervall_s": 10},
     "wiederholungen": 10, "dauer_h": 720, "verfahren": "...", "referenzmittel": "..."}
    Jede angegebene Eigenschaft braucht einen eigenen Nachweis ``art: messung`` mit passender ``eigenschaft``,
    sonst Matrix-Mangel. Ohne Messreihe bleibt sie 'unbewiesen' (Grund ``ohne_referenzmessung``); Mindestverfahren,
    Rueckfuehrung der Referenz und Pruefbedingungen prueft ``messkette.bewerte_reihe``.
Herkunft der Eingaben: ``_projekt._herkunft`` (bzw. je Teil ``_herkunft``) {"feld.pfad": "gemessen|datenblatt|norm|
berechnet|geschaetzt|angenommen: Beleg"}. Ein Nachweis auf geschaetzten/angenommenen Eingaben ist nur 'vorbehalt'.

Status je Anforderung: 'bewiesen' | 'vorbehalt' (bestanden, aber auf Annahmen/zu knapper Reserve) | 'unbewiesen' |
'verletzt'. Freigabe: 'nicht_druckfertig' (Komponente/Subsystem nicht bewiesen) -> 'druckfertig' (alles bis Integration
bewiesen) -> 'fertig' (auch Abnahme + Feld bewiesen).
"""
import datetime
import hashlib
import json
import os
import re

from . import glaubwuerdigkeit

EBENEN = ('stakeholder', 'system', 'subsystem', 'komponente')
# stakeholder (seit 19.11.2026, nach Liu et al. 2025): Wunsch in Worten des Nutzers/Kunden, validiert im Einsatz;
# system = daraus HERGELEITETE messbare Spezifikation (Feld 'herleitung': Rechnung oder Begruendung).
STUFEN_JE_EBENE = {'stakeholder': ('feld', 'abnahme'), 'system': ('abnahme', 'feld'),
                   'subsystem': ('integration', 'abnahme', 'feld'),
                   'komponente': ('komponente', 'integration')}
HERKUNFT_STARK = ('gemessen', 'datenblatt', 'norm', 'berechnet')
HERKUNFT_SCHWACH = ('geschaetzt', 'angenommen')
# Unsicherheit je Herkunft: relativ bzw. in dB (Funk). Reserve muss groesser sein, sonst 'vorbehalt'.
UNSICHERHEIT_REL = {'gemessen': 0.05, 'datenblatt': 0.10, 'norm': 0.10, 'berechnet': 0.10, 'geschaetzt': 0.30,
                    'angenommen': 0.50, None: 0.30}
UNSICHERHEIT_DB = {'gemessen': 3.0, 'datenblatt': 6.0, 'norm': 6.0, 'berechnet': 6.0, 'geschaetzt': 10.0,
                   'angenommen': 15.0, None: 10.0}
# Lageabhaengige Woerter in Anweisungen: nur mit eindeutiger Markierung zulaessig (Bodenklima: Klemmen gespiegelt)
LAGEWOERTER = r'\b(links|rechts|oben|unten|vorne|hinten|linke|rechte|obere|untere)\b'
MARKIERUNG = r'pin ?\d|dreieck|eckig|markier|aufdruck|beschrift|farbe|rot|schwarz|weiss|gelb|gruen|blau|j\d|nase|kerbe'
RAUSCHEN_125K_DBM = -174 + 10 * 5.0969 + 6     # -174 dBm/Hz + 10 log10(125 kHz) + NF 6 dB = -117 dBm


# ---------------------------------------------------------------------------------------------- Laden/Speichern

def _pfad(pdir, name):
    return os.path.join(pdir, name)


def lade(pdir, name, leer):
    p = _pfad(pdir, name)
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else leer


def speichere(pdir, name, daten):
    json.dump(daten, open(_pfad(pdir, name), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)


def kontext_hash(pdir):
    """Hash aller Eingaben, von denen Urteile abhaengen: soll, projekt.md (Merkmale), Anforderungen, Abnahme, Feld,
    Messungen, Kosten und die Firmware-Dateien mit Pruefwirkung (_projekt.firmware). Jede Aenderung macht eine an den
    Hash gebundene menschliche Freigabe ungueltig."""
    h = hashlib.sha1()
    dateien = ['cad/soll.json', 'projekt.md', 'anforderungen.json', 'abnahme.json', 'feld.json', 'messung.json',
               'kosten.json', 'stichproben.json']
    fw = (_soll(pdir).get('_projekt', {}) or {}).get('firmware') or {}
    for k in (fw.get('konstanten') or {}).values():
        if k.get('datei'):
            dateien.append(os.path.join(fw.get('pfad', ''), k['datei']))
    for f in sorted(set(dateien)):
        p = f if os.path.isabs(f) else os.path.join(pdir, f)
        if os.path.exists(p):
            h.update(f.encode())
            h.update(open(p, 'rb').read())
    return h.hexdigest()[:16]


def _soll(pdir):
    return lade(pdir, 'cad/soll.json', {})


def _feldwert(d, pfad):
    for t in pfad.split('.'):
        if not isinstance(d, dict) or t not in d:
            return None
        d = d[t]
    return d


# ---------------------------------------------------------------------------------------------- Herkunft

def herkunft_von(soll, pfad):
    """(klasse, text) fuer ein soll-Feld 'a.b.c' (projektweit) oder 'Teil:a.b'. Klasse None = nicht angegeben."""
    teil, _, f = pfad.rpartition(':')
    quelle = (soll.get(teil, {}) if teil else soll.get('_projekt', {})).get('_herkunft', {}) or {}
    txt = quelle.get(f)
    if txt is None:      # Elternfeld deckt Kinder ab ("elektronik.funk": "gemessen: ...")
        teile = f.split('.')
        for i in range(len(teile) - 1, 0, -1):
            txt = quelle.get('.'.join(teile[:i]))
            if txt:
                break
    if not txt:
        return None, 'Herkunft nicht angegeben'
    klasse = txt.split(':')[0].strip().lower()
    return (klasse if klasse in HERKUNFT_STARK + HERKUNFT_SCHWACH else None), txt


def schwaechste_herkunft(soll, eingaben):
    """('gemessen'|...|None|'geschaetzt'|'angenommen'|'fehlt', Texte). None = Herkunft nicht angegeben (zaehlt schwach)."""
    reihe = HERKUNFT_STARK + (None,) + HERKUNFT_SCHWACH
    schwach, idx, texte = 'gemessen', 0, []
    for e in eingaben or []:
        teil, _, f = e.rpartition(':')
        wert = _feldwert(soll.get(teil, {}) if teil else soll.get('_projekt', {}), f)
        if wert is None:
            return 'fehlt', texte + [f'{e}: Wert fehlt']
        k, t = herkunft_von(soll, e)
        texte.append(f'{e}: {t}')
        if reihe.index(k) > idx:
            schwach, idx = k, reihe.index(k)
    return schwach, texte


# ---------------------------------------------------------------------------------------------- Nachweise

def _vergleich(ist, op, soll_wert):
    return {'>=': ist >= soll_wert, '>': ist > soll_wert, '<=': ist <= soll_wert, '<': ist < soll_wert,
            '==': ist == soll_wert}.get(op, False)


def _reserve_ok(e, herkunft):
    """Reserve gegen Unsicherheit aus der Herkunft. None = nicht bewertbar (kein Wert/Grenze)."""
    w, g = e.get('wert'), e.get('grenze')
    if not isinstance(w, (int, float)) or not isinstance(g, (int, float)) or str(e.get('id', '')).startswith('FW'):
        return None, ''      # FW: Gleichheit gefordert, keine Reserve
    if e.get('einheit') == 'dB':
        u = UNSICHERHEIT_DB.get(herkunft, 10.0)
        r = abs(w - g) if e.get('id') != 'E16' else w    # E16: wert IST die Reserve
        return r >= u, f'Reserve {r:.1f} dB gegen Unsicherheit {u:.0f} dB ({herkunft or "Herkunft offen"})'
    if g == 0:
        return None, ''
    r = abs(w - g) / abs(g)
    u = UNSICHERHEIT_REL.get(herkunft, 0.3)
    return r >= u, f'Reserve {r * 100:.0f} % gegen Unsicherheit {u * 100:.0f} % ({herkunft or "Herkunft offen"})'


def _katalog_status(nw, katalog):
    treffer = []
    for l in (katalog or {}).values():
        for e in l:
            eid = e['id']
            if nw['ref'] == 'alle' or eid == nw['ref'] or eid.startswith(nw['ref'] + '-') or \
                    (eid == 'E1-E25' and nw['ref'].startswith('E')):
                if nw.get('teil') and e.get('teil') not in (None, nw['teil']):
                    continue
                treffer.append(e)
    if not treffer:
        return 'unbewiesen', f'Katalog {nw["ref"]}: kein Ergebnis', []
    st = [e['stufe'] for e in treffer]
    if 'fehler' in st:
        echte = [e for e in treffer if e['stufe'] == 'fehler' and not e.get('ausloeser')]
        if not echte:   # nur Ausloeser-Fehler: Pflichteingabe fehlt -> nicht bewiesen, aber kein Grenzverstoss
            return 'unbewiesen', f'Katalog {nw["ref"]}: Pflichteingabe fehlt (Ausloeser, nicht gerechnet)', treffer
        return 'verletzt', f'Katalog {nw["ref"]}: fehler', treffer
    if 'uebersprungen' in st:
        return 'unbewiesen', f'Katalog {nw["ref"]}: uebersprungen', treffer
    if 'warnung' in st:
        if nw.get('warnung_akzeptiert'):
            return 'vorbehalt', f'Katalog {nw["ref"]}: Warnung akzeptiert ({nw["warnung_akzeptiert"]})', treffer
        angenommen = any('angenommen' in (e.get('hinweis') or '') for e in treffer if e['stufe'] == 'warnung')
        return 'unbewiesen', f'Katalog {nw["ref"]}: Warnung{" (auf Annahmen)" if angenommen else ""} nicht bewertet', treffer
    return 'bewiesen', f'Katalog {nw["ref"]}: ok', treffer


def _cad_status(nw, pdir):
    out = os.path.join(pdir, 'out')
    teile = [f[:-len('.pruefung.json')] for f in os.listdir(out) if f.endswith('.pruefung.json')] \
        if os.path.isdir(out) else []
    cd = os.path.join(pdir, 'cad')
    skripte = [f[:-3] for f in os.listdir(cd) if f.endswith('.py')] if os.path.isdir(cd) else []
    if nw['ref'] != 'alle':
        teile = [t for t in teile if t == nw['ref']] or [None]
    if not teile or teile == [None]:
        return 'unbewiesen', f'cad {nw["ref"]}: kein Pruefbericht', []
    fehlend = [s for s in skripte if s not in teile] if nw['ref'] == 'alle' else []
    veraltet, schlecht = [], []
    for t in teile:
        rp, sp = os.path.join(out, t + '.pruefung.json'), os.path.join(cd, t + '.py')
        if os.path.exists(sp) and os.path.getmtime(sp) > os.path.getmtime(rp):
            veraltet.append(t)
        b = json.load(open(rp, encoding='utf-8'))
        if not b.get('ok'):
            schlecht.append(t)
    if schlecht:
        return 'verletzt', f'cad: nicht bestanden {schlecht}', []
    if fehlend or veraltet:
        return 'unbewiesen', f'cad: ohne Pruefbericht {fehlend}, Bericht aelter als Skript {veraltet} (cad_build)', []
    return 'bewiesen', f'cad {teile} ok', []


def _fem_faelle(nw, pdir):
    fd = os.path.join(pdir, 'fem')
    faelle = [f[:-9] for f in os.listdir(fd) if f.endswith('.erg.json')] if os.path.isdir(fd) else []
    return faelle if nw['ref'] == 'alle' else [f for f in faelle if f == nw['ref']]


def _fem_status(nw, pdir):
    fd = os.path.join(pdir, 'fem')
    faelle = [f[:-9] for f in os.listdir(fd) if f.endswith('.erg.json')] if os.path.isdir(fd) else []
    if nw['ref'] != 'alle':
        faelle = [f for f in faelle if f == nw['ref']]
    if not faelle:
        return 'unbewiesen', f'fem {nw["ref"]}: nicht gerechnet', []
    schlecht, vorb = [], []
    for f in faelle:
        bw = json.load(open(os.path.join(fd, f + '.erg.json'), encoding='utf-8')).get('bewertung') or {}
        if not bw.get('ok'):
            schlecht.append(f)
        elif bw.get('angenommen'):
            vorb.append(f)
    if schlecht:
        return 'verletzt', f'fem nicht ok: {schlecht}', []
    if vorb:
        return 'vorbehalt', f'fem ok, aber auf Annahmen: {vorb}', []
    return 'bewiesen', f'fem {faelle} ok', []


def _slice_status(pdir):
    s = lade(pdir, 'print/slice.json', None)
    if not s:
        return 'unbewiesen', 'nicht gesliced', []
    if not s.get('ok') or s.get('probleme'):
        return 'verletzt', f'slice: {s.get("probleme")}', []
    return 'bewiesen', 'slice ok', []


def _kicad_status(nw, extra):
    k = (extra or {}).get('kicad')
    if not k:
        return 'unbewiesen', 'kein DRC-Ergebnis (audit)', []
    err = (k.get('drc') or {}).get('error', 0)
    return ('verletzt', f'DRC {err} Fehler', []) if err else ('bewiesen', 'DRC 0 Fehler', [])


def _kriterium_text(k):
    return f'{k.get("groesse", "")} {k.get("op", "")} {k.get("wert")} {k.get("einheit", "")}'.strip()


def _abnahme_status(nw, abnahme):
    s = next((x for x in abnahme.get('schritte', []) if x['id'] == nw['ref']), None)
    if not s:
        return 'unbewiesen', f'Abnahmeschritt {nw["ref"]} fehlt (abnahme_erzeugen)', []
    if s.get('ist') is None:
        return 'unbewiesen', f'Abnahme {nw["ref"]}: noch nicht gemessen (Soll {_kriterium_text(s.get("soll") or {})})', []
    k = s.get('soll') or {}
    if 'wert' in k and isinstance(s['ist'], (int, float)):
        ok = _vergleich(s['ist'], k.get('op', '>='), k['wert'])
    else:
        ok = bool(s.get('ok'))
    return ('bewiesen' if ok else 'verletzt'), f'Abnahme {nw["ref"]}: Ist {s["ist"]} (Soll {_kriterium_text(k)})', []


def _feld_status(nw, feld):
    k = nw.get('kriterium') or {}
    if k.get('wert') is None:
        return 'unbewiesen', f'Feld: Kriterium {k.get("groesse")} ohne Zielwert (Ziel in soll/anforderungen.json nachtragen)', []
    ms = [m for m in feld.get('messungen', []) if m.get('groesse') == k.get('groesse')]
    if not ms:
        return 'unbewiesen', f'Feld: keine Messung {k.get("groesse")} (Soll {_kriterium_text(k)})', []
    schlecht = [m for m in ms if not _vergleich(m['wert'], k.get('op', '>='), k['wert'])]
    if schlecht:
        return 'verletzt', f'Feld: {len(schlecht)}/{len(ms)} Messungen verfehlen {_kriterium_text(k)} ' \
                           f'(schlechteste {min(m["wert"] for m in schlecht) if k.get("op", ">=").startswith(">") else max(m["wert"] for m in schlecht)})', []
    return 'bewiesen', f'Feld: {len(ms)} Messungen erfuellen {_kriterium_text(k)}', []


PROJEKTDATEIEN = ('projekt.md', 'anforderungen.json', 'cad/soll.json', 'abnahme.json', 'feld.json', 'messung.json',
                  'freigabe.json', 'kosten.json')
KI_PRUEFER = re.compile(r'claude|\bki\b|\bai\b|agent|gpt|assistant|mb2-|copilot|gemini', re.I)


def _manuell_status(nw, pdir):
    """Manueller Nachweis: eigene Beleg-Datei im Projekt (nicht eine der Projektdateien selbst) und ein menschlicher
    Pruefer. Eine KI kann einen manuellen Nachweis nicht erbringen."""
    b, wer = nw.get('beleg'), str(nw.get('geprueft_von') or '')
    if not b or os.path.isabs(b) or '..' in b.replace('\\', '/').split('/'):
        return 'unbewiesen', 'manueller Nachweis: Beleg muss eine Datei im Projektordner sein', []
    if b.replace('\\', '/') in PROJEKTDATEIEN:
        return 'unbewiesen', f'manueller Nachweis: {b} ist eine Projektdatei, kein Beleg', []
    if not os.path.exists(os.path.join(pdir, b)):
        return 'unbewiesen', f'manueller Nachweis: Beleg {b} fehlt', []
    if not wer.strip() or KI_PRUEFER.search(wer):
        return 'unbewiesen', f'manueller Nachweis: Pruefer {wer!r} fehlt oder ist eine KI - nur Menschen', []
    return 'bewiesen', f'manuell belegt: {b} ({wer})', []


def _messung_status(nw, anforderung, messung, kal_reihe=None, kal=None):
    """Referenzmessreihe gegen den messtechnik-Block der Anforderung. (status, text, [], info).
    kal_reihe: Reihe, aus der die Kalibrierkorrektur stammt - sie darf nicht zugleich Nachweis sein (Zirkelschluss)."""
    from .pruefungen import messkette
    if kal_reihe and nw.get('ref') == kal_reihe:
        info = {'grund': 'kalibrierdaten_als_nachweis', 'gruende': ['kalibrierdaten_als_nachweis'], 'reihe': nw.get('ref')}
        return ('unbewiesen', f'Messung {nw.get("ref")}: dieselbe Reihe lieferte die Kalibrierkorrektur - Nachweis '
                              f'braucht eine unabhaengige Messreihe nach dem Laden der Korrektur', [], info)
    if kal_reihe:
        reihen = {r.get('id'): r for r in (messung or {}).get('reihen', [])}
        rk, rn = reihen.get(kal_reihe) or {}, reihen.get(nw.get('ref')) or {}
        gleich_csv = rk.get('quelle_csv') and rk.get('quelle_csv') == rn.get('quelle_csv')
        k_datum = (kal or {}).get('datum') or rk.get('datum')
        zu_frueh = rn and k_datum and str(rn.get('datum') or '') <= str(k_datum)
        if rn and (gleich_csv or zu_frueh):
            info = {'grund': 'kalibrierdaten_als_nachweis', 'gruende': ['kalibrierdaten_als_nachweis'],
                    'reihe': nw.get('ref')}
            why = 'gleiche Quelldatei wie die Kalibrierung' if gleich_csv else \
                f'gemessen am {rn.get("datum")}, Kalibrierung vom {k_datum} - Nachweis muss danach gemessen sein'
            return 'unbewiesen', f'Messung {nw.get("ref")}: {why}', [], info
    mt = (anforderung or {}).get('messtechnik')
    eig = nw.get('eigenschaft')
    if not mt:
        info = {'grund': 'messtechnik_fehlt'}
        return 'unbewiesen', 'Nachweis messung ohne messtechnik-Block in der Anforderung', [], info
    if eig not in messkette.EIGENSCHAFTEN:
        info = {'grund': 'verfahren_unzureichend'}
        return 'unbewiesen', f'messung: eigenschaft {eig!r} unbekannt ({", ".join(messkette.EIGENSCHAFTEN)})', [], info
    reihe = next((r for r in (messung or {}).get('reihen', []) if r.get('id') == nw.get('ref')), None)
    b = messkette.bewerte_reihe(reihe, eig, mt)
    info = {k: b.get(k) for k in ('grund', 'gruende', 'datenstatus', 'kennwert', 'grenze', 'U_pruef', 'akzeptanzgrenze',
                                  'sicherheitsabstand', 'einheit', 'entscheidungsregel', 'fehlentscheidung',
                                  'auswertung_status', 'punkte')}
    info['reihe'] = nw.get('ref')
    return b['status'], f'Messung {nw.get("ref")}: {b["text"]}' + (f' [{b["grund"]}]' if b['grund'] else ''), [], info


def _messtechnik_maengel(a):
    """Matrix-Maengel einer messtechnischen Anforderung: Eigenschaft ohne Messnachweis, Bedingungen fehlen."""
    from .pruefungen import messkette
    mt = a.get('messtechnik')
    if not mt:
        return []
    m = []
    if not (mt.get('messbereich') or {}).get('einheit'):
        m.append('messtechnik.messbereich {min, max, einheit} unvollstaendig')
    if not mt.get('bedingungen'):
        m.append('messtechnik.bedingungen fehlen (Temperatur, Versorgung, Einschwingzeit, Messintervall) - '
                 'ohne sie sind Messergebnisse nicht vergleichbar')
    belegt = {n.get('eigenschaft') for n in a.get('nachweise', []) if n.get('art') == 'messung'}
    for e in messkette.EIGENSCHAFTEN:
        if isinstance(mt.get(e), dict) and e not in belegt:
            m.append(f'messtechnische Eigenschaft {e} ohne Nachweis art=messung (Verfahren: {messkette.VERFAHREN[e]})')
    return m


def nachweis_status(nw, pdir, katalog, abnahme, feld, extra=None, anforderung=None, messung=None):
    art = nw.get('art')
    if art == 'messung':
        return _messung_status(nw, anforderung, messung)[:3]
    if art == 'katalog':
        return _katalog_status(nw, katalog)
    if art == 'cad':
        return _cad_status(nw, pdir)
    if art == 'fem':
        return _fem_status(nw, pdir)
    if art == 'slice':
        return _slice_status(pdir)
    if art == 'kicad':
        return _kicad_status(nw, extra)
    if art == 'abnahme':
        return _abnahme_status(nw, abnahme)
    if art == 'feld':
        return _feld_status(nw, feld)
    if art == 'manuell':
        return _manuell_status(nw, pdir)
    if art == 'ml_modell':
        st, txt = glaubwuerdigkeit.ml_bewerte(nw.get('modell'))
        return st, txt, []
    return 'unbewiesen', f'unbekannte Nachweisart {art!r}', []


# ---------------------------------------------------------------------------------------------- Bewertung

RANG = {'verletzt': 3, 'unbewiesen': 2, 'vorbehalt': 1, 'bewiesen': 0}


def pruefen(pdir, katalog=None, extra=None):
    """V-Matrix: Status je Anforderung, Rueckverfolgbarkeit, Freigabestufe. katalog = alle()['module'] (sonst gerechnet)."""
    anf = lade(pdir, 'anforderungen.json', {}).get('anforderungen', [])
    soll = _soll(pdir)
    abnahme = lade(pdir, 'abnahme.json', {})
    feld = lade(pdir, 'feld.json', {})
    messung = lade(pdir, 'messung.json', {})
    kal = (soll.get('_projekt', {}).get('messkette') or {}).get('kalibrierung') or {}
    kal_reihe = kal.get('reihe')
    if katalog is None:
        from . import pruefungen
        katalog = pruefungen.alle(pdir)['module']
    ids = {a['id'] for a in anf}
    zeilen, matrix_maengel, glaub = [], [], []
    if not anf:
        matrix_maengel.append('Keine Anforderungen (anforderungen.json) - ohne Lastenheft ist nichts bewiesen '
                              '(anforderungen_erzeugen)')
    # Zwilling-Gedanke (DNV-RP-A204-Idee, seit 19.11.2026): widerspricht eine Feldmessung einer Modellvorhersage
    # (zu optimistisch), verliert das Modell seine Beweiskraft, bis es nachkalibriert ist
    try:
        widerlegt = {z['pruefung'] for z in feld_vergleich(feld, katalog) if z.get('urteil') == 'zu_optimistisch'}
    except Exception:  # noqa: BLE001 - Feldvergleich darf die Matrix nicht abbrechen
        widerlegt = set()
    try:
        from . import stichproben as _sp
        stich = _sp.bewerte(pdir, katalog)
    except Exception:  # noqa: BLE001
        stich = {}
    stakeholder_ids = {a['id'] for a in anf if a.get('ebene') == 'stakeholder'}
    hat_stakeholder = bool(stakeholder_ids)
    for a in anf:
        ebene = a.get('ebene')
        maengel = []
        if ebene not in EBENEN:
            maengel.append(f'Ebene {ebene!r} unbekannt ({"/".join(EBENEN)})')
        if ebene in ('stakeholder', 'system') and not a.get('herkunft'):
            maengel.append(f'{ebene}-Anforderung ohne Herkunft (wer verlangt es?)')
        if ebene == 'system' and hat_stakeholder:
            if not [e for e in a.get('eltern', []) if e in stakeholder_ids]:
                maengel.append('Systemanforderung ohne Stakeholder-Wunsch als Eltern (wessen Wunsch erfuellt sie?)')
            if not a.get('herleitung'):
                maengel.append('Systemanforderung ohne herleitung (wie folgt die Zahl aus dem Wunsch? Rechnung/Begruendung)')
        if ebene in ('subsystem', 'komponente') and not [e for e in a.get('eltern', []) if e in ids]:
            maengel.append('keine Elternanforderung (Rueckverfolgbarkeit nach oben fehlt)')
        nws = a.get('nachweise', [])
        stufen = {n.get('stufe') for n in nws}
        if ebene in STUFEN_JE_EBENE and not stufen & set(STUFEN_JE_EBENE[ebene]):
            maengel.append(f'kein Nachweis auf V-Ebene {"/".join(STUFEN_JE_EBENE[ebene])}')
        if ebene in ('stakeholder', 'system') and 'abnahme' not in stufen and 'feld' not in stufen:
            maengel.append(f'{ebene}-Anforderung braucht Abnahme am Geraet oder Feldmessung')
        for n in nws:
            if n.get('stufe') not in ('komponente', 'integration', 'abnahme', 'feld'):
                maengel.append(f'Nachweis {n.get("art")} {n.get("ref")}: stufe {n.get("stufe")!r} ungueltig '
                               f'(komponente/integration/abnahme/feld)')
        maengel += _messtechnik_maengel(a)
        herk, htexte = schwaechste_herkunft(soll, a.get('eingaben'))
        ergebnisse, st_gesamt = [], 'bewiesen' if nws else 'unbewiesen'
        for nw in nws:
            info = None
            if nw.get('art') == 'messung':
                st, txt, treffer, info = _messung_status(nw, a, messung, kal_reihe, kal)
            else:
                st, txt, treffer = nachweis_status(nw, pdir, katalog, abnahme, feld, extra)
            # Stichproben-Validierung (stichproben.json): widerlegt -> kein Nachweis; ausserhalb des gemessenen Bereichs
            # -> hoechstens vorbehalt; validiert -> nur vermerkt (der Nachweis selbst kommt aus der Pruefung)
            schl = [('katalog', nw.get('ref'))] if nw.get('art') == 'katalog' else \
                [('fem', f) for f in _fem_faelle(nw, pdir)] if nw.get('art') == 'fem' else []
            for key in schl:
                e = stich.get(key)
                if not e or e['status'] == 'ohne_punkte':
                    continue
                if e['status'] == 'widerlegt' and st in ('bewiesen', 'vorbehalt'):
                    st = 'unbewiesen'
                elif e['status'] == 'extrapolation' and st == 'bewiesen':
                    st = 'vorbehalt'
                txt += f'; Stichproben {key[1]}: {e["text"]}'
            if nw.get('art') == 'katalog' and nw.get('ref') in widerlegt and st in ('bewiesen', 'vorbehalt'):
                st, txt = 'unbewiesen', txt + f'; Feldmessung zeigt: {nw["ref"]} ist zu optimistisch - Modell ' \
                                              'nachkalibrieren (feld_abgleich), bis dahin kein Nachweis'
            # Reserve gegen Unsicherheit (nur bei bestandenem Katalog-Nachweis mit Wert/Grenze)
            if st == 'bewiesen' and treffer:
                for e in treffer:
                    ok, rtxt = _reserve_ok(e, herk if herk != 'fehlt' else None)
                    if ok is False:
                        st, txt = 'vorbehalt', txt + f'; {rtxt} - zu knapp'
                    elif ok:
                        txt += f'; {rtxt}'
            if nw.get('art') == 'fem':
                # Glaubwuerdigkeit je Modell (V&V 40): ein Modell ist hoechstens so gut wie seine Belege
                for fall in _fem_faelle(nw, pdir):
                    g = glaubwuerdigkeit.bewerte(pdir, fall, _mit_stichproben(nw.get('modell'), stich.get(('fem', fall))),
                                                 katalog, herk if herk != 'fehlt' else None)
                    glaub.append({'anforderung': a['id'], **g})
                    if RANG[g['status']] > RANG[st]:
                        st = g['status']
                    if g['status'] != 'bewiesen':
                        txt += f'; {g["text"]}'
            ergebnisse.append({'art': nw.get('art'), 'ref': nw.get('ref'), 'stufe': nw.get('stufe'),
                               'status': st, 'beleg': txt, **({'eigenschaft': nw.get('eigenschaft'), **info}
                                                              if info else {})})
            if RANG[st] > RANG[st_gesamt]:
                st_gesamt = st
        if st_gesamt == 'bewiesen' and herk in HERKUNFT_SCHWACH + (None,) and a.get('eingaben'):
            st_gesamt = 'vorbehalt'
        if herk == 'fehlt' and st_gesamt in ('bewiesen', 'vorbehalt'):
            st_gesamt = 'unbewiesen'
        if maengel and st_gesamt == 'bewiesen':
            st_gesamt = 'unbewiesen'
        zeilen.append({'id': a['id'], 'ebene': ebene, 'text': a.get('text'), 'status': st_gesamt,
                       'nachweise': ergebnisse, 'herkunft_eingaben': herk, 'herkunft_text': htexte,
                       'matrix_maengel': maengel, 'eltern': a.get('eltern', [])})
    # Kinder erben: Eltern sind hoechstens so gut wie ihr schlechtestes Kind
    # (wiederholen bis stabil: unabhaengig von der Reihenfolge, ueber beliebig viele Ebenen; vorbehalt wird mitgegeben)
    nach_id = {z['id']: z for z in zeilen}
    for _ in range(len(zeilen) + 1):
        geaendert = False
        for z in zeilen:
            for e in z['eltern']:
                if e in nach_id and RANG[z['status']] > RANG[nach_id[e]['status']]:
                    nach_id[e]['status'] = z['status']
                    if z['id'] not in nach_id[e].setdefault('wegen_kind', []):
                        nach_id[e]['wegen_kind'].append(z['id'])
                    geaendert = True
        if not geaendert:
            break
    unten = [z for z in zeilen if z['ebene'] in ('subsystem', 'komponente')]
    oben = [z for z in zeilen if z['ebene'] in ('stakeholder', 'system')]
    # Druckfertig: alle Komponenten-/Integrationsnachweise bewiesen (Abnahme/Feld duerfen noch offen sein)
    def nur_vor_abnahme(z):    # alles ausser Abnahme/Feld muss vor dem Druck stehen (auch fehlende/falsche stufe)
        return all(n['status'] in ('bewiesen', 'vorbehalt') for n in z['nachweise']
                   if n['stufe'] not in ('abnahme', 'feld'))
    druckfertig = bool(zeilen) and not matrix_maengel and all(nur_vor_abnahme(z) for z in zeilen) and \
        not any(z['status'] == 'verletzt' for z in zeilen) and not any(z['matrix_maengel'] for z in zeilen)
    risiken = risiken_sammeln(lade(pdir, 'anforderungen.json', {}))
    mfg = messtechnische_freigabe(pdir, anf, zeilen)
    mfg['risiken'] = risiken
    fertig = druckfertig and all(z['status'] in ('bewiesen',) for z in zeilen) and \
        mfg['status'] in ('nicht_anwendbar', 'freigegeben')
    freigabe = 'fertig' if fertig else ('druckfertig' if druckfertig else 'nicht_druckfertig')
    zaehl = {s: sum(1 for z in zeilen if z['status'] == s) for s in RANG}
    erg = {'freigabe': freigabe, 'zaehlung': zaehl, 'anforderungen': zeilen, 'matrix_maengel': matrix_maengel,
           'offen_abnahme': [f'{z["id"]}: {n["beleg"]}' for z in oben + unten for n in z['nachweise']
                             if n['stufe'] in ('abnahme', 'feld') and n['status'] != 'bewiesen'],
           'kontext_hash': kontext_hash(pdir), 'zeit': datetime.datetime.now().isoformat(timespec='seconds')}
    erg['messtechnische_freigabe'] = mfg
    erg['risiken'] = risiken
    erg['glaubwuerdigkeit'] = [{k: g[k] for k in ('anforderung', 'fall', 'risiko', 'status', 'text')} for g in glaub]
    os.makedirs(os.path.join(pdir, 'pruef'), exist_ok=True)
    speichere(pdir, 'pruef/v_matrix.json', erg)
    glaubwuerdigkeit.bericht(pdir, glaub)
    messprotokoll(pdir, anf, zeilen, mfg)
    return erg


# ---------------------------------------------------------------------------------------------- Messtechnische Freigabe

def _mit_stichproben(modell, sp):
    """Hat ein FEM-Modell keinen eigenen validierung-Block, aber gewertete Stichproben, gelten diese als Vergleich
    (V&V-20-Metrik je Punkt; Stufe 4 nur, wenn jeder Punkt u_num, u_input und u_D hat)."""
    if not modell or modell.get('validierung') or not sp:
        return modell
    pk = [p for p in sp.get('punkte', []) if 'E' in p]
    if not pk:
        return modell
    return dict(modell, validierung={'beleg': 'stichproben.json', 'strenge': 'unsicherheit_beidseitig',
                                     'groessen': [{'name': f'Punkt {i + 1}', 'S': p['S'], 'D': p['D'],
                                                   'u_D': p.get('u_D'), 'u_num': p.get('u_num'),
                                                   'u_input': p.get('u_input')} for i, p in enumerate(pk)]})


def risiken_sammeln(anf_datei):
    """Bewusst eingegangene Risiken (seit 19.11.2026): Feld 'risiko' je Anforderung und Liste 'risiken' auf oberster
    Ebene von anforderungen.json. Typisch: Entscheidung des Nutzers gegen eine Empfehlung. Sie blockieren nichts, muessen
    aber sichtbar sein (v_matrix, audit, Messprotokoll) und bei der menschlichen Freigabe ausdruecklich akzeptiert werden."""
    r = [{'anforderung': a['id'], 'risiko': a['risiko']} for a in anf_datei.get('anforderungen', []) if a.get('risiko')]
    r += [{'anforderung': None, 'risiko': x if isinstance(x, str) else x.get('risiko', str(x))}
          for x in anf_datei.get('risiken', [])]
    return r


def _ist_messtechnisch(a):
    return bool(a.get('messtechnik')) or any(n.get('art') == 'katalog' and str(n.get('ref', '')).startswith('MK')
                                             for n in a.get('nachweise', []))


def messtechnische_freigabe(pdir, anf, zeilen):
    """Gesamturteil zur Messfunktion. Grundsatz: KI und Software koennen hoechstens 'bereit_zur_menschlichen_freigabe'
    melden. 'freigegeben' nur mit freigabe.json {"messtechnik": {"pruefer", "datum", "kontext_hash"}}, deren Hash dem
    aktuellen Stand entspricht (jede Aenderung an soll/Anforderungen/Messungen macht die Freigabe ungueltig)."""
    ids = {a['id'] for a in anf if _ist_messtechnisch(a)}
    if not ids:
        return {'status': 'nicht_anwendbar', 'gruende': [], 'anforderungen': []}
    gruende = []
    for z in zeilen:
        if z['id'] not in ids or z['status'] == 'bewiesen':
            continue
        offen = sorted({g for n in z['nachweise'] for g in (n.get('gruende') or ([n['grund']] if n.get('grund') else []))})
        gruende.append(f'{z["id"]}: {z["status"]}' + (f' ({", ".join(offen)})' if offen else '') +
                       (f'; Matrix: {"; ".join(z["matrix_maengel"])}' if z['matrix_maengel'] else ''))
    h = kontext_hash(pdir)
    fg = (lade(pdir, 'freigabe.json', {}) or {}).get('messtechnik') or {}
    if gruende:
        st = 'nicht_freigegeben'
    elif fg.get('pruefer') and fg.get('kontext_hash') == h:
        st = 'freigegeben'
    else:
        st = 'bereit_zur_menschlichen_freigabe'
        if fg.get('pruefer'):
            gruende.append(f'Freigabe von {fg["pruefer"]} ({fg.get("datum")}) gilt fuer Stand {fg.get("kontext_hash")}, '
                           f'aktuell {h} - neu freigeben')
    return {'status': st, 'gruende': gruende, 'anforderungen': sorted(ids), 'kontext_hash': h,
            'freigabe_durch': fg.get('pruefer') if st == 'freigegeben' else None}


def messtechnik_freigeben(pdir, pruefer, notiz='', risiken_akzeptiert=False):
    """Menschliche Freigabe der Messfunktion festhalten. Absichtlich KEIN MCP-Befehl: von Hand aufrufen
    (python -c "from mb2 import anforderungen as a; a.messtechnik_freigeben('projects/x', 'Name')").
    Verweigert, solange nicht alle messtechnischen Anforderungen bewiesen sind."""
    v = pruefen(pdir)
    if v['messtechnische_freigabe']['status'] != 'bereit_zur_menschlichen_freigabe':
        raise RuntimeError(f'nicht freigebbar: {v["messtechnische_freigabe"]}')
    if v['risiken'] and not risiken_akzeptiert:
        raise RuntimeError('Offene Risiken muessen ausdruecklich akzeptiert werden (risiken_akzeptiert=True): '
                           + ' | '.join(r['risiko'] for r in v['risiken']))
    f = lade(pdir, 'freigabe.json', {})
    f['messtechnik'] = {'pruefer': pruefer, 'datum': datetime.datetime.now().isoformat(timespec='seconds'),
                        'kontext_hash': v['kontext_hash'], 'notiz': notiz,
                        'akzeptierte_risiken': [r['risiko'] for r in v['risiken']]}
    speichere(pdir, 'freigabe.json', f)
    return pruefen(pdir)['messtechnische_freigabe']


def _z(v, f='{:.4g}'):
    return '-' if v is None else (f.format(v) if isinstance(v, (int, float)) else str(v))


def messprotokoll(pdir, anf, zeilen, mfg):
    """pruef/messprotokoll.md: je Messnachweis gemessene und zulaessige Abweichung, U_pruef, Regel, Status."""
    mess = [(z, n) for z in zeilen for n in z['nachweise'] if n.get('art') == 'messung']
    if not mess and mfg['status'] == 'nicht_anwendbar':
        return None
    L = [f'# Messprotokoll {os.path.basename(pdir)}', '',
         f'Stand {kontext_hash(pdir)}, erzeugt {datetime.datetime.now().isoformat(timespec="seconds")} von '
         f'mb2/anforderungen.py. **Gruen heisst bewiesen**: nur rueckfuehrbar gemessene Reihen koennen beweisen.', '',
         f'**Messtechnische Freigabe: {mfg["status"]}**', '']
    L += [f'- {g}' for g in mfg['gruende']] + ['']
    if mfg.get('risiken'):
        L += ['**Bewusst eingegangene Risiken** (muessen bei der Freigabe akzeptiert werden):', '']
        L += [f'- {r["anforderung"] or "Projekt"}: {r["risiko"]}' for r in mfg['risiken']] + ['']
    L += ['| Anforderung | Eigenschaft | Reihe | Datenstatus | gemessen | zulaessig | U_pruef (k=2) | '
          'Akzeptanzgrenze | Auswertung | Status | Grund |', '|' + '---|' * 11]
    for z, n in mess:
        L.append(f'| {z["id"]} | {n.get("eigenschaft")} | {n.get("reihe")} | {n.get("datenstatus") or "-"} | '
                 f'{_z(n.get("kennwert"))} | {_z(n.get("grenze"))} {n.get("einheit") or ""} | '
                 f'{_z(n.get("sicherheitsabstand"))} | {_z(n.get("akzeptanzgrenze"))} | '
                 f'{n.get("auswertung_status") or "-"} | **{n["status"]}** | {", ".join(n.get("gruende") or []) or "-"} |')
    regeln = sorted({n.get('entscheidungsregel') for _, n in mess if n.get('entscheidungsregel')})
    fe = sorted({n.get('fehlentscheidung') for _, n in mess if n.get('fehlentscheidung')})
    L += ['', '## Entscheidungsregel', ''] + [f'- {r}' for r in regeln] + ['', '## Fehlentscheidung', ''] + \
         [f'- {r}' for r in fe]
    L += ['', '## Messpunkte', '']
    for z, n in mess:
        if not n.get('punkte'):
            continue
        L += [f'### {z["id"]} / {n.get("eigenschaft")} / {n.get("reihe")}', '',
              '| Referenz | Richtung | n | Mittel | s | Abweichung |', '|---|---|---|---|---|---|']
        L += [f'| {_z(p["ref"])} | {p.get("richtung") or "-"} | {p["n"]} | {_z(p["mittel"], "{:.5g}")} | '
              f'{_z(p["s"], "{:.3g}")} | {_z(p["abweichung"], "{:+.4g}")} |' for p in n['punkte']]
        L.append('')
    os.makedirs(os.path.join(pdir, 'pruef'), exist_ok=True)
    open(os.path.join(pdir, 'pruef', 'messprotokoll.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    return L


# ---------------------------------------------------------------------------------------------- Standard-Anforderungen

def standard(pdir):
    """Aus Einsatz + Merkmalen abgeleitete Grundanforderungen (Lastenheft-Geruest). Eigene Anforderungen kommen dazu."""
    from .pruefungen.merkmale import merkmale
    mk = merkmale(pdir)
    pj = _soll(pdir).get('_projekt', {})
    a = lambda m: (mk.get(m) or {}).get('aktiv')  # noqa: E731
    L = []
    L.append({'id': 'A-GERAET', 'ebene': 'system', 'herkunft': 'project_new: Idee in projekt.md',
              'text': 'Das Geraet erfuellt die Idee aus projekt.md im Einsatz (Abnahme am fertigen Geraet).',
              'nachweise': [{'art': 'abnahme', 'ref': 'AB-FUNKTION', 'stufe': 'abnahme'}]})
    L.append({'id': 'A-MONTAGE', 'ebene': 'system', 'herkunft': 'mb2-Standard (Bodenklima: Klemmen gespiegelt)',
              'text': 'Montage und Anschluss nach Anleitung sind eindeutig und geprueft (Pin 1/Farbe, nicht links/rechts).',
              'nachweise': [{'art': 'abnahme', 'ref': 'AB-ANSCHLUSS', 'stufe': 'abnahme'}]})
    L.append({'id': 'S-DRUCK', 'ebene': 'subsystem', 'eltern': ['A-GERAET'], 'herkunft': 'abgeleitet aus A-GERAET',
              'text': 'Alle Teile sind druckbar (Wand, Spalt, Ueberhang) und gesliced ohne Profilprobleme.',
              'nachweise': [{'art': 'cad', 'ref': 'alle', 'stufe': 'komponente'},
                            {'art': 'slice', 'ref': 'platte', 'stufe': 'integration'},
                            {'art': 'katalog', 'ref': 'BL', 'stufe': 'komponente'}]})
    L.append({'id': 'S-FEST', 'ebene': 'subsystem', 'eltern': ['A-GERAET'], 'herkunft': 'abgeleitet aus A-GERAET',
              'text': 'Belastete Teile halten mit wirksamer Sicherheit >= 2 (Realterme: Temperatur, Kriechen, UV).',
              'eingaben': ['material'],
              'nachweise': [{'art': 'fem', 'ref': 'alle', 'stufe': 'integration'},
                            {'art': 'katalog', 'ref': 'F23', 'stufe': 'integration'}]})
    if a('aussen') or a('elektronik') or pj.get('T_max_C') is not None:
        L.append({'id': 'S-TEMP', 'ebene': 'subsystem', 'eltern': ['A-GERAET'], 'herkunft': 'abgeleitet aus Einsatz',
                  'text': 'Teiltemperatur (Luft + Sonne + Eigenwaerme) bleibt >= 20 K unter Tg.',
                  'eingaben': ['T_max_C'] + (['farbe'] if a('aussen') else []),
                  'nachweise': [{'art': 'katalog', 'ref': 'D1', 'stufe': 'integration'}] +
                               ([{'art': 'katalog', 'ref': 'W6', 'stufe': 'integration'}] if a('aussen') else [])})
    if a('funk'):
        r = (pj.get('elektronik', {}).get('funk') or {}).get('r_m')
        L.append({'id': 'A-FUNK', 'ebene': 'system', 'herkunft': 'abgeleitet aus Merkmal Funk',
                  'text': f'Pakete kommen am Einsatzort zuverlaessig an ({r or "?"} m).',
                  'eingaben': ['elektronik.funk.r_m', 'elektronik.funk.umgebung', 'elektronik.funk.hindernisse'],
                  'nachweise': [{'art': 'abnahme', 'ref': 'AB-FUNK', 'stufe': 'abnahme'},
                                {'art': 'feld', 'ref': 'empfangsquote', 'stufe': 'feld',
                                 'kriterium': {'groesse': 'empfangsquote_proz', 'op': '>=', 'wert': 95, 'einheit': '%'}}]})
        L.append({'id': 'S-FUNK', 'ebene': 'subsystem', 'eltern': ['A-FUNK'], 'herkunft': 'abgeleitet aus A-FUNK',
                  'text': 'Linkbudget mit >= 10 dB Reserve (realistische Umgebung, Hindernisse, Kabel, Antenne).',
                  'eingaben': ['elektronik.funk.r_m', 'elektronik.funk.umgebung'],
                  'nachweise': [{'art': 'katalog', 'ref': 'E16', 'stufe': 'integration'},
                                {'art': 'katalog', 'ref': 'FW1', 'stufe': 'komponente'}]})
    if a('akku'):
        L.append({'id': 'A-AKKU', 'ebene': 'system', 'herkunft': 'abgeleitet aus Merkmal Akku',
                  'text': f'Laufzeit je Ladung/Batteriesatz >= {pj.get("laufzeit_ziel_h") or "?"} h im Einsatz.',
                  'eingaben': ['akku_mAh', 'laufzeit_ziel_h'],
                  'nachweise': [{'art': 'katalog', 'ref': 'E6', 'stufe': 'integration'},
                                {'art': 'feld', 'ref': 'laufzeit', 'stufe': 'feld',
                                 'kriterium': {'groesse': 'laufzeit_h', 'op': '>=',
                                               'wert': pj.get('laufzeit_ziel_h'), 'einheit': 'h'}}]})
        L.append({'id': 'S-STROM', 'ebene': 'subsystem', 'eltern': ['A-AKKU'], 'herkunft': 'abgeleitet aus A-AKKU',
                  'text': 'Kein Brownout bei Funkspitze (kalt, gealtert), Laden nur im erlaubten Temperaturfenster.',
                  'nachweise': [{'art': 'katalog', 'ref': 'E8', 'stufe': 'integration'},
                                {'art': 'katalog', 'ref': 'E21', 'stufe': 'integration'}]})
    if a('schrauben') or a('schnapper'):
        L.append({'id': 'S-VERBINDUNG', 'ebene': 'subsystem', 'eltern': ['A-GERAET'], 'herkunft': 'abgeleitet aus Merkmal',
                  'text': 'Schraub- und Schnappverbindungen halten dauerhaft (Kopfpressung, Restvorspannung, Dehnung).',
                  'nachweise': ([{'art': 'katalog', 'ref': 'M12', 'stufe': 'komponente'},
                                 {'art': 'katalog', 'ref': 'D4', 'stufe': 'integration'}] if a('schrauben') else []) +
                               ([{'art': 'katalog', 'ref': 'M1', 'stufe': 'komponente'}] if a('schnapper') else [])})
    zl = pj.get('ziele') or {}
    if isinstance(zl.get('zielkosten_eur_stueck'), (int, float)):
        L.append({'id': 'S-KOSTEN', 'ebene': 'subsystem', 'eltern': ['A-GERAET'], 'herkunft': 'Projektziel (ziele)',
                  'text': f'Bauteil- und Materialkosten je Geraet <= {zl["zielkosten_eur_stueck"]} EUR (kosten.json).',
                  'eingaben': ['ziele.zielkosten_eur_stueck'],
                  'nachweise': [{'art': 'katalog', 'ref': 'K1', 'stufe': 'integration'}]})
    if isinstance(zl.get('aufwand_h_stueck'), (int, float)):
        L.append({'id': 'S-AUFWAND', 'ebene': 'subsystem', 'eltern': ['A-GERAET'], 'herkunft': 'Projektziel (ziele)',
                  'text': f'Arbeitszeit je Geraet <= {zl["aufwand_h_stueck"]} h (Bau, Abgleich, Pruefung).',
                  'eingaben': ['ziele.aufwand_h_stueck'],
                  'nachweise': [{'art': 'katalog', 'ref': 'K2', 'stufe': 'integration'}]})
    if a('messung') and pj.get('messkette'):
        L.append({'id': 'S-MESSKETTE', 'ebene': 'subsystem', 'eltern': ['A-GERAET'],
                  'herkunft': 'abgeleitet aus Merkmal Messung',
                  'text': 'Unsicherheitsbudget der Messkette (U, k = 2) und rauschbegrenzte Aufloesung erfuellen die '
                          'Ziele; ADC wird ueber den Messbereich nicht uebersteuert.',
                  'eingaben': ['messkette.adc_rauschen_V', 'messkette.u_ref_V', 'messkette.empfindlichkeit_V_je_einheit'],
                  'nachweise': [{'art': 'katalog', 'ref': 'MK1', 'stufe': 'integration'},
                                {'art': 'katalog', 'ref': 'MK2', 'stufe': 'integration'}] +
                               ([{'art': 'katalog', 'ref': 'MK3', 'stufe': 'komponente'}]
                                if (pj['messkette'].get('messbereich')) else [])})
    return L


def erzeugen(pdir):
    """anforderungen.json anlegen/ergaenzen: Standard-Anforderungen hinzufuegen, vorhandene (auch geaenderte) behalten."""
    alt = lade(pdir, 'anforderungen.json', {'anforderungen': []})
    vorhanden = {a['id'] for a in alt['anforderungen']}
    neu = [a for a in standard(pdir) if a['id'] not in vorhanden]
    alt['anforderungen'] += neu
    alt.setdefault('hinweis', 'V-Modell (mb2/anforderungen.py): system <-> abnahme/feld, subsystem <-> integration, '
                              'komponente <-> komponente. Eigene Anforderungen des Nutzers als system-Ebene mit herkunft '
                              'ergaenzen; Standard-Eintraege anpassen statt loeschen.')
    speichere(pdir, 'anforderungen.json', alt)
    return {'neu': [a['id'] for a in neu], 'gesamt': len(alt['anforderungen'])}


# ---------------------------------------------------------------------------------------------- Abnahme

STANDARD_SCHRITTE = {
    'AB-ANSCHLUSS': {'anweisung': 'Jede Klemme/jeden Stecker nach Pin-Nummer (Pin 1 = Dreieck bzw. eckiges Pad) und '
                                  'Aderfarbe anschliessen, dann je Ader Durchgang Pin -> Ziel messen.',
                     'soll': {'groesse': 'falsch_angeschlossen', 'op': '==', 'wert': 0, 'einheit': 'Adern'}},
    'AB-FUNKTION': {'anweisung': 'Fertiges Geraet nach projekt.md in Betrieb nehmen; alle Messwerte plausibel?',
                    'soll': {'groesse': 'funktion_ok', 'op': '==', 'wert': 1, 'einheit': 'ja=1'}},
    'AB-FUNK': {'anweisung': 'Am endgueltigen Einbauort (Antennen montiert, Deckel zu) Neustart ueber den Reset-Pin '
                             '(nicht Batterie ziehen: Pufferkondensatoren halten den Chip), dann SNR des ersten Pakets '
                             'an der Basis ablesen.',
                'soll': {'groesse': 'snr_dB', 'op': '>=', 'wert': -5, 'einheit': 'dB'}},
}


def lageabhaengig(text):
    """Anweisung nennt links/rechts/oben/unten ohne eindeutige Markierung -> Hinweis (sonst None)."""
    t = text.lower().replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue')
    if re.search(LAGEWOERTER, t) and not re.search(MARKIERUNG, t):
        return 'lageabhaengig ohne Markierung (Pin 1/Dreieck/Farbe/Aufdruck nennen)'
    return None


def abnahme_erzeugen(pdir):
    """abnahme.json aus allen Nachweisen art='abnahme' erzeugen; vorhandene Ist-Werte und eigene Schritte bleiben."""
    anf = lade(pdir, 'anforderungen.json', {}).get('anforderungen', [])
    ab = lade(pdir, 'abnahme.json', {'schritte': []})
    da = {s['id']: s for s in ab['schritte']}
    for a in anf:
        for nw in a.get('nachweise', []):
            if nw.get('art') != 'abnahme':
                continue
            s = da.get(nw['ref'])
            vorlage = STANDARD_SCHRITTE.get(nw['ref'], {})
            if not s:
                s = {'id': nw['ref'], 'anforderung': a['id'],
                     'anweisung': nw.get('anweisung') or vorlage.get('anweisung') or f'Pruefung fuer {a["id"]}: {a.get("text")}',
                     'soll': nw.get('kriterium') or vorlage.get('soll') or {}, 'ist': None, 'datum': None, 'notiz': ''}
                ab['schritte'].append(s)
                da[s['id']] = s
    probleme = []
    for s in ab['schritte']:
        p = lageabhaengig(s.get('anweisung', ''))
        if p:
            probleme.append(f'{s["id"]}: {p}')
        if not (s.get('soll') or {}).get('groesse'):
            probleme.append(f'{s["id"]}: kein messbares Soll')
    ab['hinweis'] = 'Ist-Werte mit abnahme_eintragen(projekt, schritt, ist, notiz). Erst mit allen Ist-Werten ist das ' \
                    'Projekt "fertig" (nicht nur "druckfertig").'
    speichere(pdir, 'abnahme.json', ab)
    return {'schritte': [s['id'] for s in ab['schritte']], 'offen': [s['id'] for s in ab['schritte'] if s.get('ist') is None],
            'probleme': probleme}


def abnahme_eintragen(pdir, schritt, ist, notiz=''):
    ab = lade(pdir, 'abnahme.json', {'schritte': []})
    s = next((x for x in ab['schritte'] if x['id'] == schritt), None)
    if s is None:
        raise RuntimeError(f'Abnahmeschritt {schritt!r} unbekannt – erst abnahme_erzeugen')
    s['ist'] = ist
    s['datum'] = datetime.date.today().isoformat()
    if notiz:
        s['notiz'] = notiz
    k = s.get('soll') or {}
    if 'wert' in k and isinstance(ist, (int, float)):
        s['ok'] = _vergleich(ist, k.get('op', '>='), k['wert'])
    speichere(pdir, 'abnahme.json', ab)
    return s


# ---------------------------------------------------------------------------------------------- Feld

# Feldgroesse -> (Katalog-ID, daten-Schluessel der Vorhersage, Umrechnung Messung -> Vorhersagegroesse, Toleranz)
VORHERSAGE = {
    'snr_dB': ('E16', 'P_rx_dBm', lambda m: m + RAUSCHEN_125K_DBM, 8.0),      # SNR -> P_rx = SNR + Rauschen
    'rssi_dBm': ('E16', 'P_rx_dBm', lambda m: m, 8.0),
    'laufzeit_h': ('E6', None, lambda m: m, None),                              # wert von E6
}


def feld_eintragen(pdir, groesse, wert, einheit='', ort='', quelle='', datum=None):
    f = lade(pdir, 'feld.json', {'messungen': []})
    m = {'groesse': groesse, 'wert': wert, 'einheit': einheit, 'ort': ort, 'quelle': quelle,
         'datum': datum or datetime.date.today().isoformat()}
    f['messungen'].append(m)
    speichere(pdir, 'feld.json', f)
    return m


def messreihe_eintragen(pdir, reihe):
    """Referenzmessreihe in messung.json speichern (gleiche id wird ersetzt). Format: mb2/pruefungen/messkette.py."""
    from .pruefungen import messkette
    if not reihe.get('id'):
        raise ValueError('Messreihe braucht eine id')
    if reihe.get('eigenschaft') not in messkette.EIGENSCHAFTEN:
        raise ValueError(f'eigenschaft muss eine von {messkette.EIGENSCHAFTEN} sein')
    m = lade(pdir, 'messung.json', {'reihen': []})
    m['reihen'] = [r for r in m['reihen'] if r.get('id') != reihe['id']] + [reihe]
    speichere(pdir, 'messung.json', m)
    return {'id': reihe['id'], 'punkte': len(reihe.get('punkte', [])), 'reihen': len(m['reihen'])}


CSV_SPALTEN = ('punkt_C', 'richtung', 'nr', 'zeit', 'referenz_C', 'sensor_C', 'roh_code_a', 'roh_code_b')


def messreihen_aus_csv(pdir, csv_datei, kopf, ids):
    """Messwert-Tabelle (Vorlage demonstratoren/MB2-TEMP-001/vorlage_messwerte.csv, Semikolon, Dezimalkomma erlaubt)
    in messung.json einlesen. Eine Tabelle kann mehrere Eigenschaften belegen: ids = {eigenschaft: reihen_id}, z. B.
    {"genauigkeit": "R-GEN-1", "hysterese": "R-HYS-1"}. kopf = gemeinsame Angaben jeder Reihe (datenstatus, datum,
    sensor_id, seriennummer, verfahren, referenz {...}, bedingungen {...}, pruefunsicherheit [...]).
    Zeilen ohne referenz_C oder sensor_C werden uebersprungen und gezaehlt (nie still ergaenzt)."""
    import csv
    pfad = csv_datei if os.path.isabs(csv_datei) else os.path.join(pdir, csv_datei)
    zahl = lambda v: float(str(v).strip().replace(',', '.')) if str(v or '').strip() else None  # noqa: E731
    punkte, leer = [], 0
    with open(pfad, encoding='utf-8-sig', newline='') as f:
        for z in csv.DictReader(f, delimiter=';'):
            ref, ist = zahl(z.get('referenz_C')), zahl(z.get('sensor_C'))
            if ref is None or ist is None:
                leer += 1
                continue
            punkte.append({'ref': ref, 'ist': ist, 'punkt_C': zahl(z.get('punkt_C')),
                           'richtung': (z.get('richtung') or 'auf').strip() or 'auf', 'nr': z.get('nr'),
                           'zeit': (z.get('zeit') or '').strip() or None,
                           'roh_code': [zahl(z.get('roh_code_a')), zahl(z.get('roh_code_b'))]})
    if not punkte:
        raise ValueError(f'{pfad}: keine Zeile mit referenz_C und sensor_C')
    # Gleiche Referenzwerte je Punkt: die Statistik gruppiert nach ref - bei schwankender Referenz nach Sollpunkt
    # gruppieren und die Abweichung je Einzelwert erhalten (ist - ref wird auf den Sollpunkt verschoben)
    for p in punkte:
        if p['punkt_C'] is not None:
            p['ist'], p['ref'] = p['punkt_C'] + (p['ist'] - p['ref']), p['punkt_C']
    erg = []
    for eig, rid in ids.items():
        r = {**kopf, 'id': rid, 'eigenschaft': eig, 'quelle_csv': os.path.basename(pfad),
             'punkte': [dict(p) for p in punkte if eig == 'hysterese' or p['richtung'] == 'auf']}
        erg.append(messreihe_eintragen(pdir, r))
    return {'reihen': erg, 'zeilen': len(punkte), 'uebersprungen_leer': leer}


def kalibrierung_auswerten(pdir, reihe_id, grad=2):
    """Kalibrierreihe (messung.json) auswerten und - nur wenn nachweisfaehig (rueckfuehrbar gemessen, Referenz- und
    Kopplungsunsicherheit bekannt) - Koeffizienten und Unsicherheiten in soll.json _projekt.messkette.kalibrierung
    schreiben, Herkunft 'gemessen: Reihe ...'. Sonst nur Ergebnis zurueckgeben, nichts schreiben."""
    from .sensorprofile import rtd
    reihe = next((r for r in lade(pdir, 'messung.json', {}).get('reihen', []) if r.get('id') == reihe_id), None)
    if not reihe:
        raise ValueError(f'Reihe {reihe_id} nicht in messung.json')
    p = os.path.join(pdir, 'cad', 'soll.json')
    s = lade(pdir, 'cad/soll.json', {})
    mk = s.get('_projekt', {}).get('messkette') or {}
    erg = rtd.kalibrierung_auswerten(reihe, mk.get('messbereich') or {}, grad)
    erg['geschrieben'] = False
    if erg.get('nachweisfaehig'):
        kal = mk.setdefault('kalibrierung', {})
        kal.update({k: erg[k] for k in ('koeffizienten', 'grad', 'u_fit', 'freiheitsgrade_fit', 'u_referenz',
                                        'u_kopplung', 'reihe', 'datum')})
        h = s['_projekt'].setdefault('_herkunft', {})
        quelle = f'gemessen: Kalibrierreihe {reihe_id} vom {reihe.get("datum")}, Referenz ' \
                 f'{(reihe.get("referenz") or {}).get("kalibrierschein")}'
        for f in ('koeffizienten', 'u_fit', 'u_referenz', 'u_kopplung'):
            h[f'messkette.kalibrierung.{f}'] = quelle
        json.dump(s, open(p, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
        erg['geschrieben'] = True
    return erg


def feld_abgleich(pdir, katalog=None, feldfall_ordner=None):
    """Vorhersage gegen Messung. Ist die Vorhersage optimistischer als Messung + Toleranz, wird ein Feldfall
    (Regressionstest) unter tests/feldfaelle/ geschrieben – das Modell muss danach mindestens so pessimistisch sein."""
    feld = lade(pdir, 'feld.json', {'messungen': []})
    if katalog is None:
        from . import pruefungen
        katalog = pruefungen.alle(pdir)['module']
    erg = feld_vergleich(feld, katalog)
    faelle = []
    for z in erg:
        if z.get('urteil') == 'zu_optimistisch':
            m, pid, schluessel, gem, tol = z['messung'], z['pruefung'], z['schluessel'], z['_gem'], z['toleranz']
            ordner = feldfall_ordner or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                     'tests', 'feldfaelle')
            os.makedirs(ordner, exist_ok=True)
            name = f'{os.path.basename(pdir)}_{pid}_{m["groesse"]}_{m["datum"]}.json'
            json.dump({'projekt': os.path.basename(pdir), 'pruefung': pid, 'schluessel': schluessel,
                       'gemessen_umgerechnet': gem, 'toleranz': tol, 'messung': m,
                       'soll_projekt': _soll(pdir).get('_projekt', {}),
                       'regel': 'Modell darf nicht optimistischer als gemessen + Toleranz sein'},
                      open(os.path.join(ordner, name), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
            faelle.append(name)
    for z in erg:
        z.pop('_gem', None)
        z.pop('schluessel', None)
    return {'abgleich': erg, 'neue_feldfaelle': faelle}


def feld_vergleich(feld, katalog):
    """Vorhersage gegen Feldmessung, ohne Seiteneffekte (fuer feld_abgleich und die V-Matrix)."""
    alle_e = [e for l in katalog.values() for e in l]
    erg = []
    for m in feld.get('messungen', []):
        v = VORHERSAGE.get(m['groesse'])
        if not v:
            erg.append({'messung': m, 'urteil': 'keine Vorhersage zugeordnet'})
            continue
        pid, schluessel, umr, tol = v
        e = next((x for x in alle_e if x['id'] == pid and (x.get('daten') or schluessel is None)), None)
        if not e:
            erg.append({'messung': m, 'urteil': f'{pid} hat keine Vorhersage (Eingaben fehlen)'})
            continue
        vorh = (e.get('daten') or {}).get(schluessel) if schluessel else e.get('wert')
        if vorh is None:
            erg.append({'messung': m, 'urteil': f'{pid}: Vorhersagewert fehlt'})
            continue
        gem = umr(m['wert'])
        diff = vorh - gem
        tol = tol if tol is not None else abs(gem) * 0.2
        urteil = 'zu_optimistisch' if diff > tol else ('passt' if abs(diff) <= tol else 'zu_pessimistisch')
        erg.append({'messung': m, 'pruefung': pid, 'vorhersage': round(vorh, 2), 'gemessen_umgerechnet': round(gem, 2),
                    'abweichung': round(diff, 2), 'toleranz': tol, 'urteil': urteil, '_gem': gem,
                    'schluessel': schluessel})
    return erg

