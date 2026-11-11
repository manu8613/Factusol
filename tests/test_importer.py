from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from custom_components.factusol.hours import eh_of, local_midnight_eh
from custom_components.factusol.importer import CsvFormatError, parse_csv

TZ = ZoneInfo("Europe/Madrid")

PERIOD_CSV = """CUPS;FECHA-HORA;INV / VER;PERIODO TARIFARIO;CONSUMO Wh;GENERACION Wh;
ES0000000000000000XX;2026/10/25 00:00;1;Valle;54;0;
ES0000000000000000XX;2026/10/25 01:00;1;Valle;39;0;
ES0000000000000000XX;2026/10/25 02:00;1;Valle;38;0;
ES0000000000000000XX;2026/10/25 02:00;0;Valle;41;0;
ES0000000000000000XX;2026/10/25 03:00;0;Valle;40;5;
"""

BILLED_CSV = """CUPS;Fecha;Hora;Consumo_kWh;Metodo_obtencion
ES0000000000000000XX;25/10/2026;1;0,039;D
ES0000000000000000XX;25/10/2026;2;0,038;D
ES0000000000000000XX;25/10/2026;3;0,041;D
ES0000000000000000XX;25/10/2026;4;0,035;D
ES0000000000000000XX;25/10/2026;5;0,040;D
"""


def test_period_format_resolves_the_repeated_autumn_hour() -> None:
    hours = parse_csv(PERIOD_CSV, TZ)
    ehs = [h.eh for h in hours]
    assert ehs == list(range(ehs[0], ehs[0] + 5))  # cinco horas seguidas, ninguna repetida
    # la primera fila acaba a las 00:00 del 25 (CEST): empieza a las 23:00 del 24
    assert ehs[0] == eh_of(datetime(2026, 10, 24, 21, tzinfo=UTC))
    assert (hours[0].imp_wh, hours[0].exp_wh, hours[0].net_imp_wh) == (54.0, 0.0, None)
    assert hours[4].exp_wh == 5.0


def test_billed_format_counts_elapsed_hours() -> None:
    hours = parse_csv(BILLED_CSV, TZ)
    midnight = local_midnight_eh(datetime(2026, 10, 25).date(), TZ)
    assert [h.eh for h in hours] == [midnight + i for i in range(5)]
    assert hours[0].net_imp_wh == pytest.approx(39.0)
    assert hours[0].imp_wh is None


def test_both_formats_agree_on_the_same_hour() -> None:
    a = parse_csv(PERIOD_CSV, TZ)
    b = parse_csv(BILLED_CSV, TZ)
    # La primera fila del formato A cierra la última hora del día 24: las demás van
    # una por una con las horas 1..4 del formato B, incluida la repetida de las 02:00.
    for row_a, row_b in zip(a[1:], b, strict=False):
        assert row_a.eh == row_b.eh
        assert max(row_a.imp_wh - row_a.exp_wh, 0) == pytest.approx(row_b.net_imp_wh)


def test_bom_and_unknown_header() -> None:
    assert parse_csv("﻿" + PERIOD_CSV, TZ)
    with pytest.raises(CsvFormatError):
        parse_csv("a;b;c\n1;2;3\n", TZ)
    with pytest.raises(CsvFormatError):
        parse_csv("", TZ)
