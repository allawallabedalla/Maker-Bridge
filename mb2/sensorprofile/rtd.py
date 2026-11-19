"""Profil Widerstandsthermometer, ratiometrische 3-Leiter-Messung mit zwei Stromquellen (seit 19.11.2026).

Kennlinie: IEC 60751 (Callendar-Van Dusen), A = 3,9083e-3, B = -5,775e-7, C = -4,183e-12 (C nur unter 0 °C).
Grenzabweichung je Klasse (IEC 60751): AA 0,1 + 0,0017|t|, A 0,15 + 0,002|t|, B 0,3 + 0,005|t|, C 0,6 + 0,01|t| (°C).

Schaltung (Messgleichung, Bezugspunkte eindeutig):
    IDAC1 -> Leitung 1 -> RTD -> Leitung 3 -> R_ref -> AVSS;  IDAC2 -> Leitung 2 -> Leitung 3 (Kompensation)
    V_ref  = (I1 + I2) * R_ref                      (beide Stroeme durch R_ref: ratiometrisch, I faellt heraus)
    V_in   = I1 * (R_rtd + R_L1) - I2 * R_L2         (AIN+ an Leitung 1, AIN- an Leitung 2)
    D      = G (1 + e_G) (V_in + V_os + V_rausch + V_quant + V_inl) / V_ref     (Anteil des Vollausschlags)
    Mit IDAC-Tausch (idac_tausch): Mittel aus D(I1, I2) und D(I2, I1) - die Fehlanpassung m faellt in erster
    Ordnung heraus, ohne Tausch wirkt sie als Verstaerkungsfehler m/2 auf R_rtd.
    Firmware: R_mess = D * 2 R_ref,nenn / G;  T_anzeige = CVD^-1(R_mess) (+ Kalibrierkorrektur)
Modi: ``ab_werk`` (Klassentoleranz des Elements, Bauteiltoleranzen wirken) und ``kalibriert`` (Mehrpunktkalibrierung
gegen Referenz: Systematik von Element, R_ref, Verstaerkung, Offset ist in der Korrektur; es bleiben Kalibrier-
unsicherheit, Temperaturdrift der Elektronik gegen T_kal, Rauschen, Quantisierung).

Alle Bauteilgrenzen (Rauschen, Verstaerkungsfehler, IDAC-Compliance, PGA-Eingangsbereich, Referenzbereich ...) sind
EINGABEN unter ``messkette.bauteile.adc``. Fehlt ein Wert, wird der Beitrag/die Pruefung nicht gerechnet und das
steht im Ergebnis - es gibt keine eingebauten Datenblattwerte.
"""
import math

from ..pruefungen import ergebnis, uebersprungen
from ..pruefungen import messkette as MK

A, B, C = 3.9083e-3, -5.775e-7, -4.183e-12
KLASSEN = {'AA': (0.10, 0.0017), 'A': (0.15, 0.002), 'B': (0.30, 0.005), 'C': (0.60, 0.010)}
Q = 'mb2/sensorprofile/rtd.py (IEC 60751 Callendar-Van Dusen; ratiometrische 3-Leiter-Messgleichung)'
# Eingangsfelder des ADC (Datenblatt). Fehlende Felder nennt das Ergebnis.
ADC_FELDER = {
    'rauschen_Vrms': 'Eingangsbezogenes Rauschen RMS bei gewaehlter Verstaerkung/Datenrate (Rauschtabelle)',
    'verstaerkungsfehler_rel': 'Verstaerkungsfehler (relativ, Betrag)',
    'verstaerkungsdrift_ppm_K': 'Drift des Verstaerkungsfehlers',
    'offset_V': 'Eingangsoffset nach Firmware-Massnahmen (Betrag)',
    'offsetdrift_V_K': 'Offsetdrift',
    'inl_ppm_fsr': 'Integrale Nichtlinearitaet',
    'idac_fehlanpassung_rel': 'Fehlanpassung IDAC1/IDAC2 (relativ)',
    'ref_eingangsstrom_A': 'Strom in den Referenzeingang (Betrag)',
}


# ---------------------------------------------------------------------------------------------- IEC 60751

def r_von_t(t, r0=100.0):
    r = r0 * (1 + A * t + B * t * t)
    if t < 0:
        r += r0 * C * (t - 100) * t ** 3
    return r


