"""Horas absolutas (UTC) y su paso a hora local, a prueba de cambios de hora."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, tzinfo


def eh_of(moment: datetime) -> int:
    """Hora absoluta (horas desde 1970 en UTC) a la que pertenece ``moment``."""
    return int(moment.timestamp() // 3600)


def eh_start(eh: int) -> datetime:
    """Inicio de la hora absoluta ``eh`` en UTC."""
    return datetime.fromtimestamp(eh * 3600, UTC)


def eh_local(eh: int, tz: tzinfo) -> datetime:
    """Inicio de la hora ``eh`` en la zona horaria local."""
    return eh_start(eh).astimezone(tz)


def local_midnight_eh(day: date, tz: tzinfo) -> int:
    """Hora absoluta de la medianoche local que abre ``day``."""
    return eh_of(datetime(day.year, day.month, day.day, tzinfo=tz))


def month_key(local: datetime) -> str:
    return f"{local.year}-{local.month:02d}"


def add_months(day: date, months: int) -> date:
    """Suma meses a una fecha con día <= 28 (los ciclos nunca pasan de 28)."""
    index = day.year * 12 + day.month - 1 + months
    return day.replace(year=index // 12, month=index % 12 + 1)


def days_between(start: date, end: date) -> int:
    return (end - start).days


__all__ = [
    "add_months",
    "days_between",
    "eh_local",
    "eh_of",
    "eh_start",
    "local_midnight_eh",
    "month_key",
    "timedelta",
]
