"""Messkette und Messtechnik: Unsicherheitsbudget, Aufloesung, Bewertung von Referenzmessreihen (MK1-MK3, seit 19.11.2026).

Anlass: mb2 bewies die Konstruktion eines Geraets, nicht seine Messfunktion. Ein bestandener ERC/DRC oder eine
konvergierte FEM sagt nichts darueber, ob ein Sensor seine Messgroesse richtig erfasst.

Grundsaetze
- **Generisch.** Dieses Modul kennt keine Sensortypen. Es rechnet mit Spannungen, Empfindlichkeiten und Messpunkten.
  Sensorabhaengige Pruefprofile (Temperatur, Druck, Beschleunigung, Feuchte ...) kommen spaeter als Daten dazu.
- **Deterministisch.** Kein Zufall, keine KI. Gleiche Eingabe, gleiches Ergebnis.
- **Budget als Einzelbeitraege.** Jeder Beitrag bleibt mit Wert, Verteilung, Sensitivitaet, Herkunft und Anteil sichtbar.
- **Vereinfachtes GUM-Modell (JCGM 100:2008).** Lineare Fortpflanzung erster Ordnung:
  u_c^2 = sum (c_i u_i)^2 + 2 sum r_ij c_i u_i c_j u_j. Sensitivitaeten c_i werden vorgegeben, nicht aus einem
  Modell abgeleitet. Nichtlineare Modelle, Monte-Carlo (JCGM 101) und Korrelationen ohne Angabe sind NICHT abgedeckt.
  Das steht in jedem Ergebnis unter ``modell``.

Teil 1 – Unsicherheitsbudget (``budget``, ``messkette_berechnen``)
    Beitrag: {"name", "wert", "verteilung": "u|normal|rechteck|dreieck|u_form", "k" (nur normal), "c" (Sensitivitaet,
              Ausgabeeinheit je Eingabeeinheit), "einheit", "herkunft", "freiheitsgrade" (optional)}
    - u:        wert ist bereits die Standardunsicherheit (k = 1)
    - normal:   wert ist eine erweiterte Unsicherheit U mit Faktor k (z. B. Kalibrierschein) -> u = U / k
    - rechteck: wert ist die Halbbreite a (Toleranz, Quantisierung, Temperaturkoeffizient x dT) -> u = a / sqrt(3)
    - dreieck:  u = a / sqrt(6);   u_form (Arcus-Sinus, z. B. Sinusstoerung): u = a / sqrt(2)
    Freiheitsgrade: fehlt die Angabe, gilt sie als unendlich (Typ B). Mit Angabe Welch-Satterthwaite; k dann aus der
    t-Verteilung fuer 95,45 % (GUM Tabelle G.2), sonst das vorgegebene k.

Teil 2 – Aufloesung (``aufloesung``)
    q = V_ref / 2^bits; Quantisierungsrauschen q / sqrt(12) (Gleichverteilung). Rauschbegrenzte Aufloesung aus
    sigma_ges = sqrt(sigma_rausch^2 / n_mittel + q^2 / 12): effektive Bits log2(V_ref / sigma_ges),
    rauschfreie Bits log2(V_ref / (6,6 sigma_ges)). Die kleinste sicher unterscheidbare Aenderung ist
    max(q, 6,6 sigma_ges) (Spitze-Spitze, 99,9 %). Die nominale Bitzahl ist NICHT die Aufloesung.

Teil 3 – Bewertung von Referenzmessreihen (``bewerte_reihe``) fuer die V-Matrix (Nachweisart ``messung``)
    Datei ``messung.json`` im Projekt: {"reihen": [Reihe]}
    Reihe: {"id": "R-LIN-1", "eigenschaft": "genauigkeit|linearitaet|hysterese|drift|wiederholbarkeit|messbereich",
            "verfahren": "Mehrpunktvergleich im Bad ...", "datum": "2026-11-19", "pruefer": "...", "geraet": "SN 0001",
            "referenz": {"mittel": "Pt100 Klasse AA + Messbruecke", "U": 0.03, "k": 2, "einheit": "°C",
                         "rueckfuehrung": "DAkkS-Kalibrierschein D-K-12345 Nr. 678", "gueltig_bis": "2027-06-30"},
            "bedingungen": {"T_umgebung_C": 23, "U_V": 3.3, "einschwingzeit_s": 300},
            "punkte": [{"ref": 0.0, "ist": 0.12, "richtung": "auf|ab", "t_h": 0}]}
    Je Eigenschaft gilt ein Mindestverfahren (VERFAHREN). Ist es nicht erfuellt, ist die Anforderung 'unbewiesen' mit
    Grund 'verfahren_unzureichend' – auch wenn die Zahl gut aussieht. Eine Zweipunktkalibrierung beweist keine
    Linearitaet, eine Kalibrierung keine Drift.
    Konformitaet mit Schutzband (ILAC-G8): Kennwert + U_pruef <= Grenze -> bewiesen; Kennwert <= Grenze < Kennwert +
    U_pruef -> vorbehalt (Graubereich); Kennwert > Grenze -> verletzt. U_pruef = k * u_ref (Unsicherheit des
    Referenzmittels, k = 2).

Teil 4 – Katalog-Pruefungen (``pruefe``) aus soll.json ``_projekt.messkette`` (Felder siehe FELDER.md):
    MK1 Unsicherheitsbudget der Messkette: U <= ziel_U
    MK2 Rauschbegrenzte Aufloesung: kleinste unterscheidbare Aenderung <= ziel_aufloesung
    MK3 Aussteuerung: Signal am ADC-Eingang bleibt ueber den Messbereich innerhalb 0 ... V_ref (mit 2 % Rand)
"""
import datetime
import math
import re

from . import ergebnis, projekt_soll, uebersprungen

Q = 'mb2/pruefungen/messkette.py (JCGM 100:2008 GUM, vereinfacht; ILAC-G8 Schutzband)'
MODELL = ('vereinfachtes GUM-Modell: lineare Fortpflanzung erster Ordnung, Sensitivitaeten vorgegeben, '
          'Korrelationen nur wenn angegeben, kein Monte-Carlo (JCGM 101)')
