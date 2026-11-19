"""Alle Befehle an einer Stelle. CLI (python -m mb2) und MCP-Server lesen diese Tabelle -
Name, Docstring und Parameter gibt es nur einmal. Schwere Module werden erst im Befehl importiert."""
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJEKTE = os.path.join(BASE, 'projects')
BEFEHLE = {}


def befehl(gruppe):
    def reg(fn):
        fn.gruppe = gruppe
        BEFEHLE[fn.__name__] = fn
        return fn
    return reg


def pdir(projekt):
    d = os.path.join(PROJEKTE, projekt)
    if not os.path.isdir(d):
        raise RuntimeError(f'Projekt {projekt!r} gibt es nicht ({PROJEKTE}). Erst project_new.')
    return d


# ---------------------------------------------------------------- Projekt

# Einsatzbedingungen, die jede Pruefung braucht (Audit Scheinsicherheit 15.11.2026). Unbekannt -> None: realterme
# rechnet dann ungünstig und meldet hoechstens warnung; ein erkanntes Merkmal ohne Eingabe ist ein Katalog-fehler.
EINSATZ_FELDER = {
    'aussen': 'true/false – Sonne, UV, Kaelte, Regen',
    'T_min_C': 'kaelteste Umgebung am Teil (C)',
    'T_max_C': 'waermste Umgebungsluft am Teil (C), ohne Sonne',
    'farbe': 'Filamentfarbe (Sonne: Absorption)',
    'material': 'PLA/PETG/ASA (Standard aus Einsatz: aussen/warm -> PETG/ASA)',
    'lebensdauer_h': 'geplante Nutzungsdauer in Stunden (Kriechen, Alterung)',
    'akku_mAh': 'Akku/Batterie-Kapazitaet (falls vorhanden)',
    'akku_chemie': 'lipo | li_fes2 (L91) | alkali | lifepo4 | nimh',
    'laufzeit_ziel_h': 'Laufzeit-Ziel je Ladung/Batteriesatz (h)',
    'fallhoehe_m': 'Fallhoehe bei Handgeraeten (m)',
}


# Projektziele: werden beim Start abgefragt. "unbekannt" ist eine erlaubte Antwort (wird als Risiko gefuehrt).
ZIEL_FELDER = {
    'zielkosten_eur_stueck': 'Bauteil- und Materialkosten je Geraet in EUR (ohne Arbeitszeit)',
    'stueckzahl': 'wie viele Geraete gebaut werden',
    'termin': 'bis wann das erste Geraet fertig und geprueft sein muss (JJJJ-MM-TT)',
    'aufwand_h_stueck': 'Arbeitszeit je Geraet in Stunden (Bau, Abgleich, Pruefung)',
    'fehlerfolge': 'was passiert, wenn das Geraet falsch arbeitet: gering | mittel | hoch',
    'prioritaet': 'Reihenfolge von qualitaet, kosten, zeit - was gibt bei einem Konflikt nach?',
    'pruefmittel': 'vorhandene Mess- und Pruefgeraete (Liste)',
    'zeit_h_pro_woche': 'wie viele Stunden pro Woche fuer das Projekt verfuegbar sind (fuer Aufwand gegen Termin)',
}


@befehl('projekt')
def project_new(projekt: str, idee: str, anforderungen: str = '', einsatz: dict | None = None,
                ziele: dict | None = None):
    """Projektordner anlegen: electronics/ cad/ out/ fem/ print/ + projekt.md + cad/soll.json mit _projekt-Vorlage.
    einsatz = Einsatzbedingungen {aussen, T_min_C, T_max_C, farbe, material, lebensdauer_h, akku_mAh, akku_chemie,
    laufzeit_ziel_h, fallhoehe_m, elektronik: {funk: {r_m, umgebung, hindernisse, kabel, ...}, module: [...]},
    nicht_relevant: {ID: Grund}} – was unbekannt ist, weglassen (dann ungünstig gerechnet).
    ziele = Projektziele (ZIEL_FELDER: Zielkosten, Stueckzahl, Termin, Aufwand, Fehlerfolge, Prioritaet, Pruefmittel);
    jede Angabe vorher hinterfragen (Quelle, Plausibilitaet, Widerspruch), "unbekannt" ist erlaubt. Danach eingaben_offen."""
    d = os.path.join(PROJEKTE, projekt)
    if os.path.exists(d):
        raise RuntimeError('Gibt es schon: ' + d)
    for sub in ('electronics', 'cad', 'out', 'fem', 'print'):
        os.makedirs(os.path.join(d, sub))
    einsatz = dict(einsatz or {})
    zeilen = [f'- {k}: {einsatz[k]}' if k in einsatz else f'- {k}: **offen** ({v})' for k, v in EINSATZ_FELDER.items()]
    if (einsatz.get('elektronik') or {}).get('funk'):
        zeilen.append(f'- Funkstrecke: {einsatz["elektronik"]["funk"]}')
    ziele = dict(ziele or {})
    zielzeilen = [f'- {k}: {ziele[k]}' if k in ziele else f'- {k}: **offen** ({v})' for k, v in ZIEL_FELDER.items()]
    if ziele:
        einsatz['ziele'] = ziele
    with open(os.path.join(d, 'projekt.md'), 'w', encoding='utf-8') as f:
        f.write(f'# {projekt}\n\n## Idee\n{idee}\n\n## Anforderungen\n{anforderungen or "-"}\n\n'
                '## Ziele (KPIs)\n' + '\n'.join(zielzeilen) + '\n\n'
                '## Einsatzbedingungen\n' + '\n'.join(zeilen) + '\n\n## Entscheidungen\n\n## Audit\n')
    einsatz.setdefault('nicht_relevant', {})
    einsatz.setdefault('_herkunft', {})
    json.dump({'_projekt': einsatz}, open(os.path.join(d, 'cad', 'soll.json'), 'w', encoding='utf-8'),
              indent=1, ensure_ascii=False)
    from . import anforderungen as an
    an.erzeugen(d)
    an.abnahme_erzeugen(d)
    return {'projekt': d, 'offen': [k for k in EINSATZ_FELDER if k not in einsatz],
            'ziele_offen': [k for k in ZIEL_FELDER if k not in ziele],
            'naechstes': 'Lastenheft: eigene Anforderungen des Nutzers in anforderungen.json (Ebene system, herkunft), '
                         '_projekt._herkunft je Einsatzwert (gemessen|datenblatt|geschaetzt|angenommen: Beleg), '
                         'dann eingaben_offen'}


