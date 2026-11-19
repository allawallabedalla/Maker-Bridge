/* MB2-TEMP-001: Rechnung vom ADC-Rohwert zur Temperatur. Reines C, ohne Hardware, auf dem PC testbar
 * (tests/test_temp_demonstrator.py kompiliert es mit g++ und vergleicht mit mb2/sensorprofile/rtd.py).
 *
 * Messgleichung (ratiometrisch, 3-Leiter, zwei IDACs durch R_ref):
 *   D = Code / 2^23 = G * V_in / V_ref,  V_ref = 2 I R_ref,  V_in = I R_rtd  ->  R_rtd = D * 2 R_ref / G
 * Mit IDAC-Tausch: D = (D_a + D_b) / 2 (Fehlanpassung der Stromquellen faellt in erster Ordnung heraus).
 * Kennlinie IEC 60751 (Callendar-Van Dusen).
 * Rohwerte (Codes) und berechnete Temperatur werden getrennt ausgegeben - die Rechnung ist nachtraeglich wiederholbar.
 */
#ifndef MB2_RTD_RECHNUNG_H
#define MB2_RTD_RECHNUNG_H

#include <math.h>
#include <stdint.h>

#define CVD_A 3.9083e-3
#define CVD_B (-5.775e-7)
#define CVD_C (-4.183e-12)

/* Fehlerbits je Messwert */
#define RTD_OK 0
#define RTD_UEBERSTEUERT 1      /* Code an der Aussteuerungsgrenze (+/- Vollausschlag) */
#define RTD_UNPLAUSIBEL 2       /* R ausserhalb -50 ... +150 °C: Leitungsbruch, Kurzschluss, falscher Fuehler */
#define RTD_TAUSCH_ABWEICHUNG 4 /* D_a und D_b weichen > 1 % ab: Leitung/IDAC defekt */

static inline int32_t rtd_vorzeichen24(uint32_t roh)
{
    roh &= 0xFFFFFFu;
    return (roh & 0x800000u) ? (int32_t)(roh | 0xFF000000u) : (int32_t)roh;
}

static inline double cvd_r_aus_t(double t, double r0)
{
    double r = r0 * (1.0 + CVD_A * t + CVD_B * t * t);
    if (t < 0.0)
        r += r0 * CVD_C * (t - 100.0) * t * t * t;
    return r;
}

static inline double cvd_t_aus_r(double r, double r0)
{
    double t = (-CVD_A + sqrt(CVD_A * CVD_A - 4.0 * CVD_B * (1.0 - r / r0))) / (2.0 * CVD_B);
    if (r >= r0)
        return t;
    for (int i = 0; i < 20; i++) {   /* Newton unter 0 °C */
        double d = r0 * (CVD_A + 2.0 * CVD_B * t + CVD_C * (4.0 * t * t * t - 300.0 * t * t));
        double dt = (cvd_r_aus_t(t, r0) - r) / d;
        t -= dt;
        if (fabs(dt) < 1e-12)
            break;
    }
    return t;
}

/* code_b wird nur bei tausch != 0 benutzt. Rueckgabe: Fehlerbits; *r_ohm und *t_c immer gesetzt. */
static inline int rtd_rechnen(int32_t code_a, int32_t code_b, int tausch, double rref, int gain, double r0,
                              double *r_ohm, double *t_c)
{
    const double vs = 8388608.0;   /* 2^23 */
    int f = RTD_OK;
    if (code_a >= 0x7FFFFF || code_a <= -0x800000 || (tausch && (code_b >= 0x7FFFFF || code_b <= -0x800000)))
        f |= RTD_UEBERSTEUERT;
    double da = code_a / vs, db = tausch ? code_b / vs : da;
    if (tausch && fabs(da - db) > 0.01 * fabs(da + db) / 2.0)
        f |= RTD_TAUSCH_ABWEICHUNG;
    *r_ohm = (da + db) / 2.0 * 2.0 * rref / gain;
    if (*r_ohm < cvd_r_aus_t(-50.0, r0) || *r_ohm > cvd_r_aus_t(150.0, r0))
        f |= RTD_UNPLAUSIBEL;
    *t_c = cvd_t_aus_r(*r_ohm > 0 ? *r_ohm : r0, r0);
    return f;
}

#endif
