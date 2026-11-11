"""Libro de horas: neteo horario, periodos y facturación de un mes completo."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal as D
from zoneinfo import ZoneInfo

import pytest

from custom_components.factusol.billing import Tariff, compute_bill
from custom_components.factusol.hours import local_midnight_eh
from custom_components.factusol.ledger import Calibration, Ledger, aggregate_cycle, hour_net

from .test_billing import TARIFF

TZ = ZoneInfo("Europe/Madrid")


def eh(day: str, hour: int) -> int:
    d = date.fromisoformat(day)
    return local_midnight_eh(d, TZ) + hour


def test_hour_net_is_hourly_balance() -> None:
    cal = Calibration()
    assert hour_net([100, 60, None, None, None], cal, True) == (40.0, 0.0, False)
    assert hour_net([60, 100, None, None, None], cal, True) == (0.0, 40.0, False)
    # el dato oficial manda sobre el propio
    assert hour_net([100, 60, 80, 90, None], cal, True) == (0.0, 10.0, True)
    # solo consumo neto oficial (fichero de consumo facturado)
    assert hour_net([100, 60, None, None, 33], cal, True) == (33.0, 0.0, True)


def test_calibration_offset_applies_only_to_closed_hours() -> None:
    cal = Calibration(factor_imp=1.1, offset_imp=5.0)
    assert hour_net([100, 0, None, None, None], cal, True)[0] == pytest.approx(115.0)
    assert hour_net([100, 0, None, None, None], cal, False)[0] == pytest.approx(110.0)
    assert hour_net([0, 0, None, None, None], Calibration(offset_imp=-5.0), True)[0] == 0.0


def test_a_whole_month_reproduces_an_invoice() -> None:
    ledger = Ledger(TZ)
    # martes 1 de septiembre de 2026
    ledger.add_own(eh("2026-09-01", 10), 8690, 0)  # punta
    ledger.add_own(eh("2026-09-01", 8), 5880, 0)  # llano
    ledger.add_own(eh("2026-09-01", 3), 18150, 0)  # valle
    ledger.add_own(eh("2026-09-02", 13), 0, 563520)  # exportación
    ledger.add_own(eh("2026-09-02", 12), 500, 500)  # se anula dentro de la hora
    ledger.add_own(eh("2026-09-02", 16), 700, 200)  # 500 Wh netos de llano
    now = datetime(2026, 10, 3, 9, tzinfo=UTC)
    totals = aggregate_cycle(ledger, [TARIFF], date(2026, 9, 1), date(2026, 10, 1), now, Calibration())
    assert totals.kwh["punta"] == pytest.approx(8.69)
    assert totals.kwh["llano"] == pytest.approx(5.88 + 0.5)
    assert totals.kwh["valle"] == pytest.approx(18.15)
    assert totals.excedente_kwh == pytest.approx(563.52)
    assert totals.horas_sin_datos > 700
    bill = compute_bill(totals.segments, D("175.29"))
    assert bill.dias == D(30)
    assert bill.kwh["punta"] == D("8.69")


def test_official_hours_replace_own_and_count() -> None:
    ledger = Ledger(TZ)
    h = eh("2026-09-01", 10)
    ledger.add_own(h, 1000, 0)
    ledger.set_official(h, 900, 100, None)
    now = datetime(2026, 10, 3, tzinfo=UTC)
    totals = aggregate_cycle(ledger, [TARIFF], date(2026, 9, 1), date(2026, 10, 1), now, Calibration())
    assert totals.horas_oficiales == 1 and totals.horas_propias == 0
    assert totals.kwh["punta"] == pytest.approx(0.8)
    assert totals.importacion_bruta_kwh == pytest.approx(0.9)
    assert totals.exportacion_bruta_kwh == pytest.approx(0.1)


def test_future_hours_and_partial_day() -> None:
    ledger = Ledger(TZ)
    now = datetime(2026, 9, 10, 12, tzinfo=UTC)  # 14:00 hora local
    ledger.add_own(eh("2026-09-20", 10), 5000, 0)  # futura: no cuenta
    ledger.add_own(eh("2026-09-09", 10), 1000, 0)
    totals = aggregate_cycle(ledger, [TARIFF], date(2026, 9, 1), date(2026, 10, 1), now, Calibration())
    assert totals.kwh["punta"] == pytest.approx(1.0)
    days = sum((s.days for s in totals.segments), D(0))
    assert D("9.5") < days < D("9.7")  # 9 días y 14 h


def test_set_own_if_missing_and_roundtrip() -> None:
    ledger = Ledger(TZ)
    h = eh("2026-09-01", 10)
    assert ledger.set_own_if_missing(h, 10, 2)
    assert not ledger.set_own_if_missing(h, 99, 99)
    assert ledger.get(h)[0] == 10
    dump = ledger.dump_month("2026-09")
    other = Ledger(TZ)
    other.load_month("2026-09", dump)
    assert other.get(h) == ledger.get(h)
    assert ledger.official_range() is None
    ledger.set_official(h, 1, 2, None)
    assert ledger.official_range() == (h, h)


def test_tariff_change_splits_segments() -> None:
    later = Tariff.from_dict(
        {
            "desde": "2026-09-16",
            "potencia_punta_kw": 4.6,
            "potencia_valle_kw": 4.6,
            "precio_potencia_punta": 0.1,
            "precio_potencia_valle": 0.02,
            "precio_punta": 0.2,
            "precio_llano": 0.15,
            "precio_valle": 0.1,
            "precio_excedentes": 0.07,
        }
    )
    ledger = Ledger(TZ)
    ledger.add_own(eh("2026-09-02", 10), 1000, 0)
    ledger.add_own(eh("2026-09-17", 10), 2000, 0)
    now = datetime(2026, 10, 3, tzinfo=UTC)
    totals = aggregate_cycle(ledger, [TARIFF, later], date(2026, 9, 1), date(2026, 10, 1), now, Calibration())
    assert [s.days for s in totals.segments] == [D(15), D(15)]
    assert [float(s.kwh["punta"]) for s in totals.segments] == [1.0, 2.0]
