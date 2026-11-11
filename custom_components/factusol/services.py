"""Servicios de Factusol."""

from __future__ import annotations

from typing import Any

import homeassistant.helpers.config_validation as cv
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError

from .compat import vol
from .const import (
    ATTR_ENTRY,
    DOMAIN,
    SERVICE_CALIBRATE,
    SERVICE_IMPORT,
    SERVICE_NEW_TARIFF,
    SERVICE_REBUILD,
    SERVICE_REGISTER_BILL,
    SERVICE_SET_FIXED,
    SERVICE_SET_HUCHA,
    TARIFF_FIELDS,
)
from .manager import FactusolConfigEntry, FactusolManager

_ENTRY = {vol.Optional(ATTR_ENTRY): cv.string}
_NUM = vol.Coerce(float)

NEW_TARIFF_SCHEMA = vol.Schema(
    {**_ENTRY, vol.Required("fecha"): cv.date, **{vol.Optional(f): _NUM for f in TARIFF_FIELDS}}
)
IMPORT_SCHEMA = vol.Schema({**_ENTRY, vol.Required("ruta"): cv.string})
CALIBRATE_SCHEMA = vol.Schema(
    {
        **_ENTRY,
        vol.Optional("desde"): cv.date,
        vol.Optional("hasta"): cv.date,
        vol.Optional("modo", default="factor"): vol.In(["factor", "factor_y_desfase"]),
        vol.Optional("aplicar", default=False): cv.boolean,
    }
)
REBUILD_SCHEMA = vol.Schema({**_ENTRY, vol.Required("desde"): cv.date})
BILL_SCHEMA = vol.Schema(
    {
        **_ENTRY,
        vol.Required("fecha_fin"): cv.date,
        vol.Optional("total_bruto"): _NUM,
        vol.Optional("hucha_aplicada"): _NUM,
        vol.Optional("total_a_pagar"): _NUM,
        vol.Optional("hucha_ingreso"): _NUM,
        vol.Optional("saldo_hucha_final"): _NUM,
        vol.Optional("consumo_punta"): _NUM,
        vol.Optional("consumo_llano"): _NUM,
        vol.Optional("consumo_valle"): _NUM,
        vol.Optional("excedente_kwh"): _NUM,
    }
)
HUCHA_SCHEMA = vol.Schema({**_ENTRY, vol.Required("saldo"): _NUM, vol.Required("fecha"): cv.date})
FIXED_SCHEMA = vol.Schema({**_ENTRY, vol.Required("valor"): _NUM})


def _manager(hass: HomeAssistant, call: ServiceCall) -> FactusolManager:
    entries: list[FactusolConfigEntry] = hass.config_entries.async_loaded_entries(DOMAIN)
    if entry_id := call.data.get(ATTR_ENTRY):
        entries = [e for e in entries if e.entry_id == entry_id]
    if not entries:
        raise HomeAssistantError("No hay ninguna instalación de Factusol cargada")
    if len(entries) > 1:
        raise HomeAssistantError("Hay varias instalaciones: indica config_entry_id")
    return entries[0].runtime_data


def async_setup_services(hass: HomeAssistant) -> None:
    async def new_tariff(call: ServiceCall) -> None:
        values = {k: v for k, v in call.data.items() if k in TARIFF_FIELDS}
        await _manager(hass, call).async_new_tariff(call.data["fecha"], values)

    async def import_official(call: ServiceCall) -> dict[str, Any]:
        return await _manager(hass, call).async_import_official(call.data["ruta"])

    async def calibrate(call: ServiceCall) -> dict[str, Any]:
        return await _manager(hass, call).async_calibrate(
            call.data.get("desde"), call.data.get("hasta"), call.data["modo"], call.data["aplicar"]
        )

    async def rebuild(call: ServiceCall) -> dict[str, Any]:
        return await _manager(hass, call).async_rebuild_history(call.data["desde"])

    async def register_bill(call: ServiceCall) -> dict[str, Any]:
        data = {k: v for k, v in call.data.items() if k not in (ATTR_ENTRY, "fecha_fin")}
        return await _manager(hass, call).async_register_bill(call.data["fecha_fin"], data)

    async def set_hucha(call: ServiceCall) -> None:
        await _manager(hass, call).async_set_hucha(call.data["saldo"], call.data["fecha"])

    async def set_fixed(call: ServiceCall) -> None:
        await _manager(hass, call).async_set_fixed(call.data["valor"])

    optional = SupportsResponse.OPTIONAL
    hass.services.async_register(DOMAIN, SERVICE_NEW_TARIFF, new_tariff, NEW_TARIFF_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_IMPORT, import_official, IMPORT_SCHEMA, supports_response=optional)
    hass.services.async_register(DOMAIN, SERVICE_CALIBRATE, calibrate, CALIBRATE_SCHEMA, supports_response=optional)
    hass.services.async_register(DOMAIN, SERVICE_REBUILD, rebuild, REBUILD_SCHEMA, supports_response=optional)
    hass.services.async_register(
        DOMAIN, SERVICE_REGISTER_BILL, register_bill, BILL_SCHEMA, supports_response=optional
    )
    hass.services.async_register(DOMAIN, SERVICE_SET_HUCHA, set_hucha, HUCHA_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SET_FIXED, set_fixed, FIXED_SCHEMA)


__all__ = ["async_setup_services"]
