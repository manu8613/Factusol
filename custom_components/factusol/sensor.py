"""Sensores de Factusol."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .entity import FactusolEntity
from .hours import eh_start
from .manager import FactusolConfigEntry, FactusolManager, Snapshot
from .prices import last_change, price_history
from .schedule import LLANO, PUNTA, VALLE

EUR = "€"
EUR_KWH = "€/kWh"


@dataclass(frozen=True, kw_only=True)
class FactusolSensorDescription(SensorEntityDescription):
    """Describe un sensor de Factusol."""

    value_fn: Callable[[FactusolManager, Snapshot], StateType | datetime]
    attr_fn: Callable[[FactusolManager, Snapshot], dict[str, Any]] | None = None
    cycle_reset: bool = False


def _round(value: Any, digits: int = 2) -> float:
    return round(float(value), digits)


def _bill_attrs(m: FactusolManager, s: Snapshot) -> dict[str, Any]:
    c = s.current
    return {
        **c.bill.as_dict(),
        "ciclo_inicio": c.start.isoformat(),
        "ciclo_fin": c.end.isoformat(),
        "horas_oficiales": c.totals.horas_oficiales,
        "horas_propias": c.totals.horas_propias,
        "horas_sin_datos": c.totals.horas_sin_datos,
        "importacion_bruta_kwh": _round(c.totals.importacion_bruta_kwh, 3),
        "exportacion_bruta_kwh": _round(c.totals.exportacion_bruta_kwh, 3),
    }


def _price_alert_attrs(m: FactusolManager, s: Snapshot) -> dict[str, Any]:
    history = price_history(m.invoices)
    change = last_change(history)
    return {
        "hay_cambios": change is not None,
        "factura_inicio": history[-1]["inicio"] if history else None,
        "factura_fin": history[-1]["fin"] if history else None,
        "cambios": change["cambios"] if change else [],
    }


def _price_history_attrs(m: FactusolManager, s: Snapshot) -> dict[str, Any]:
    return {"facturas": price_history(m.invoices)}


def _history(m: FactusolManager, s: Snapshot) -> dict[str, Any]:
    months = []
    for c in s.cycles:
        b = c.bill
        months.append(
            {
                "ciclo": c.start.isoformat(),
                "cerrado": c.closed,
                "real": c.real is not None,
                "consumo_kwh": _round(b.consumo_total),
                "excedente_kwh": _round(b.excedente_kwh),
                "total_bruto": _round(b.total_bruto),
                "hucha_ingreso": _round(b.hucha_ingreso),
                "hucha_aplicada": _round(b.hucha_aplicada),
                "total_a_pagar": _round(b.total_a_pagar),
                "coste_real": _round(b.coste_real),
                "saldo_hucha": _round(b.saldo_hucha_final),
            }
        )
    first = s.cycles[0].start.isoformat() if s.cycles else None
    older = []
    for key in sorted(m.invoices):
        rec = m.invoices[key]
        if first is None or key >= first or rec.get("total_bruto") is None:
            continue
        gross = float(rec["total_bruto"])
        stored = float(rec.get("hucha_ingreso") or 0.0)
        applied = float(rec.get("hucha_aplicada") or 0.0)
        older.append(
            {
                "ciclo": key,
                "cerrado": True,
                "real": True,
                "consumo_kwh": _round(sum(float(rec.get(k) or 0.0) for k in ("consumo_punta", "consumo_llano", "consumo_valle"))),
                "excedente_kwh": _round(rec.get("excedente_kwh") or 0.0),
                "total_bruto": _round(gross),
                "hucha_ingreso": _round(stored),
                "hucha_aplicada": _round(applied),
                "total_a_pagar": _round(rec.get("total_a_pagar", gross - applied)),
                "coste_real": _round(gross - stored),
                "saldo_hucha": None if rec.get("saldo_hucha_final") is None else _round(rec["saldo_hucha_final"]),
            }
        )
    return {"meses": older + months}


def _official_last(m: FactusolManager, s: Snapshot) -> datetime | None:
    rng = m.ledger.official_range()
    return eh_start(rng[1] + 1) if rng else None


def _fit(m: FactusolManager, flow: str) -> dict[str, Any] | None:
    return (m.report or {}).get(flow)


SENSORS: tuple[FactusolSensorDescription, ...] = (
    FactusolSensorDescription(
        key="periodo_actual",
        device_class=SensorDeviceClass.ENUM,
        options=[PUNTA, LLANO, VALLE],
        value_fn=lambda m, s: s.period,
    ),
    FactusolSensorDescription(
        key="precio_energia",
        native_unit_of_measurement=EUR_KWH,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=5,
        value_fn=lambda m, s: _round(s.price_kwh, 6),
    ),
    FactusolSensorDescription(
        key="precio_excedentes",
        native_unit_of_measurement=EUR_KWH,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=5,
        value_fn=lambda m, s: _round(s.price_surplus, 6),
    ),
    *(
        FactusolSensorDescription(
            key=f"consumo_{period}",
            device_class=SensorDeviceClass.ENERGY,
            native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            state_class=SensorStateClass.TOTAL,
            suggested_display_precision=2,
            cycle_reset=True,
            value_fn=lambda m, s, p=period: _round(s.current.bill.kwh[p]),
        )
        for period in (PUNTA, LLANO, VALLE)
    ),
    FactusolSensorDescription(
        key="consumo_total",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        cycle_reset=True,
        value_fn=lambda m, s: _round(s.current.bill.consumo_total),
    ),
    FactusolSensorDescription(
        key="excedentes",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        cycle_reset=True,
        value_fn=lambda m, s: _round(s.current.bill.excedente_kwh),
    ),
    FactusolSensorDescription(
        key="factura_estimada",
        native_unit_of_measurement=EUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda m, s: _round(s.current.bill.total_bruto),
        attr_fn=_bill_attrs,
    ),
    FactusolSensorDescription(
        key="hucha_aplicada",
        native_unit_of_measurement=EUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda m, s: _round(s.current.bill.hucha_aplicada),
    ),
    FactusolSensorDescription(
        key="factura_a_pagar",
        native_unit_of_measurement=EUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda m, s: _round(s.current.bill.total_a_pagar),
    ),
    FactusolSensorDescription(
        key="hucha_ingreso",
        native_unit_of_measurement=EUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda m, s: _round(s.current.bill.hucha_ingreso),
    ),
    FactusolSensorDescription(
        key="coste_real",
        native_unit_of_measurement=EUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda m, s: _round(s.current.bill.coste_real),
    ),
    FactusolSensorDescription(
        key="saldo_hucha_proyectado",
        native_unit_of_measurement=EUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda m, s: _round(s.current.bill.saldo_hucha_final),
    ),
    FactusolSensorDescription(
        key="saldo_hucha_facturado",
        native_unit_of_measurement=EUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda m, s: _round(s.hucha_billed),
    ),
    FactusolSensorDescription(
        key="factura_anterior",
        native_unit_of_measurement=EUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda m, s: _round(s.previous.bill.total_bruto) if s.previous else None,
    ),
    FactusolSensorDescription(
        key="coste_real_anterior",
        native_unit_of_measurement=EUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda m, s: _round(s.previous.bill.coste_real) if s.previous else None,
    ),
    FactusolSensorDescription(
        key="coste_real_ano",
        native_unit_of_measurement=EUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda m, s: _round(s.cost_year),
    ),
    FactusolSensorDescription(
        key="historial_facturas",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda m, s: len(s.cycles),
        attr_fn=_history,
    ),
    FactusolSensorDescription(
        key="alerta_precios",
        value_fn=lambda m, s: len(c["cambios"]) if (c := last_change(price_history(m.invoices))) else 0,
        attr_fn=_price_alert_attrs,
    ),
    FactusolSensorDescription(
        key="historial_precios",
        value_fn=lambda m, s: len(price_history(m.invoices)),
        attr_fn=_price_history_attrs,
    ),
    FactusolSensorDescription(
        key="costes_fijos",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda m, s: _round(m.fixed_total, 4),
    ),
    FactusolSensorDescription(
        key="energia_costes_fijos",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda m, s: 0.0,
    ),
    FactusolSensorDescription(
        key="desfase_importacion",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda m, s: (_fit(m, "importacion") or {}).get("desfase_pct"),
        attr_fn=lambda m, s: {**(_fit(m, "importacion") or {}), "meses": (m.report or {}).get("meses", {})},
    ),
    FactusolSensorDescription(
        key="desfase_exportacion",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda m, s: (_fit(m, "exportacion") or {}).get("desfase_pct"),
        attr_fn=lambda m, s: _fit(m, "exportacion") or {},
    ),
    FactusolSensorDescription(
        key="ultimo_dato_oficial",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_official_last,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: FactusolConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    manager = entry.runtime_data
    async_add_entities(FactusolSensor(manager, description) for description in SENSORS)


class FactusolSensor(FactusolEntity, SensorEntity):
    """Sensor calculado por el gestor."""

    entity_description: FactusolSensorDescription

    def __init__(self, manager: FactusolManager, description: FactusolSensorDescription) -> None:
        super().__init__(manager, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator, self.coordinator.data)

    @property
    def last_reset(self) -> datetime | None:
        if not self.entity_description.cycle_reset or self.coordinator.data is None:
            return None
        start = self.coordinator.data.current.start
        return datetime(start.year, start.month, start.day, tzinfo=self.coordinator.tz)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        fn = self.entity_description.attr_fn
        if fn is None or self.coordinator.data is None:
            return None
        return fn(self.coordinator, self.coordinator.data)
