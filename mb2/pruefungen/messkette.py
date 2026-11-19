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
    if nu is None or nu == math.inf:
        return None
    for n, t in T_9545:
        if nu <= n:
            return t
    return 2.0


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
    erg = {'beitraege': zeilen, 'einheit': einheit, 'modell': MODELL, 'fehlt': fehlt}
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
    """Liste der Abweichungen. soll-Skalar: ist gleich (2 %); soll [a, b]: ist (Skalar oder Bereich) liegt darin."""
    ab = []
    for key, s in (soll or {}).items():
        if key not in (ist or {}):
            ab.append(f'{key} fehlt in der Messreihe')
            continue
        i = ist[key]
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


def bewerte_reihe(reihe, eigenschaft, messtechnik, heute=None):
    """Bewertung einer Messreihe gegen die messtechnische Anforderung.

    Rueckgabe {'status', 'grund', 'text', 'kennwert', 'U_pruef', 'grenze', 'einheit'}. grund ist bei 'unbewiesen'
    einer von: ohne_referenzmessung, referenz_ohne_unsicherheit, referenz_nicht_rueckfuehrbar, referenz_abgelaufen,
    verfahren_unzureichend, bedingungen_abweichend, einheit_unpassend, grenze_fehlt, messbereich_fehlt."""
    mt = messtechnik or {}

    def raus(grund, text, status='unbewiesen'):
        return {'status': status, 'grund': grund, 'text': text, 'kennwert': None, 'U_pruef': None,
                'grenze': None, 'einheit': None}

    if not reihe:
        return raus('ohne_referenzmessung', f'{eigenschaft}: keine Referenzmessreihe in messung.json')
    if reihe.get('eigenschaft') != eigenschaft:
        return raus('verfahren_unzureichend', f'Reihe {reihe.get("id")} misst {reihe.get("eigenschaft")!r}, '
                                              f'nicht {eigenschaft!r}')
    mb = mt.get('messbereich') or {}
    if mb.get('min') is None or mb.get('max') is None:
        return raus('messbereich_fehlt', 'messtechnik.messbereich {min, max, einheit} fehlt')
    lo, hi, me = float(mb['min']), float(mb['max']), mb.get('einheit', '')
    spanne = hi - lo
    ref = reihe.get('referenz') or {}
    u_ref = _u_referenz(ref)
    if u_ref is None:
        return raus('referenz_ohne_unsicherheit', f'Reihe {reihe.get("id")}: Referenz ohne Unsicherheit (u oder U, k)')
    if not ref.get('rueckfuehrung'):
        return raus('referenz_nicht_rueckfuehrbar', f'Reihe {reihe.get("id")}: Rueckfuehrung der Referenz fehlt '
                                                    '(Kalibrierschein, Normal)')
    if ref.get('einheit') and ref['einheit'] != me:
        return raus('einheit_unpassend', f'Referenz in {ref["einheit"]}, Messbereich in {me}')
    gb = ref.get('gueltig_bis')
    pruefdatum = reihe.get('datum') or (heute or datetime.date.today().isoformat())
    if gb and str(pruefdatum) > str(gb):
        return raus('referenz_abgelaufen', f'Referenz gueltig bis {gb}, Messung am {pruefdatum}')
    ab = _bedingungen_passen(mt.get('bedingungen'), reihe.get('bedingungen'))
    if ab:
        return raus('bedingungen_abweichend', 'Pruefbedingungen weichen ab: ' + '; '.join(ab))
    pk = [p for p in reihe.get('punkte', []) if isinstance(p.get('ref'), (int, float))
          and isinstance(p.get('ist'), (int, float))]
    U_pruef = 2.0 * u_ref
    ziel = mt.get(eigenschaft) or {}
    grenze = ziel.get('max_abs')
    einheit = ziel.get('einheit', me)
    zu_wenig = lambda t: raus('verfahren_unzureichend', f'{eigenschaft}: {t} (verlangt: {VERFAHREN[eigenschaft]})')  # noqa: E731

    if eigenschaft == 'messbereich':
        if not pk:
            return zu_wenig('keine Messpunkte')
        rs = [p['ref'] for p in pk]
        rand = 0.02 * spanne
        if min(rs) > lo + rand or max(rs) < hi - rand:
            return zu_wenig(f'Referenz {min(rs)} ... {max(rs)} {me} deckt {lo} ... {hi} nicht ab')
        g = (mt.get('genauigkeit') or {})
        if g.get('max_abs') is not None:
            e_max = max(abs(p['ist'] - p['ref']) for p in pk if p['ref'] <= lo + rand or p['ref'] >= hi - rand)
            e_g = _einheit_umrechnen(e_max, g.get('einheit', me), me, spanne)
            if e_g is not None and e_g > g['max_abs']:
                return {'status': 'verletzt', 'grund': None, 'kennwert': e_g, 'U_pruef': None, 'grenze': g['max_abs'],
                        'einheit': g.get('einheit', me),
                        'text': f'Messbereich: Abweichung an der Grenze {e_g:.4g} > {g["max_abs"]} (Saettigung?)'}
        return {'status': 'bewiesen', 'grund': None, 'kennwert': [min(rs), max(rs)], 'U_pruef': None,
                'grenze': [lo, hi], 'einheit': me, 'text': f'Messbereich {min(rs)} ... {max(rs)} {me} gemessen'}

    if grenze is None:
        return raus('grenze_fehlt', f'messtechnik.{eigenschaft}.max_abs fehlt')

    zeitbasis = False
    if eigenschaft == 'genauigkeit':
        if len({p['ref'] for p in pk}) < 3:
            return zu_wenig(f'{len({p["ref"] for p in pk})} Referenzwerte')
        kennwert = max(abs(p['ist'] - p['ref']) for p in pk)
    elif eigenschaft == 'linearitaet':
        rs = sorted({p['ref'] for p in pk})
        if len(rs) < 5 or (rs[-1] - rs[0]) < 0.8 * spanne:
            return zu_wenig(f'{len(rs)} Referenzwerte ueber {rs[-1] - rs[0] if rs else 0:.4g} von {spanne:.4g}')
        a, b = _gerade([p['ref'] for p in pk], [p['ist'] for p in pk])
        kennwert = max(abs(p['ist'] - (a + b * p['ref'])) for p in pk)
    elif eigenschaft == 'hysterese':
        auf = {}
        abw = {}
        for p in pk:
            (auf if p.get('richtung') == 'auf' else abw if p.get('richtung') == 'ab' else {}).setdefault(
                p['ref'], []).append(p['ist'])
        gemeinsam = sorted(set(auf) & set(abw))
        if len(gemeinsam) < 3:
            return zu_wenig(f'{len(gemeinsam)} gemeinsame Referenzwerte auf/ab')
        kennwert = max(abs(_mittel(auf[r]) - _mittel(abw[r])) for r in gemeinsam)
    elif eigenschaft == 'drift':
        pt = [p for p in pk if isinstance(p.get('t_h'), (int, float))]
        dauer = float(mt.get('dauer_h', 168))
        ts = [p['t_h'] for p in pt]
        if len(pt) < 3 or max(ts) - min(ts) < dauer:
            return zu_wenig(f'{len(pt)} Zeitpunkte ueber {(max(ts) - min(ts)) if ts else 0:.4g} h (verlangt {dauer:g} h)')
        _, b = _gerade(ts, [p['ist'] - p['ref'] for p in pt])
        kennwert, zeitbasis = abs(b), True          # je Stunde
        U_pruef = None                               # Referenz-Offset faellt in der Steigung heraus
    elif eigenschaft == 'wiederholbarkeit':
        n_min = int(mt.get('wiederholungen', 10))
        gruppen = {}
        for p in pk:
            gruppen.setdefault(p['ref'], []).append(p['ist'])
        gross = {r: v for r, v in gruppen.items() if len(v) >= n_min}
        if not gross:
            return zu_wenig(f'hoechstens {max((len(v) for v in gruppen.values()), default=0)} Wiederholungen '
                            f'je Referenzwert (verlangt {n_min})')
        kennwert = max(_std(v) for v in gross.values())
        U_pruef = None                               # Streuung, nicht Abweichung zur Referenz
    else:
        return raus('verfahren_unzureichend', f'Eigenschaft {eigenschaft!r} unbekannt ({", ".join(EIGENSCHAFTEN)})')

    k_g = _einheit_umrechnen(kennwert, einheit, me, spanne, zeitbasis)
    if k_g is None:
        return raus('einheit_unpassend', f'{eigenschaft}: Einheit {einheit!r} nicht aus {me!r} umrechenbar '
                                         f'(erlaubt: {me}, %FS{", <einheit>/h|d|Jahr" if zeitbasis else ""})')
    u_g = _einheit_umrechnen(U_pruef, einheit, me, spanne) if U_pruef is not None else 0.0
    erg = {'kennwert': k_g, 'U_pruef': u_g, 'grenze': grenze, 'einheit': einheit, 'grund': None}
    txt = f'{eigenschaft} {k_g:.4g} {einheit} (U_pruef {u_g:.3g}) gegen <= {grenze} {einheit}, Reihe {reihe.get("id")}'
    if k_g > grenze:
        return {**erg, 'status': 'verletzt', 'text': txt + ' - ueberschritten'}
    if k_g + u_g > grenze:
        return {**erg, 'status': 'vorbehalt', 'text': txt + ' - im Graubereich der Pruefunsicherheit (ILAC-G8)'}
    return {**erg, 'status': 'bewiesen', 'text': txt + (' - nur Pruefzeitraum, Extrapolation' if zeitbasis else '')}


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


def pruefe(pdir):
    pj = projekt_soll(pdir)
    mk = pj.get('messkette')
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