TEILER = {'u': 1.0, 'rechteck': math.sqrt(3), 'dreieck': math.sqrt(6), 'u_form': math.sqrt(2)}
# GUM Tabelle G.2: t_p(nu) fuer p = 95,45 %
T_9545 = ((1, 13.97), (2, 4.53), (3, 3.31), (4, 2.87), (5, 2.65), (6, 2.52), (7, 2.43), (8, 2.37), (9, 2.32),
          (10, 2.28), (11, 2.25), (12, 2.23), (13, 2.21), (14, 2.20), (15, 2.18), (16, 2.17), (17, 2.16), (18, 2.15),
          (19, 2.14), (20, 2.13), (25, 2.11), (30, 2.09), (35, 2.07), (40, 2.06), (45, 2.06), (50, 2.05),
          (100, 2.025))
SPITZE_SPITZE = 6.6     # sigma -> Spitze-Spitze (99,9 % bei Normalverteilung)
EIGENSCHAFTEN = ('messbereich', 'genauigkeit', 'linearitaet', 'hysterese', 'drift', 'wiederholbarkeit')
# Mindestverfahren je Eigenschaft (Texte fuer Maengel; die Pruefung steht in bewerte_reihe)
VERFAHREN = {
    'messbereich': 'Messpunkte an beiden Bereichsgrenzen (je innerhalb 2 % der Spanne)',
    'genauigkeit': 'Vergleich mit rueckfuehrbarer Referenz an >= 3 Punkten ueber den Messbereich',
    'linearitaet': 'Mehrpunktmessung: >= 5 verschiedene Referenzwerte ueber >= 80 % der Spanne',
    'hysterese': 'Auf- und Abwaertsmessung an >= 3 gemeinsamen Referenzwerten',
    'drift': 'zeitlich wiederholte Messung: >= 3 Zeitpunkte ueber >= dauer_h (Standard 168 h)',
    'wiederholbarkeit': '>= wiederholungen (Standard 10) Messungen am selben Referenzwert unter gleichen Bedingungen',
}
ZEIT_H = {'h': 1.0, 'd': 24.0, 'tag': 24.0, 'woche': 168.0, 'monat': 730.5, 'jahr': 8766.0, 'a': 8766.0}


# ---------------------------------------------------------------------------------------------- Teil 1: Budget

def _k_aus_nu(nu):
    """t-Faktor 95,45 % nach GUM Tabelle G.2; nu wird ABGERUNDET (GUM G.4.1), also konservativ."""
    if nu is None or nu == math.inf:
        return None
    t = T_9545[0][1]
    for n, tn in T_9545:
        if n <= nu:
            t = tn
    return t


def standardunsicherheit(b):
    """u_i eines Beitrags in seiner Eingabeeinheit (None, wenn der Wert fehlt)."""
    w = b.get('wert')
    if w is None:
        return None
    v = b.get('verteilung', 'u')
    if v == 'normal':
        return abs(w) / float(b.get('k', 2.0))
    if v not in TEILER:
        raise ValueError(f'Verteilung {v!r} unbekannt (u, normal, rechteck, dreieck, u_form)')
    return abs(w) / TEILER[v]


def budget(beitraege, k=2.0, einheit='', korrelationen=None):
    """Unsicherheitsbudget. Gibt Einzelbeitraege, u_c, k, U zurueck. Fehlt ein Wert, ist u_c None ('fehlt' nennt ihn).
    korrelationen: [{"a": name, "b": name, "r": -1..1}]."""
    zeilen, fehlt = [], []
    for b in beitraege:
        u = standardunsicherheit(b)
        if u is None:
            fehlt.append(b['name'])
            continue
        c = float(b.get('c', 1.0))
        zeilen.append({'name': b['name'], 'wert': b['wert'], 'verteilung': b.get('verteilung', 'u'),
                       'u_i': u, 'c': c, 'beitrag': abs(c) * u, 'einheit_eingang': b.get('einheit', ''),
                       'herkunft': b.get('herkunft'), 'freiheitsgrade': b.get('freiheitsgrade')})
    for z in zeilen:
        z['einheit_ausgang'] = einheit
    kr_ok = [kr for kr in korrelationen or [] if kr.get('a') in {z['name'] for z in zeilen}
             and kr.get('b') in {z['name'] for z in zeilen}]
    erg = {'beitraege': zeilen, 'einheit': einheit, 'modell': MODELL, 'fehlt': fehlt,
           'korrelationen': kr_ok,
           'korrelationen_hinweis': ('Korrelationen beruecksichtigt: ' + ', '.join(
               f'{kr["a"]}~{kr["b"]} r={kr["r"]}' for kr in kr_ok)) if kr_ok else
           'keine Korrelationen angegeben: alle Beitraege als unkorreliert behandelt (nicht geprueft)'}
    if fehlt:
        erg.update(u_c=None, k=k, U=None)
        return erg
    var = sum(z['beitrag'] ** 2 for z in zeilen)
    nach = {z['name']: z for z in zeilen}
    for kr in korrelationen or []:
        a, b = nach.get(kr['a']), nach.get(kr['b'])
        if a and b:
            var += 2 * float(kr['r']) * a['c'] * a['u_i'] * b['c'] * b['u_i']
    u_c = math.sqrt(max(var, 0.0))
    # Welch-Satterthwaite, nur wenn mindestens ein Beitrag endliche Freiheitsgrade hat
    nu_eff = None
    if any(z['freiheitsgrade'] for z in zeilen) and u_c > 0:
        nenner = sum(z['beitrag'] ** 4 / z['freiheitsgrade'] for z in zeilen if z['freiheitsgrade'])
        nu_eff = u_c ** 4 / nenner if nenner else math.inf
    k_t = _k_aus_nu(nu_eff)
    k_eff = max(k, k_t) if k_t else k
    for z in zeilen:
        z['anteil_proz'] = 100.0 * z['beitrag'] ** 2 / var if var > 0 else 0.0
    erg.update(u_c=u_c, k=k_eff, U=k_eff * u_c, nu_eff=nu_eff,
               dominant=max(zeilen, key=lambda z: z['beitrag'])['name'] if zeilen else None)
    if k_t and k_t > k:
        erg['hinweis'] = f'nu_eff = {nu_eff:.1f} -> k = {k_t} (t-Verteilung 95,45 %) statt {k}'
    return erg


