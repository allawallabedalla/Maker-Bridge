"""Duenner MCP-Server: jedes Werkzeug aus befehle.BEFEHLE, jeder Aufruf als eigener Prozess `python -m mb2 ...`.
Keine Logik hier - ein Absturz von OCCT/Gmsh/Loeser trifft nur den einen Aufruf, stdin ist zu."""
import functools
import inspect
import json
import subprocess
import sys

from mcp.server.fastmcp import FastMCP

from .befehle import BASE, BEFEHLE

mcp = FastMCP('mb2', instructions=(
    'maker-bridge 2: Idee -> KiCad 10 -> build123d -> FEM (Gmsh/CalculiX/Elmer) -> PrusaSlicer (Prusa MK4 IS 0.4). '
    'Ohne Oberflaeche, alles in mm. Nach jedem CAD-Schritt Pruefbericht lesen und das PNG ansehen; bei ok=false '
    'nicht weiter. Druckt nie - nur Slicen. V-Modell (VMODELL.md): project_new mit einsatz, Lastenheft in '
    'anforderungen.json, Herkunft jeder Eingabe in _projekt._herkunft; gruen heisst bewiesen - audit.freigabe '
    'nicht_druckfertig | druckfertig | fertig (fertig erst mit abnahme_eintragen am Geraet und feld_eintragen).'))
TIMEOUT = {'fem': 7200, 'audit': 7200, 'kicad': 3600, 'slice': 1800}


def _werkzeug(name, fn):
    @functools.wraps(fn)
    def aufruf(**kw):
        p = subprocess.run([sys.executable, '-m', 'mb2', name, json.dumps(kw)], cwd=BASE, capture_output=True,
                           text=True, encoding='utf-8', errors='replace', stdin=subprocess.DEVNULL,
                           timeout=TIMEOUT.get(fn.gruppe, 900))
        try:
            return json.loads(p.stdout)
        except ValueError:
            return {'ok_aufruf': False, 'fehler': f'Prozess endete mit {p.returncode}', 'log': (p.stdout + p.stderr)[-2000:]}
    aufruf.__signature__ = inspect.signature(fn)
    return aufruf


for _n, _f in BEFEHLE.items():
    mcp.add_tool(_werkzeug(_n, _f), name=_n, description=inspect.getdoc(_f))


if __name__ == '__main__':
    mcp.run()
