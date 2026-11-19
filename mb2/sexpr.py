"""Minimaler S-Expression-Parser für KiCad-Dateien (.kicad_pcb / .kicad_sch / .kicad_mod)."""
import re

_TOKEN = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))', re.S)


class Sym(str):
    """Unquotiertes Atom (Schlüsselwort/Zahl) – grenzt sich von quotierten Strings ab."""


def parse(text):
    stack, cur = [], []
    for m in _TOKEN.finditer(text):
        lp, rp, qs, atom = m.groups()
        if lp:
            stack.append(cur)
            cur = []
        elif rp:
            done = cur
            cur = stack.pop()
            cur.append(done)
        elif qs is not None:
            cur.append(qs.replace('\\"', '"').replace('\\\\', '\\'))
        elif atom is not None:
            cur.append(Sym(atom))
    return cur[0] if cur else []


def head(node):
    return node[0] if isinstance(node, list) and node else None


def children(node, name):
    return [c for c in node[1:] if isinstance(c, list) and head(c) == name]


def child(node, name):
    for c in node[1:]:
        if isinstance(c, list) and head(c) == name:
            return c
    return None


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def prop(node, key):
    """KiCad (property "Reference" "R1" ...) -> "R1"."""
    for p in children(node, 'property'):
        if len(p) > 2 and p[1] == key:
            return p[2]
    # Ältere Formate: (fp_text reference "R1")
    for t in children(node, 'fp_text'):
        if len(t) > 2 and t[1] == key.lower():
            return t[2]
    return None