def drdt(t, r0=100.0):
    d = r0 * (A + 2 * B * t)
    if t < 0:
        d += r0 * C * (4 * t ** 3 - 300 * t ** 2)
    return d


def t_von_r(r, r0=100.0):
    """Umkehrung: geschlossen fuer R >= R0, Newton fuer R < R0 (|Fehler| < 1e-9 °C)."""
    if r >= r0:
        return (-A + math.sqrt(A * A - 4 * B * (1 - r / r0))) / (2 * B)
    t = (-A + math.sqrt(A * A - 4 * B * (1 - r / r0))) / (2 * B)
    for _ in range(20):
        dt = (r_von_t(t, r0) - r) / drdt(t, r0)
        t -= dt
        if abs(dt) < 1e-12:
            break
    return t


def klassentoleranz(klasse, t):
    a, b = KLASSEN[klasse.upper()]
    return a + b * abs(t)


# ---------------------------------------------------------------------------------------------- Messmodell

def _p(mk):
    s, sc, adc = mk.get('sensor') or {}, mk.get('schaltung') or {}, (mk.get('bauteile') or {}).get('adc') or {}
    return s, sc, adc


def anzeige(t, x, mk):
    """Angezeigte Temperatur bei wahrer Temperatur t und Stoergroessen x (alle Schaetzwerte 0 = ideal)."""
    s, sc, _ = _p(mk)
    r0 = float(s.get('R0_ohm', 100.0))
    i, rref, g = float(sc['I_idac_A']), float(sc['R_ref_ohm']), float(sc['gain'])
    rl = float(sc.get('R_leitung_ohm', 0.0))
    r = r_von_t(t + x.get('dt_sensor', 0.0) + x.get('dt_selbst', 0.0), r0)
    m = x.get('m_idac', 0.0)
    i1, i2 = i * (1 + m / 2), i * (1 - m / 2)
    rl1, rl2 = rl + x.get('dR_leitung', 0.0) / 2, rl - x.get('dR_leitung', 0.0) / 2
    rref_w = rref * (1 + x.get('dR_ref_rel', 0.0) + x.get('tk_ref_rel', 0.0))
    i_refein = x.get('i_ref_eingang', 0.0)       # Strom in den Referenzeingang, verringert den Strom durch R_ref
    v_err = sum(x.get(k, 0.0) for k in ('v_offset', 'v_offsetdrift', 'v_rausch', 'v_quant', 'v_inl'))
    eg = 1 + x.get('e_gain', 0.0) + x.get('e_gaindrift', 0.0)

    def d(ia, ib):
        return g * eg * (ia * (r + rl1) - ib * rl2 + v_err) / ((ia + ib - i_refein) * rref_w)

    dd = (d(i1, i2) + d(i2, i1)) / 2 if sc.get('idac_tausch') else d(i1, i2)
    return t_von_r(dd * 2 * rref / g, r0) + sum(x.get(k, 0.0) for k in ('dt_kal', 'dt_kal_referenz', 'dt_kal_fit',
                                                                         'dt_kal_kopplung'))


def lsb_eingang(mk):
    _, sc, _ = _p(mk)
    vref = 2 * float(sc['I_idac_A']) * float(sc['R_ref_ohm'])
    return 2 * vref / float(sc['gain']) / 2 ** int(sc.get('bits', 24))


def _dT_el(sc):
    te = sc.get('T_elektronik_C')
    tk = float(sc.get('T_kal_C', 23.0))
    if not te:
        return None
    return max(abs(float(te[0]) - tk), abs(float(te[1]) - tk))


