/* MB2-TEMP-001: ADS1220-Treiber fuer die ratiometrische 3-Leiter-PT100-Messung mit IDAC-Tausch.
 * Reines C mit austauschbarer SPI-Schicht (Rueckruffunktionen) -> auf dem PC mit einer Attrappe testbar
 * (tests/test_temp_demonstrator.py). Quelle aller Codes: TI ADS1220 SBAS501D (Rev. Mai 2026):
 *   Befehle         S. 38, Tab. 8-7     RESET 0000 011x, START/SYNC 0000 100x, POWERDOWN 0000 001x,
 *                                       RDATA 0001 xxxx, RREG 0010 rrnn, WREG 0100 rrnn (nn = Bytes - 1)
 *   RESET-Wartezeit S. 38, 8.5.3.1     >= 50 us + 32 t_CLK
 *   SPI             S. 36, 8.5.1       nur Modus 1 (CPOL = 0, CPHA = 1)
 *   Datenformat     S. 37, Gl. 15      24 Bit Zweierkomplement, 7FFFFFh / 800000h = Vollausschlag (abgeschnitten)
 *   Register        S. 42-46, Tab. 8-8 bis 8-14
 *   Einzelwandlung  S. 34, 8.4.2.1     jeder Registerschreibzugriff startet eine Wandlung; START/SYNC waehrend
 *                                       einer Wandlung startet sie neu (S. 38, 8.5.3.2)
 *   Offset          S. 32, 8.3.12      MUX = 1110b schliesst AINP/AINN auf (AVDD + AVSS)/2 kurz
 *   3-Leiter-RTD    S. 55-58, Abb. 9-6 AINP = AIN1, AINN = AIN0, IDAC1 = AIN2, IDAC2 = AIN3, REFP0/REFN0 an R_ref
 */
#ifndef MB2_ADS1220_H
#define MB2_ADS1220_H

#include <stdint.h>
#include "config.h"
#include "rtd_rechnung.h"

/* Befehle (Tab. 8-7) */
#define ADS1220_RESET 0x06
#define ADS1220_START 0x08
#define ADS1220_POWERDOWN 0x02
#define ADS1220_RDATA 0x10
#define ADS1220_RREG(rr, n) ((uint8_t)(0x20 | ((rr) << 2) | ((n) - 1)))
#define ADS1220_WREG(rr, n) ((uint8_t)(0x40 | ((rr) << 2) | ((n) - 1)))

/* Register 0 (Tab. 8-10): MUX[7:4] GAIN[3:1] PGA_BYPASS[0] */
#define ADS1220_MUX_AIN1_AIN0 0x6   /* 0110b: AINP = AIN1, AINN = AIN0 */
#define ADS1220_MUX_KURZ 0xE        /* 1110b: Eingaenge auf Mitte kurzgeschlossen (Offsetkalibrierung) */
#define ADS1220_REG0(mux, gaincode) ((uint8_t)(((mux) << 4) | ((gaincode) << 1) | 0))   /* PGA aktiv */
/* Register 1 (Tab. 8-11/8-12): DR[7:5] MODE[4:3] CM[2] TS[1] BCS[0] */
#define ADS1220_DR_20SPS 0x0        /* Normalmodus: 000b = 20 SPS */
#define ADS1220_MODE_NORMAL 0x0
#define ADS1220_REG1 ((uint8_t)((ADS1220_DR_20SPS << 5) | (ADS1220_MODE_NORMAL << 3)))   /* CM = 0: Einzelwandlung */
/* Register 2 (Tab. 8-13): VREF[7:6] 50/60[5:4] PSW[3] IDAC[2:0] */
#define ADS1220_VREF_REFP0 0x1      /* 01b: externe Referenz REFP0/REFN0 */
#define ADS1220_FIR_50_60 0x1       /* 01b: 50 + 60 Hz (nur bei 20 SPS Normalmodus) */
#define ADS1220_REG2(idaccode) ((uint8_t)((ADS1220_VREF_REFP0 << 6) | (ADS1220_FIR_50_60 << 4) | (idaccode)))
/* Register 3 (Tab. 8-14): I1MUX[7:5] I2MUX[4:2] DRDYM[1] 0 */
#define ADS1220_IMUX_AIN2 0x3
#define ADS1220_IMUX_AIN3 0x4
#define ADS1220_REG3(i1, i2) ((uint8_t)(((i1) << 5) | ((i2) << 2)))
#define ADS1220_REG3_A ADS1220_REG3(ADS1220_IMUX_AIN2, ADS1220_IMUX_AIN3)   /* IDAC1 -> AIN2, IDAC2 -> AIN3 */
#define ADS1220_REG3_B ADS1220_REG3(ADS1220_IMUX_AIN3, ADS1220_IMUX_AIN2)   /* getauscht */

static inline uint8_t ads1220_gaincode(int gain)
{
    uint8_t c = 0;
    while ((1 << c) < gain && c < 7)
        c++;
    return c;   /* 1 -> 000b ... 128 -> 111b */
}

static inline uint8_t ads1220_idaccode(int ua)
{
    switch (ua) {   /* Tab. 8-13 */
    case 10: return 1; case 50: return 2; case 100: return 3; case 250: return 4;
    case 500: return 5; case 1000: return 6; case 1500: return 7; default: return 0;
    }
}

