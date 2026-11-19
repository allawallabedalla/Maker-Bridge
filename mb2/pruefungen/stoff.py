"""Stofftransport und chemische Vertraeglichkeit (CH1-CH4, seit 19.11.2026). Fuer jedes Geraet mit Medium- oder
Umweltkontakt (Fluidik, Messzellen, Dichtungen, Gehaeuse im Chemikalienkontakt).

Grenze ehrlich: keine Reaktionskinetik und keine Chemie-Simulation. Die Bridge prueft, dass jede Paarung Werkstoff x
Medium mit einer Quelle belegt ist, und rechnet Diffusionszeiten und Drift mit Lehrbuchformeln. Werte kommen nie aus
dem Code.

soll.json ``_projekt.stoff``:
    {"benetzt": [{"teil": "kanal", "werkstoff": "PMMA"}, {"teil": "dichtung", "werkstoff": "FKM"}],
     "medien": [{"name": "Isopropanol 70 %", "T_max_C": 40}],
     "bestaendigkeit": [{"werkstoff": "PMMA", "medium": "Isopropanol 70 %", "bewertung": "A|B|C|D", "T_C": 20,
                         "quelle": "Herstellertabelle ... Seite ..."}],              # A bestaendig ... D unbestaendig
     "mischung": {"D_m2_s": 1e-9, "breite_mm": 0.5, "v_m_s": 0.02, "laenge_mm": 20, "muss_mischen": true},
     "ansprechen": {"D_m2_s": 1e-9, "schichtdicke_mm": 0.05, "ansprechzeit_max_s": 5},
     "drift": {"drift_rel_je_h": 1e-5, "kalibrierintervall_h": 2000, "toleranz_rel": 0.02}}  # Belag/Adsorption,
                                                                                         # gemessen (_herkunft.stoff.drift)
CH1 Werkstoffvertraeglichkeit: jede Paarung braucht einen Eintrag mit Quelle. A ok, B warnung (bedingt bestaendig),
    C/D fehler; nur bei niedrigerer Temperatur belegt als T_max des Mediums -> warnung; fehlender Eintrag -> fehler.
CH2 Mischung quer zum Kanal: Pe = v w / D, Mischlaenge L_mix ~ v w^2 / D (Diffusion ueber die Breite w). Muss gemischt
    werden und L < L_mix -> fehler (laminar mischt nur durch Diffusion); sonst info.
CH3 Ansprechzeit durch Diffusion: t = delta^2 / (2 D) (Einstein-Smoluchowski, 1D) gegen ansprechzeit_max_s.
CH4 Drift durch Belag/Adsorption: drift_rel_je_h x kalibrierintervall_h <= toleranz_rel. Ohne gemessene Drift
    hoechstens warnung.
"""
from . import ergebnis, projekt_soll, uebersprungen

Q = 'mb2/pruefungen/stoff.py (Vertraeglichkeit belegt, Diffusion nach Lehrbuch)'
T = {'CH1': 'Werkstoffvertraeglichkeit', 'CH2': 'Mischung quer zum Kanal', 'CH3': 'Ansprechzeit Diffusion',
     'CH4': 'Drift durch Belag/Adsorption'}
STUFE = {'A': 'ok', 'B': 'warnung', 'C': 'fehler', 'D': 'fehler'}