@befehl('projekt')
def eingaben_offen(projekt: str):
    """Welche Eingaben fehlen, damit die Pruefungen echt statt angenommen rechnen: erkannte Merkmale (Funk, Akku,
    aussen, Schrauben ...) mit fehlender Eingabe (= Katalog-fehler), Realterm-Annahmen (= hoechstens warnung) und
    offene Einsatzbedingungen. Rechnet keine FEM; Laufzeit wie pruefkatalog. Nach project_new und nach jedem Schritt."""
    from . import pruefungen
    d = pdir(projekt)
    r = pruefungen.alle(d)
    pj = pruefungen.projekt_soll(d)
    pflicht, annahmen, entwurf = [], [], []
    for l in r['module'].values():
        for e in l:
            if e.get('ausloeser') or (e['stufe'] == 'fehler' and 'Merkmal "' in (e.get('hinweis') or '')):
                zeile = f'{e["id"]}{" [" + e["teil"] + "]" if e.get("teil") else ""}: {e["hinweis"][:240]}'
                (entwurf if e.get('wartet_auf') == 'entwurf' else pflicht).append(zeile)
            elif e['stufe'] == 'warnung' and 'angenommen' in (e.get('hinweis') or ''):
                annahmen.append(f'{e["id"]}{" [" + e["teil"] + "]" if e.get("teil") else ""}: {e["hinweis"][:160]}')
    offen = {k: v for k, v in EINSATZ_FELDER.items() if pj.get(k) is None}
    zo = {k: v for k, v in ZIEL_FELDER.items() if (pj.get('ziele') or {}).get(k) is None}
    return {'merkmale': r.get('merkmale', {}), 'pflicht_fehlt': pflicht, 'wartet_auf_entwurf': entwurf,
            'annahmen': annahmen[:40], 'einsatz_offen': offen, 'ziele_offen': zo, 'nicht_relevant': pj.get('nicht_relevant', {}),
            'fertig': not pflicht and not entwurf,
            'hinweis': 'pflicht_fehlt: Eingabe nachtragen (FELDER.md) oder _projekt.nicht_relevant mit echter Begruendung; '
                       'Umgebung/Hindernisse/Temperaturen nie geschoent eintragen, nur damit es gruen wird.'}


# ---------------------------------------------------------------- V-Modell (Anforderungen, Abnahme, Feld)

@befehl('anforderungen')
def anforderungen_erzeugen(projekt: str):
    """anforderungen.json (V-Modell) anlegen/ergaenzen: Standard-Anforderungen aus Einsatz und Merkmalen (Druck,
    Festigkeit, Temperatur, Funk, Akku, Verbindungen, Montage, Funktion). Vorhandene und eigene bleiben erhalten.
    Eigene Anforderungen des Nutzers als Ebene 'system' mit herkunft ergaenzen (Form: mb2/anforderungen.py)."""
    from . import anforderungen as an
    r = an.erzeugen(pdir(projekt))
    r['abnahme'] = an.abnahme_erzeugen(pdir(projekt))
    return r


@befehl('anforderungen')
def anforderungen_pruefen(projekt: str):
    """V-Matrix: je Anforderung Status bewiesen | vorbehalt | unbewiesen | verletzt mit Belegen, Reserve gegen
    Unsicherheit, Herkunft der Eingaben, Rueckverfolgbarkeit (Eltern, V-Ebene). Freigabe: nicht_druckfertig |
    druckfertig | fertig. Schreibt pruef/v_matrix.json."""
    from . import anforderungen as an
    return an.pruefen(pdir(projekt))


@befehl('anforderungen')
def abnahme_eintragen(projekt: str, schritt: str, ist: float | str, notiz: str = ''):
    """Ist-Wert eines Abnahmeschritts am realen Geraet eintragen (abnahme.json), z. B. AB-FUNK snr_dB."""
    from . import anforderungen as an
    return an.abnahme_eintragen(pdir(projekt), schritt, ist, notiz)


@befehl('anforderungen')
def feld_eintragen(projekt: str, groesse: str, wert: float, einheit: str = '', ort: str = '', quelle: str = '',
                   datum: str = ''):
    """Messung im Einsatz festhalten (feld.json): snr_dB, rssi_dBm, empfangsquote_proz, laufzeit_h, T_teil_C ..."""
    from . import anforderungen as an
    return an.feld_eintragen(pdir(projekt), groesse, wert, einheit, ort, quelle, datum or None)


