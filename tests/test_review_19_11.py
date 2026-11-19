"""Regressionstests zu den Review-Befunden vom 19.11.2026 (Mechanik, Firmware-Parser).
Aufruf aus maker-bridge-2/:  uv run python tests/test_review_19_11.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mb2 import realterme as rt                         # noqa: E402
from mb2.pruefungen import firmware                     # noqa: E402
from mb2.pruefungen.dauer import drucker_bbox           # noqa: E402
from mb2.pruefungen.messkette import _k_aus_nu          # noqa: E402
from mb2 import fem, sicherheit                          # noqa: E402
from mb2.pruefungen import fem_plausi                    # noqa: E402


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



def test_sicherheitsziel_zentral():
    """Ein Ziel fuer alle: Minimum der Pruefung, Projektziel und M26 - nie lascher als das Minimum."""
    assert sicherheit.ziel({}, None, None, 'z', 2.0)[0] == 2.0
    assert sicherheit.ziel({'sicherheit': 2.5}, None, None, 'z', 2.0)[0] == 2.5
    assert sicherheit.ziel({'sicherheit': 2.5}, None, None, 'z', 3.0)[0] == 3.0        # M4-Minimum bleibt
    assert sicherheit.ziel({'sicherheit': 2.5}, {'sicherheit': 1.0}, None, 'z', 1.5)[0] == 1.5   # Teil, Minimum
    s26 = sicherheit.ziel({'lastfaktor': 1.5}, None, 'PETG', 'z', 2.0)[0]
    assert s26 > 2.0, s26                                                                # M26 hebt an


def test_fem_bewertung_nutzt_projektziel():
    """Vorher fest 2,0: ein Projekt mit Ziel 10 bekam gruen bei S = 3."""
    lf = {'last': {'sicherheit': {'PETG': {'z': 3.0}}}}
    ohne = fem.bewertung_mech(lf, ['PETG'], kontext=None, dauer={'last': False})
    mit = fem.bewertung_mech(lf, ['PETG'], kontext=None, dauer={'last': False}, projekt={'sicherheit': 10})
    assert ohne['S_ziel'] == 2.0 and mit['S_ziel'] == 10.0 and not mit['ok'], (ohne, mit)


def test_m7_m9_realfaktor():
    """M7/M9 bekommen Abminderung und Ziel aus derselben Quelle wie die FEM-Bewertung."""
    so = {'_projekt': {'sicherheit': 2.5, 'T_max_C': 30}}
    fr = fem_plausi._realfaktor(None, so, {'lasten': [{'name': 'last'}]}, 'fall', 'last')
    f, S, ang, txt = fr('PETG')
    assert f >= 1.0 and S == 2.5 and 'Ziel' in txt, (f, S, ang, txt)


if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_') and callable(f):
            f()
            print('ok', n)
    print('alle ok')
