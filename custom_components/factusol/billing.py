"""Motor de facturación 2.0TD: sin Home Assistant, probado contra facturas reales.

Replica el cálculo de una factura de autoconsumo con compensación de excedentes y
hucha de excedentes (saldo en euros que se descuenta de facturas futuras):

    potencia + (energía - compensación) + bono social  -> base del impuesto eléctrico
    + impuesto eléctrico + servicios (alquiler...)     -> base del IVA
    + IVA                                              -> total bruto
    - hucha aplicada                                   -> total a pagar

Cada línea se redondea a céntimos (mitad hacia arriba) y las bases suman las líneas
ya redondeadas, igual que la factura.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .schedule import LLANO, PERIODS, PUNTA, VALLE

CENT = Decimal("0.01")
ZERO = Decimal(0)


def dec(value: Any) -> Decimal:
    """Convierte a Decimal sin arrastrar el error binario de los float."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def kwh2(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Tariff:
    """Precios y cargos vigentes desde ``desde`` (incluido)."""

    desde: date
    potencia_punta_kw: Decimal
    potencia_valle_kw: Decimal
    precio_potencia_punta: Decimal  # €/kW·día
    precio_potencia_valle: Decimal  # €/kW·día
    precio_punta: Decimal  # €/kWh
    precio_llano: Decimal
    precio_valle: Decimal
    precio_excedentes: Decimal  # €/kWh
    bono_social_dia: Decimal  # €/día
    alquiler_dia: Decimal  # €/día
    otros_dia: Decimal  # €/día (servicios sin impuesto eléctrico)
    otros_mes: Decimal  # €/ciclo completo (servicios sin impuesto eléctrico)
    impuesto_electrico: Decimal  # %
    impuesto_minimo_mwh: Decimal  # €/MWh
    iva: Decimal  # %

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Tariff:
        return cls(
            desde=date.fromisoformat(data["desde"]),
            potencia_punta_kw=dec(data["potencia_punta_kw"]),
            potencia_valle_kw=dec(data["potencia_valle_kw"]),
            precio_potencia_punta=dec(data["precio_potencia_punta"]),
            precio_potencia_valle=dec(data["precio_potencia_valle"]),
            precio_punta=dec(data["precio_punta"]),
            precio_llano=dec(data["precio_llano"]),
            precio_valle=dec(data["precio_valle"]),
            precio_excedentes=dec(data["precio_excedentes"]),
            bono_social_dia=dec(data.get("bono_social_dia", 0)),
            alquiler_dia=dec(data.get("alquiler_dia", 0)),
            otros_dia=dec(data.get("otros_dia", 0)),
            otros_mes=dec(data.get("otros_mes", 0)),
            impuesto_electrico=dec(data.get("impuesto_electrico", 0)),
            impuesto_minimo_mwh=dec(data.get("impuesto_minimo_mwh", 0)),
            iva=dec(data.get("iva", 0)),
        )

    def price(self, period: str) -> Decimal:
        return {PUNTA: self.precio_punta, LLANO: self.precio_llano, VALLE: self.precio_valle}[period]

    def fixed_daily(self) -> Decimal:
        """Coste fijo por día con impuestos (potencia, bono social, alquiler y otros)."""
        taxed = (
            self.potencia_punta_kw * self.precio_potencia_punta
            + self.potencia_valle_kw * self.precio_potencia_valle
            + self.bono_social_dia
        )
        taxed *= 1 + self.impuesto_electrico / 100
        untaxed = self.alquiler_dia + self.otros_dia + self.otros_mes / 30
        return (taxed + untaxed) * (1 + self.iva / 100)


def tariff_on(tariffs: list[Tariff], day: date) -> Tariff:
    """Tarifa vigente en ``day``: la última con ``desde`` <= day (o la primera)."""
    chosen = tariffs[0]
    for tariff in tariffs:
        if tariff.desde <= day:
            chosen = tariff
    return chosen


@dataclass
class Segment:
    """Tramo del ciclo con una misma tarifa."""

    tariff: Tariff
    days: Decimal
    kwh: dict[str, Decimal] = field(default_factory=lambda: {p: ZERO for p in PERIODS})
    excedente_kwh: Decimal = ZERO