def budget_aus_modell(modell, eingaben, k=2.0, einheit='', korrelationen=None):
    """GUM-Budget aus einer Modellgleichung y = modell(x) mit NUMERISCHEN Sensitivitaeten c_i = dy/dx_i
    (zentrale Differenz am Arbeitspunkt, Schritt = u_i). Lineare Naeherung erster Ordnung.

    eingaben: {name: {"wert": x_i (Schaetzwert), "u": {"wert", "verteilung", "k"} | None, "einheit", "herkunft"}}.
    Eingaben ohne "u" sind feste Parameter. Fehlt ein Schaetzwert oder eine Unsicherheitsangabe (wert None),
    steht der Name in 'fehlt' und u_c ist None. Zusaetzlich 'nichtlinear_max': groesster Unterschied zwischen
    Vorwaerts- und Rueckwaertsdifferenz relativ zum Beitrag (Hinweis, ob die lineare Naeherung traegt)."""
    x0 = {n: e.get('wert') for n, e in eingaben.items()}
    fehlt = [n for n, v in x0.items() if v is None]
    fehlt += [n for n, e in eingaben.items() if e.get('u') is not None and e['u'].get('wert') is None]
    if fehlt:
        return {'beitraege': [], 'einheit': einheit, 'modell': MODELL + '; Sensitivitaeten numerisch', 'u_c': None,
                'U': None, 'k': k, 'fehlt': sorted(set(fehlt)), 'y': None,
                'korrelationen_hinweis': 'nicht gerechnet'}
    y0 = modell(dict(x0))
    beitr, nl = [], 0.0
    for n, e in eingaben.items():
        if e.get('u') is None:
            continue
        ui = standardunsicherheit(e['u'])
        h = ui if ui > 0 else max(abs(x0[n]) * 1e-6, 1e-12)
        xp, xm = dict(x0), dict(x0)
        xp[n] = x0[n] + h
        xm[n] = x0[n] - h
        yp, ym = modell(xp), modell(xm)
        c = (yp - ym) / (2 * h)
        if ui > 0 and abs(c * ui) > 1e-15:
            nl = max(nl, abs((yp - y0) - (y0 - ym)) / (2 * abs(c * ui)))
        beitr.append({'name': n, 'wert': e['u']['wert'], 'verteilung': e['u'].get('verteilung', 'u'),
                      'k': e['u'].get('k', 2.0), 'c': c, 'einheit': e.get('einheit', ''),
                      'herkunft': e.get('herkunft'), 'freiheitsgrade': e.get('freiheitsgrade')})
    erg = budget(beitr, k, einheit, korrelationen)
    erg['y'] = y0
    erg['nichtlinear_max'] = nl
    erg['modell'] = MODELL + '; Sensitivitaeten numerisch aus der Modellgleichung (zentrale Differenz, Schritt u_i)'
    return erg


def messkette_berechnen(adc_bits, v_ref, adc_noise_rms_v, v_ref_uncertainty_v, gain=1.0, sensor_uncertainty=0.0,
                        k=2.0, *, empfindlichkeit_v_je_einheit=1.0, signal_v=None, tk_ref_ppm_k=0.0, delta_t_k=0.0,
                        u_gain_rel=0.0, tk_gain_ppm_k=0.0, u_offset_v=0.0, kalibrier_u=0.0, n_mittel=1,
                        einheit='', herkunft=None, zusatz=None):
    """Budget einer Messkette Sensor -> Verstaerker -> ADC, umgerechnet in die Messgroesse.

    Bezugspunkte (eindeutig): adc_noise_rms_v, v_ref_uncertainty_v (Standardunsicherheit, k=1), signal_v am
    ADC-Eingang; u_offset_v am Verstaerkereingang (eingangsbezogen); sensor_uncertainty und kalibrier_u
    (Standardunsicherheit) in der Messgroesse. Referenz- und Verstaerkungsfehler sind relativ und wirken auf das
    Signal: Standard signal_v = v_ref (Vollausschlag, ungunstigster Fall).
    Sensitivitaeten: ADC-Eingang c = 1 / (gain * S), Verstaerkereingang c = 1 / S, Messgroesse c = 1.
    zusatz: weitere Beitraege im Format von ``budget``. herkunft: {name: 'datenblatt: ...'}.
    """
    h = herkunft or {}
    s = float(empfindlichkeit_v_je_einheit)
    if s == 0 or gain == 0:
        raise ValueError('Empfindlichkeit und Verstaerkung duerfen nicht 0 sein')
    c_adc, c_ein = 1.0 / (gain * s), 1.0 / s
    sig = v_ref if signal_v is None else signal_v
    a = aufloesung(adc_bits, v_ref, adc_noise_rms_v, n_mittel)
    bt = [
        {'name': 'adc_quantisierung', 'wert': a['q_V'] / 2, 'verteilung': 'rechteck', 'c': c_adc, 'einheit': 'V',
         'herkunft': h.get('adc_quantisierung', 'berechnet: q/2 Halbbreite')},
        {'name': 'adc_rauschen', 'wert': adc_noise_rms_v / math.sqrt(max(n_mittel, 1)), 'verteilung': 'u',
         'c': c_adc, 'einheit': 'V', 'herkunft': h.get('adc_rauschen')},
        {'name': 'adc_referenz', 'wert': v_ref_uncertainty_v / v_ref * sig, 'verteilung': 'u', 'c': c_adc,
         'einheit': 'V', 'herkunft': h.get('adc_referenz')},
    ]
    if tk_ref_ppm_k and delta_t_k:
        bt.append({'name': 'referenz_tk', 'wert': tk_ref_ppm_k * 1e-6 * delta_t_k * sig, 'verteilung': 'rechteck',
                   'c': c_adc, 'einheit': 'V', 'herkunft': h.get('referenz_tk')})
    if u_gain_rel:
        bt.append({'name': 'verstaerkung', 'wert': u_gain_rel * sig, 'verteilung': 'u', 'c': c_adc, 'einheit': 'V',
                   'herkunft': h.get('verstaerkung')})
    if tk_gain_ppm_k and delta_t_k:
        bt.append({'name': 'verstaerkung_tk', 'wert': tk_gain_ppm_k * 1e-6 * delta_t_k * sig,
                   'verteilung': 'rechteck', 'c': c_adc, 'einheit': 'V', 'herkunft': h.get('verstaerkung_tk')})
    if u_offset_v:
        bt.append({'name': 'offset', 'wert': u_offset_v, 'verteilung': 'u', 'c': c_ein, 'einheit': 'V',
                   'herkunft': h.get('offset')})
    if sensor_uncertainty:
        bt.append({'name': 'sensorelement', 'wert': sensor_uncertainty, 'verteilung': 'u', 'c': 1.0,
                   'einheit': einheit, 'herkunft': h.get('sensorelement')})
    if kalibrier_u:
        bt.append({'name': 'kalibrierung', 'wert': kalibrier_u, 'verteilung': 'u', 'c': 1.0, 'einheit': einheit,
                   'herkunft': h.get('kalibrierung')})
    bt += list(zusatz or [])
    erg = budget(bt, k, einheit)
    erg['aufloesung'] = {**a, 'q_messgroesse': a['q_V'] * c_adc,
                         'kleinste_aenderung_messgroesse': a['kleinste_aenderung_V'] * c_adc}
    erg['bezug'] = {'signal_V_am_adc': sig, 'c_adc': c_adc, 'c_eingang': c_ein}
    return erg


