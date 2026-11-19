/* MB2-TEMP-001: Konfigurationskonstanten mit Pruefwirkung.
 * FW1 (mb2/pruefungen/firmware.py) vergleicht sie mit cad/soll.json _projekt.messkette - nur hier aendern UND dort.
 */
#ifndef MB2_TEMP_001_CONFIG_H
#define MB2_TEMP_001_CONFIG_H

#define PGA_GAIN 16          /* messkette.schaltung.gain, Auslegung MK3: 67 % Aussteuerung bei 100 °C */
#define RREF_OHM 1650.0      /* messkette.schaltung.R_ref_ohm (0,01 %, 10 ppm/K laut Lastenheft) */
#define IDAC_UA 500          /* messkette.schaltung.I_idac_A = 500 uA je Stromquelle */
#define IDAC_TAUSCH 1        /* 1 = je Messwert zwei Wandlungen mit getauschten IDACs, Mittelwert */
#define RTD_R0_OHM 100.0     /* PT100, IEC 60751 */
#define MESSRATE_HZ 5        /* Lastenheft A-MESSRATE */
#define EINSCHWING_US 1000   /* messkette.schaltung.einschwing_s: Wartezeit nach IDAC-Tausch (Filter noch offen) */
#define WANDLUNG_TIMEOUT_MS 100  /* Einzelwandlung 20 SPS = 50,06 ms (SBAS501D S. 30, Tab. 8-4) + Reserve */
#define OFFSET_MITTEL 8      /* Wandlungen fuer die Offsetkalibrierung beim Start */

#endif