@befehl('anforderungen')
def messreihe_eintragen(projekt: str, reihe: dict):
    """Referenzmessreihe (Kalibrierung/Pruefstand) in messung.json: {id, eigenschaft, verfahren, datum, referenz {mittel,
    U, k, einheit, rueckfuehrung, gueltig_bis}, bedingungen, punkte [{ref, ist, richtung, t_h}]}. Nachweis in
    anforderungen.json: {art: messung, ref: <id>, eigenschaft, stufe: abnahme}. Format: mb2/pruefungen/messkette.py."""
    from . import anforderungen as an
    return an.messreihe_eintragen(pdir(projekt), reihe)


@befehl('anforderungen')
def messreihen_aus_csv(projekt: str, csv_datei: str, kopf: dict, ids: dict):
    """Messwert-Tabelle (Semikolon-CSV: punkt_C;richtung;nr;zeit;referenz_C;sensor_C;roh_code_a;roh_code_b) als
    Messreihen in messung.json einlesen. ids = {eigenschaft: reihen_id}; kopf = datenstatus, datum, sensor_id,
    seriennummer, verfahren, referenz {mittel, seriennummer, kalibrierschein, rueckfuehrung, U, k, einheit,
    gueltig_bis}, bedingungen, pruefunsicherheit."""
    from . import anforderungen as an
    return an.messreihen_aus_csv(pdir(projekt), csv_datei, kopf, ids)


@befehl('messtechnik')
def kalibrierung_auswerten(projekt: str, reihe: str, grad: int = 2):
    """Kalibrierreihe aus messung.json auswerten (Korrekturpolynom, u_fit, u_referenz, u_kopplung). Schreibt die
    Koeffizienten nur bei rueckfuehrbar gemessener Reihe in soll.json; danach Firmware-Konstanten KAL_K0..K2 angleichen
    (FW1) und eine UNABHAENGIGE Nachweisreihe messen - die Kalibrierreihe zaehlt nicht als Nachweis."""
    from . import anforderungen as an
    return an.kalibrierung_auswerten(pdir(projekt), reihe, grad)


@befehl('messtechnik')
def messkette_rechnen(projekt: str):
    """Unsicherheitsbudget (Einzelbeitraege, u_c, k, U) und rauschbegrenzte Aufloesung aus soll.json
    _projekt.messkette. Vereinfachtes GUM-Modell, Grenzen stehen im Ergebnis unter 'modell'."""
    from .pruefungen import messkette, projekt_soll
    return messkette.rechne(projekt_soll(pdir(projekt)))


@befehl('anforderungen')
def feld_abgleich(projekt: str):
    """Vorhersage (Katalog) gegen Feldmessung. Zu optimistisch -> Feldfall unter tests/feldfaelle/ (Regressionstest:
    das Modell muss danach mindestens so pessimistisch sein) -> realterme/E16 nachkalibrieren."""
    from . import anforderungen as an
    return an.feld_abgleich(pdir(projekt))


@befehl('projekt')
def project_status(projekt: str):
    """Was liegt vor, was ist geprueft, was fehlt als Naechstes."""
    d = pdir(projekt)
    ls = lambda sub, ext: sorted(f for f in os.listdir(os.path.join(d, sub)) if f.endswith(ext))  # noqa: E731
    teile = [f[:-3] for f in ls('cad', '.py')]
    pr = {}
    for t in teile:
        p = os.path.join(d, 'out', t + '.pruefung.json')
        pr[t] = json.load(open(p, encoding='utf-8')).get('ok') if os.path.exists(p) else None
    fem = {f[:-5]: json.load(open(os.path.join(d, 'fem', f), encoding='utf-8')).get('bewertung')
           for f in ls('fem', '.erg.json')} if os.path.isdir(os.path.join(d, 'fem')) else {}
    st = {'kicad': ls('electronics', '.kicad_pcb'), 'teile_pruefung_ok': pr, 'fem': fem,
          'platte': os.path.exists(os.path.join(d, 'print', 'platte.3mf')), 'gcode': ls('print', '.gcode')}  # .gcode deckt .bgcode mit ab
    sp = os.path.join(d, 'cad', 'soll.json')
    pj = json.load(open(sp, encoding='utf-8')).get('_projekt', {}) if os.path.exists(sp) else {}
    st['einsatz_offen'] = [k for k in EINSATZ_FELDER if pj.get(k) is None]
    if not teile:
        st['naechstes'] = 'Gehaeuse-Skript(e) in cad/ schreiben, dann cad_build'
    elif any(v is not True for v in pr.values()):
        st['naechstes'] = 'cad_build fuer nicht bestandene/ungepruefte Teile'
    elif not st['platte']:
        st['naechstes'] = 'FEM wo noetig, dann cad_plate'
    elif not st['gcode']:
        st['naechstes'] = 'slice'
    else:
        st['naechstes'] = 'Audit-Kreis abschliessen'
    return st


# ---------------------------------------------------------------- CAD

@befehl('cad')
def cad_build(projekt: str, teil: str, neu: bool = False):
    """cad/<teil>.py ausfuehren (build123d), pruefen (gueltig, Volumen/BBox gegen soll.json, Kollision mit
    Platzhaltern, Wand >= 1,8 mm, Spalt >= 0,4 mm), STEP + 3MF + PNG nach out/. Ergebnis: Pruefbericht.
    Bei ok=false NICHT weitermachen - Fehler beheben. Das PNG immer mit Read ansehen.
    Unveraenderte Eingaben (cad/, Platinendaten, mb2-Code) -> gespeicherter Bericht (aus_cache=true); neu=true erzwingt."""
    from . import cache
    d = pdir(projekt)
    erg_pfad = os.path.join(d, 'out', teil + '.pruefung.json')
    key = cache.schluessel(cache.cad_eingaben(d), {'teil': teil})
    if not neu and (hit := cache.treffer(erg_pfad, key)):
        return hit
    from . import cad
    return cache.merken(erg_pfad, cad.build(d, teil), key)