# ---------------------------------------------------------------------------------------------- Teil 2: Aufloesung

def aufloesung(bits, v_ref, rauschen_rms_v=0.0, n_mittel=1):
    """Nominale und rauschbegrenzte Aufloesung eines ADC (Spannung am ADC-Eingang)."""
    q = v_ref / 2 ** bits
    u_q = q / math.sqrt(12)
    sigma = math.sqrt(rauschen_rms_v ** 2 / max(n_mittel, 1) + u_q ** 2)
    return {'q_V': q, 'u_quant_V': u_q, 'sigma_ges_V': sigma,
            'effektive_bits': min(bits, math.log2(v_ref / sigma)),
            'rauschfreie_bits': min(bits, math.log2(v_ref / (SPITZE_SPITZE * sigma))),
            'kleinste_aenderung_V': max(q, SPITZE_SPITZE * sigma)}


# ---------------------------------------------------------------------------------------------- Teil 3: Messreihen

def _mittel(x):
    return sum(x) / len(x)


def _std(x):
    if len(x) < 2:
        return None
    m = _mittel(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1))


def _gerade(x, y):
    """Ausgleichsgerade y = a + b x (kleinste Quadrate). (a, b) oder None."""
    n = len(x)
    mx, my = _mittel(x), _mittel(y)
    sxx = sum((v - mx) ** 2 for v in x)
    if n < 2 or sxx == 0:
        return None
    b = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / sxx
    return my - b * mx, b


def _u_referenz(ref):
    """Standardunsicherheit des Referenzmittels (k = 1) oder None."""
    if not isinstance(ref, dict):
        return None
    if ref.get('u') is not None:
        return abs(float(ref['u']))
    if ref.get('U') is not None:
        return abs(float(ref['U'])) / float(ref.get('k', 2.0))
    return None


def _bedingungen_passen(soll, ist):
    """Liste der Abweichungen. soll-Skalar: ist gleich (2 %); soll [a, b]: ist (Skalar oder Bereich) liegt darin;
    Schluessel auf _min/_max: ist >= bzw. <= soll (z. B. einschwingzeit_min_s)."""
    ab = []
    for key, s in (soll or {}).items():
        if key not in (ist or {}):
            ab.append(f'{key} fehlt in der Messreihe')
            continue
        i = ist[key]
        if re.search(r'_min(_[a-z0-9]+)?$', key) and isinstance(s, (int, float)) and isinstance(i, (int, float)):
            if i < s:
                ab.append(f'{key} = {i} kleiner als verlangt {s}')
            continue
        if re.search(r'_max(_[a-z0-9]+)?$', key) and isinstance(s, (int, float)) and isinstance(i, (int, float)):
            if i > s:
                ab.append(f'{key} = {i} groesser als erlaubt {s}')
            continue
        if isinstance(s, (list, tuple)) and len(s) == 2:
            lo, hi = (i if isinstance(i, (list, tuple)) else (i, i))
            if lo < s[0] or hi > s[1]:
                ab.append(f'{key} = {i} ausserhalb {s}')
        elif isinstance(s, (int, float)) and isinstance(i, (int, float)):
            if abs(i - s) > 0.02 * max(abs(s), 1e-12):
                ab.append(f'{key} = {i} statt {s}')
        elif s != i:
            ab.append(f'{key} = {i!r} statt {s!r}')
    return ab


def _einheit_umrechnen(wert, einheit, mess_einheit, spanne, zeitbasis=False):
    """Kennwert (in Messgroesseneinheit bzw. je Stunde) -> Einheit der Grenze. None, wenn nicht umrechenbar."""
    e = (einheit or '').replace(' ', '')
    if zeitbasis:
        if '/' not in e:
            return None
        oben, unten = e.split('/', 1)
        f = ZEIT_H.get(unten.lower())
        if f is None:
            return None
        w = wert * f
        if oben == '%FS':
            return w / spanne * 100 if spanne else None
        return w if oben == mess_einheit else None
    if e == '%FS':
        return wert / spanne * 100 if spanne else None
    return wert if e == mess_einheit else None


DATENSTATUS = ('rueckfuehrbar_gemessen', 'gemessen_nicht_rueckfuehrbar', 'demonstrationsdaten_nicht_rueckfuehrbar',
               'simuliert')
REGEL = ('ILAC-G8:09/2019, geschuetztes Annehmen (guarded acceptance), Schutzband w = U_pruef (k = 2): '
         'konform nur wenn Kennwert <= Grenze - w')