def eingaben(mk, t, herkunft=lambda f: None):
    """Eingangsgroessen fuer budget_aus_modell bei Temperatur t. Wert None = fehlt (wird gemeldet)."""
    s, sc, adc = _p(mk)
    modus = mk.get('modus', 'ab_werk')
    kal = mk.get('kalibrierung') or {}
    dte = _dT_el(sc)
    n = max(int(sc.get('mittelung', 1)), 1)
    i = float(sc['I_idac_A'])

    def e(name, verteilung, wert, einheit, feld):
        return name, {'wert': 0.0, 'u': {'wert': wert, 'verteilung': verteilung}, 'einheit': einheit,
                      'herkunft': herkunft(feld)}

    def mal(a, b):
        return None if a is None or b is None else a * b

    rausch = adc.get('rauschen_Vrms')
    z = [
        e('v_rausch', 'u', None if rausch is None else rausch / math.sqrt(n), 'V', 'bauteile.adc.rauschen_Vrms'),
        ('v_quant', {'wert': 0.0, 'u': {'wert': lsb_eingang(mk) / 2, 'verteilung': 'rechteck'}, 'einheit': 'V',
                     'herkunft': 'berechnet'}),
        e('tk_ref_rel', 'rechteck', mal(sc.get('R_ref_tk_ppm_K') and sc['R_ref_tk_ppm_K'] * 1e-6, dte), '1',
          'schaltung.R_ref_tk_ppm_K'),
        e('e_gaindrift', 'rechteck', mal(adc.get('verstaerkungsdrift_ppm_K') and adc['verstaerkungsdrift_ppm_K'] * 1e-6,
                                         dte), '1', 'bauteile.adc.verstaerkungsdrift_ppm_K'),
        e('v_offsetdrift', 'rechteck', mal(adc.get('offsetdrift_V_K'), dte), 'V', 'bauteile.adc.offsetdrift_V_K'),
    ]
    if s.get('eigenerwaermung_mW_K'):
        p_mw = i ** 2 * r_von_t(t, float(s.get('R0_ohm', 100))) * 1e3
        dts = p_mw / float(s['eigenerwaermung_mW_K'])
    else:
        dts = None
    if modus == 'ab_werk':
        fsr = 2 * 2 * i * float(sc['R_ref_ohm']) / float(sc['gain'])
        m = adc.get('idac_fehlanpassung_rel')
        z += [
            e('dt_sensor', 'rechteck', klassentoleranz(s.get('klasse', 'A'), t), '°C', 'sensor.klasse'),
            e('dt_selbst', 'rechteck', dts, '°C', 'sensor.eigenerwaermung_mW_K'),
            e('dR_ref_rel', 'rechteck', sc.get('R_ref_tol_rel'), '1', 'schaltung.R_ref_tol_rel'),
            e('dR_leitung', 'rechteck', sc.get('dR_leitung_ohm'), 'Ohm', 'schaltung.dR_leitung_ohm'),
            e('m_idac', 'rechteck', m, '1', 'bauteile.adc.idac_fehlanpassung_rel'),
            e('e_gain', 'rechteck', adc.get('verstaerkungsfehler_rel'), '1', 'bauteile.adc.verstaerkungsfehler_rel'),
            e('v_offset', 'rechteck', adc.get('offset_V'), 'V', 'bauteile.adc.offset_V'),
            e('i_ref_eingang', 'rechteck', adc.get('ref_eingangsstrom_A'), 'A', 'bauteile.adc.ref_eingangsstrom_A'),
            e('v_inl', 'rechteck', mal(adc.get('inl_ppm_fsr') and adc['inl_ppm_fsr'] * 1e-6, fsr), 'V',
              'bauteile.adc.inl_ppm_fsr'),
        ]
    else:
        # Mehrpunktkalibrierung gegen Referenz: Systematik von Element, R_ref, Verstaerkung, Offset, INL, Leitungen und
        # IDAC steckt in der Korrektur. Es bleiben die Unsicherheit der Kalibrierung selbst (drei Beitraege) und alles,
        # was sich zwischen Kalibrierung und Einsatz aendert (Elektroniktemperatur, Eigenerwaermung im anderen Medium).
        z += [
            e('dt_kal_referenz', 'u', kal.get('u_referenz'), '°C', 'kalibrierung.u_referenz'),
            ('dt_kal_fit', {'wert': 0.0, 'u': {'wert': kal.get('u_fit'), 'verteilung': 'u'}, 'einheit': '°C',
                            'herkunft': herkunft('kalibrierung.u_fit'), 'freiheitsgrade': kal.get('freiheitsgrade_fit')}),
            e('dt_kal_kopplung', 'u', kal.get('u_kopplung'), '°C', 'kalibrierung.u_kopplung'),
            e('dt_selbst', 'rechteck', dts, '°C', 'sensor.eigenerwaermung_mW_K'),
        ]
    weg = mk.get('vernachlaessigt') or {}
    return {k: v for k, v in z if k not in weg}