@befehl('cad')
def cad_plate(projekt: str, teile: list[str], abstand: float = 10.0):
    """Gepruefte Teile druckfertig gedreht nebeneinander auf EIN 3MF legen (print/platte.3mf + PNG).
    abstand = Luft zwischen den Teilen in mm (Standard 10, damit Brims nicht zusammenwachsen)."""
    from . import cad
    return cad.platte(pdir(projekt), teile, abstand=abstand)


@befehl('cad')
def cad_check_step(step: str, wand_min: float = 1.8, spalt_min: float = 0.4):
    """Beliebige STEP-Datei pruefen (gueltig, Masse, Wand, Spalt) - z. B. ein fremdes oder altes Teil."""
    from build123d import import_step
    from . import cad
    r = cad.pruefen(import_step(step), soll={'ausnahmen': {'wand_min': wand_min, 'spalt_min': spalt_min}})
    r.pop('_markierungen', None)
    return r


@befehl('cad')
def cad_check_3mf(pfad: str, wand_min: float = 1.8, spalt_min: float = 0.4):
    """Druckplatte als 3MF pruefen (z. B. Fusion-Export der alten Bridge): je Objekt gueltig, Masse, Wand, Spalt + PNG
    (rote Punkte = Problemstellen). Ergebnis und Bilder unter maker-bridge-2/audits/<dateiname>/."""
    from . import cad
    ziel = os.path.join(BASE, 'audits', os.path.splitext(os.path.basename(pfad))[0])
    return cad.pruefe_3mf(pfad, ziel, wand_min, spalt_min)


# ---------------------------------------------------------------- FEM

@befehl('fem')
def fem_mech(projekt: str, fall: str, neu: bool = False):
    """Mechanik mit CalculiX: fem/<fall>.json (STEP, Material, Lagerung, Lasten, optional nichtlinear/Kontakt).
    Ergebnis fem/<fall>.erg.json + PNG: max. von Mises, Sicherheit je PLA/PETG/ASA, max. Verschiebung.
    Unveraenderter Lastfall + STEP + mb2-Code -> gespeichertes Ergebnis (aus_cache=true); neu=true erzwingt."""
    return _fem_gecacht(projekt, fall, neu, 'mechanik')


@befehl('fem')
def fem_waerme(projekt: str, fall: str, neu: bool = False):
    """Waerme mit Elmer: fem/<fall>.json (STEP, Material, Waermequellen, Konvektion). Ergebnis T_max + PNG.
    Unveraenderter Lastfall + STEP + mb2-Code -> gespeichertes Ergebnis (aus_cache=true); neu=true erzwingt."""
    return _fem_gecacht(projekt, fall, neu, 'waerme')


@befehl('fem')
def fem_sensitivitaet(projekt: str, fall: str, rel: float = 0.2, nur: list[str] | None = None):
    """Sensitivitaet von fem/<fall> (V&V-40-Faktor): jede Eingabe -rel/+rel verstellt und neu gerechnet (gecacht).
    Standardsatz Mechanik: Lasten, Wegvorgaben, E-Modul + Festigkeit je Druckstoff; Waerme: Quellen, h, Waermeleitung.
    Ergebnis fem/sens/<fall>.sens.json: Kennzahl je Seite, Elastizitaet, robust (bleibt ok), vollstaendig.
    Nichtlineare/Kontakt-Faelle rechnen 2 Laeufe je Parameter - nur=[...] begrenzt."""
    from . import sensitivitaet
    d = pdir(projekt)
    alt = os.path.join(d, 'fem', fall + '.erg.json')
    art = 'mechanik' if os.path.exists(alt) and 'lastfaelle' in json.load(open(alt, encoding='utf-8')) else (
        'waerme' if os.path.exists(alt) else _art_aus_spec(d, fall))
    return sensitivitaet.studie(projekt, d, fall, art, lambda p, f, a: _fem_gecacht(p, f, False, a), rel, nur)


def _art_aus_spec(d, fall):
    s = json.load(open(os.path.join(d, 'fem', fall + '.json'), encoding='utf-8'))
    return 'waerme' if s.get('konvektion') or any(k.get('waerme_W') for k in s.get('koerper', [])) else 'mechanik'


def _fem_gecacht(projekt, fall, neu, art):
    from . import cache, werkzeuge
    d = pdir(projekt)
    erg_pfad = os.path.join(d, 'fem', fall + '.erg.json')
    loeser = werkzeuge.ccx() if art == 'mechanik' else werkzeuge.elmer_bin()
    key = cache.schluessel(cache.fem_eingaben(d, fall), {'fall': fall, 'art': art, 'loeser': str(loeser)})
    if not neu and (hit := cache.treffer(erg_pfad, key)):
        # Bewertung haengt seit 15.11.2026 an realterme (soll.json, projekt.md) -> bei jedem Abruf neu bewerten,
        # ohne neu zu rechnen (alte Caches tragen sonst die alte Idealbewertung weiter)
        if art == 'mechanik' and hit.get('lastfaelle') and hit.get('bewertung'):
            from . import fem
            spec = json.load(open(os.path.join(d, 'fem', fall + '.json'), encoding='utf-8'))
            from .material import ueberschrieben
            with ueberschrieben(spec.get('material_override')):
                rk, dauer = fem._realkontext(d, spec, fall, list(hit['lastfaelle']))
                hit['bewertung'] = fem.bewertung_mech(hit['lastfaelle'], hit['bewertung'].get('material', []),
                                                      kontext=rk, dauer=dauer)
        return hit
    from . import fem
    return cache.merken(erg_pfad, getattr(fem, art)(d, fall), key)


