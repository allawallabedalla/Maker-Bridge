"""Analytische Pruefungen aus dem OCW-Pruefkatalog (OCW_PRUEFKATALOG.md).

Jedes Fachmodul in diesem Paket hat eine Funktion ``pruefe(pdir: str) -> list[dict]``. Sie liest selbst, was sie
braucht, aus dem Projektordner (cad/soll.json, out/*.pruefung.json, out/*.step, fem/*.json + *.erg.json,
print/slice.json, electronics/...) und gibt eine Liste von Ergebnissen zurueck (Form siehe ``ergebnis``).

Regeln fuer alle Module:
- Fehlt eine Eingabe (Kennwert, soll-Feld, FEM-Ergebnis), meldet die Pruefung stufe='uebersprungen' mit Grund.
  ABER (seit 15.11.2026): enthaelt der Entwurf erkennbar das Merkmal, um das es geht (``merkmale.py``, Tabelle
  ``AUSLOESER``), stuft ``alle`` das Ueberspringen zu 'fehler' hoch – und meldet eine Pruefung bei ausgeloestem Merkmal
  gar nichts, ergaenzt ``alle`` einen 'fehler'. Verzicht nur ausdruecklich: ``_projekt.nicht_relevant: {"S4": "Grund"}``.
- Idealformeln holen ihre Abschlaege aus ``mb2/realterme.py``; Annahmen erlauben hoechstens 'warnung'.
- Keine Pruefung darf einen Alarm unterdruecken; im Zweifel 'warnung' statt 'ok'.
- Jede Pruefung nennt ihre Katalog-ID (z. B. 'M5') und die Quelle.
- Nichts schreiben ausser optional ``<pdir>/pruef/<modul>.json`` (macht ``alle`` selbst).
"""
import importlib
import re
import json
import os

MODULE = ('fem_plausi', 'waerme', 'mechanik', 'dauer', 'toleranz', 'schwingung', 'elektronik', 'druck', 'firmware',
          'messkette', 'kpi', 'widerspruch', 'stroemung', 'daten')
STUFEN = ('ok', 'info', 'warnung', 'fehler', 'uebersprungen')


def ergebnis(id, titel, stufe, *, wert=None, grenze=None, einheit='', quelle='', hinweis='', teil=None, daten=None):
    """Einheitliches Ergebnis einer Pruefung."""
    assert stufe in STUFEN, stufe
    e = {'id': id, 'titel': titel, 'stufe': stufe, 'wert': wert, 'grenze': grenze, 'einheit': einheit,
         'quelle': quelle, 'hinweis': hinweis}
    if teil is not None:
        e['teil'] = teil
    if daten:
        e['daten'] = daten
    return e


def uebersprungen(id, titel, grund, quelle='', teil=None):
    return ergebnis(id, titel, 'uebersprungen', quelle=quelle, hinweis=grund, teil=teil)


def soll(pdir):
    """cad/soll.json (je Teil ein Eintrag) – leer, wenn nicht vorhanden. Projektweite Felder unter '_projekt'."""
    p = os.path.join(pdir, 'cad', 'soll.json')
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}


def projekt_soll(pdir):
    return soll(pdir).get('_projekt', {})


# Merkmal -> (Pruef-IDs, noetige Eingabe). Ein 'uebersprungen' dieser IDs bei aktivem Merkmal ist ein 'fehler'.
# Neue Pruefungen tragen hier eine Zeile ein, statt still zu schweigen.
# 'E1-E25' (Elektronik ganz uebersprungen) zaehlt fuer jedes E-Ziel; 'E-Rest' (Kaufmodul: E6/E8/E15/E16/E21 gerechnet,
# Rest braucht KiCad) ist bewusst KEIN Ausloeser-Ziel.
AUSLOESER = {
    'funk': (('E16', 'E15'), 'soll.json _projekt.elektronik.funk {r_m, umgebung, hindernisse, kabel, P_t_dBm, '
                             'P_rx_min_dBm, G_t_dBi, G_r_dBi}; Kaufmodul: elektronik.module'),
    'akku': (('E6', 'E8', 'E21'), 'akku_mAh, akku_chemie, laufzeit_ziel_h, T_min_C (Kaufmodul: elektronik.module)'),
    'aussen': (('W6', 'D1'), '_projekt.aussen/farbe, T_max_C, T_min_C'),
    'elektronik': (('D1',), '_projekt.T_max_C (Luft am Teil) oder Waerme-FEM'),
    'schrauben': (('M12', 'M13', 'D4'), 'Teil.schrauben [{d_mm, anzahl, vorspannung_N, art, ...}]'),
    'schnapper': (('M1', 'M2'), 'Teil.schnapper [{L_mm, b_mm, t_mm, hinterschnitt_mm, ...}]'),
    'dauerlast': (('D2', 'D3'), 'Teil.dauerlast'),
    'handgeraet': (('S4',), '_projekt.fallhoehe_m, masse_g'),
    'anregung': (('S2',), '_projekt.anregung_Hz'),
    'lautsprecher': (('S5',), '_projekt.lautsprecher / elektronik.lautsprecher_Ohm'),
    'fem_mech': (('M7', 'M9'), 'Druckrichtung (druck_drehung) bzw. Slice'),
    'firmware': (('FW1', 'FW2'), '_projekt.firmware {pfad, konstanten: {NAME: {datei, soll|soll_aus}}, hosttest: '
                                 '{quellen, test}} und Befehl firmware_test (Rechenlogik am PC)'),
    'ziele': (('K1', 'K2'), '_projekt.ziele {zielkosten_eur_stueck, aufwand_h_stueck} und kosten.json {posten, '
                            'arbeitsschritte} (Ziel "unbekannt" ist erlaubt und wird als Risiko gemeldet)'),
    'fluid': (('FL1', 'FL2'), '_projekt.stroemung {medium: {viskositaet_Pa_s, dichte_kg_m3}, kanaele: [{d_mm|b_mm+h_mm, '
                              'L_mm, Q_max_ml_min, dp_max_Pa, einlauf_vor_sensor_mm}]} mit _herkunft der Stoffwerte'),
    'daten': (('DS1',), '_projekt.daten {datensatz_bytes, intervall_s, speicher_bytes, aufbewahrung_h, uebertragung, '
                        'schreibzyklen_max, schreibblock_bytes}'),
    'messung': (('MK1', 'MK2'), '_projekt.messkette {adc_bits, v_ref_V, adc_rauschen_V, u_ref_V, '
                                'empfindlichkeit_V_je_einheit, ziel_U, ziel_aufloesung, ...}'),
}


