"""Lectura de facturas de luz 2.0TD en PDF (formato de la comercializadora con Solar Cloud).

Este módulo no depende de Home Assistant. Del PDF solo se conservan cifras: el texto
completo (que incluye datos personales) no se guarda ni se registra en ningún sitio.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from io import BytesIO
from typing import Any

logging.getLogger("pypdf").setLevel(logging.ERROR)  # avisos de fuentes: ruido y sin datos útiles

MAX_PDF_BYTES = 5_000_000
MAX_PDF_PAGES = 12

_NUM = r"(?:-?\d{1,3}(?:\.\d{3})*(?:,\d+)?|-?\d+(?:,\d+)?)"
_DATE = r"(\d{2})/(\d{2})/(\d{4})"


class InvoiceError(ValueError):
    """El PDF no se puede leer o no es una factura reconocible."""


@dataclass
class ParsedInvoice:
    """Cifras de una factura."""

    inicio: date  # primer día facturado
    fin: date  # último día facturado
    dias: int
    factura: dict[str, float] = field(default_factory=dict)  # campos de registrar_factura
    tarifa: dict[str, float] = field(default_factory=dict)  # precios de la factura
    avisos: list[str] = field(default_factory=list)


def _n(text: str) -> float:
    return float(text.replace(".", "").replace(",", "."))


def _day(match: tuple[str, str, str]) -> date:
    return date(int(match[2]), int(match[1]), int(match[0]))


def extract_text(data: bytes) -> str:
    """Texto del PDF (bloquea: llamar desde un executor)."""
    if len(data) > MAX_PDF_BYTES:
        raise InvoiceError("El PDF es demasiado grande (máximo 5 MB)")
    if not data.startswith(b"%PDF-"):
        raise InvoiceError("El fichero no es un PDF")
    try:
        from pypdf import PdfReader  # noqa: PLC0415 - dependencia opcional hasta que se usa
    except ImportError as err:  # pragma: no cover
        raise InvoiceError("Falta la librería pypdf (se instala al reiniciar Home Assistant)") from err
    try:
        reader = PdfReader(BytesIO(data), strict=False)
        if len(reader.pages) > MAX_PDF_PAGES:
            raise InvoiceError("El PDF tiene demasiadas páginas para ser una factura")
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except InvoiceError:
        raise
    except Exception as err:  # noqa: BLE001 - pypdf lanza muchos tipos de error
        raise InvoiceError("No he podido leer el PDF") from err


def parse_invoice(text: str) -> ParsedInvoice:
    """Extrae las cifras del texto de una factura."""
    flat = re.sub(r"\s+", " ", text)
    period = re.search(rf"PERIODO DE FACTURACI[ÓO]N:?(?: N[ºo°] FACTURA:)?\s*{_DATE}\s*-\s*{_DATE}", flat)
    if not period:
        raise InvoiceError("No parece una factura de luz 2.0TD de este formato")
    g = period.groups()
    prev_end, end = _day(g[:3]), _day(g[3:])
    if end <= prev_end:
        raise InvoiceError("Las fechas del periodo no son coherentes")
    out = ParsedInvoice(inicio=prev_end + timedelta(days=1), fin=end, dias=(end - prev_end).days)
    f, t, warn = out.factura, out.tarifa, out.avisos

    def find(pattern: str, group: int = 1, flags: int = 0) -> list[str]:
        return [m.group(group) if group else m.group(0) for m in re.finditer(pattern, flat, flags)]

    # Energía por periodo
    kwh_prices: dict[str, float] = {}
    for name, key in (("Punta", "punta"), ("Llano", "llano"), ("Valle", "valle")):
        rows = re.findall(rf"{name} ({_NUM}) kWh x ({_NUM}) €/kWh", flat)
        if rows:
            f[f"consumo_{key}"] = round(sum(_n(r[0]) for r in rows), 4)
            if len({_n(r[1]) for r in rows}) == 1:
                kwh_prices[key] = _n(rows[0][1])
            else:
                warn.append(f"El precio de la energía {key} cambia dentro del periodo: no se actualiza la tarifa")
    for key, field_name in (("punta", "precio_punta"), ("llano", "precio_llano"), ("valle", "precio_valle")):
        if key in kwh_prices:
            t[field_name] = kwh_prices[key]
    # Potencia
    for name, key in (("Punta", "punta"), ("Valle", "valle")):
        rows = re.findall(rf"{name} ({_NUM}) kW x (\d+) d[ií]as x ({_NUM}) €/kW d[ií]a", flat)
        if len(rows) == 1:
            t[f"potencia_{key}_kw"] = _n(rows[0][0])
            t[f"precio_potencia_{key}"] = _n(rows[0][2])
        elif rows:
            warn.append(f"El precio de la potencia {key} cambia dentro del periodo: no se actualiza la tarifa")
    # Cargos y servicios
    if m := re.search(rf"Financiaci[óo]n bono social fijo (\d+) d[ií]as x ({_NUM}) €/d[ií]a", flat):
        t["bono_social_dia"] = _n(m.group(2))
    if m := re.search(rf"Alquiler equipos medida (\d+) d[ií]as x ({_NUM}) €/d[ií]a", flat):
        t["alquiler_dia"] = _n(m.group(2))
    if m := re.search(rf"Impuesto sobre electricidad ({_NUM}) %", flat):
        t["impuesto_electrico"] = _n(m.group(1))
    if m := re.search(rf"IVA ({_NUM}) % s/", flat):
        t["iva"] = _n(m.group(1))
    # Excedentes
    if m := re.search(rf"energ[ií]a excedentaria del [úu]ltimo mes es ({_NUM}) kWh", flat):
        f["excedente_kwh"] = abs(_n(m.group(1)))
    if m := re.search(rf"precio de compensaci[óo]n de los excedentes es ({_NUM}) ?€", flat):
        t["precio_excedentes"] = _n(m.group(1))
    # Totales
    total = re.search(rf"IMPORTE TOTAL ({_NUM}) €", flat)
    iva = re.search(rf"IVA {_NUM} % s/{_NUM} € ({_NUM}) €", flat)
    if not total or not iva:
        raise InvoiceError("No encuentro el importe total y el IVA de la factura")
    f["total_bruto"] = round(_n(total.group(1)) + _n(iva.group(1)), 2)
    if m := re.search(rf"Bono Solar Cloud \(1\) ({_NUM}) €", flat):
        f["hucha_aplicada"] = abs(_n(m.group(1)))
    if m := re.search(rf"TOTAL IMPORTE FACTURA ({_NUM}) €", flat):
        f["total_a_pagar"] = _n(m.group(1))
    if m := re.search(rf"importe almacenado en Solar Cloud.*? ha sido de ({_NUM}) ?€", flat):
        f["hucha_ingreso"] = _n(m.group(1))
    elif "excedente_kwh" in f:
        f["hucha_ingreso"] = 0.0
    if m := re.search(rf"saldo Solar Cloud disponible.*?(?:ascienda|asciende) a un total de ({_NUM}) ?€", flat):
        f["saldo_hucha_final"] = _n(m.group(1))
    # Comprobaciones: lo leído debe cuadrar entre sí
    if (m := re.search(rf"Total ({_NUM}) kWh hasta", flat)) and f.keys() >= {"consumo_punta", "consumo_llano", "consumo_valle"}:
        if abs(_n(m.group(1)) - sum(f[k] for k in ("consumo_punta", "consumo_llano", "consumo_valle"))) > 0.02:
            raise InvoiceError("Los kWh por periodo no suman el total de la factura")
    if "total_a_pagar" in f and "hucha_aplicada" in f and abs(f["total_bruto"] - f["hucha_aplicada"] - f["total_a_pagar"]) > 0.02:
        raise InvoiceError("El total, la hucha aplicada y el importe a pagar no cuadran")
    return out


def as_service_data(parsed: ParsedInvoice) -> dict[str, Any]:
    """Resumen de lo leído, para devolver al usuario (solo cifras)."""
    return {
        "inicio": parsed.inicio.isoformat(),
        "fin": parsed.fin.isoformat(),
        "dias": parsed.dias,
        **parsed.factura,
    }