@befehl('fem')
def fem_materialien():
    """Materialtabelle (E, nu, Festigkeit, Waermeleitung, Glasuebergang) fuer PLA, PETG, ASA."""
    from .material import MATERIAL
    return MATERIAL


# ---------------------------------------------------------------- Elektronik

@befehl('kicad')
def kicad_new(projekt: str, breite_mm: float, hoehe_mm: float, eckloecher: bool = True):
    """KiCad-Projekt electronics/<projekt>.kicad_pro/.kicad_sch/.kicad_pcb mit Rechteck-Kontur (+ M3-Ecken)."""
    from . import kicad
    return kicad.new_project(os.path.join(pdir(projekt), 'electronics'), projekt, breite_mm, hoehe_mm, eckloecher)


@befehl('kicad')
def kicad_erc(projekt: str):
    """Elektrische Regelpruefung des Schaltplans."""
    from . import kicad
    return kicad.erc(_kfile(projekt, '.kicad_sch'))


@befehl('kicad')
def kicad_drc(projekt: str):
    """Design-Regelpruefung der Platine (inkl. Abgleich mit dem Schaltplan)."""
    from . import kicad
    return kicad.drc(_kfile(projekt, '.kicad_pcb'))


@befehl('kicad')
def kicad_sync(projekt: str, nur_schaltplan: bool = False):
    """F8 ohne KiCad-Oberflaeche: Platine aus dem Schaltplan aktualisieren (Footprints anlegen/tauschen, Werte,
    Netze). Neue Teile liegen rechts neben der Platine, dann per layout.py platzieren. nur_schaltplan=True
    entfernt auch Footprints ohne Symbol (z. B. Eckloecher aus kicad_new). KiCad muss geschlossen sein."""
    from . import kicad
    return kicad.sync_from_schematic(_kfile(projekt, '.kicad_pcb'), nur_schaltplan)


@befehl('kicad')
def kicad_layout(projekt: str, skript: str = 'layout.py'):
    """electronics/<skript> mit KiCads Python ausfuehren (Platzieren per pcbnew), cwd = electronics/.
    KiCad muss geschlossen sein. Rueckgabe: stdout/stderr (Ende) + DRC-Zaehler."""
    import subprocess
    from . import kicad
    ed = os.path.join(pdir(projekt), 'electronics')
    pfad = os.path.join(ed, skript)
    if not os.path.isfile(pfad):
        raise RuntimeError('Skript fehlt: ' + pfad)
    r = subprocess.run([kicad.kicad_python(), pfad], cwd=ed, capture_output=True, text=True, timeout=1800,
                       stdin=subprocess.DEVNULL)
    return {'ok': r.returncode == 0, 'returncode': r.returncode, 'stdout': r.stdout[-3000:], 'stderr': r.stderr[-3000:],
            'drc': kicad.drc(_kfile(projekt, '.kicad_pcb')).get('counts')}


@befehl('kicad')
def kicad_route(projekt: str, durchgaenge: int = 100):
    """Freerouting (headless). Gesperrte Bahnen bleiben, Zonen werden neu gefuellt. Danach kicad_cat + kicad_drc."""
    from . import kicad
    return kicad.autoroute(_kfile(projekt, '.kicad_pcb'), durchgaenge)


@befehl('kicad')
def kicad_cat(projekt: str, x_mm: float, y_mm: float, hoehe_mm: float = 5.0, seite: str = 'top'):
    """Katze in den Bestueckungsdruck (Pflicht fuer jede Platine). (x, y) = Pfote links unten, Platinen-Frame."""
    from . import kicad
    return kicad.add_cat(_kfile(projekt, '.kicad_pcb'), x_mm, y_mm, hoehe_mm, seite)


@befehl('kicad')
def kicad_board(projekt: str):
    """Board-Info (Masse, Bohrungen, Bauteile mit Courtyard, Teile am Rand) + board.step fuer die CAD-Skripte.
    Rahmen: Ursprung linke untere Platinenecke, Y oben, Z=0 Platinenunterseite, mm."""
    from . import kicad
    d = pdir(projekt)
    pcb = _kfile(projekt, '.kicad_pcb')
    info = kicad.board_info(pcb)
    json.dump(info, open(os.path.join(d, 'electronics', 'board_info.json'), 'w', encoding='utf-8'), indent=1)
    step = kicad.export_step(pcb, os.path.join(d, 'electronics', 'board.step'))
    return {'board_info': info, 'step': step['step'] if step['ok'] else step}


@befehl('kicad')
def kicad_render(projekt: str, seite: str = 'top', iso: bool = False):
    """PNG der Platine (kicad-cli 3D-Render) nach electronics/. Mit Read ansehen."""
    from . import kicad
    pcb = _kfile(projekt, '.kicad_pcb')
    return kicad.render(pcb, os.path.splitext(pcb)[0] + f'_{seite}{"_iso" if iso else ""}.png', seite, iso)


@befehl('kicad')
def kicad_schematic_pdf(projekt: str):
    """Schaltplan als PDF (zum Ansehen mit Read)."""
    from . import kicad
    sch = _kfile(projekt, '.kicad_sch')
    return kicad.sch_pdf(sch, os.path.splitext(sch)[0] + '.pdf')


