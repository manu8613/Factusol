"""Factusol: factura de luz 2.0TD con neteo horario, hucha de excedentes y calibración."""

from __future__ import annotations

import homeassistant.helpers.config_validation as cv
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .manager import FactusolConfigEntry, FactusolManager
from .services import async_setup_services

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: FactusolConfigEntry) -> bool:
    manager = FactusolManager(hass, entry)
    await manager.async_load()
    await hass.async_add_executor_job(lambda: manager.data_dir.mkdir(parents=True, exist_ok=True))
    await manager.async_config_entry_first_refresh()
    entry.runtime_data = manager
    manager.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: FactusolConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: FactusolConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_flush()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: FactusolConfigEntry) -> None:
    manager = FactusolManager(hass, entry)
    await manager.async_load()
    await manager.async_remove_stores()