def _ausloeser_anwenden(pdir, erg):
    """Hochstufen nach AUSLOESER. Gibt (merkmale, anzahl_hochgestuft) zurueck; aendert erg an Ort und Stelle."""
    from .merkmale import merkmale as _merkmale
    try:
        mk = _merkmale(pdir)
    except Exception as ex:  # noqa: BLE001 - Merkmale nicht lesbar ist selbst ein Befund
        erg.setdefault('ausloeser', []).append(ergebnis('A0', 'Projektmerkmale', 'fehler',
                                                        hinweis=f'merkmale.py abgestuerzt: {type(ex).__name__}: {ex}'))
        return {}, 0
    verzicht = projekt_soll(pdir).get('nicht_relevant', {}) or {}
    n = 0
    gesehen = set()
    for name, (ids, eingabe) in AUSLOESER.items():
        info = mk.get(name) or {}
        if not info.get('aktiv'):
            continue
        for l in erg.values():
            for e in l:
                eid = e['id']
                treffer = [i for i in ids if eid == i or eid.startswith(i + '-') or (eid == 'E1-E25' and i.startswith('E'))]
                if not treffer:
                    continue
                gesehen.update(treffer)
                if e['stufe'] != 'uebersprungen':
                    continue
                grund = verzicht.get(treffer[0]) or verzicht.get(eid)
                if grund:
                    e['stufe'] = 'info'
                    e['hinweis'] = f'nicht relevant laut soll.json: {grund} (Merkmal {name}: {info["quelle"]}). ' + e['hinweis']
                else:
                    e['stufe'] = 'fehler'
                    e['hinweis'] = (f'Merkmal "{name}" erkannt ({info["quelle"]}), Pruefung nicht gerechnet: '
                                    f'{e["hinweis"]}. Noetig: {eingabe}')
                    e['ausloeser'] = name
                    # Grund ist der Entwurfsstand (noch kein Teil/keine Geometrie), nicht eine fehlende Angabe
                    entwurf = re.search(r'keine (Teile|Geometrie)|kein Pruefbericht|keine \.kicad_pcb', e['hinweis'])
                    e['wartet_auf'] = 'entwurf' if entwurf and 'soll-Daten' not in e['hinweis'] else 'eingabe'
                    n += 1
        for i in ids:
            if i in gesehen:
                continue
            if verzicht.get(i):
                erg.setdefault('ausloeser', []).append(ergebnis(i, f'{i} (Ausloeser {name})', 'info',
                                                                hinweis=f'nicht relevant laut soll.json: {verzicht[i]}'))
                continue
            erg.setdefault('ausloeser', []).append(ergebnis(
                i, f'{i} (Ausloeser {name})', 'fehler',
                hinweis=f'Merkmal "{name}" erkannt ({info["quelle"]}), aber {i} hat kein Ergebnis geliefert. '
                        f'Eingabe nachtragen: {eingabe} – oder _projekt.nicht_relevant.{i} mit Begruendung.'))
            gesehen.add(i)
            n += 1
    return mk, n


def alle(pdir, module=MODULE):
    """Alle Fachmodule laufen lassen. Ein Absturz eines Moduls wird als 'fehler' gemeldet, nicht verschluckt.
    Danach Ausloeser-Hochstufung (siehe AUSLOESER)."""
    erg = {}
    for m in module:
        try:
            mod = importlib.import_module(f'mb2.pruefungen.{m}')
            liste = mod.pruefe(pdir)
        except ModuleNotFoundError as ex:
            if ex.name == f'mb2.pruefungen.{m}':
                continue
            liste = [ergebnis(m, f'Modul {m}', 'fehler', hinweis=f'{type(ex).__name__}: {ex}')]
        except Exception as ex:  # noqa: BLE001 - Modulfehler sichtbar machen
            liste = [ergebnis(m, f'Modul {m}', 'fehler', hinweis=f'{type(ex).__name__}: {ex}')]
        erg[m] = liste
    mk, hoch = _ausloeser_anwenden(pdir, erg) if set(module) == set(MODULE) else ({}, 0)
    os.makedirs(os.path.join(pdir, 'pruef'), exist_ok=True)
    json.dump(erg, open(os.path.join(pdir, 'pruef', 'katalog.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    zaehl = {s: sum(1 for l in erg.values() for e in l if e['stufe'] == s) for s in STUFEN}
    return {'module': erg, 'zaehlung': zaehl, 'ok': zaehl['fehler'] == 0, 'hochgestuft': hoch,
            'merkmale': {k: v['quelle'] for k, v in mk.items() if v.get('aktiv')}}
