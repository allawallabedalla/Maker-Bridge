"""Hilfen gegen Scheinsicherheit in Tests (19.11.2026): Ein Test, der nichts prueft, darf nicht 'bestanden' melden.

Statt still zurueckzukehren, wenn ein Beispielprojekt oder ein langer Lauf fehlt, wirft der Test ``NichtAusgefuehrt``.
``tests/alle.py`` zaehlt das als 'nicht ausgefuehrt' mit Klasse, nie als bestanden.
"""
import os


class NichtAusgefuehrt(Exception):
    def __init__(self, klasse, grund):
        super().__init__(f'{klasse}: {grund}')
        self.klasse = klasse
        self.grund = grund


def beispielprojekt(pfad, unterordner=''):
    """Pfad zurueckgeben oder NichtAusgefuehrt('beispielprojekt_fehlt') werfen."""
    if not os.path.isdir(os.path.join(pfad, unterordner)):
        raise NichtAusgefuehrt('beispielprojekt_fehlt', f'{pfad} fehlt (projects/ ist nicht im Repository)')
    return pfad


def lang(variable='MB2_LANG'):
    if os.environ.get(variable) != '1':
        raise NichtAusgefuehrt('lauf_nicht_angefordert', f'{variable}=1 fuer den langen Lauf setzen')
