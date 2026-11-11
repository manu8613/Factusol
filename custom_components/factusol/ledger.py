"""Libro de horas: lo que mide tu pinza y lo que dice el contador de la distribuidora.

Cada hora absoluta (UTC) guarda, en Wh, la importación y la exportación propias y, si
se han importado, las oficiales. El neteo es horario: en cada hora solo cuenta el saldo
(importación - exportación), que es como se factura.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo
from decimal import Decimal
from typing import Any

from .billing import Segment, Tariff, dec, tariff_on
from .hours import eh_local, eh_of, local_midnight_eh, month_key
from .schedule import PERIODS, period_of

OWN_IMP, OWN_EXP, DIST_IMP, DIST_EXP, DIST_NET = range(5)


@dataclass(frozen=True)
class Calibration:
    """Corrección de la pinza: valor = max(propio * factor + desfase, 0) (Wh por hora)."""

    factor_imp: float = 1.0
    offset_imp: float = 0.0
    factor_exp: float = 1.0
    offset_exp: float = 0.0


def hour_net(
    rec: list[float | None], cal: Calibration, closed: bool
) -> tuple[float, float, bool]:
    """Saldo horario (importación neta, exportación neta, es_oficial) en Wh."""
    if rec[DIST_IMP] is not None and rec[DIST_EXP] is not None:
        imp, exp = float(rec[DIST_IMP]), float(rec[DIST_EXP])
        return max(imp - exp, 0.0), max(exp - imp, 0.0), True
    own_imp = rec[OWN_IMP] or 0.0
    own_exp = rec[OWN_EXP] or 0.0
    off_i = cal.offset_imp if closed else 0.0
    off_e = cal.offset_exp if closed else 0.0
    imp = max(own_imp * cal.factor_imp + off_i, 0.0)
    exp = max(own_exp * cal.factor_exp + off_e, 0.0)
    if rec[DIST_NET] is not None:
        net_imp = float(rec[DIST_NET])
        return net_imp, (0.0 if net_imp > 0 else max(exp - imp, 0.0)), True
    return max(imp - exp, 0.0), max(exp - imp, 0.0), False


class Ledger:
    """Horas guardadas, agrupadas por mes local para guardarlas en ficheros pequeños."""

    def __init__(self, tz: tzinfo) -> None:
        self.tz = tz
        self.months: dict[str, dict[int, list[float | None]]] = {}
        self.dirty: set[str] = set()

    # ------------------------------------------------------------- acceso
    def _month(self, eh: int) -> dict[int, list[float | None]]:
        key = month_key(eh_local(eh, self.tz))
        return self.months.setdefault(key, {})

    def get(self, eh: int) -> list[float | None] | None:
        return self._month(eh).get(eh)

    def _rec(self, eh: int) -> list[float | None]:
        month = self._month(eh)
        rec = month.get(eh)
        if rec is None:
            rec = month[eh] = [None, None, None, None, None]
        self.dirty.add(month_key(eh_local(eh, self.tz)))
        return rec

    # ------------------------------------------------------------- escritura
    def add_own(self, eh: int, imp_wh: float, exp_wh: float) -> None:
        rec = self._rec(eh)
        rec[OWN_IMP] = (rec[OWN_IMP] or 0.0) + imp_wh
        rec[OWN_EXP] = (rec[OWN_EXP] or 0.0) + exp_wh

    def set_own_if_missing(self, eh: int, imp_wh: float, exp_wh: float) -> bool:
        """Rellena una hora sin medida propia (reconstrucción desde estadísticas)."""
        rec = self.get(eh)
        if rec is not None and rec[OWN_IMP] is not None:
            return False
        rec = self._rec(eh)
        rec[OWN_IMP], rec[OWN_EXP] = imp_wh, exp_wh
        return True

    def set_official(
        self, eh: int, imp_wh: float | None, exp_wh: float | None, net_imp_wh: float | None
    ) -> None:
        rec = self._rec(eh)
        if imp_wh is not None and exp_wh is not None:
            rec[DIST_IMP], rec[DIST_EXP] = imp_wh, exp_wh
        if net_imp_wh is not None:
            rec[DIST_NET] = net_imp_wh

    # ------------------------------------------------------------- persistencia
    def dump_month(self, key: str) -> dict[str, list[float | None]]:
        return {str(eh): rec for eh, rec in sorted(self.months.get(key, {}).items())}

    def load_month(self, key: str, data: dict[str, Any]) -> None:
        self.months[key] = {int(eh): list(rec) for eh, rec in data.items()}

    # ------------------------------------------------------------- consultas
    def iter_hours(self, start_eh: int, end_eh: int):
        """Horas con datos en [start_eh, end_eh)."""
        for month in self.months.values():
            for eh, rec in month.items():
                if start_eh <= eh < end_eh:
                    yield eh, rec

    def official_range(self) -> tuple[int, int] | None:
        eh_all = [
            eh
            for month in self.months.values()
            for eh, rec in month.items()
            if rec[DIST_IMP] is not None or rec[DIST_NET] is not None
        ]
        return (min(eh_all), max(eh_all)) if eh_all else None


@dataclass
class CycleTotals:
    """Energía neta de un ciclo, lista para facturar."""

    segments: list[Segment]
    kwh: dict[str, float]
    excedente_kwh: float
    horas_oficiales: int
    horas_propias: int
    horas_sin_datos: int
    importacion_bruta_kwh: float
    exportacion_bruta_kwh: float


def segment_days(
    tz: tzinfo, tariffs: list[Tariff], start: date, end: date, now: datetime
) -> dict[Tariff, Decimal]:
    """Días de cada tarifa en [start, end) hasta ``now`` (fracción en el día en curso)."""
    out: dict[Tariff, Decimal] = {}
    now_local = now.astimezone(tz)
    day = start
    while day < end:
        midnight = datetime(day.year, day.month, day.day, tzinfo=tz)
        if midnight > now_local:
            break
        if now_local >= datetime(day.year, day.month, day.day, tzinfo=tz) + timedelta(days=1):
            frac = Decimal(1)
        else:
            frac = Decimal(str(round((now_local - midnight).total_seconds() / 86400, 4)))
        tariff = tariff_on(tariffs, day)
        out[tariff] = out.get(tariff, Decimal(0)) + frac
        day += timedelta(days=1)
    return out


def aggregate_cycle(
    ledger: Ledger,
    tariffs: list[Tariff],
    start: date,
    end: date,
    now: datetime,
    cal: Calibration,
    extra_holidays: frozenset[tuple[int, int]] = frozenset(),
) -> CycleTotals:
    """Suma las horas de [start, end) por periodo y tramo de tarifa.

    Las horas futuras no cuentan. La hora en curso se cuenta sin el desfase aditivo,
    que solo se añade cuando la hora ya está cerrada.
    """
    tz = ledger.tz
    now_eh = eh_of(now)
    start_eh = local_midnight_eh(start, tz)
    end_eh = local_midnight_eh(end, tz)
    segments: dict[Tariff, Segment] = {}

    def seg(tariff: Tariff) -> Segment:
        return segments.setdefault(tariff, Segment(tariff=tariff, days=Decimal(0)))

    for tariff, days in segment_days(tz, tariffs, start, end, now).items():
        seg(tariff).days = days

    official = own = missing = 0
    gross_imp = gross_exp = 0.0
    for eh in range(start_eh, min(end_eh, now_eh + 1)):
        rec = ledger.get(eh)
        if rec is None:
            missing += 1
            continue
        local = eh_local(eh, tz)
        net_imp, net_exp, is_official = hour_net(rec, cal, closed=eh < now_eh)
        if is_official:
            official += 1
        else:
            own += 1
        target = seg(tariff_on(tariffs, local.date()))
        target.kwh[period_of(local, extra_holidays)] += dec(net_imp) / 1000
        target.excedente_kwh += dec(net_exp) / 1000
        gross_imp += (rec[DIST_IMP] if rec[DIST_IMP] is not None else (rec[OWN_IMP] or 0.0)) / 1000
        gross_exp += (rec[DIST_EXP] if rec[DIST_EXP] is not None else (rec[OWN_EXP] or 0.0)) / 1000

    ordered = sorted(segments.values(), key=lambda s: s.tariff.desde)
    return CycleTotals(
        segments=ordered,
        kwh={p: float(sum((s.kwh[p] for s in ordered), Decimal(0))) for p in PERIODS},
        excedente_kwh=float(sum((s.excedente_kwh for s in ordered), Decimal(0))),
        horas_oficiales=official,
        horas_propias=own,
        horas_sin_datos=missing,
        importacion_bruta_kwh=gross_imp,
        exportacion_bruta_kwh=gross_exp,
    )
