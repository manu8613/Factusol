"""Lectura de los CSV de consumo horario que descarga la distribuidora.

Dos formatos, detectados por la cabecera:

* ``consumo_periodo``: ``CUPS;FECHA-HORA;INV / VER;PERIODO TARIFARIO;CONSUMO Wh;GENERACION Wh;``
  con la hora en que ACABA el tramo (``2026/11/09 01:00`` = 00:00-01:00) e ``INV / VER``
  = 1 en horario de verano. Trae importación y exportación brutas de cada hora.
* ``consumo_facturado``: ``CUPS;Fecha;Hora;Consumo_kWh;Metodo_obtencion`` con la hora
  como número de hora transcurrida desde la medianoche local (1-24; 23 y 25 los días de
  cambio de hora). Trae solo el consumo neto facturable.

El CUPS no se guarda ni se registra.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo

from .hours import eh_of, local_midnight_eh


class CsvFormatError(ValueError):
    """El fichero no es ninguno de los formatos conocidos."""


@dataclass(frozen=True)
class OfficialHour:
    eh: int
    imp_wh: float | None  # importación bruta
    exp_wh: float | None  # exportación bruta
    net_imp_wh: float | None  # consumo neto facturable


def _num(text: str) -> float:
    return float(text.strip().replace(",", "."))


def parse_csv(text: str, tz: tzinfo) -> list[OfficialHour]:
    """Devuelve las horas del CSV (las repetidas del cambio de hora ya vienen separadas)."""
    reader = csv.reader(io.StringIO(text.lstrip("﻿")), delimiter=";")
    try:
        header = [h.strip().lower() for h in next(reader)]
    except StopIteration as err:
        raise CsvFormatError("fichero vacío") from err
    if len(header) > 5 and header[1].startswith("fecha-hora"):
        return _parse_period(reader, tz)
    if len(header) >= 4 and header[1] == "fecha" and header[2] == "hora":
        return _parse_billed(reader, tz)
    raise CsvFormatError("cabecera desconocida")


def _parse_period(reader, tz: tzinfo) -> list[OfficialHour]:
    out: list[OfficialHour] = []
    for row in reader:
        if len(row) < 6 or not row[1].strip():
            continue
        day, clock = row[1].strip().split(" ")
        year, month, dom = (int(x) for x in day.split("/"))
        hour = int(clock[:2])
        summer = row[2].strip() == "1"
        # Instante en que acaba la hora; el indicador resuelve la hora repetida de otoño.
        end_local = datetime(year, month, dom, hour, tzinfo=tz, fold=0 if summer else 1)
        end_utc = end_local.astimezone(UTC)
        out.append(
            OfficialHour(
                eh=eh_of(end_utc) - 1,
                imp_wh=_num(row[4]),
                exp_wh=_num(row[5]),
                net_imp_wh=None,
            )
        )
    return out


def _parse_billed(reader, tz: tzinfo) -> list[OfficialHour]:
    out: list[OfficialHour] = []
    for row in reader:
        if len(row) < 4 or not row[1].strip():
            continue
        dom, month, year = (int(x) for x in row[1].strip().split("/"))
        hour = int(row[2])
        midnight = local_midnight_eh(datetime(year, month, dom).date(), tz)
        out.append(
            OfficialHour(
                eh=midnight + hour - 1,
                imp_wh=None,
                exp_wh=None,
                net_imp_wh=_num(row[3]) * 1000,
            )
        )
    return out


__all__ = ["CsvFormatError", "OfficialHour", "parse_csv"]
