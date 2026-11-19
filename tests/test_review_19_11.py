"""Regressionstests zu den Review-Befunden vom 19.11.2026 (Mechanik, Firmware-Parser).
Aufruf aus maker-bridge-2/:  uv run python tests/test_review_19_11.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mb2 import realterme as rt                         # noqa: E402
from mb2.pruefungen import firmware                     # noqa: E402
from mb2.pruefungen.dauer import drucker_bbox           # noqa: E402
from mb2.pruefungen.messkette import _k_aus_nu          # noqa: E402


def test_waerme_fem_ohne_t_max_bleibt_annahme():
    """FEM mit stiller 25-°C-Umgebung darf die Luft-Annahme nicht aufheben (vorher: 26 °C, 'nicht angenommen')."""
    T, terme, ang = rt.teil_temperatur({'elektronik': True}, T_fem_C=26.0)
    assert ang and T >= 40.0, (T, terme, ang)


def test_druckdrehung_wie_build123d():
    """Reihenfolge wie Rotation(x, y, z): erst Z, dann Y, dann X (vorher X -> Y -> Z)."""
    assert drucker_bbox({'bbox_mm': [10, 20, 30], 'druck_drehung': [90, 0, 90]}) == (20.0, 30.0, 10.0)


def test_fw1_parser_hex_exponent_endung():
    assert firmware._wert_aus_datei('#define K2 -1.5e-6\n', 'K2') == -1.5e-6
    assert firmware._wert_aus_datei('#define A 0x10u\n', 'A') == 16
    assert firmware._wert_aus_datei('const float B = 2.5f;\n', 'B') == 2.5


def test_t_faktor_abgerundet():
    """GUM G.4.1: nu abrunden -> konservativ (vorher 1,2 -> 4,53)."""
    assert _k_aus_nu(1.2) == 13.97 and _k_aus_nu(20.5) == 2.13 and _k_aus_nu(6) == 2.52


if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_') and callable(f):
            f()
            print('ok', n)
    print('alle ok')
