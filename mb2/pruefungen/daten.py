"""Datenbudget: Speicher, Uebertragung, Flash-Verschleiss (DS1-DS3, seit 19.11.2026). Fuer jedes Geraet, das Daten
aufzeichnet oder sendet (Logger, Sensor, Zaehler).

Warum: "Daten speichern und uebertragen" klingt nach Nebensache. Ein voller Speicher nach drei Tagen, ein Funkkanal,
der die Daten nicht schafft, oder ein Flash, der nach einem Jahr verschlissen ist, sind Konstruktionsfehler.

soll.json ``_projekt.daten`` (alle Zahlen mit _herkunft, z. B. Datenblatt des Speichers / Funkrechner):
    {"datensatz_bytes": 16, "intervall_s": 1,
     "speicher_bytes": 4194304, "reserve_anteil": 0.2, "aufbewahrung_h": 720,          # DS1
     "uebertragung": {"pakete_je_h": 60, "nutzdaten_bytes_je_paket": 51,                # DS2
                      "luftzeit_s_je_paket": 0.37, "duty_max": 0.01},                   #   Funk mit Duty-Cycle
                      # oder: "ueberhang_bytes_je_paket": 13, "rate_bit_s": 9600, "nutzanteil": 0.5 (Leitung)
     "schreibzyklen_max": 100000, "schreibblock_bytes": 4096, "puffer_datensaetze": 64} # DS3, Lebensdauer aus
                                                                                         # _projekt.lebensdauer_h
DS1 Speicher: datensatz x 3600/intervall x aufbewahrung_h <= speicher x (1 - reserve). Meldet die Zeit bis voll.
DS2 Uebertragung: anfallende Nutzdaten je Stunde <= pakete_je_h x nutzdaten (sonst staut es sich); Kanal:
    pakete_je_h x luftzeit <= duty_max x 3600 bzw. pakete_je_h x (nutz + ueberhang) x 8 / rate <= nutzanteil x 3600.
DS3 Flash-Verschleiss: je Schreibvorgang wird mindestens ein Block geschrieben (puffer_datensaetze Saetze werden im RAM
    gesammelt). Vollzyklen = geschriebene Bytes ueber die Lebensdauer / speicher_bytes (ideales Wear-Leveling,
    guenstigster Fall) <= 0,5 x schreibzyklen_max -> ok; <= 1 -> warnung; sonst fehler.
"""
from . import ergebnis, projekt_soll, uebersprungen

Q = 'mb2/pruefungen/daten.py (Datenbudget)'
T = {'DS1': 'Datenspeicher', 'DS2': 'Datenuebertragung', 'DS3': 'Flash-Verschleiss'}


