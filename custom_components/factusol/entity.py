"""Entidad base de Factusol."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .manager import FactusolManager


class FactusolEntity(CoordinatorEntity[FactusolManager]):
    """Entidad colgada del dispositivo de facturación."""

    _attr_has_entity_name = True

    def __init__(self, manager: FactusolManager, key: str) -> None:
        super().__init__(manager)
        entry = manager.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Factusol",
            model="Factura de luz 2.0TD",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://github.com/manu8613/Factusol",
        )
