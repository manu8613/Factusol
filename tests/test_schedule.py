from __future__ import annotations

from datetime import datetime

from custom_components.factusol.schedule import LLANO, PUNTA, VALLE, parse_extra_holidays, period_of


def at(day: str, hour: int) -> datetime:
    return datetime.fromisoformat(f"{day}T{hour:02d}:00:00")


def test_weekday_hours() -> None:
    # martes 1 septiembre 2026
    expected = {0: VALLE, 7: VALLE, 8: LLANO, 9: LLANO, 10: PUNTA, 13: PUNTA, 14: LLANO, 17: LLANO, 18: PUNTA, 21: PUNTA, 22: LLANO, 23: LLANO}
    for hour, period in expected.items():
        assert period_of(at("2026-09-01", hour)) == period, hour


def test_weekend_and_national_holidays_are_valley() -> None:
    assert period_of(at("2026-09-05", 11)) == VALLE  # sábado
    assert period_of(at("2026-10-12", 11)) == VALLE  # lunes, festivo nacional
    assert period_of(at("2026-12-08", 19)) == VALLE


def test_extra_holidays() -> None:
    extra = parse_extra_holidays("15/05, 2-11; basura 99/99")
    assert extra == frozenset({(5, 15), (11, 2)})
    assert period_of(at("2026-05-15", 11)) == PUNTA
    assert period_of(at("2026-05-15", 11), extra) == VALLE