def _n(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0


def _fehlt(d, felder):
    return [f for f in felder if not _n(d.get(f))]


def pruefe(pdir):
    pj = projekt_soll(pdir)
    d = pj.get('daten')
    if not d:
        return [uebersprungen(i, T[i], 'soll-Feld _projekt.daten fehlt', Q) for i in ('DS1', 'DS2', 'DS3')]
    out = []
    basis = _fehlt(d, ('datensatz_bytes', 'intervall_s'))
    je_h = d['datensatz_bytes'] * 3600.0 / d['intervall_s'] if not basis else None
    # DS1
    f = basis + _fehlt(d, ('speicher_bytes', 'aufbewahrung_h'))
    if f:
        out.append(uebersprungen('DS1', T['DS1'], f'fehlt: {", ".join(f)}', Q))
    else:
        r = float(d.get('reserve_anteil', 0.2))
        nutzbar = d['speicher_bytes'] * (1 - r)
        bedarf = je_h * d['aufbewahrung_h']
        bis_voll_h = nutzbar / je_h
        out.append(ergebnis('DS1', T['DS1'], 'ok' if bedarf <= nutzbar else 'fehler', wert=round(bedarf),
                            grenze=round(nutzbar), einheit='Byte', quelle=Q,
                            hinweis=f'{d["datensatz_bytes"]} B alle {d["intervall_s"]} s = {je_h:.0f} B/h; '
                                    f'{d["aufbewahrung_h"]} h brauchen {bedarf:.0f} B, nutzbar {nutzbar:.0f} B '
                                    f'(Reserve {r:.0%}); voll nach {bis_voll_h:.0f} h'))
    # DS2
    u = d.get('uebertragung')
    if not u:
        out.append(uebersprungen('DS2', T['DS2'], 'daten.uebertragung fehlt (nur lokal gespeichert?)', Q))
    else:
        f = basis + _fehlt(u, ('pakete_je_h', 'nutzdaten_bytes_je_paket'))
        if f:
            out.append(uebersprungen('DS2', T['DS2'], f'fehlt: {", ".join(f)}', Q))
        else:
            kap = u['pakete_je_h'] * u['nutzdaten_bytes_je_paket']
            teile = [f'Nutzdaten {je_h:.0f} B/h gegen {kap:.0f} B/h ({u["pakete_je_h"]} Pakete x '
                     f'{u["nutzdaten_bytes_je_paket"]} B)']
            st = 'ok' if je_h <= kap else 'fehler'
            if _n(u.get('luftzeit_s_je_paket')) and _n(u.get('duty_max')):
                belegt, frei = u['pakete_je_h'] * u['luftzeit_s_je_paket'], u['duty_max'] * 3600
                teile.append(f'Luftzeit {belegt:.1f} s/h gegen Duty-Cycle {frei:.1f} s/h')
                st = st if belegt <= frei else 'fehler'
                wert, grenze, einheit = belegt, frei, 's/h'
            elif _n(u.get('rate_bit_s')):
                bits = u['pakete_je_h'] * (u['nutzdaten_bytes_je_paket'] + float(u.get('ueberhang_bytes_je_paket') or 0)) * 8
                belegt, frei = bits / u['rate_bit_s'], float(u.get('nutzanteil', 0.5)) * 3600
                teile.append(f'Leitung {belegt:.1f} s/h belegt gegen {frei:.0f} s/h nutzbar')
                st = st if belegt <= frei else 'fehler'
                wert, grenze, einheit = belegt, frei, 's/h'
                if u.get('ueberhang_bytes_je_paket') is None and st == 'ok':
                    st, teile = 'warnung', teile + ['Ueberhang je Paket fehlt (angenommen 0 B)']
            else:
                wert, grenze, einheit = je_h, kap, 'B/h'
                if st == 'ok':
                    st, teile = 'warnung', teile + ['Kanal nicht geprueft: luftzeit_s_je_paket + duty_max oder rate_bit_s fehlt']
            out.append(ergebnis('DS2', T['DS2'], st, wert=round(wert, 3), grenze=round(grenze, 3), einheit=einheit,
                                quelle=Q, hinweis='; '.join(teile)))
    # DS3
    lh = pj.get('lebensdauer_h')
    f = basis + _fehlt(d, ('speicher_bytes', 'schreibzyklen_max', 'schreibblock_bytes')) + ([] if _n(lh) else ['lebensdauer_h'])
    if f:
        out.append(uebersprungen('DS3', T['DS3'], f'fehlt: {", ".join(f)}', Q))
    else:
        puffer = max(1, int(d.get('puffer_datensaetze') or 1))
        je_schreiben = max(d['schreibblock_bytes'], d['datensatz_bytes'] * puffer)
        schreibvorgaenge_h = 3600.0 / d['intervall_s'] / puffer
        zyklen = schreibvorgaenge_h * je_schreiben * lh / d['speicher_bytes']
        g = d['schreibzyklen_max']
        st = 'ok' if zyklen <= 0.5 * g else 'warnung' if zyklen <= g else 'fehler'
        out.append(ergebnis('DS3', T['DS3'], st, wert=round(zyklen, 1), grenze=g, einheit='Vollzyklen', quelle=Q,
                            hinweis=f'{schreibvorgaenge_h:.1f} Schreibvorgaenge/h x {je_schreiben} B (Block {d["schreibblock_bytes"]} B, '
                                    f'Puffer {puffer} Saetze) ueber {lh} h = {zyklen:.1f} Vollzyklen gegen {g} '
                                    '(ideales Wear-Leveling, guenstigster Fall)'))
    return out
