"""Sensorprofile (seit 19.11.2026): sensortyp-abhaengige Messmodelle als Ergaenzung zu ``pruefungen/messkette.py``.

``messkette.py`` bleibt generisch (Budget, Aufloesung, Messreihen). Ein Profil liefert fuer einen Sensortyp:
- die Modellgleichung (Anzeige als Funktion aller Eingangs- und Stoergroessen) fuer ``budget_aus_modell``,
- die Arbeitspunkte (Spannungen, Stroeme) fuer die Aussteuerungs- und Bauteilgrenzen,
- die rauschbegrenzte Aufloesung in der Messgroesse.
Auswahl ueber ``_projekt.messkette.profil``. Bauteilgrenzen kommen als Daten (``bauteile``), nie aus dem Profil.
"""
PROFILE = {'rtd_ratiometrisch_3leiter': 'mb2.sensorprofile.rtd'}
