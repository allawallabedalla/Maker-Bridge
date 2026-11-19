"""Richtwerte fuer gedruckte Teile (0,4-mm-Duese, 100 % Waende/hohe Fuellung). Festigkeit in Schichtrichtung (Z)
ist deutlich kleiner - die Sicherheit wird gegen beide Werte ausgewiesen. Quellen: Prusament-Datenblaetter
(Zugversuch gedruckt, XY bzw. Z) und uebliche Literaturwerte; fuer Dauerlast/Kriechen gelten sie NICHT."""
import contextlib

MATERIAL = {
    'PLA':  {'E_MPa': 2300.0,  # Prusament PLA TDS 2,3 GPa gedruckt (vorher 3500 = Vollmaterial, nicht konservativ; 10.11.2026)
              'nu': 0.36, 'festigkeit_xy_MPa': 50.0, 'festigkeit_z_MPa': 30.0,
             'dichte_kg_m3': 1240.0, 'waermeleitung_W_mK': 0.13, 'glasuebergang_C': 57.0},
    'PETG': {'E_MPa': 2000.0, 'nu': 0.38, 'festigkeit_xy_MPa': 45.0, 'festigkeit_z_MPa': 28.0,
             'dichte_kg_m3': 1270.0, 'waermeleitung_W_mK': 0.20, 'glasuebergang_C': 80.0},
    'ASA':  {'E_MPa': 2000.0, 'nu': 0.35, 'festigkeit_xy_MPa': 40.0, 'festigkeit_z_MPa': 25.0,
             'dichte_kg_m3': 1070.0, 'waermeleitung_W_mK': 0.17, 'glasuebergang_C': 100.0},
    # Hilfsmaterialien fuer Modellteile (z. B. Stift, Schraube, Platine)
    'STARR': {'E_MPa': 200000.0, 'nu': 0.3, 'dichte_kg_m3': 7850.0, 'waermeleitung_W_mK': 50.0},
    'FR4':   {'E_MPa': 22000.0, 'nu': 0.15, 'dichte_kg_m3': 1850.0, 'waermeleitung_W_mK': 0.3},
    'ALU':   {'E_MPa': 70000.0, 'nu': 0.33, 'dichte_kg_m3': 2700.0, 'waermeleitung_W_mK': 200.0},
}
DRUCKSTOFFE = ('PLA', 'PETG', 'ASA')


@contextlib.contextmanager
def ueberschrieben(over):
    """Kennwerte fuer einen Lauf ersetzen, z. B. {"PETG": {"E_MPa": 1700}} (Lastfeld "material_override", genutzt von
    fem_sensitivitaet). Danach wieder die Tabelle, auch bei Fehlern."""
    alt = {m: dict(v) for m, v in MATERIAL.items()}
    try:
        for m, felder in (over or {}).items():
            if m not in MATERIAL:
                raise KeyError(f'material_override: Material {m!r} unbekannt')
            MATERIAL[m].update(felder)
        yield
    finally:
        for m, v in alt.items():
            MATERIAL[m].clear()
            MATERIAL[m].update(v)
