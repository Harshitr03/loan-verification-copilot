from __future__ import annotations
from fnma_sf.layout import POSITIONS, field


def parse_line(line: str) -> dict:
    parts = line.rstrip("\n").split("|")          # parts[0] == "" (leading pipe)
    return {name: field(parts, pos) for name, pos in POSITIONS.items()}


def iter_rows(path):
    with open(path) as f:
        for line in f:
            if line.strip():
                yield parse_line(line)