FEHLENTSCHEIDUNG = {
    'bewiesen': 'Wahrscheinlichkeit einer falschen Annahme <= 2,3 % (einseitig, Normalverteilung, k = 2 am '
                'Akzeptanzgrenzwert); kleiner, je weiter der Kennwert unter der Akzeptanzgrenze liegt',
    'vorbehalt': 'Graubereich: Kennwert zwischen Akzeptanzgrenze und Grenze - Wahrscheinlichkeit, dass die Grenze '
                 'tatsaechlich ueberschritten ist, bis 50 %; keine Konformitaetsaussage',
    'verletzt': 'Kennwert ueber der Grenze - Wahrscheinlichkeit einer falschen Rueckweisung hoechstens 50 % (direkt '
                'an der Grenze), unter 2,3 % ab Grenze + U_pruef',
    'einfach': 'einfache Akzeptanz (Streuungs-/Steigungskennwert ohne Referenzabweichung, w = 0): '
               'Fehlentscheidung an der Grenze bis 50 %',
}
# Pflichtfelder eines rueckfuehrbaren Nachweises
PFLICHT_REIHE = ('sensor_id', 'seriennummer', 'datum', 'verfahren')
PFLICHT_REFERENZ = ('mittel', 'seriennummer', 'kalibrierschein', 'rueckfuehrung', 'gueltig_bis')