@dataclass
class Bill:
    """Resultado de una factura (estimada o real)."""

    dias: Decimal
    kwh: dict[str, Decimal]
    excedente_kwh: Decimal
    potencia: Decimal
    energia: dict[str, Decimal]
    energia_total: Decimal
    compensacion: Decimal
    bono_social: Decimal
    base_impuesto: Decimal
    impuesto_electrico: Decimal
    total_energia: Decimal
    servicios: Decimal
    importe_total: Decimal
    iva: Decimal
    total_bruto: Decimal
    hucha_ingreso: Decimal
    hucha_aplicada: Decimal
    total_a_pagar: Decimal
    coste_real: Decimal
    saldo_hucha_inicial: Decimal
    saldo_hucha_final: Decimal

    @property
    def consumo_total(self) -> Decimal:
        return sum(self.kwh.values(), ZERO)

    def as_dict(self) -> dict[str, Any]:
        """Representación para atributos y almacenamiento (números, no Decimal)."""
        out: dict[str, Any] = {}
        for key, value in self.__dict__.items():
            if isinstance(value, Decimal):
                out[key] = float(value)
            elif isinstance(value, dict):
                out[key] = {k: float(v) for k, v in value.items()}
            else:
                out[key] = value
        out["consumo_total"] = float(self.consumo_total)
        return out


def compute_bill(
    segments: list[Segment], hucha_saldo: Decimal = ZERO, hucha_activa: bool = True
) -> Bill:
    """Calcula la factura de uno o varios tramos de tarifa."""
    potencia = ZERO
    bono = ZERO
    servicios = ZERO
    energia = {p: ZERO for p in PERIODS}
    kwh = {p: ZERO for p in PERIODS}
    valor_excedentes = ZERO
    excedente = ZERO
    dias = ZERO
    minimo = ZERO
    cycle_days = Decimal(sum((s.days for s in segments), ZERO)) or Decimal(1)

    for seg in segments:
        t = seg.tariff
        dias += seg.days
        potencia += money(t.potencia_punta_kw * seg.days * t.precio_potencia_punta)
        potencia += money(t.potencia_valle_kw * seg.days * t.precio_potencia_valle)
        bono += money(seg.days * t.bono_social_dia)
        servicios += money(seg.days * t.alquiler_dia)
        servicios += money(seg.days * t.otros_dia)
        servicios += money(t.otros_mes * seg.days / cycle_days)
        for period in PERIODS:
            amount = kwh2(seg.kwh[period])
            kwh[period] += amount
            energia[period] += money(amount * t.price(period))
        excedente += kwh2(seg.excedente_kwh)
        valor_excedentes += money(kwh2(seg.excedente_kwh) * t.precio_excedentes)
        minimo += sum((kwh2(seg.kwh[p]) for p in PERIODS), ZERO) * t.impuesto_minimo_mwh / 1000

    energia_total = sum(energia.values(), ZERO)
    compensacion = min(valor_excedentes, energia_total)
    base = potencia + energia_total - compensacion + bono
    last = segments[-1].tariff if segments else None
    rate = (last.impuesto_electrico if last else ZERO) / 100
    impuesto = max(money(base * rate), money(minimo)) if last else ZERO
    total_energia = base + impuesto
    importe_total = total_energia + servicios
    iva = money(importe_total * ((last.iva if last else ZERO) / 100))
    total_bruto = importe_total + iva

    ingreso = money(max(valor_excedentes - compensacion, ZERO)) if hucha_activa else ZERO
    aplicada = min(max(hucha_saldo, ZERO), total_bruto) if hucha_activa else ZERO
    return Bill(
        dias=dias,
        kwh=kwh,
        excedente_kwh=excedente,
        potencia=potencia,
        energia=energia,
        energia_total=energia_total,
        compensacion=compensacion,
        bono_social=bono,
        base_impuesto=base,
        impuesto_electrico=impuesto,
        total_energia=total_energia,
        servicios=servicios,
        importe_total=importe_total,
        iva=iva,
        total_bruto=total_bruto,
        hucha_ingreso=ingreso,
        hucha_aplicada=aplicada,
        total_a_pagar=total_bruto - aplicada,
        coste_real=total_bruto - ingreso,
        saldo_hucha_inicial=hucha_saldo,
        saldo_hucha_final=hucha_saldo + ingreso - aplicada,
    )