def budget_bei(mk, t, herkunft=lambda f: None):
    return MK.budget_aus_modell(lambda x: anzeige(t, x, mk), eingaben(mk, t, herkunft), float(mk.get('k', 2.0)),
                                mk.get('einheit', '°C'))


def arbeitspunkt(mk, t):
    """Spannungen bei Nennwerten (Leitungen nominal). AVSS = 0 V."""
    s, sc, _ = _p(mk)
    i, rref, g = float(sc['I_idac_A']), float(sc['R_ref_ohm']), float(sc['gain'])
    rl = float(sc.get('R_leitung_ohm', 0.0))
    r = r_von_t(t, float(s.get('R0_ohm', 100.0)))
    vref = 2 * i * rref
    v_unten = vref + 2 * i * rl                       # Leitung 3 traegt beide Stroeme
    ain_p, ain_n = v_unten + i * (r + rl), v_unten + i * rl
    vin = ain_p - ain_n
    return {'t_C': t, 'R_rtd_ohm': r, 'V_ref_V': vref, 'V_ain_p_V': ain_p, 'V_ain_n_V': ain_n, 'V_in_V': vin,
            'aussteuerung': g * vin / vref, 'P_rtd_W': i * i * r, 'P_ref_W': (2 * i) ** 2 * rref}


# ---------------------------------------------------------------------------------------------- Pruefungen

def _punkte(mk):
    mb = mk.get('messbereich') or {}
    lo, hi = float(mb['min']), float(mb['max'])
    n = 13
    return [lo + (hi - lo) * j / (n - 1) for j in range(n)]


def kalibrierung_auswerten(reihe, messbereich, grad=2):
    """Mehrpunktkalibrierung gegen Referenz: Korrektur t_korr = t_roh + k0 + k1 t_roh + k2 t_roh^2.
    Eingabe: Messreihe mit punkte [{ref, ist}] (ist = unkorrigierte Anzeige des Geraets, je Punkt gemittelt).
    Mindestverfahren: >= grad + 3 verschiedene Referenzwerte ueber >= 80 % des Messbereichs.
    u_fit = Standardabweichung der Reste der Punktmittel; u_referenz aus dem Kalibrierschein der Referenz (U / k);
    u_kopplung aus pruefunsicherheit 'thermische_kopplung' der Reihe (Rechteck-Halbbreite / sqrt(3)).
    nachweisfaehig nur bei datenstatus 'rueckfuehrbar_gemessen'."""
    stat = MK.punkt_statistik([p for p in reihe.get('punkte', []) if isinstance(p.get('ref'), (int, float))
                               and isinstance(p.get('ist'), (int, float))])
    refs = sorted({z['ref'] for z in stat})
    spanne = float(messbereich['max']) - float(messbereich['min'])
    gruende = []
    if len(refs) < grad + 3 or (refs[-1] - refs[0] if refs else 0) < 0.8 * spanne:
        gruende.append(f'verfahren_unzureichend: {len(refs)} Referenzwerte ueber '
                       f'{(refs[-1] - refs[0]) if refs else 0:g} von {spanne:g} (verlangt >= {grad + 3} ueber 80 %)')
        return {'gruende': gruende, 'nachweisfaehig': False}
    x = [z['mittel'] for z in stat]
    f = MK.korrektur_fit(x, [z['ref'] - z['mittel'] for z in stat], grad)
    ref = reihe.get('referenz') or {}
    u_ref = MK._u_referenz(ref)
    kopp = next((b for b in reihe.get('pruefunsicherheit') or [] if b.get('name') == 'thermische_kopplung'), None)
    u_k = MK.standardunsicherheit(kopp) if kopp else None
    if reihe.get('datenstatus') != 'rueckfuehrbar_gemessen':
        gruende.append(f'{reihe.get("datenstatus") or "datenstatus_fehlt"}: Koeffizienten nur zur Demonstration')
    if u_ref is None:
        gruende.append('referenz_ohne_unsicherheit')
    if u_k is None:
        gruende.append('thermische_kopplung nicht bestimmt (pruefunsicherheit)')
    k = f['koeffizienten'] + [0.0] * (3 - len(f['koeffizienten']))
    return {'koeffizienten': {'k0': k[0], 'k1': k[1], 'k2': k[2]}, 'grad': grad, 'u_fit': f['s'],
            'freiheitsgrade_fit': f['freiheitsgrade'], 'max_rest': f['max_rest'], 'u_referenz': u_ref,
            'u_kopplung': u_k, 'reihe': reihe.get('id'), 'datum': reihe.get('datum'),
            'datenstatus': reihe.get('datenstatus'), 'gruende': gruende,
            'nachweisfaehig': reihe.get('datenstatus') == 'rueckfuehrbar_gemessen' and u_ref is not None and u_k is not None,
            'punkte': [{'t_roh': z['mittel'], 'ref': z['ref'], 'rest': r} for z, r in zip(stat, f['reste'])]}