def punkt_statistik(punkte):
    """Je (Referenzwert, Richtung): n, Mittelwert, Standardabweichung, Abweichung Mittel - Referenz."""
    g = {}
    for p in punkte:
        g.setdefault((p['ref'], p.get('richtung')), []).append(p['ist'])
    out = []
    for (r, ri), v in sorted(g.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        m = _mittel(v)
        out.append({'ref': r, 'richtung': ri, 'n': len(v), 'mittel': m, 's': _std(v), 'abweichung': m - r})
    return out


def _u_pruef(reihe, u_ref, stat):
    """Erweiterte Pruefunsicherheit (k = 2): Referenz, weitere Pruefbeitraege (Kopplung, Badinhomogenitaet ...) und
    Streuung des Mittelwerts (groesstes s / sqrt(n)). Gibt (U, Budget)."""
    bt = [{'name': 'referenzthermometer', 'wert': u_ref, 'verteilung': 'u', 'herkunft': 'Kalibrierschein'}]
    bt += list(reihe.get('pruefunsicherheit') or [])
    sm = [((z['s'] / math.sqrt(z['n'])), z['n'] - 1) for z in stat if z['s'] is not None]
    if sm:
        w, nu = max(sm)
        bt.append({'name': 'streuung_mittelwert', 'wert': w, 'verteilung': 'u', 'herkunft': 'berechnet: s/sqrt(n)',
                   'freiheitsgrade': nu})
    b = budget(bt, 2.0)
    return b['U'], b


def bewerte_reihe(reihe, eigenschaft, messtechnik, heute=None):
    """Bewertung einer Messreihe gegen die messtechnische Anforderung (Protokollzeile).

    Rueckgabe u. a.: status, grund (erster sperrender Grund), gruende (alle), kennwert, grenze, U_pruef,
    akzeptanzgrenze, sicherheitsabstand, entscheidungsregel, fehlentscheidung, auswertung_status (was die Zahlen
    allein ergaeben), datenstatus, punkte (Statistik je Punkt), pruef_budget.
    Sperrende Gruende (Status 'unbewiesen', die Zahlen werden trotzdem ausgewertet und gezeigt):
      ohne_referenzmessung, datenstatus_fehlt, demonstrationsdaten_nicht_rueckfuehrbar, gemessen_nicht_rueckfuehrbar,
      simuliert, referenz_ohne_unsicherheit, referenz_nicht_rueckfuehrbar, referenz_abgelaufen,
      nachweisdaten_unvollstaendig, bedingungen_abweichend, verfahren_unzureichend, einheit_unpassend,
      grenze_fehlt, messbereich_fehlt.
    Nur datenstatus 'rueckfuehrbar_gemessen' kann 'bewiesen' werden."""
    mt = messtechnik or {}
    leer = {'status': 'unbewiesen', 'kennwert': None, 'U_pruef': None, 'grenze': None, 'einheit': None,
            'akzeptanzgrenze': None, 'sicherheitsabstand': None, 'entscheidungsregel': REGEL,
            'fehlentscheidung': None, 'auswertung_status': None, 'datenstatus': None, 'punkte': [],
            'pruef_budget': None}
    if not reihe:
        return {**leer, 'grund': 'ohne_referenzmessung', 'gruende': ['ohne_referenzmessung'],
                'text': f'{eigenschaft}: keine Referenzmessreihe in messung.json'}
    gruende, texte = [], []

    def sperre(g, t):
        gruende.append(g)
        texte.append(t)

    rid = reihe.get('id')
    ds = reihe.get('datenstatus')
    if ds is None:
        sperre('datenstatus_fehlt', f'Reihe {rid}: datenstatus fehlt ({" | ".join(DATENSTATUS)})')
    elif ds not in DATENSTATUS:
        sperre('datenstatus_fehlt', f'Reihe {rid}: datenstatus {ds!r} unbekannt')
    elif ds != 'rueckfuehrbar_gemessen':
        sperre(ds, f'Reihe {rid}: {ds} - kein Nachweis')
    if reihe.get('eigenschaft') != eigenschaft:
        sperre('verfahren_unzureichend', f'Reihe {rid} misst {reihe.get("eigenschaft")!r}, nicht {eigenschaft!r}')
    mb = mt.get('messbereich') or {}
    if mb.get('min') is None or mb.get('max') is None:
        return {**leer, 'grund': 'messbereich_fehlt', 'gruende': gruende + ['messbereich_fehlt'], 'datenstatus': ds,
                'text': 'messtechnik.messbereich {min, max, einheit} fehlt'}
    lo, hi, me = float(mb['min']), float(mb['max']), mb.get('einheit', '')
    spanne = hi - lo
    ref = reihe.get('referenz') or {}
    u_ref = _u_referenz(ref)
    if u_ref is None:
        sperre('referenz_ohne_unsicherheit', f'Reihe {rid}: Referenz ohne Unsicherheit (u oder U, k)')
        u_ref = 0.0
    if not ref.get('rueckfuehrung'):
        sperre('referenz_nicht_rueckfuehrbar', f'Reihe {rid}: Rueckfuehrung der Referenz fehlt')
    if ref.get('einheit') and ref['einheit'] != me:
        sperre('einheit_unpassend', f'Referenz in {ref["einheit"]}, Messbereich in {me}')
    gb = ref.get('gueltig_bis')
    pruefdatum = str(reihe.get('datum') or (heute or datetime.date.today().isoformat()))[:10]
    if gb and pruefdatum > str(gb):
        sperre('referenz_abgelaufen', f'Referenz gueltig bis {gb}, Messung am {pruefdatum}')
    if ds == 'rueckfuehrbar_gemessen':
        f1 = [f for f in PFLICHT_REIHE if not reihe.get(f)]
        f2 = [f'referenz.{f}' for f in PFLICHT_REFERENZ if not ref.get(f)]
        if f1 or f2:
            sperre('nachweisdaten_unvollstaendig', f'Reihe {rid}: fehlt {", ".join(f1 + f2)}')
    ab = _bedingungen_passen(mt.get('bedingungen'), reihe.get('bedingungen'))
    if ab:
        sperre('bedingungen_abweichend', 'Pruefbedingungen weichen ab: ' + '; '.join(ab))
    pk = [p for p in reihe.get('punkte', []) if isinstance(p.get('ref'), (int, float))
          and isinstance(p.get('ist'), (int, float))]
    stat = punkt_statistik(pk)
    U_pruef, pb = _u_pruef(reihe, u_ref, stat)
    ziel = mt.get(eigenschaft) or {}
    grenze = ziel.get('max_abs')
    einheit = ziel.get('einheit', me)
    basis = {**leer, 'datenstatus': ds, 'punkte': stat, 'pruef_budget': pb, 'einheit': einheit, 'grenze': grenze}

    def fertig(kennwert=None, u=None, ausw=None, zusatz=''):
        g0 = gruende[0] if gruende else None
        st = 'unbewiesen' if gruende else ausw
        if ausw == 'verletzt' and ds in ('rueckfuehrbar_gemessen', 'gemessen_nicht_rueckfuehrbar'):
            st = 'verletzt'      # eine echte Messung ueber der Grenze ist ein Befund, auch ohne Rueckfuehrung
        w = u
        txt = (f'{eigenschaft}: Kennwert {kennwert:.4g} {einheit}, zulaessig {grenze} {einheit}, U_pruef '
               f'{(u or 0):.3g}, Akzeptanzgrenze {(grenze - (u or 0)):.4g}' if isinstance(kennwert, (int, float))
               and grenze is not None else f'{eigenschaft}: nicht ausgewertet')
        txt += zusatz
        if gruende:
            txt += ' | ' + '; '.join(texte)
        return {**basis, 'status': st, 'grund': g0 if st != 'bewiesen' else None, 'gruende': gruende,
                'kennwert': kennwert, 'U_pruef': u, 'sicherheitsabstand': w,
                'akzeptanzgrenze': (grenze - (u or 0)) if grenze is not None and u is not None else grenze,
                'auswertung_status': ausw, 'text': txt,
                'entscheidungsregel': REGEL if u is not None else FEHLENTSCHEIDUNG['einfach'],
                'fehlentscheidung': FEHLENTSCHEIDUNG.get(ausw) if u is not None else FEHLENTSCHEIDUNG['einfach']}

    def zu_wenig(t):
        sperre('verfahren_unzureichend', f'{eigenschaft}: {t} (verlangt: {VERFAHREN.get(eigenschaft, "?")})')
        return fertig()

    if eigenschaft == 'messbereich':
        rs = [p['ref'] for p in pk]
        if not rs:
            return zu_wenig('keine Messpunkte')
        rand = 0.02 * spanne
        if min(rs) > lo + rand or max(rs) < hi - rand:
            return zu_wenig(f'Referenz {min(rs)} ... {max(rs)} {me} deckt {lo} ... {hi} nicht ab')
        g = mt.get('genauigkeit') or {}
        rnd = [z for z in stat if z['ref'] <= lo + rand or z['ref'] >= hi - rand]
        e_max = max(abs(z['abweichung']) for z in rnd)
        basis.update(grenze=g.get('max_abs'), einheit=g.get('einheit', me))
        grenze = g.get('max_abs')
        einheit = g.get('einheit', me)
        if grenze is None:
            return {**fertig(), 'auswertung_status': 'bewiesen' if not gruende else None,
                    'status': 'bewiesen' if not gruende else 'unbewiesen',
                    'text': f'Messbereich {min(rs)} ... {max(rs)} {me} angefahren (keine Genauigkeitsgrenze)'}
        e_g = _einheit_umrechnen(e_max, einheit, me, spanne)
        return _entscheide(fertig, e_g, _einheit_umrechnen(U_pruef, einheit, me, spanne), grenze,
                           f' (Abweichung an den Bereichsgrenzen {min(rs)} / {max(rs)} {me})')

    if grenze is None:
        sperre('grenze_fehlt', f'messtechnik.{eigenschaft}.max_abs fehlt')
        return fertig()

    zeitbasis, u_k = False, U_pruef
    if eigenschaft == 'genauigkeit':
        if len({z['ref'] for z in stat}) < 3:
            return zu_wenig(f'{len({z["ref"] for z in stat})} Referenzwerte')
        kennwert = max(abs(z['abweichung']) for z in stat)
    elif eigenschaft == 'linearitaet':
        rs = sorted({z['ref'] for z in stat})
        if len(rs) < 5 or (rs[-1] - rs[0]) < 0.8 * spanne:
            return zu_wenig(f'{len(rs)} Referenzwerte ueber {rs[-1] - rs[0] if rs else 0:.4g} von {spanne:.4g}')
        a, b = _gerade([z['ref'] for z in stat], [z['mittel'] for z in stat])
        kennwert = max(abs(z['mittel'] - (a + b * z['ref'])) for z in stat)
    elif eigenschaft == 'hysterese':
        auf = {z['ref']: z['mittel'] for z in stat if z['richtung'] == 'auf'}
        abw = {z['ref']: z['mittel'] for z in stat if z['richtung'] == 'ab'}
        gemeinsam = sorted(set(auf) & set(abw))
        if len(gemeinsam) < 3:
            return zu_wenig(f'{len(gemeinsam)} gemeinsame Referenzwerte auf/ab')
        kennwert = max(abs(auf[r] - abw[r]) for r in gemeinsam)
        sm = [z['s'] / math.sqrt(z['n']) for z in stat if z['s'] is not None]
        if not sm:   # ohne Wiederholungen keine Unsicherheit der Differenz -> kein Schutzband moeglich
            return zu_wenig('keine Wiederholungen je Punkt (Streuung unbekannt, kein Schutzband moeglich)')
        u_k = 2 * math.sqrt(2) * max(sm)     # Differenz zweier Mittelwerte; Referenzoffset faellt heraus
    elif eigenschaft == 'drift':
        pt = [p for p in pk if isinstance(p.get('t_h'), (int, float))]
        dauer = float(mt.get('dauer_h', 168))
        ts = [p['t_h'] for p in pt]
        if len({*ts}) < 3 or max(ts) - min(ts) < dauer:
            return zu_wenig(f'{len({*ts})} Zeitpunkte ueber {(max(ts) - min(ts)) if ts else 0:.4g} h '
                            f'(verlangt {dauer:g} h)')
        _, b = _gerade(ts, [p['ist'] - p['ref'] for p in pt])
        kennwert, zeitbasis, u_k = abs(b), True, None
    elif eigenschaft == 'wiederholbarkeit':
        n_min = int(mt.get('wiederholungen', 10))
        gross = [z for z in stat if z['n'] >= n_min]
        if not gross:
            return zu_wenig(f'hoechstens {max((z["n"] for z in stat), default=0)} Wiederholungen je Punkt '
                            f'(verlangt {n_min})')
        kennwert, u_k = max(z['s'] for z in gross), None
    else:
        sperre('verfahren_unzureichend', f'Eigenschaft {eigenschaft!r} unbekannt ({", ".join(EIGENSCHAFTEN)})')
        return fertig()

    k_g = _einheit_umrechnen(kennwert, einheit, me, spanne, zeitbasis)
    if k_g is None:
        sperre('einheit_unpassend', f'{eigenschaft}: Einheit {einheit!r} nicht aus {me!r} umrechenbar '
                                    f'(erlaubt: {me}, %FS{", <einheit>/h|d|Jahr" if zeitbasis else ""})')
        return fertig()
    u_g = _einheit_umrechnen(u_k, einheit, me, spanne) if u_k is not None else None
    return _entscheide(fertig, k_g, u_g, grenze, ' - nur Pruefzeitraum, Extrapolation' if zeitbasis else '')


def _entscheide(fertig, kennwert, u, grenze, zusatz=''):
    if kennwert > grenze:
        ausw = 'verletzt'
    elif u is not None and kennwert + u > grenze:
        ausw = 'vorbehalt'
    else:
        ausw = 'bewiesen'
    return fertig(kennwert, u, ausw, zusatz)

def korrektur_fit(x, y, grad=2):
    """Ausgleichspolynom y = k0 + k1 x + ... (kleinste Quadrate). Rueckgabe Koeffizienten, Restfehler je Punkt,
    Standardabweichung der Reste s (Freiheitsgrade n - grad - 1) als u_fit. Generisch, ohne Sensorwissen."""
    import numpy as np
    x, y = np.asarray(x, float), np.asarray(y, float)
    n, m = len(x), grad + 1
    if n <= m:
        raise ValueError(f'{n} Punkte fuer Grad {grad} zu wenig (mindestens {m + 1})')
    A = np.vander(x, m, increasing=True)
    k, *_ = np.linalg.lstsq(A, y, rcond=None)
    rest = y - A @ k
    nu = n - m
    s = float(np.sqrt((rest ** 2).sum() / nu))
    return {'koeffizienten': [float(v) for v in k], 'reste': [float(v) for v in rest], 's': s, 'freiheitsgrade': nu,
            'n': n, 'max_rest': float(abs(rest).max())}


# ---------------------------------------------------------------------------------------------- Teil 4: Katalog

PFLICHT = ('adc_bits', 'v_ref_V', 'adc_rauschen_V', 'u_ref_V', 'empfindlichkeit_V_je_einheit')


def aus_soll(mk):
    """messkette_berechnen aus soll.json _projekt.messkette."""
    return messkette_berechnen(
        int(mk['adc_bits']), float(mk['v_ref_V']), float(mk['adc_rauschen_V']), float(mk['u_ref_V']),
        float(mk.get('verstaerkung', 1.0)), float(mk.get('sensor_u', 0.0)), float(mk.get('k', 2.0)),
        empfindlichkeit_v_je_einheit=float(mk['empfindlichkeit_V_je_einheit']), signal_v=mk.get('signal_V'),
        tk_ref_ppm_k=float(mk.get('tk_ref_ppm_K', 0.0)), delta_t_k=float(mk.get('delta_T_K', 0.0)),
        u_gain_rel=float(mk.get('u_verstaerkung_rel', 0.0)), tk_gain_ppm_k=float(mk.get('tk_verstaerkung_ppm_K', 0.0)),
        u_offset_v=float(mk.get('u_offset_V', 0.0)), kalibrier_u=float(mk.get('kalibrier_u', 0.0)),
        n_mittel=int(mk.get('mittelung', 1)), einheit=mk.get('einheit', ''), zusatz=mk.get('beitraege'))


def _schwache_herkunft(pj):
    """Felder unter messkette.*, deren Herkunft geschaetzt/angenommen/offen ist."""
    from ..anforderungen import HERKUNFT_STARK, herkunft_von
    soll = {'_projekt': pj}
    mk = pj.get('messkette') or {}
    felder = [f for f in PFLICHT + ('sensor_u', 'kalibrier_u', 'u_offset_V', 'u_verstaerkung_rel') if f in mk]
    return [f for f in felder if herkunft_von(soll, f'messkette.{f}')[0] not in HERKUNFT_STARK]


def _profil(mk):
    import importlib
    from ..sensorprofile import PROFILE
    if mk.get('profil') not in PROFILE:
        raise ValueError(f'messkette.profil {mk.get("profil")!r} unbekannt ({", ".join(PROFILE)})')
    return importlib.import_module(PROFILE[mk['profil']])


def herkunft_klasse(pj):
    """f('bauteile.adc.rauschen_Vrms') -> Herkunftsklasse des Felds messkette.<f> (None = nicht angegeben)."""
    from ..anforderungen import herkunft_von
    return lambda f: herkunft_von({'_projekt': pj}, f'messkette.{f}')[0]


def rechne(pj):
    """Fuer den Befehl messkette_rechnen: generisch (aus_soll) oder Profil-Budget je Temperatur."""
    mk = pj.get('messkette')
    if not mk:
        return {'fehler': 'soll.json _projekt.messkette fehlt (Felder: mb2/pruefungen/FELDER.md)'}
    if mk.get('profil'):
        pr = _profil(mk)
        hk = herkunft_klasse(pj)
        return {'profil': mk['profil'], 'pruefungen': pr.pruefe(mk, hk),
                'je_temperatur': [{'t_C': t, **pr.budget_bei(mk, t, lambda f: hk(f) or 'offen')}
                                  for t in pr._punkte(mk)]}
    return aus_soll(mk)


def pruefe(pdir):
    pj = projekt_soll(pdir)
    mk = pj.get('messkette')
    if mk and mk.get('profil'):
        return _profil(mk).pruefe(mk, herkunft_klasse(pj))
    if not mk:
        g = 'soll.json _projekt.messkette fehlt (ADC, Referenz, Rauschen, Empfindlichkeit)'
        return [uebersprungen('MK1', 'Unsicherheitsbudget Messkette', g, Q),
                uebersprungen('MK2', 'Rauschbegrenzte Aufloesung', g, Q)]
    fehlt = [f for f in PFLICHT if mk.get(f) is None]
    if fehlt:
        g = f'messkette: {", ".join(fehlt)} fehlt'
        return [uebersprungen('MK1', 'Unsicherheitsbudget Messkette', g, Q),
                uebersprungen('MK2', 'Rauschbegrenzte Aufloesung', g, Q)]
    b = aus_soll(mk)
    e = mk.get('einheit', '')
    schwach = _schwache_herkunft(pj)
    annahme = f'; Herkunft schwach/offen: {", ".join(schwach)} (angenommen)' if schwach else ''
    out = []
    # MK1
    tab = ', '.join(f'{z["name"]} {z["beitrag"]:.3g} ({z["anteil_proz"]:.0f} %)' for z in
                    sorted(b['beitraege'], key=lambda z: -z['beitrag']))
    daten = {'beitraege': b['beitraege'], 'u_c': b['u_c'], 'k': b['k'], 'U': b['U'], 'modell': b['modell'],
             'aufloesung': b['aufloesung']}
    ziel = mk.get('ziel_U')
    if ziel is None:
        out.append(uebersprungen('MK1', 'Unsicherheitsbudget Messkette',
                                 f'messkette.ziel_U fehlt (U = {b["U"]:.4g} {e} gerechnet)', Q))
    else:
        st = 'fehler' if b['U'] > ziel else ('warnung' if schwach else 'ok')
        out.append(ergebnis('MK1', 'Unsicherheitsbudget Messkette', st, wert=b['U'], grenze=ziel, einheit=e,
                            quelle=Q, daten=daten,
                            hinweis=f'U = k*u_c = {b["k"]:g}*{b["u_c"]:.4g} {e}; dominant {b["dominant"]}; {tab}'
                                    f'{annahme}{"; " + b["hinweis"] if b.get("hinweis") else ""}. {MODELL}'))
    # MK2
    a = b['aufloesung']
    za = mk.get('ziel_aufloesung')
    txt = (f'q = {a["q_V"] * 1e6:.4g} uV nominal, sigma_ges = {a["sigma_ges_V"] * 1e6:.4g} uV, effektiv '
           f'{a["effektive_bits"]:.1f} Bit, rauschfrei {a["rauschfreie_bits"]:.1f} Bit von {mk["adc_bits"]}; '
           f'kleinste unterscheidbare Aenderung {a["kleinste_aenderung_messgroesse"]:.4g} {e}')
    if za is None:
        out.append(uebersprungen('MK2', 'Rauschbegrenzte Aufloesung', f'messkette.ziel_aufloesung fehlt ({txt})', Q))
    else:
        w = a['kleinste_aenderung_messgroesse']
        st = 'fehler' if w > za else ('warnung' if schwach else 'ok')
        out.append(ergebnis('MK2', 'Rauschbegrenzte Aufloesung', st, wert=w, grenze=za, einheit=e, quelle=Q,
                            hinweis=txt + annahme, daten={'aufloesung': a}))
    # MK3 nur mit Messbereich
    mb = mk.get('messbereich')
    if mb and mb.get('min') is not None and mb.get('max') is not None:
        g, s = float(mk.get('verstaerkung', 1.0)), float(mk['empfindlichkeit_V_je_einheit'])
        v0 = float(mk.get('offset_V_am_adc', 0.0))
        vs = sorted(v0 + g * s * float(x) for x in (mb['min'], mb['max']))
        rand = 0.02 * float(mk['v_ref_V'])
        ok = vs[0] >= rand and vs[1] <= float(mk['v_ref_V']) - rand
        out.append(ergebnis('MK3', 'Aussteuerung ADC', 'ok' if ok else 'fehler', wert=[round(v, 6) for v in vs],
                            grenze=[rand, float(mk['v_ref_V']) - rand], einheit='V', quelle=Q,
                            hinweis=f'Signal am ADC {vs[0]:.4g} ... {vs[1]:.4g} V bei Messbereich {mb["min"]} ... '
                                    f'{mb["max"]} {e} (Rand 2 % gegen Saettigung)'))
    return out
