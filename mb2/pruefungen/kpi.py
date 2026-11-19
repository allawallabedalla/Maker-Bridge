"""Projektziele (KPIs): Kosten, Aufwand, Termin, Prioritaet, Fehlerfolge (K1-K4, seit 19.11.2026).

Warum: Technik ohne Ziele laesst sich nicht abwaegen. "So genau wie moeglich" und "so billig wie moeglich" zugleich ist
kein Ziel, sondern ein Widerspruch. Die Ziele kommen beim Projektstart vom Nutzer (project_new(..., ziele=...)) und
werden wie jede andere Eingabe hinterfragt: Herkunft, Plausibilitaet, Widerspruch zu anderen Angaben.

soll.json ``_projekt.ziele`` (jedes Feld darf "unbekannt" sein - das ist eine ehrliche Antwort und wird als Risiko
gemeldet, nie still angenommen):
    {"zielkosten_eur_stueck": 40, "stueckzahl": 5, "termin": "2027-03-31", "aufwand_h_stueck": 3,
     "fehlerfolge": "gering|mittel|hoch", "prioritaet": ["qualitaet", "kosten", "zeit"],
     "pruefmittel": ["Referenzthermometer ...", "Temperaturbad ..."]}
Projektdatei ``kosten.json`` (Nachweis):
    {"posten": [{"name": "ADS1220", "menge": 1, "preis_eur": 4.1, "quelle": "Angebot ... 11/2026"}],
     "arbeitsschritte": [{"name": "Bestuecken", "h": 0.5, "quelle": "geschaetzt"}]}

K1 Stueckkosten (Summe menge x preis) <= zielkosten_eur_stueck
K2 Arbeitszeit je Stueck (Summe der Schritte) <= aufwand_h_stueck
K3 Termin liegt in der Zukunft
K4 Prioritaet ist eine eindeutige Reihenfolge von qualitaet, kosten, zeit (nicht "alles gleich wichtig")
Posten ohne Preis oder Quelle zaehlen als Luecke (warnung bzw. fehler), nie als 0 EUR.
"""
import datetime
import json
import os

from . import ergebnis, projekt_soll, uebersprungen

Q = 'mb2/pruefungen/kpi.py (Projektziele)'
PRIO = ('qualitaet', 'kosten', 'zeit')


def _unbekannt(v):
    return isinstance(v, str) and v.strip().lower() in ('unbekannt', 'weiss nicht', 'weiß nicht', '?')


def _kosten(pdir):
    p = os.path.join(pdir, 'kosten.json')
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else None


def _summe(liste, wert, menge=None):
    luecken, s = [], 0.0
    for x in liste or []:
        v = x.get(wert)
        m = x.get(menge, 1) if menge else 1
        if not isinstance(v, (int, float)) or not isinstance(m, (int, float)):
            luecken.append(f'{x.get("name", "?")}: {wert} fehlt')
            continue
        if not x.get('quelle'):
            luecken.append(f'{x.get("name", "?")}: Quelle fehlt')
        s += v * m
    return s, luecken


def pruefe(pdir, heute=None):
    z = projekt_soll(pdir).get('ziele')
    if not z:
        g = 'soll.json _projekt.ziele fehlt (project_new(..., ziele=...)): ohne Ziele keine Abwaegung'
        return [uebersprungen(i, t, g, Q) for i, t in (('K1', 'Stueckkosten'), ('K2', 'Arbeitszeit je Stueck'),
                                                       ('K3', 'Termin'), ('K4', 'Prioritaet'))]
    k = _kosten(pdir)
    out = []
    for kid, titel, ziel_f, liste, wert, menge, einheit in (
            ('K1', 'Stueckkosten', 'zielkosten_eur_stueck', 'posten', 'preis_eur', 'menge', 'EUR'),
            ('K2', 'Arbeitszeit je Stueck', 'aufwand_h_stueck', 'arbeitsschritte', 'h', None, 'h')):
        ziel = z.get(ziel_f)
        if ziel is None:
            out.append(uebersprungen(kid, titel, f'ziele.{ziel_f} nicht abgefragt', Q))
            continue
        if _unbekannt(ziel):
            out.append(ergebnis(kid, titel, 'warnung', quelle=Q,
                                hinweis=f'Ziel {ziel_f} unbekannt: keine Kontrolle moeglich - Risiko, nicht ok'))
            continue
        if not k or not k.get(liste):
            out.append(uebersprungen(kid, titel, f'kosten.json {liste} fehlt (Ziel {ziel} {einheit})', Q))
            continue
        s, luecken = _summe(k[liste], wert, menge)
        st = 'fehler' if s > ziel else ('warnung' if luecken else 'ok')
        out.append(ergebnis(kid, titel, st, wert=round(s, 2), grenze=ziel, einheit=einheit, quelle=Q,
                            hinweis=f'Summe {s:.2f} {einheit} gegen Ziel {ziel} {einheit}'
                                    + (f'; Luecken (nicht als 0 gezaehlt): {"; ".join(luecken)}' if luecken else '')))
    t = z.get('termin')
    if t is None:
        out.append(uebersprungen('K3', 'Termin', 'ziele.termin nicht abgefragt', Q))
    elif _unbekannt(t):
        out.append(ergebnis('K3', 'Termin', 'warnung', quelle=Q, hinweis='Termin unbekannt: Aufwand nicht planbar'))
    else:
        h = heute or datetime.date.today().isoformat()
        out.append(ergebnis('K3', 'Termin', 'fehler' if str(t) <= h else 'ok', wert=t, grenze=f'> {h}', quelle=Q,
                            hinweis=f'Termin {t}' + (' liegt nicht in der Zukunft' if str(t) <= h else '')))
    p = z.get('prioritaet')
    if p is None:
        out.append(uebersprungen('K4', 'Prioritaet', 'ziele.prioritaet nicht abgefragt', Q))
    else:
        ok = isinstance(p, list) and sorted(p) == sorted(PRIO)
        out.append(ergebnis('K4', 'Prioritaet', 'ok' if ok else 'fehler', wert=p, quelle=Q,
                            hinweis='eindeutige Reihenfolge' if ok else
                            f'Prioritaet muss eine Reihenfolge von {", ".join(PRIO)} sein, jedes genau einmal - '
                            f'"alles gleich wichtig" laesst keine Abwaegung zu'))
    return out