def korrigieren(t_roh, koeff):
    return t_roh + koeff['k0'] + koeff['k1'] * t_roh + koeff['k2'] * t_roh ** 2


def planung(mk, fehlt, herkunft=lambda f: None):
    """Wie viel Unsicherheit duerfen die fehlenden Beitraege zusammen noch haben, damit U <= ziel_U bleibt?
    Rechnet das Budget ohne sie; u_frei_max = sqrt((ziel_U / k)^2 - u_rest^2). Planungswert, kein Nachweis."""
    import copy
    ziel = mk.get('ziel_U')
    if ziel is None:
        return None
    m2 = copy.deepcopy(mk)
    m2['vernachlaessigt'] = {**(mk.get('vernachlaessigt') or {}), **{f: 'Planung' for f in fehlt}}
    tab = [(t, budget_bei(m2, t, herkunft)) for t in _punkte(m2)]
    if any(b['u_c'] is None for _, b in tab):
        return None
    t_w, b_w = max(tab, key=lambda tb: tb[1]['u_c'])
    rest = (ziel / b_w['k']) ** 2 - b_w['u_c'] ** 2
    return {'u_rest': b_w['u_c'], 't_C': t_w, 'k': b_w['k'], 'ziel_U': ziel, 'fehlt': list(fehlt),
            'u_frei_max': math.sqrt(rest) if rest > 0 else None,
            'beitraege_rest': [{'name': z['name'], 'beitrag': z['beitrag']} for z in b_w['beitraege']]}