@befehl('kicad')
def kicad_fab(projekt: str):
    """Fertigungsdaten: Gerber-ZIP, Bohrdaten, Bestueckungsliste, BOM nach electronics/fab/."""
    from . import kicad
    d = os.path.join(pdir(projekt), 'electronics')
    return kicad.export_fab(_kfile(projekt, '.kicad_pcb'), _kfile(projekt, '.kicad_sch'), os.path.join(d, 'fab'))


@befehl('kicad')
def kicad_find(art: str, suche: str):
    """Bibliothek durchsuchen: art = 'symbol' | 'footprint'. Nur Standardbibliothek."""
    from . import kicad
    return kicad.find_symbols(suche) if art == 'symbol' else kicad.find_footprints(suche)


@befehl('kicad')
def kicad_symbol(lib_id: str):
    """Symboldefinition (fuer lib_symbols) + Pinliste mit Positionen."""
    from . import kicad
    return kicad.get_symbol(lib_id)


def _kfile(projekt, ext):
    d = os.path.join(pdir(projekt), 'electronics')
    hits = [f for f in os.listdir(d) if f.endswith(ext) and '.vor-' not in f]
    if not hits:
        raise RuntimeError(f'Keine {ext} in {d} - erst kicad_new.')
    return os.path.join(d, sorted(hits)[0])


# ---------------------------------------------------------------- Slicen

def _bricklayers_objekte(d):
    """Teile mit "bricklayers": true in cad/soll.json -> {'teile': Namen, 'bbox_mm': Lage aus print/platte.json}
    oder None. Prueft, dass alle auf der aktuellen Platte liegen."""
    sp, pp = os.path.join(d, 'cad', 'soll.json'), os.path.join(d, 'print', 'platte.json')
    if not os.path.exists(sp):
        return None
    soll = json.load(open(sp, encoding='utf-8'))
    gewollt = {t for t, v in soll.items() if isinstance(v, dict) and v.get('bricklayers')}
    if not gewollt:
        return None
    platte = json.load(open(pp, encoding='utf-8')) if os.path.exists(pp) else {}
    if 'bbox_mm' not in platte:
        raise RuntimeError('bricklayers gesetzt, aber print/platte.json ohne Lagen - cad_plate neu ausfuehren.')
    fehlt = gewollt - set(platte['teile'])
    if fehlt:
        raise RuntimeError(f'bricklayers fuer {sorted(fehlt)} gesetzt, die nicht auf der Platte liegen.')
    return {'teile': gewollt, 'bbox_mm': platte['bbox_mm']}


