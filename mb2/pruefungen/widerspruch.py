"""Widerspruchspruefung: Anforderungen, Ziele und Einsatzbedingungen gegeneinander (X1-X9, seit 19.11.2026).

Warum: Einzelpruefungen sehen jede Angabe fuer sich. Widersprueche entstehen zwischen Angaben (Genauigkeit gegen
Pruefmittel, Messbereich gegen Einsatz, Aufwand gegen Termin ...). Lehre aus MB2-TEMP-001: 100 °C Messbereich fuer
Aussenluft, Budget gleich Toleranz, Bus zu lang - alles erst spaet aufgefallen.

Regeln (deterministisch, nur aus vorhandenen Daten; fehlt eine Angabe: 'uebersprungen' mit Feldname):
  X1 Pruefmittel gegen Toleranz: Toleranz / U_Referenz >= 4 (Faustregel "4:1", Test Uncertainty Ratio,
     z. B. ANSI/NCSL Z540.3) -> ok; 1 ... 4 warnung; < 1 fehler (Referenz ungenauer als die Toleranz).
  X2 Messbereich gegen Einsatz: Einsatztemperatur T_min_C ... T_max_C muss im Messbereich liegen (fehler);
     Messbereich mehr als doppelt so breit wie der Einsatz -> warnung (Aufwand ohne Nutzen).
  X3 Auslegungsbudget gegen Toleranz: messkette.ziel_U > Genauigkeit -> fehler; = Genauigkeit -> warnung
     (kein Platz fuer das ILAC-G8-Schutzband beim Nachweis).
  X4 Ziele ohne Quelle: Zahlenwerte in _projekt.ziele ohne _herkunft -> warnung (Wunsch oder belegt?).
  X5 Aufwand gegen Termin: aufwand_h_stueck x stueckzahl gegen ziele.zeit_h_pro_woche x Wochen bis Termin.
  X6 Prioritaet gegen Fehlerfolge: fehlerfolge 'hoch', aber 'kosten' oder 'zeit' vor 'qualitaet' -> warnung.
  X7 Bus gegen Leitungslaenge: _projekt.schnittstelle {bus, leitung_m}: SPI > 0,3 m, I2C > 1 m -> warnung
     (Faustregel: Platinenbusse; laengere Wege brauchen RS-485, I2C-Verlaengerer oder analoges Fuehlerkabel).
  X8 Kalibrierung gegen Aufwand: Modus kalibriert, aber in kosten.json kein Arbeitsschritt mit "kalib" -> warnung.
  X9 Stueckzahl 1 gegen Seriengedanke: stueckzahl == 1 -> info "Nachweise gelten nur fuer dieses Geraet";
     verlangt eine Anforderung Reproduzierbarkeit/Exemplarstreuung -> fehler.
  X10 Erkennung gegen Messgroessen (Beobachtbarkeit): jeder Fehler in "erkennung" einer Anforderung braucht
     "braucht_eine_von" (Listen von Messgroessen, die ihn vom Normalbetrieb unterscheiden). Keine Liste ist in
     _projekt.messgroessen vollstaendig vorhanden -> fehler (z. B. Leck HINTER dem einzigen Durchflusssensor ist
     unsichtbar: braucht Durchfluss ein UND aus, oder Druck + Pumpenzustand). Ohne Begruendung -> warnung.
Jede Meldung nennt: was nicht zusammenpasst, warum es zaehlt, wie man es aufloest.
"""
import datetime
import json
import os

from . import ergebnis, projekt_soll, uebersprungen

Q = 'mb2/pruefungen/widerspruch.py (Widerspruchspruefung)'
FAUST = {'spi': 0.3, 'i2c': 1.0}


def _json(pdir, name, leer):
    p = os.path.join(pdir, name)
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else leer


def _mess_anforderungen(pdir):
    return [a for a in _json(pdir, 'anforderungen.json', {}).get('anforderungen', []) if a.get('messtechnik')]


def _toleranz(mt):
    """Genauigkeitsgrenze in Messgroesseneinheit (oder None)."""
    g, mb = mt.get('genauigkeit') or {}, mt.get('messbereich') or {}
    if g.get('max_abs') is None:
        return None
    if g.get('einheit') == '%FS' and mb.get('max') is not None and mb.get('min') is not None:
        return g['max_abs'] / 100 * (mb['max'] - mb['min'])
    return float(g['max_abs'])


