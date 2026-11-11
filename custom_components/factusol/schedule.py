"""Periodos horarios de la tarifa 2.0TD (punta, llano y valle)."""

from __future__ import annotations

import re
from datetime import date, datetime

PUNTA = "punta"
LLANO = "llano"
VALLE = "valle"
PERIODS = (PUNTA, LLANO, VALLE)

# Festivos nacionales de fecha fija que cuentan como valle todo el día.
NATIONAL_HOLIDAYS: frozenset[tuple[int, int]] = frozenset(
    {(1, 1), (1, 6), (5, 1), (8, 15), (10, 12), (11, 1), (12, 6), (12, 8), (12, 25)}
)

_LLANO_HOURS = frozenset({8, 9, 14, 15, 16, 17, 22, 23})


def parse_extra_holidays(text: str | None) -> frozenset[tuple[int, int]]:
    """Lee festivos extra con formato DD/MM separados por comas, espacios o punto y coma."""
    found: set[tuple[int, int]] = set()
    for day, month in re.findall(r"(\d{1,2})\s*[/-]\s*(\d{1,2})", text or ""):
        d, m = int(day), int(month)
        if 1 <= m <= 12 and 1 <= d <= 31:
            found.add((m, d))
    return frozenset(found)


def is_valley_day(day: date, extra: frozenset[tuple[int, int]] = frozenset()) -> bool:
    """Fines de semana y festivos: todo el día es valle."""
    return day.weekday() >= 5 or (day.month, day.day) in NATIONAL_HOLIDAYS or (
        (day.month, day.day) in extra
    )


def period_of(local: datetime, extra: frozenset[tuple[int, int]] = frozenset()) -> str:
    """Periodo de la hora que EMPIEZA en ``local`` (hora local peninsular)."""
    if is_valley_day(local.date(), extra):
        return VALLE
    hour = local.hour
    if hour < 8:
        return VALLE
    return LLANO if hour in _LLANO_HOURS else PUNTA
