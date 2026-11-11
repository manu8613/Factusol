"""Asistente y opciones de Factusol."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    DateSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
)
from homeassistant.util import dt as dt_util

from .compat import vol
from .const import (
    CONF_CYCLE_DAY,
    CONF_EXPORT_ENTITY,
    CONF_EXTRA_HOLIDAYS,
    CONF_HUCHA_BALANCE,
    CONF_HUCHA_DATE,
    CONF_HUCHA_ENABLED,
    CONF_IMPORT_ENTITY,
    CONF_TARIFFS,
    DEFAULT_CYCLE_DAY,
    DEFAULT_NAME,
    DEFAULT_TARIFF,
    DOMAIN,
    T_FROM,
    T_OTHER_DAY,
    T_OTHER_MONTH,
    T_POWER_PEAK,
    T_POWER_PRICE_PEAK,
    T_POWER_PRICE_VALLEY,
    T_POWER_VALLEY,
    T_PRICE_FLAT,
    T_PRICE_PEAK,
    T_PRICE_SURPLUS,
    T_PRICE_VALLEY,
    T_RENTAL,
    T_SOCIAL,
    T_TAX,
    T_TAX_MIN,
    T_VAT,
)


def _number(minimum: float, maximum: float, step: float, unit: str | None = None) -> NumberSelector:
    config = NumberSelectorConfig(
        min=minimum,
        max=maximum,
        step=step if step >= 0.001 else "any",  # los selectores no admiten pasos menores
        mode=NumberSelectorMode.BOX,
    )
    if unit:
        config["unit_of_measurement"] = unit
    return NumberSelector(config)


def _energy_entity() -> EntitySelector:
    return EntitySelector(EntitySelectorConfig(domain="sensor", device_class="energy"))


def _optional(key: str, values: dict[str, Any]) -> Any:
    return vol.Optional(key, description={"suggested_value": values.get(key)})


def _sources_schema(values: dict[str, Any]) -> vol.Schema:
    imp = (
        vol.Required(CONF_IMPORT_ENTITY, default=values[CONF_IMPORT_ENTITY])
        if values.get(CONF_IMPORT_ENTITY)
        else vol.Required(CONF_IMPORT_ENTITY)
    )
    return vol.Schema(
        {
            imp: _energy_entity(),
            _optional(CONF_EXPORT_ENTITY, values): _energy_entity(),
            vol.Required(CONF_CYCLE_DAY, default=values.get(CONF_CYCLE_DAY, DEFAULT_CYCLE_DAY)): _number(
                1, 28, 1, "día"
            ),
            vol.Optional(CONF_EXTRA_HOLIDAYS, default=values.get(CONF_EXTRA_HOLIDAYS, "")): TextSelector(),
        }
    )


def _prices_schema(t: dict[str, Any]) -> vol.Schema:
    d = DEFAULT_TARIFF
    return vol.Schema(
        {
            vol.Required(T_POWER_PEAK, default=t.get(T_POWER_PEAK, d[T_POWER_PEAK])): _number(0, 50, 0.01, "kW"),
            vol.Required(T_POWER_VALLEY, default=t.get(T_POWER_VALLEY, d[T_POWER_VALLEY])): _number(0, 50, 0.01, "kW"),
            vol.Required(
                T_POWER_PRICE_PEAK, default=t.get(T_POWER_PRICE_PEAK, d[T_POWER_PRICE_PEAK])
            ): _number(0, 1, 0.000001, "€/kW·día"),
            vol.Required(
                T_POWER_PRICE_VALLEY, default=t.get(T_POWER_PRICE_VALLEY, d[T_POWER_PRICE_VALLEY])
            ): _number(0, 1, 0.000001, "€/kW·día"),
            vol.Required(T_PRICE_PEAK, default=t.get(T_PRICE_PEAK, d[T_PRICE_PEAK])): _number(0, 2, 0.000001, "€/kWh"),
            vol.Required(T_PRICE_FLAT, default=t.get(T_PRICE_FLAT, d[T_PRICE_FLAT])): _number(0, 2, 0.000001, "€/kWh"),
            vol.Required(T_PRICE_VALLEY, default=t.get(T_PRICE_VALLEY, d[T_PRICE_VALLEY])): _number(0, 2, 0.000001, "€/kWh"),
            vol.Required(
                T_PRICE_SURPLUS, default=t.get(T_PRICE_SURPLUS, d[T_PRICE_SURPLUS])
            ): _number(0, 2, 0.000001, "€/kWh"),
        }
    )


def _charges_schema(t: dict[str, Any]) -> vol.Schema:
    d = DEFAULT_TARIFF
    return vol.Schema(
        {
            vol.Required(T_SOCIAL, default=t.get(T_SOCIAL, d[T_SOCIAL])): _number(0, 1, 0.000001, "€/día"),
            vol.Required(T_RENTAL, default=t.get(T_RENTAL, d[T_RENTAL])): _number(0, 1, 0.000001, "€/día"),
            vol.Required(T_OTHER_DAY, default=t.get(T_OTHER_DAY, d[T_OTHER_DAY])): _number(0, 10, 0.000001, "€/día"),
            vol.Required(T_OTHER_MONTH, default=t.get(T_OTHER_MONTH, d[T_OTHER_MONTH])): _number(0, 500, 0.01, "€/ciclo"),
            vol.Required(T_TAX, default=t.get(T_TAX, d[T_TAX])): _number(0, 20, 0.00000001, "%"),
            vol.Required(T_TAX_MIN, default=t.get(T_TAX_MIN, d[T_TAX_MIN])): _number(0, 10, 0.01, "€/MWh"),
            vol.Required(T_VAT, default=t.get(T_VAT, d[T_VAT])): _number(0, 30, 0.01, "%"),
        }
    )


def _hucha_schema(values: dict[str, Any]) -> vol.Schema:
    today = dt_util.now().date()
    default_date = (today.replace(day=1) - timedelta(days=1)).isoformat()
    return vol.Schema(
        {
            vol.Required(CONF_HUCHA_ENABLED, default=values.get(CONF_HUCHA_ENABLED, True)): BooleanSelector(),
            vol.Required(CONF_HUCHA_BALANCE, default=values.get(CONF_HUCHA_BALANCE, 0.0)): _number(0, 100000, 0.01, "€"),
            vol.Required(CONF_HUCHA_DATE, default=values.get(CONF_HUCHA_DATE, default_date)): DateSelector(),
        }
    )


class FactusolConfigFlow(ConfigFlow, domain=DOMAIN):
    """Alta de un contrato."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._tariff: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_IMPORT_ENTITY])
            self._abort_if_unique_id_configured()
            self._data = {**user_input, CONF_CYCLE_DAY: int(user_input[CONF_CYCLE_DAY])}
            return await self.async_step_precios()
        schema = _sources_schema({}).extend({vol.Required(CONF_NAME, default=DEFAULT_NAME): TextSelector()})
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_precios(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._tariff.update(user_input)
            return await self.async_step_cargos()
        return self.async_show_form(step_id="precios", data_schema=_prices_schema({}))

    async def async_step_cargos(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._tariff.update(user_input)
            return await self.async_step_hucha()
        return self.async_show_form(step_id="cargos", data_schema=_charges_schema({}))

    async def async_step_hucha(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            data = {**self._data, **user_input}
            name = data.pop(CONF_NAME, DEFAULT_NAME)
            tariff = {**DEFAULT_TARIFF, **self._tariff, T_FROM: "2000-01-01"}
            return self.async_create_entry(title=name, data=data, options={CONF_TARIFFS: [tariff]})
        return self.async_show_form(step_id="hucha", data_schema=_hucha_schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> FactusolOptionsFlow:
        return FactusolOptionsFlow()


class FactusolOptionsFlow(OptionsFlow):
    """Cambia fuentes, precios, cargos y hucha. Los precios editan la tarifa vigente."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["fuentes", "precios", "cargos", "hucha"])

    def _values(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    def _latest(self) -> dict[str, Any]:
        tariffs = self._values().get(CONF_TARIFFS) or [dict(DEFAULT_TARIFF)]
        return dict(max(tariffs, key=lambda t: t[T_FROM]))

    def _save(self, changes: dict[str, Any]) -> ConfigFlowResult:
        return self.async_create_entry(data={**self.config_entry.options, **changes})

    def _save_tariff(self, changes: dict[str, Any]) -> ConfigFlowResult:
        tariffs = [dict(t) for t in (self._values().get(CONF_TARIFFS) or [dict(DEFAULT_TARIFF)])]
        latest = max(tariffs, key=lambda t: t[T_FROM])
        latest.update(changes)
        return self._save({CONF_TARIFFS: tariffs})

    async def async_step_fuentes(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            user_input = {**user_input, CONF_CYCLE_DAY: int(user_input[CONF_CYCLE_DAY])}
            user_input.setdefault(CONF_EXPORT_ENTITY, None)
            return self._save(user_input)
        return self.async_show_form(step_id="fuentes", data_schema=_sources_schema(self._values()))

    async def async_step_precios(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save_tariff(user_input)
        return self.async_show_form(step_id="precios", data_schema=_prices_schema(self._latest()))

    async def async_step_cargos(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save_tariff(user_input)
        return self.async_show_form(step_id="cargos", data_schema=_charges_schema(self._latest()))

    async def async_step_hucha(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        return self.async_show_form(step_id="hucha", data_schema=_hucha_schema(self._values()))


__all__ = ["FactusolConfigFlow", "FactusolOptionsFlow"]
