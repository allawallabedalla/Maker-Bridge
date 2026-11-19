/* MB2-TEMP-001 am Raspberry Pi (Linux spidev). Uebersetzen: gcc -O2 -o mb2temp rpi_mb2_temp_001.c -lm
 * SPI einschalten (raspi-config -> Interface -> SPI), Modul an SPI0/CE0 (SCHNITTSTELLE.md).
 * Ausgabe auf stdout, eine Zeile je Messwert, Zeitstempel UTC (ISO 8601) vom Host:
 *   zeit_utc;code_a;code_b;offset_code;fehlerbits;r_ohm;t_roh_c;t_c
 * DRDY wird nicht gebraucht: nach START wird fest 60 ms gewartet (Einzelwandlung 20 SPS = 50,06 ms laut
 * SBAS501D S. 30, Tab. 8-4, plus Reserve), dann RDATA.
 */
#define _POSIX_C_SOURCE 200809L
#include <fcntl.h>
#include <linux/spi/spidev.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

#include "ads1220.h"

static int spi_fd = -1;

static void rpi_transfer(void *ctx, const uint8_t *tx, uint8_t *rx, int n)
{
    (void)ctx;
    uint8_t dummy[8];
    struct spi_ioc_transfer t;
    memset(&t, 0, sizeof t);
    t.tx_buf = (unsigned long)tx;
    t.rx_buf = (unsigned long)(rx ? rx : dummy);
    t.len = (unsigned)n;
    t.speed_hz = 1000000;
    t.bits_per_word = 8;
    if (ioctl(spi_fd, SPI_IOC_MESSAGE(1), &t) < 0 && rx)
        memset(rx, 0, (size_t)n);   /* Fehler -> Register-Gegenlesen schlaegt fehl -> Fehlerbit */
}

static void rpi_warte_us(void *ctx, uint32_t us)
{
    (void)ctx;
    struct timespec ts = {us / 1000000u, (long)(us % 1000000u) * 1000L};
    nanosleep(&ts, 0);
}

static int rpi_warte_drdy(void *ctx, uint32_t timeout_ms)
{
    (void)timeout_ms;
    rpi_warte_us(ctx, 60000);   /* feste Wandlungszeit statt DRDY-Pin */
    return 1;
}

static uint32_t rpi_zeit_ms(void *ctx)
{
    (void)ctx;
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint32_t)(ts.tv_sec * 1000u + ts.tv_nsec / 1000000);
}

int main(int argc, char **argv)
{
    const char *dev = argc > 1 ? argv[1] : "/dev/spidev0.0";
    uint8_t mode = SPI_MODE_1, bits = 8;
    uint32_t speed = 1000000;
    spi_fd = open(dev, O_RDWR);
    if (spi_fd < 0 || ioctl(spi_fd, SPI_IOC_WR_MODE, &mode) < 0 || ioctl(spi_fd, SPI_IOC_WR_BITS_PER_WORD, &bits) < 0 ||
        ioctl(spi_fd, SPI_IOC_WR_MAX_SPEED_HZ, &speed) < 0) {
        fprintf(stderr, "SPI %s nicht nutzbar\n", dev);
        return 1;
    }
    ads1220_t adc = {rpi_transfer, rpi_warte_drdy, rpi_warte_us, rpi_zeit_ms, 0, 0};
    int f = ads1220_start(&adc);
    f |= ads1220_offset_kalibrieren(&adc, OFFSET_MITTEL);
    printf("# MB2-TEMP-001 gain=%d rref=%.1f idac_ua=%d tausch=%d offset_code=%ld start_fehler=%d kal=%.9g/%.9g/%.9g\n",
           PGA_GAIN, RREF_OHM, IDAC_UA, IDAC_TAUSCH, (long)adc.offset_code, f, KAL_K0, KAL_K1, KAL_K2);
    printf("# zeit_utc;code_a;code_b;offset_code;fehlerbits;r_ohm;t_roh_c;t_c\n");
    fflush(stdout);
    struct timespec naechster;
    clock_gettime(CLOCK_MONOTONIC, &naechster);
    for (;;) {
        struct timespec jetzt;
        clock_gettime(CLOCK_REALTIME, &jetzt);
        char zeit[32];
        struct tm utc;
        gmtime_r(&jetzt.tv_sec, &utc);
        strftime(zeit, sizeof zeit, "%Y-%m-%dT%H:%M:%SZ", &utc);
        ads1220_messwert_t m = ads1220_messen(&adc);
        printf("%s;%ld;%ld;%ld;%d;%.5f;%.4f;%.4f\n", zeit, (long)m.code_a, (long)m.code_b, (long)m.offset_code,
               m.fehler, m.r_ohm, m.t_roh_c, m.t_c);
        fflush(stdout);
        naechster.tv_sec += MESSPERIODE_MS / 1000;
        naechster.tv_nsec += (long)(MESSPERIODE_MS % 1000) * 1000000L;
        if (naechster.tv_nsec >= 1000000000L) {
            naechster.tv_sec++;
            naechster.tv_nsec -= 1000000000L;
        }
        clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &naechster, 0);
    }
}