def _u_referenz(pdir, pj):
    """Groesste erweiterte Unsicherheit (k = 2) der Referenzen in messung.json bzw. aus kalibrierung.u_referenz."""
    werte = []
    for r in _json(pdir, 'messung.json', {}).get('reihen', []):
        ref = r.get('referenz') or {}
        if ref.get('U') is not None:
            werte.append(2 * float(ref['U']) / float(ref.get('k', 2)))
        elif ref.get('u') is not None:
            werte.append(2 * float(ref['u']))
    ku = ((pj.get('messkette') or {}).get('kalibrierung') or {}).get('u_referenz')
    if ku is not None:
        werte.append(2 * float(ku))
    return max(werte) if werte else None


def pruefe(pdir, heute=None):
    pj = projekt_soll(pdir)
    z = pj.get('ziele') or {}
    mk = pj.get('messkette') or {}
    mess = _mess_anforderungen(pdir)
    out = []

    # X1 Pruefmittel gegen Toleranz
    tols = [t for t in (_toleranz(a['messtechnik']) for a in mess) if t is not None]
    tol = min(tols) if tols else None          # engste Toleranz zaehlt
    u_ref = _u_referenz(pdir, pj)
    if tol is None or u_ref is None or u_ref == 0:
        out.append(uebersprungen('X1', 'Pruefmittel gegen Toleranz',
                                 'Genauigkeit (messtechnik.genauigkeit) oder Referenz-Unsicherheit (messung.json '
                                 'referenz.U bzw. messkette.kalibrierung.u_referenz) fehlt', Q))
    else:
        v = tol / u_ref
        st = 'ok' if v >= 4 else ('warnung' if v >= 1 else 'fehler')
        out.append(ergebnis('X1', 'Pruefmittel gegen Toleranz', st, wert=round(v, 2), grenze=4, einheit=':1', quelle=Q,
                            hinweis=f'Toleranz {tol:g}, Referenz U = {u_ref:g} -> Verhaeltnis {v:.1f}:1. '
                                    + ('' if st == 'ok' else
                                       'Die Referenz ist zu ungenau, um die Toleranz sicher nachzuweisen (Faustregel '
                                       '4:1). Aufloesen: a) genauere Referenz, b) Toleranz lockern, c) mit Schutzband '
                                       'nach ILAC-G8 leben (engere Akzeptanzgrenze).')))

    # X2 Messbereich gegen Einsatz (nur Temperatur in °C)
    einsatz = (pj.get('T_min_C'), pj.get('T_max_C'))
    mb = next((a['messtechnik'].get('messbereich') for a in mess if (a['messtechnik'].get('messbereich') or {})
               .get('einheit') == '°C'), None)
    if not mb or None in einsatz:
        out.append(uebersprungen('X2', 'Messbereich gegen Einsatz', 'messtechnik.messbereich in °C oder '
                                                                    '_projekt.T_min_C/T_max_C fehlt', Q))
    else:
        lo, hi = float(mb['min']), float(mb['max'])
        e_lo, e_hi = float(einsatz[0]), float(einsatz[1])
        if e_lo < lo or e_hi > hi:
            out.append(ergebnis('X2', 'Messbereich gegen Einsatz', 'fehler', wert=[lo, hi], grenze=[e_lo, e_hi],
                                einheit='°C', quelle=Q,
                                hinweis=f'Einsatz {e_lo:g} ... {e_hi:g} °C liegt nicht im Messbereich {lo:g} ... '
                                        f'{hi:g} °C. Aufloesen: Messbereich erweitern oder Einsatzangabe pruefen.'))
        elif (hi - lo) > 2 * (e_hi - e_lo):
            out.append(ergebnis('X2', 'Messbereich gegen Einsatz', 'warnung', wert=[lo, hi], grenze=[e_lo, e_hi],
                                einheit='°C', quelle=Q,
                                hinweis=f'Messbereich {lo:g} ... {hi:g} °C ist mehr als doppelt so breit wie der '
                                        f'Einsatz {e_lo:g} ... {e_hi:g} °C: mehr Kalibrierpunkte und Aufwand ohne '
                                        f'Nutzen. Aufloesen: Messbereich an den Einsatz anpassen (mit Reserve).'))
        else:
            out.append(ergebnis('X2', 'Messbereich gegen Einsatz', 'ok', wert=[lo, hi], grenze=[e_lo, e_hi],
                                einheit='°C', quelle=Q, hinweis='Einsatz liegt im Messbereich, Bereich angemessen'))

    # X3 Auslegungsbudget gegen Toleranz
    zu = mk.get('ziel_U')
    if zu is None or tol is None:
        out.append(uebersprungen('X3', 'Budget gegen Toleranz', 'messkette.ziel_U oder Genauigkeit fehlt', Q))
    else:
        st = 'fehler' if zu > tol else ('warnung' if zu >= tol else 'ok')
        out.append(ergebnis('X3', 'Budget gegen Toleranz', st, wert=zu, grenze=tol, quelle=Q,
                            hinweis=f'Auslegungsziel U = {zu:g} gegen Toleranz {tol:g}. '
                                    + {'fehler': 'Das Budget erlaubt mehr Unsicherheit als die Toleranz - ein Nachweis '
                                                 'ist so unmoeglich. Aufloesen: ziel_U deutlich unter die Toleranz.',
                                       'warnung': 'Kein Platz fuer das Schutzband beim Nachweis: jeder Messwert nahe '
                                                  'der Grenze bleibt im Graubereich. Aufloesen: ziel_U etwa auf die '
                                                  'Haelfte der Toleranz.',
                                       'ok': 'Budget laesst Platz fuer das Schutzband.'}[st]))

    # X4 Ziele ohne Quelle
    if not z:
        out.append(uebersprungen('X4', 'Ziele mit Quelle', '_projekt.ziele fehlt', Q))
    else:
        h = pj.get('_herkunft') or {}
        ohne = [k for k, v in z.items() if isinstance(v, (int, float)) and not h.get(f'ziele.{k}')]
        out.append(ergebnis('X4', 'Ziele mit Quelle', 'warnung' if ohne else 'ok', quelle=Q,
                            hinweis=(f'Ohne Quelle: {", ".join(ohne)}. Nachfragen: Wunsch, Vorgabe oder belegt? '
                                     f'In _projekt._herkunft["ziele.<feld>"] eintragen.') if ohne else
                            'alle Zahlenziele haben eine Quelle'))

    # X5 Aufwand gegen Termin
    a_h, n, t, kap = z.get('aufwand_h_stueck'), z.get('stueckzahl'), z.get('termin'), z.get('zeit_h_pro_woche')
    def _datum(x):
        try:
            return datetime.date.fromisoformat(str(x))
        except ValueError:
            return None
    if not all(isinstance(x, (int, float)) for x in (a_h, n, kap)) or _datum(t) is None:
        out.append(uebersprungen('X5', 'Aufwand gegen Termin', 'ziele.aufwand_h_stueck, stueckzahl, termin und '
                                                              'zeit_h_pro_woche noetig', Q))
    else:
        h0 = datetime.date.fromisoformat(heute or datetime.date.today().isoformat())
        wochen = max((datetime.date.fromisoformat(t) - h0).days / 7, 0)
        bedarf, verfuegbar = a_h * n, kap * wochen
        out.append(ergebnis('X5', 'Aufwand gegen Termin', 'fehler' if bedarf > verfuegbar else 'ok',
                            wert=round(bedarf, 1), grenze=round(verfuegbar, 1), einheit='h', quelle=Q,
                            hinweis=f'{a_h:g} h x {n:g} Stueck = {bedarf:.0f} h gegen {kap:g} h/Woche x '
                                    f'{wochen:.1f} Wochen = {verfuegbar:.0f} h'
                                    + ('. Aufloesen: Termin schieben, Stueckzahl senken oder Aufwand je Stueck '
                                       'senken (z. B. anderes Kalibrierverfahren).' if bedarf > verfuegbar else '')))

    # X6 Prioritaet gegen Fehlerfolge
    p, f = z.get('prioritaet'), z.get('fehlerfolge')
    if not isinstance(p, list) or f is None:
        out.append(uebersprungen('X6', 'Prioritaet gegen Fehlerfolge', 'ziele.prioritaet oder fehlerfolge fehlt', Q))
    else:
        konflikt = f == 'hoch' and p and p[0] != 'qualitaet'
        out.append(ergebnis('X6', 'Prioritaet gegen Fehlerfolge', 'warnung' if konflikt else 'ok', wert=p, quelle=Q,
                            hinweis=(f'Fehlerfolge hoch, aber "{p[0]}" steht vor Qualitaet. Bei einem Konflikt wuerde '
                                     f'die Qualitaet nachgeben, obwohl Fehler teuer sind. Klaeren: bewusst so?')
                            if konflikt else 'Prioritaet passt zur Fehlerfolge'))

    # X7 Bus gegen Leitungslaenge
    s = pj.get('schnittstelle') or {}
    bus, lm = str(s.get('bus', '')).lower(), s.get('leitung_m')
    if bus not in FAUST or not isinstance(lm, (int, float)):
        out.append(uebersprungen('X7', 'Bus gegen Leitungslaenge', '_projekt.schnittstelle {bus: spi|i2c, leitung_m} '
                                                                  'fehlt', Q))
    else:
        zu_lang = lm > FAUST[bus]
        out.append(ergebnis('X7', 'Bus gegen Leitungslaenge', 'warnung' if zu_lang else 'ok', wert=lm,
                            grenze=FAUST[bus], einheit='m', quelle=Q,
                            hinweis=(f'{bus.upper()} ueber {lm:g} m: Platinenbus, Faustregel hoechstens '
                                     f'{FAUST[bus]:g} m. Aufloesen: Elektronik naeher an den Rechner und nur das '
                                     f'Fuehlerkabel verlaengern, RS-485 oder I2C-Verlaengerer.') if zu_lang else
                            f'{bus.upper()}-Leitung {lm:g} m innerhalb der Faustregel'))

    # X8 Kalibrierung gegen Aufwand
    if mk.get('modus') != 'kalibriert':
        out.append(uebersprungen('X8', 'Kalibrierung im Aufwand', 'kein Modus kalibriert', Q))
    else:
        schritte = (_json(pdir, 'kosten.json', {}) or {}).get('arbeitsschritte') or []
        hat = any('kalib' in str(x.get('name', '')).lower() for x in schritte)
        out.append(ergebnis('X8', 'Kalibrierung im Aufwand', 'ok' if hat else 'warnung', quelle=Q,
                            hinweis='Kalibrierung ist als Arbeitsschritt eingeplant' if hat else
                            'Jedes Geraet wird kalibriert, aber kosten.json enthaelt keinen Kalibrierschritt: Aufwand '
                            'und Termin sind zu optimistisch. Aufloesen: Schritt mit Stunden je Geraet eintragen.'))

    # X9 Stueckzahl 1 gegen Seriengedanke
    if z.get('stueckzahl') is None:
        out.append(uebersprungen('X9', 'Stueckzahl gegen Seriennachweis', 'ziele.stueckzahl fehlt', Q))
    elif z['stueckzahl'] == 1:
        serie = [a['id'] for a in _json(pdir, 'anforderungen.json', {}).get('anforderungen', [])
                 if any(w in (a.get('text', '') + json.dumps(a.get('messtechnik', {}))).lower()
                        for w in ('reproduzierbar', 'exemplarstreuung', 'serienstreuung'))]
        out.append(ergebnis('X9', 'Stueckzahl gegen Seriennachweis', 'fehler' if serie else 'info', quelle=Q,
                            hinweis=(f'Stueckzahl 1, aber {", ".join(serie)} verlangt Reproduzierbarkeit zwischen '
                                     f'Geraeten - mit einem Geraet nicht nachweisbar.') if serie else
                            'Stueckzahl 1: alle Nachweise gelten nur fuer dieses eine Geraet (Seriennummer).'))
    else:
        out.append(ergebnis('X9', 'Stueckzahl gegen Seriennachweis', 'ok', quelle=Q,
                            hinweis=f'Stueckzahl {z["stueckzahl"]}'))
    # X10 Beobachtbarkeit der Erkennungsfunktionen
    erk = [(a['id'], f) for a in _json(pdir, 'anforderungen.json', {}).get('anforderungen', [])
           for f in a.get('erkennung') or []]
    mg = pj.get('messgroessen')
    if not erk:
        out.append(uebersprungen('X10', 'Erkennung gegen Messgroessen', 'keine Anforderung mit erkennung', Q))
    elif not isinstance(mg, list):
        out.append(uebersprungen('X10', 'Erkennung gegen Messgroessen',
                                 '_projekt.messgroessen fehlt (Liste der Groessen, die das Geraet wirklich misst)', Q))
    else:
        for aid, f in erk:
            alt = [set(x) for x in f.get('braucht_eine_von') or [] if isinstance(x, list) and x]
            tit = f'Erkennung gegen Messgroessen: {f.get("fehler")} ({aid})'
            if not alt:
                out.append(ergebnis('X10', tit, 'warnung', quelle=Q,
                                    hinweis='braucht_eine_von fehlt: Welche Messgroessen unterscheiden diesen Fehler vom '
                                            'Normalbetrieb? Ohne Begruendung ist die Erkennung eine Behauptung.'))
                continue
            da = [sorted(x) for x in alt if x <= set(mg)]
            fehlen = [sorted(x - set(mg)) for x in alt]
            out.append(ergebnis('X10', tit, 'ok' if da else 'fehler', quelle=Q, daten={'vorhanden': mg, 'braucht': [sorted(x) for x in alt]},
                                hinweis=(f'beobachtbar ueber {da[0]}' if da else
                                         f'nicht beobachtbar: gemessen wird {mg}, es fehlt je Variante {fehlen} - '
                                         'Messgroesse ergaenzen (zweiter Sensor, Druck, Pumpenzustand) oder die '
                                         'Anforderung auf das Machbare einschraenken')))
    return out