def pruefe(mk, herkunft_klasse):
    """MK1-MK4 fuer das RTD-Profil. herkunft_klasse(feld) -> 'datenblatt'|...|None (fuer warnung bei Annahmen)."""
    e = mk.get('einheit', '°C')
    out = []
    pflicht = [f for f in ('I_idac_A', 'R_ref_ohm', 'gain') if (mk.get('schaltung') or {}).get(f) is None]
    if pflicht or not (mk.get('messbereich') or {}).get('max') is not None:
        g = f'messkette.schaltung {", ".join(pflicht) or ""} / messbereich fehlt'
        return [uebersprungen(i, n, g, Q) for i, n in (('MK1', 'Unsicherheitsbudget Messkette'),
                                                       ('MK2', 'Rauschbegrenzte Aufloesung'),
                                                       ('MK3', 'Aussteuerung ADC'))]
    _, sc, adc = _p(mk)

    def hk(f):
        k = herkunft_klasse(f)
        return f'{k}' if k else 'offen'

    # MK1: Budget ueber den Messbereich, schlechtester Punkt zaehlt
    tabelle = [(t, budget_bei(mk, t, hk)) for t in _punkte(mk)]
    fehlt = sorted({f for _, b in tabelle for f in b['fehlt']})
    ziel = mk.get('ziel_U')
    schwach = sorted({z['name'] for _, b in tabelle for z in b['beitraege']
                      if (z.get('herkunft') or 'offen') in ('offen', 'geschaetzt', 'angenommen')})
    if fehlt:
        txt = (f'Profil rtd, Modus {mk.get("modus", "ab_werk")}: Werte fehlen fuer {", ".join(fehlt)} '
               f'(Datenblatt/Messung eintragen, keine Annahme)')
        plan = planung(mk, fehlt, hk)
        if plan:
            txt += (f'. Planung: die uebrigen Beitraege ergeben u = {plan["u_rest"]:.3g} {e} (schlechtester Punkt '
                    f'{plan["t_C"]:g} {e}); fuer {", ".join(fehlt)} zusammen bleiben hoechstens u = '
                    f'{plan["u_frei_max"]:.3g} {e}' if plan['u_frei_max'] else '; Ziel schon ohne sie verfehlt')
        r = uebersprungen('MK1', 'Unsicherheitsbudget Messkette', txt, Q)
        if plan:
            r['daten'] = {'planung': plan}
        out.append(r)
    else:
        t_w, b_w = max(tabelle, key=lambda tb: tb[1]['U'])
        daten = {'modus': mk.get('modus', 'ab_werk'), 'schlechtester_punkt_C': t_w, 'beitraege': b_w['beitraege'],
                 'u_c': b_w['u_c'], 'k': b_w['k'], 'U': b_w['U'], 'modell': b_w['modell'],
                 'korrelationen_hinweis': b_w['korrelationen_hinweis'], 'nichtlinear_max': b_w['nichtlinear_max'],
                 'je_temperatur': [{'t_C': t, 'u_c': b['u_c'], 'U': b['U'], 'dominant': b['dominant']}
                                   for t, b in tabelle]}
        tab = ', '.join(f'{z["name"]} {z["beitrag"]:.3g} ({z["anteil_proz"]:.0f} %)'
                        for z in sorted(b_w['beitraege'], key=lambda z: -z['beitrag']))
        txt = (f'U = {b_w["k"]:g}*{b_w["u_c"]:.4g} = {b_w["U"]:.4g} {e} bei {t_w:g} {e} (schlechtester Punkt, '
               f'Modus {daten["modus"]}); {tab}. {b_w["korrelationen_hinweis"]}. {b_w["modell"]}')
        if schwach:
            txt += f'; Herkunft schwach/offen: {", ".join(schwach)} (angenommen)'
        weg = mk.get('vernachlaessigt') or {}
        if weg:
            txt += '; vernachlaessigt (begruendet, angenommen): ' + '; '.join(f'{k}: {v}' for k, v in weg.items())
            daten['vernachlaessigt'] = weg
            schwach = schwach or list(weg)
        if ziel is None:
            out.append(uebersprungen('MK1', 'Unsicherheitsbudget Messkette', 'messkette.ziel_U fehlt; ' + txt, Q))
        else:
            st = 'fehler' if b_w['U'] > ziel else ('warnung' if schwach else 'ok')
            out.append(ergebnis('MK1', 'Unsicherheitsbudget Messkette', st, wert=b_w['U'], grenze=ziel, einheit=e,
                                quelle=Q, hinweis=txt, daten=daten))
    # MK2: rauschbegrenzte Aufloesung, kleinste Steigung im Bereich (oberes Ende)
    rausch = adc.get('rauschen_Vrms')
    za = mk.get('ziel_aufloesung')
    if rausch is None:
        out.append(uebersprungen('MK2', 'Rauschbegrenzte Aufloesung',
                                 'bauteile.adc.rauschen_Vrms fehlt (Rauschtabelle des ADC bei Verstaerkung/Datenrate)', Q))
    else:
        n = max(int(sc.get('mittelung', 1)), 1)
        q = lsb_eingang(mk)
        sigma = math.sqrt(rausch ** 2 / n + q ** 2 / 12)
        i = float(sc['I_idac_A'])
        r0 = float((mk.get('sensor') or {}).get('R0_ohm', 100))
        steig = min(i * drdt(t, r0) for t in _punkte(mk))          # V/°C am Eingang
        klein = max(q, MK.SPITZE_SPITZE * sigma) / steig
        vref = 2 * i * float(sc['R_ref_ohm'])
        fsr = 2 * vref / float(sc['gain'])
        txt = (f'LSB {q * 1e9:.4g} nV, sigma_ges {sigma * 1e9:.4g} nV (Rauschen/sqrt({n}) + q/sqrt(12)), Steigung '
               f'{steig * 1e6:.4g} uV/{e}; effektiv {math.log2(fsr / sigma):.1f} Bit, rauschfrei '
               f'{math.log2(fsr / (MK.SPITZE_SPITZE * sigma)):.1f} Bit von {sc.get("bits", 24)} nominal; '
               f'kleinste unterscheidbare Aenderung {klein:.4g} {e} (6,6 sigma), RMS {sigma / steig:.3g} {e}')
        if za is None:
            out.append(uebersprungen('MK2', 'Rauschbegrenzte Aufloesung', 'messkette.ziel_aufloesung fehlt; ' + txt, Q))
        else:
            k = herkunft_klasse('bauteile.adc.rauschen_Vrms')
            st = 'fehler' if klein > za else ('ok' if k in ('datenblatt', 'gemessen', 'norm', 'berechnet') else 'warnung')
            out.append(ergebnis('MK2', 'Rauschbegrenzte Aufloesung', st, wert=klein, grenze=za, einheit=e, quelle=Q,
                                hinweis=txt + ('' if st != 'warnung' else '; Rauschwert-Herkunft offen (angenommen)'),
                                daten={'lsb_V': q, 'sigma_V': sigma, 'steigung_V_je_C': steig}))
    # MK3: Aussteuerung ueber den Messbereich (Vollausschlag +-V_ref/G), Reserve
    ap = [arbeitspunkt(mk, t) for t in _punkte(mk)]
    res = float(adc.get('aussteuerung_reserve', 0.05))
    a_max = max(abs(p['aussteuerung']) for p in ap)
    t_max = max(ap, key=lambda p: abs(p['aussteuerung']))['t_C']
    out.append(ergebnis('MK3', 'Aussteuerung ADC', 'fehler' if a_max > 1 - res else 'ok', wert=a_max, grenze=1 - res,
                        einheit='Anteil FS', quelle=Q,
                        hinweis=f'G*V_in/V_ref max {a_max * 100:.1f} % bei {t_max:g} {e} (Reserve {res * 100:.0f} %); '
                                f'V_ref = 2*I*R_ref = {ap[0]["V_ref_V"]:.4g} V, V_in {ap[0]["V_in_V"] * 1e3:.4g} ... '
                                f'{ap[-1]["V_in_V"] * 1e3:.4g} mV, Vollausschlag +-{ap[0]["V_ref_V"] / float(sc["gain"]) * 1e3:.4g} mV',
                        daten={'arbeitspunkte': ap}))
    if adc.get('verstaerkungen'):
        moegl = [g for g in adc['verstaerkungen'] if max(abs(g * p['V_in_V'] / p['V_ref_V']) for p in ap) <= 1 - res]
        out[-1]['hinweis'] += f'; groesste zulaessige Verstaerkung {max(moegl) if moegl else "keine"}'
    out += _bauteilgrenzen(mk, ap, herkunft_klasse)
    return out


