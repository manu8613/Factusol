"""Entidades number: factores y desfases de calibración de la pinza."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import KEY_FACTOR_EXP, KEY_FACTOR_IMP, KEY_OFFSET_EXP, KEY_OFFSET_IMP
from .entity import FactusolEntity
from .manager import FactusolConfigEntry, FactusolManager

NUMBERS: tuple[NumberEntityDescription, ...] = (
    NumberEntityDescription(
        key=KEY_FACTOR_IMP,
        entity_category=EntityCategory.CONFIG,
        native_min_value=0.5,
        native_max_value=1.5,
        native_step=0.0001,
        mode=NumberMode.BOX,
    ),
    NumberEntityDescription(
        key=KEY_FACTOR_EXP,
        entity_category=EntityCategory.CONFIG,
        native_min_value=0.5,
        native_max_value=1.5,
        native_step=0.0001,
        mode=NumberMode.BOX,
    ),
    NumberEntityDescription(
        key=KEY_OFFSET_IMP,
        entity_category=EntityCategory.CONFIG,
        native_min_value=-100,
        native_max_value=100,
        native_step=0.01,
        native_unit_of_measurement="Wh",
        mode=NumberMode.BOX,
    ),
    NumberEntityDescription(
        key=KEY_OFFSET_EXP,
        entity_category=EntityCategory.CONFIG,
        native_min_value=-100,
        native_max_value=100,
        native_step=0.01,
        native_unit_of_measurement="Wh",
        mode=NumberMode.BOX,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: FactusolConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    manager = entry.runtime_data
    async_add_entities(FactusolNumber(manager, d) for d in NUMBERS)


class FactusolNumber(FactusolEntity, NumberEntity):
    """Valor de calibración editable."""

    def __init__(self, manager: FactusolManager, description: NumberEntityDescription) -> None:
        super().__init__(manager, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float:
        return float(self.coordinator.settings[self.entity_description.key])

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_setting(self.entity_description.key, value)
