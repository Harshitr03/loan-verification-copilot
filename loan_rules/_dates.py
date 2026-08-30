from __future__ import annotations
from datetime import date, datetime

_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d")


def parse_date(value):
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    for fmt in _FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None