@befehl('slice')
def slice_plate(projekt: str, material: str = 'Prusament PETG @PGIS', druck: str = '0.20mm SPEED @MK4IS 0.4',
          stuetzen: bool = False, brim_mm: float = 0.0, perimeter: int = 0):
    """print/platte.3mf fuer Prusa MK4 IS 0.4 slicen -> print/<projekt>.bgcode + PrusaSlicer-Projekt.
    Profile aus dem Bundle aufgeloest, danach im G-Code geprueft. Bei problems NICHT drucken.
    brim_mm > 0: Brim nur aussen (hohe, schmale Teile). perimeter > 0: Wandlinien statt Profilwert.
    Teile mit "bricklayers": true in cad/soll.json bekommen versetzte Innenwaende -> print/<projekt>.gcode.
    Schickt nichts an den Drucker."""
    from . import slicer
    d = pdir(projekt)
    bl = _bricklayers_objekte(d)
    erg = slicer.slice_platte(os.path.join(d, 'print', 'platte.3mf'), os.path.join(d, 'print', projekt + '.bgcode'),
                              druck, material, stuetzen, brim_mm=brim_mm, perimeter=perimeter, bricklayers=bl)
    if bl:
        erg['bricklayers_teile'] = sorted(bl['teile'])
    # Druckfreigabe nur mit validen CAD-Daten fuer alle Kaufteile (Regel des Nutzers, 11.11.2026)
    offen = []
    for f in sorted(os.listdir(os.path.join(d, 'out'))) if os.path.isdir(os.path.join(d, 'out')) else []:
        if f.endswith('.pruefung.json'):
            b = json.load(open(os.path.join(d, 'out', f), encoding='utf-8'))
            offen += [f'{b.get("teil")}: {x}' for x in b.get('ungeprueft') or []]
    if offen:
        erg['ok'] = False
        erg['ungeprueft'] = offen
        erg['probleme'] = (erg.get('probleme') or []) + [
            'Kaufteile ohne valide CAD-Quelle (nur Entwurf, NICHT drucken): ' + '; '.join(offen)]
    json.dump(erg, open(os.path.join(d, 'print', 'slice.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False,
              default=str)
    return erg


@befehl('slice')
def slice_profiles(suche: str = ''):
    """Druck- und Filamentprofile fuer den MK4 IS 0.4 (z. B. suche='ASA')."""
    from . import slicer
    return slicer.list_profiles(slicer.DRUCKER, suche)


# ---------------------------------------------------------------- Audit

def _katalog_zeile(modul, e):
    teil = f' [{e["teil"]}]' if e.get('teil') else ''
    wert = f' ({e["wert"]}{" " + e["einheit"] if e.get("einheit") else ""}' \
           f'{", Grenze " + str(e["grenze"]) if e.get("grenze") is not None else ""})' if e.get('wert') is not None else ''
    return f'{e["id"]}{teil} {e["titel"]}{wert}: {e.get("hinweis") or ""} <{modul}>'


@befehl('audit')
def pruefkatalog(projekt: str, module: list[str] | None = None):
    """Analytische Katalog-Pruefungen (OCW_PRUEFKATALOG.md, mb2/pruefungen: fem_plausi, waerme, mechanik, dauer,
    toleranz, schwingung, elektronik). Liest nur vorhandene Ergebnisse (STEP, FEM, Slicer, KiCad), rechnet KEINE FEM.
    Schreibt pruef/katalog.json (alle Ergebnisse mit ID, Quelle, Wert, Grenze, Hinweis). Ergebnis: zaehlung je Stufe,
    fehler + warnungen als Zeilen, uebersprungen je ID (fehlende Eingabe -> soll-Feld nachtragen, siehe
    mb2/pruefungen/FELDER.md). module = Teilmenge, Standard alle."""
    import time
    from . import pruefungen
    d = pdir(projekt)
    t0 = time.time()
    r = pruefungen.alle(d, tuple(module) if module else pruefungen.MODULE)
    zeilen = lambda st: [_katalog_zeile(m, e) for m, l in r['module'].items() for e in l if e['stufe'] == st]  # noqa: E731
    ueber = {}
    for l in r['module'].values():
        for e in l:
            if e['stufe'] == 'uebersprungen':
                ueber[e['id']] = ueber.get(e['id'], 0) + 1
    return {'ok': r['ok'], 'zaehlung': r['zaehlung'], 'fehler': zeilen('fehler'), 'warnungen': zeilen('warnung'),
            'uebersprungen_je_id': ueber, 'hochgestuft': r.get('hochgestuft', 0), 'merkmale': r.get('merkmale', {}),
            'laufzeit_s': round(time.time() - t0, 1),
            'datei': os.path.join(d, 'pruef', 'katalog.json')}


@befehl('audit')
def audit(projekt: str):
    """Alle messbaren Pruefungen des Audit-Kreises in EINEM Aufruf, deterministisch: cad_build je Teil und jeder
    schon gerechnete FEM-Fall (beides gecacht, rechnet nur Geaendertes neu), DRC, Druckplatte und G-Code gegen
    veraltete Staende (aelter als ihre Eingaben), Slicer-Profilpruefung, danach die Katalog-Pruefungen (pruefkatalog,
    pruef/katalog.json). Ergebnis: maengel (Katalog-'fehler' als 'Katalog ...'), katalog_warnungen, katalog, bilder.
    Ersetzt NICHT den Blick des Pruefers auf Bilder, Ueberhaenge, Montage und Anforderungen."""
    d = pdir(projekt)
    maengel, bilder, teile, fem_erg = [], [], {}, {}
    mt = lambda p: os.path.getmtime(p) if os.path.exists(p) else None  # noqa: E731

    for f in sorted(os.listdir(os.path.join(d, 'cad'))):
        if not f.endswith('.py'):
            continue
        t = f[:-3]
        try:
            b = cad_build(projekt, t)
        except Exception as e:  # noqa: BLE001 - Skriptfehler ist ein Mangel, kein Abbruch des Audits
            maengel.append(f'Teil {t}: Skript laeuft nicht ({type(e).__name__}: {e})')
            continue
        teile[t] = {k: b.get(k) for k in ('ok', 'wand_min_mm', 'spalt_min_mm', 'kollision_mm3', 'volumen_abweichung',
                                          'fehler', 'warnungen', 'ausnahmen', 'aus_cache', 'ungeprueft') if k in b}
        bilder.append(b['dateien']['png'])
        if not b.get('ok'):
            maengel.append(f'Teil {t}: Pruefung nicht bestanden: {b.get("fehler")}')
        if b.get('ungeprueft'):
            maengel.append(f'Teil {t}: Kaufteile ohne valide CAD-Quelle (vor dem Druck Hersteller-STEP/Zeichnung '
                           f'oder Messung): {"; ".join(b["ungeprueft"])}')

    fem_dir = os.path.join(d, 'fem')
    for f in sorted(os.listdir(fem_dir)) if os.path.isdir(fem_dir) else []:
        if not f.endswith('.json') or f.endswith('.erg.json'):
            continue
        fall = f[:-5]
        alt = os.path.join(fem_dir, fall + '.erg.json')
        if not os.path.exists(alt):
            maengel.append(f'FEM {fall}: Lastfall angelegt, aber nie gerechnet')
            continue
        art = 'mechanik' if 'lastfaelle' in json.load(open(alt, encoding='utf-8')) else 'waerme'
        try:
            e = _fem_gecacht(projekt, fall, False, art)
        except Exception as ex:  # noqa: BLE001
            maengel.append(f'FEM {fall}: Rechnung scheitert ({type(ex).__name__}: {ex})')
            continue
        fem_erg[fall] = {'art': art, 'bewertung': e.get('bewertung'), 'aus_cache': e.get('aus_cache', False)}
        bilder += [lf['bild'] for lf in e.get('lastfaelle', {}).values() if lf.get('bild')] +                   ([e['bild']] if e.get('bild') else [])
        if not (e.get('bewertung') or {}).get('ok'):
            maengel.append(f'FEM {fall}: Bewertung nicht ok: {e.get("bewertung")}')

    kicad = None
    el = os.path.join(d, 'electronics')
    if any(x.endswith('.kicad_pcb') for x in os.listdir(el)):
        r = kicad_drc(projekt)
        kicad = {'drc': r.get('counts', {})}
        if r.get('counts', {}).get('error'):
            maengel.append(f'DRC: {r["counts"]["error"]} Fehler')
        pcb, step = _kfile(projekt, '.kicad_pcb'), os.path.join(el, 'board.step')
        if mt(step) is None or mt(step) < mt(pcb):
            maengel.append('board.step fehlt oder ist aelter als die Platine - kicad_board neu, dann cad_build')
        txt = open(pcb, encoding='utf-8', errors='replace').read()
        if '(group "Katze"' not in txt:
            maengel.append('Keine Katze im Bestueckungsdruck gefunden (kicad_cat)')

    platte = os.path.join(d, 'print', 'platte.3mf')
    steps = [mt(os.path.join(d, 'out', t + '.step')) for t in teile]
    steps = [x for x in steps if x]
    if mt(platte) is None:
        maengel.append('Keine Druckplatte (cad_plate)')
    elif steps and mt(platte) < max(steps):
        maengel.append('Druckplatte aelter als ein Teil - cad_plate neu')
    if os.path.exists(platte):
        bilder.append(os.path.join(d, 'print', 'platte.png'))

    sl = os.path.join(d, 'print', 'slice.json')
    slicen = json.load(open(sl, encoding='utf-8')) if os.path.exists(sl) else None
    # mit Bricklayers entsteht .gcode statt .bgcode (slice.json sagt welches)
    gcode = (slicen or {}).get('gcode') or os.path.join(d, 'print', projekt + '.bgcode')
    if _bricklayers_objekte(d) and not (slicen or {}).get('bricklayers'):
        maengel.append('bricklayers in soll.json gesetzt, aber der G-Code ist ohne - slice_plate neu')
    if mt(gcode) is None:
        maengel.append('Kein G-Code (slice_plate)')
    elif mt(platte) and mt(gcode) < mt(platte):
        maengel.append('G-Code aelter als die Druckplatte - slice_plate neu')
    if slicen and (not slicen.get('ok') or slicen.get('probleme')):
        maengel.append(f'Slicer-Profilpruefung: {slicen.get("probleme")}')

    # Katalog-Pruefungen zuletzt: lesen die eben (gecacht) erzeugten CAD-/FEM-Ergebnisse, rechnen selbst nichts neu
    katalog, katalog_warnungen = None, []
    try:
        k = pruefkatalog(projekt)
        katalog = {'zaehlung': k['zaehlung'], 'uebersprungen_je_id': k['uebersprungen_je_id'],
                   'hochgestuft': k.get('hochgestuft', 0), 'merkmale': k.get('merkmale', {}),
                   'laufzeit_s': k['laufzeit_s'], 'datei': k['datei']}
        maengel += [f'Katalog {z}' for z in k['fehler']]
        katalog_warnungen = k['warnungen']
    except Exception as ex:  # noqa: BLE001 - nicht laufende Pruefungen sind ein Mangel, kein stilles ok
        maengel.append(f'Katalog-Pruefungen laufen nicht ({type(ex).__name__}: {ex})')

    # V-Modell: Beweispflicht je Anforderung (gruen nur mit Beleg, nicht "nichts gefunden")
    vmatrix, freigabe = None, 'nicht_druckfertig'
    try:
        from . import anforderungen as an
        kat = json.load(open(os.path.join(d, 'pruef', 'katalog.json'), encoding='utf-8')) if katalog else None
        v = an.pruefen(d, katalog=kat, extra={'kicad': kicad})
        freigabe = v['freigabe']
        vmatrix = {'freigabe': freigabe, 'zaehlung': v['zaehlung'], 'offen_abnahme': v['offen_abnahme'],
                   'risiken': v.get('risiken', []), 'messtechnische_freigabe': v['messtechnische_freigabe']['status'],
                   'datei': os.path.join(d, 'pruef', 'v_matrix.json')}
        maengel += [f'V-Matrix: {m}' for m in v['matrix_maengel']]
        for z in v['anforderungen']:
            vor_abnahme = [n for n in z['nachweise'] if n['stufe'] in ('komponente', 'integration')]
            if z['status'] == 'verletzt' or any(n['status'] in ('verletzt', 'unbewiesen') for n in vor_abnahme):
                maengel.append(f'Anforderung {z["id"]} {z["status"]}: '
                               + '; '.join(n['beleg'] for n in z['nachweise'] if n['status'] != 'bewiesen'))
            for m in z['matrix_maengel']:
                maengel.append(f'Anforderung {z["id"]}: {m}')
    except Exception as ex:  # noqa: BLE001
        maengel.append(f'V-Matrix laeuft nicht ({type(ex).__name__}: {ex})')

    return {'messbar_ok': not maengel, 'freigabe': freigabe if not maengel or freigabe == 'nicht_druckfertig'
            else 'nicht_druckfertig', 'v_matrix': vmatrix,
            'maengel': maengel, 'katalog_warnungen': katalog_warnungen,
            'katalog': katalog, 'teile': teile, 'fem': fem_erg, 'kicad': kicad,
            'slicen': {k: slicen.get(k) for k in ('ok', 'stats', 'probleme')} if slicen else None,
            'bilder': [b for b in bilder if os.path.exists(b)],
            'offen_fuer_pruefer': 'Bilder ansehen, Ueberhaenge/Bruecken in Druckrichtung, Montage, Anforderungen aus '
                                  'projekt.md, fehlende Lastfaelle, Kippgefahr - das misst audit nicht.'}


# ---------------------------------------------------------------- Werkzeuge

@befehl('werkzeuge')
def tools_status():
    """Wo liegen ccx, Elmer, KiCad, PrusaSlicer, Java, Freerouting."""
    from . import werkzeuge
    return werkzeuge.status()