def _n(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0


def pruefe(pdir):
    pj = projekt_soll(pdir)
    st = pj.get('stoff')
    if not st:
        return [uebersprungen(i, T[i], 'soll-Feld _projekt.stoff fehlt (benetzte Werkstoffe, Medien)', Q)
                for i in ('CH1', 'CH2', 'CH3', 'CH4')]
    out = []
    # CH1
    ben, med = st.get('benetzt') or [], st.get('medien') or []
    if not ben or not med:
        out.append(uebersprungen('CH1', T['CH1'], 'stoff.benetzt oder stoff.medien fehlt', Q))
    for b in ben:
        for m in med:
            tit = f'{T["CH1"]} {b.get("werkstoff")} ({b.get("teil", "?")}) / {m.get("name")}'
            e = next((x for x in st.get('bestaendigkeit') or [] if x.get('werkstoff') == b.get('werkstoff')
                      and x.get('medium') == m.get('name')), None)
            if not e:
                out.append(ergebnis('CH1', tit, 'fehler', quelle=Q, teil=b.get('teil'),
                                    hinweis='keine Bestaendigkeitsangabe fuer diese Paarung - Herstellertabelle mit '
                                            'Seite eintragen (nicht raten)'))
                continue
            s = STUFE.get(str(e.get('bewertung', '')).upper())
            hin = f'Bewertung {e.get("bewertung")} bei {e.get("T_C", "?")} C ({e.get("quelle") or "ohne Quelle"})'
            if s is None:
                s, hin = 'fehler', f'Bewertung {e.get("bewertung")!r} unbekannt (A, B, C, D)'
            if s == 'ok' and not e.get('quelle'):
                s, hin = 'warnung', hin + ' - Quelle fehlt'
            if s == 'ok' and _n(m.get('T_max_C')) and (e.get('T_C') is None or e['T_C'] < m['T_max_C']):
                s, hin = 'warnung', hin + f' - nur bis {e.get("T_C")} C belegt, Medium bis {m["T_max_C"]} C'
            out.append(ergebnis('CH1', tit, s, quelle=Q, teil=b.get('teil'), hinweis=hin))
    # CH2
    mi = st.get('mischung')
    if not mi or not all(_n(mi.get(f)) for f in ('D_m2_s', 'breite_mm', 'v_m_s', 'laenge_mm')):
        out.append(uebersprungen('CH2', T['CH2'], 'stoff.mischung {D_m2_s, breite_mm, v_m_s, laenge_mm} fehlt', Q))
    else:
        w = mi['breite_mm'] * 1e-3
        pe = mi['v_m_s'] * w / mi['D_m2_s']
        lmix = mi['v_m_s'] * w * w / mi['D_m2_s'] * 1e3
        s = ('ok' if mi['laenge_mm'] >= lmix else 'fehler') if mi.get('muss_mischen') else 'info'
        out.append(ergebnis('CH2', T['CH2'], s, wert=round(lmix, 4), grenze=mi['laenge_mm'], einheit='mm', quelle=Q,
                            hinweis=f'Pe = v w / D = {pe:.3g}; Mischlaenge ~ v w^2 / D = {lmix:.4g} mm gegen Kanal '
                                    f'{mi["laenge_mm"]} mm' + ('' if not mi.get('muss_mischen') or s == 'ok' else
                                                              ' - mischt nicht: Mischer, laengerer oder schmalerer Kanal')))
    # CH3
    an = st.get('ansprechen')
    if not an or not all(_n(an.get(f)) for f in ('D_m2_s', 'schichtdicke_mm', 'ansprechzeit_max_s')):
        out.append(uebersprungen('CH3', T['CH3'], 'stoff.ansprechen {D_m2_s, schichtdicke_mm, ansprechzeit_max_s} fehlt', Q))
    else:
        t = (an['schichtdicke_mm'] * 1e-3) ** 2 / (2 * an['D_m2_s'])
        out.append(ergebnis('CH3', T['CH3'], 'ok' if t <= an['ansprechzeit_max_s'] else 'fehler', wert=round(t, 4),
                            grenze=an['ansprechzeit_max_s'], einheit='s', quelle=Q,
                            hinweis=f't = delta^2/(2D) = {t:.4g} s fuer {an["schichtdicke_mm"]} mm'))
    # CH4
    dr = st.get('drift')
    if not dr or not all(_n(dr.get(f)) for f in ('drift_rel_je_h', 'kalibrierintervall_h', 'toleranz_rel')):
        out.append(uebersprungen('CH4', T['CH4'], 'stoff.drift {drift_rel_je_h, kalibrierintervall_h, toleranz_rel} fehlt', Q))
    else:
        d = dr['drift_rel_je_h'] * dr['kalibrierintervall_h']
        herk = str((pj.get('_herkunft') or {}).get('stoff.drift', '')).split(':')[0].strip().lower()
        s = 'fehler' if d > dr['toleranz_rel'] else ('ok' if herk == 'gemessen' else 'warnung')
        out.append(ergebnis('CH4', T['CH4'], s, wert=round(d, 6), grenze=dr['toleranz_rel'], quelle=Q,
                            hinweis=f'{dr["drift_rel_je_h"]:.3g}/h x {dr["kalibrierintervall_h"]} h = {d:.3g} relativ; '
                                    f'Kalibrierintervall hoechstens {dr["toleranz_rel"] / dr["drift_rel_je_h"]:.0f} h'
                                    + ('' if herk == 'gemessen' else '; Drift nicht gemessen (angenommen)')))
    return out