def _bauteilgrenzen(mk, ap, herkunft_klasse):
    """MK4-*: Grenzen des ADC aus messkette.bauteile.adc (fehlt ein Wert: uebersprungen mit Feldname)."""
    _, sc, adc = _p(mk)
    g = float(sc['gain'])
    avdd = adc.get('avdd_V')
    rf = float(sc.get('R_filter_ohm', 0.0))
    i = float(sc['I_idac_A'])
    out = []

    def st_ok(ok, felder):
        if not ok:
            return 'fehler'
        stark = all(herkunft_klasse(f) in ('datenblatt', 'gemessen', 'norm', 'berechnet') for f in felder)
        return 'ok' if stark else 'warnung'

    vref = ap[0]['V_ref_V']
    lo, hi = adc.get('vref_min_V'), adc.get('vref_max_V')
    if lo is None or (hi is None and avdd is None):
        out.append(uebersprungen('MK4-REF', 'Referenzspannungsbereich', 'bauteile.adc.vref_min_V/vref_max_V fehlt', Q))
    else:
        hi = hi if hi is not None else avdd
        out.append(ergebnis('MK4-REF', 'Referenzspannungsbereich', st_ok(lo <= vref <= hi, ['bauteile.adc.vref_min_V']),
                            wert=vref, grenze=[lo, hi], einheit='V', quelle=Q,
                            hinweis=f'V_ref = 2*I*R_ref = {vref:.4g} V gegen {lo} ... {hi} V'))
    cr = adc.get('idac_compliance_rand_V')
    if cr is None or avdd is None:
        out.append(uebersprungen('MK4-IDAC', 'IDAC-Compliance', 'bauteile.adc.idac_compliance_rand_V/avdd_V fehlt', Q))
    else:
        v_pin = max(p['V_ain_p_V'] for p in ap) + i * rf
        gr = avdd - cr
        out.append(ergebnis('MK4-IDAC', 'IDAC-Compliance', st_ok(v_pin <= gr, ['bauteile.adc.idac_compliance_rand_V']),
                            wert=v_pin, grenze=gr, einheit='V', quelle=Q,
                            hinweis=f'IDAC-Pin max {v_pin:.4g} V (inkl. Filter {rf:g} Ohm) gegen AVDD - {cr} = {gr:.4g} V'))
    pr, anteil = adc.get('pga_ausgang_rand_V'), adc.get('vcm_min_avdd_anteil')
    if pr is None or avdd is None:
        out.append(uebersprungen('MK4-PGA', 'PGA-Gleichtaktbereich', 'bauteile.adc.pga_ausgang_rand_V/avdd_V fehlt', Q))
    else:
        vin = max(abs(p['V_in_V']) for p in ap)
        vcm = [(p['V_ain_p_V'] + p['V_ain_n_V']) / 2 for p in ap]
        unten = pr + g * vin / 2
        if anteil is not None:
            unten = max(unten, anteil * avdd)
        oben = avdd - pr - g * vin / 2
        ok = unten <= min(vcm) and max(vcm) <= oben
        out.append(ergebnis('MK4-PGA', 'PGA-Gleichtaktbereich', st_ok(ok, ['bauteile.adc.pga_ausgang_rand_V']),
                            wert=[min(vcm), max(vcm)], grenze=[unten, oben], einheit='V', quelle=Q,
                            hinweis=f'V_CM {min(vcm):.4g} ... {max(vcm):.4g} V gegen max(AVSS + {pr} + G*V_in,max/2, '
                                    f'{anteil} AVDD) = {unten:.4g} ... AVDD - {pr} - G*V_in,max/2 = {oben:.4g} V '
                                    f'(G = {g:g}, V_in,max = {vin * 1e3:.4g} mV)'))
    tw, f = adc.get('wandlungszeit_s'), sc.get('messrate_Hz')
    if tw is None or f is None:
        out.append(uebersprungen('MK5', 'Zeitbudget Messrate', 'bauteile.adc.wandlungszeit_s/schaltung.messrate_Hz fehlt', Q))
    else:
        n = max(int(sc.get('mittelung', 1)), 1)
        t = n * (float(tw) + float(sc.get('einschwing_s', 0.0)))
        out.append(ergebnis('MK5', 'Zeitbudget Messrate', st_ok(t <= 1 / f, ['bauteile.adc.wandlungszeit_s']),
                            wert=t, grenze=1 / f, einheit='s', quelle=Q,
                            hinweis=f'{n} Wandlungen x ({float(tw) * 1e3:.4g} ms + Einschwingen '
                                    f'{float(sc.get("einschwing_s", 0.0)) * 1e3:.3g} ms) = {t * 1e3:.4g} ms je Messwert '
                                    f'gegen {1e3 / f:.4g} ms bei {f:g} Hz (SPI-Zeit nicht enthalten)'))
    s = mk.get('sensor') or {}
    p = max(x['P_rtd_W'] for x in ap)
    if s.get('eigenerwaermung_mW_K'):
        dts = p * 1e3 / float(s['eigenerwaermung_mW_K'])
        gr = 0.1 * float(mk.get('ziel_U') or 0.5)
        out.append(ergebnis('MK4-SELBST', 'Eigenerwaermung RTD', 'ok' if dts <= gr else 'warnung', wert=dts, grenze=gr,
                            einheit='°C', quelle=Q,
                            hinweis=f'P = I^2 R = {p * 1e6:.3g} uW, Eigenerwaermung {dts * 1e3:.3g} mK '
                                    f'(Grenze 10 % von ziel_U; Koeffizient haengt vom Medium ab)'))
    else:
        out.append(uebersprungen('MK4-SELBST', 'Eigenerwaermung RTD',
                                 f'sensor.eigenerwaermung_mW_K fehlt (P = {p * 1e6:.3g} uW berechnet)', Q))
    return out