/* Hardwareschicht: transfer() mit CS-Rahmen, warte_drdy() true = Daten bereit, warte_us() */
typedef struct {
    void (*transfer)(void *ctx, const uint8_t *tx, uint8_t *rx, int n);
    int (*warte_drdy)(void *ctx, uint32_t timeout_ms);
    void (*warte_us)(void *ctx, uint32_t us);
    uint32_t (*zeit_ms)(void *ctx);
    void *ctx;
    int32_t offset_code;
} ads1220_t;

/* Fehlerbits zusaetzlich zu RTD_* */
#define ADS1220_REGISTER_FALSCH 16
#define ADS1220_TIMEOUT 32

static inline void ads1220_cmd(ads1220_t *d, uint8_t c)
{
    d->transfer(d->ctx, &c, 0, 1);
}

static inline int ads1220_konfig(ads1220_t *d, uint8_t r0, uint8_t r3)
{
    uint8_t tx[5] = {ADS1220_WREG(0, 4), r0, ADS1220_REG1, ADS1220_REG2(ads1220_idaccode(IDAC_UA)), r3};
    d->transfer(d->ctx, tx, 0, 5);
    uint8_t q[5] = {ADS1220_RREG(0, 4), 0, 0, 0, 0}, rx[5] = {0};
    d->transfer(d->ctx, q, rx, 5);
    return (rx[1] == tx[1] && rx[2] == tx[2] && rx[3] == tx[3] && rx[4] == tx[4]) ? 0 : ADS1220_REGISTER_FALSCH;
}

static inline int ads1220_start(ads1220_t *d)
{
    ads1220_cmd(d, ADS1220_RESET);
    d->warte_us(d->ctx, 100);                 /* >= 50 us + 32 t_CLK (8 us bei 4,096 MHz) */
    d->offset_code = 0;
    return ads1220_konfig(d, ADS1220_REG0(ADS1220_MUX_AIN1_AIN0, ads1220_gaincode(PGA_GAIN)), ADS1220_REG3_A);
}

static inline int ads1220_lesen(ads1220_t *d, int32_t *code)
{
    if (!d->warte_drdy(d->ctx, WANDLUNG_TIMEOUT_MS))
        return ADS1220_TIMEOUT;
    uint8_t tx[4] = {ADS1220_RDATA, 0, 0, 0}, rx[4] = {0};
    d->transfer(d->ctx, tx, rx, 4);
    *code = rtd_vorzeichen24(((uint32_t)rx[1] << 16) | ((uint32_t)rx[2] << 8) | rx[3]);
    return 0;
}

/* Offset bei gleicher Verstaerkung mit kurzgeschlossenen Eingaengen messen (Mittel aus n Wandlungen). */
static inline int ads1220_offset_kalibrieren(ads1220_t *d, int n)
{
    int f = ads1220_konfig(d, ADS1220_REG0(ADS1220_MUX_KURZ, ads1220_gaincode(PGA_GAIN)), ADS1220_REG3_A);
    int64_t s = 0;
    for (int i = 0; i < n && !f; i++) {
        int32_t c;
        ads1220_cmd(d, ADS1220_START);
        f |= ads1220_lesen(d, &c);
        s += c;
    }
    d->offset_code = (f || n <= 0) ? 0 : (int32_t)(s / n);
    return f | ads1220_konfig(d, ADS1220_REG0(ADS1220_MUX_AIN1_AIN0, ads1220_gaincode(PGA_GAIN)), ADS1220_REG3_A);
}

typedef struct {
    uint32_t zeit_ms;
    int32_t code_a, code_b;   /* Rohwerte (offsetkorrigiert NICHT enthalten -> roh) */
    int32_t offset_code;
    int fehler;
    double r_ohm, t_roh_c, t_c;   /* t_roh_c ohne, t_c mit Kalibrierkorrektur */
} ads1220_messwert_t;

/* Eine Phase: IDAC-Routing schreiben (startet eine Wandlung), Einschwingen abwarten, mit START neu starten. */
static inline int ads1220_phase(ads1220_t *d, uint8_t r3, int32_t *code)
{
    uint8_t tx[2] = {ADS1220_WREG(3, 1), r3};
    d->transfer(d->ctx, tx, 0, 2);
    d->warte_us(d->ctx, EINSCHWING_US);
    ads1220_cmd(d, ADS1220_START);
    return ads1220_lesen(d, code);
}

static inline ads1220_messwert_t ads1220_messen(ads1220_t *d)
{
    ads1220_messwert_t m = {0};
    m.zeit_ms = d->zeit_ms(d->ctx);
    m.offset_code = d->offset_code;
    m.fehler = ads1220_phase(d, ADS1220_REG3_A, &m.code_a);
    if (IDAC_TAUSCH && !m.fehler)
        m.fehler |= ads1220_phase(d, ADS1220_REG3_B, &m.code_b);
    /* Uebersteuerung an den ROHcodes pruefen: nach dem Offsetabzug laege ein gesaettigter Wert unter der Grenze */
    if (m.code_a >= 0x7FFFFF || m.code_a <= -0x800000 || (IDAC_TAUSCH && (m.code_b >= 0x7FFFFF || m.code_b <= -0x800000)))
        m.fehler |= RTD_UEBERSTEUERT;
    m.fehler |= rtd_rechnen(m.code_a - d->offset_code, m.code_b - d->offset_code, IDAC_TAUSCH, RREF_OHM, PGA_GAIN,
                            RTD_R0_OHM, &m.r_ohm, &m.t_roh_c);
    m.t_c = rtd_korrektur(m.t_roh_c, KAL_K0, KAL_K1, KAL_K2);
    return m;
}

#endif
