"""Config Flow für die Lastspitze-Integration."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
)

from .const import (
    DOMAIN,
    CONF_NAME,
    CONF_POWER_SENSOR,
    CONF_ENABLE_WALLBOX,
    CONF_WALLBOX_COUNT,
    CONF_WALLBOXES,
    CONF_WB_AMP,
    CONF_WB_MAX_AMP,
    CONF_ABOVE_THRESHOLD,
    CONF_ABOVE_DURATION,
    CONF_BELOW_THRESHOLD,
    CONF_BELOW_DURATION,
    CONF_MIN_AMP,
    CONF_REDUCE_STEP,
    CONF_NOTIFY_SERVICE,
    CONF_NOTIFY_TARGET,
    DEFAULT_NAME,
    DEFAULT_ENABLE_WALLBOX,
    DEFAULT_WALLBOX_COUNT,
    DEFAULT_ABOVE_THRESHOLD,
    DEFAULT_ABOVE_DURATION,
    DEFAULT_BELOW_THRESHOLD,
    DEFAULT_BELOW_DURATION,
    DEFAULT_MIN_AMP,
    DEFAULT_REDUCE_STEP,
    DEFAULT_NOTIFY_SERVICE,
)

MAX_WALLBOXES = 10


def _base_schema(defaults: dict) -> vol.Schema:
    """Leistungssensor + Schwellwerte + Wallbox-An/Aus-Schalter."""
    return vol.Schema(
        {
            vol.Required(
                CONF_POWER_SENSOR, default=defaults.get(CONF_POWER_SENSOR)
            ): EntitySelector(EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_ABOVE_THRESHOLD,
                default=defaults.get(CONF_ABOVE_THRESHOLD, DEFAULT_ABOVE_THRESHOLD),
            ): NumberSelector(
                NumberSelectorConfig(min=1000, max=50000, step=100, mode=NumberSelectorMode.BOX, unit_of_measurement="W")
            ),
            vol.Optional(
                CONF_ABOVE_DURATION,
                default=defaults.get(CONF_ABOVE_DURATION, DEFAULT_ABOVE_DURATION),
            ): NumberSelector(
                NumberSelectorConfig(min=0, max=3600, step=10, mode=NumberSelectorMode.BOX, unit_of_measurement="s")
            ),
            vol.Optional(
                CONF_BELOW_THRESHOLD,
                default=defaults.get(CONF_BELOW_THRESHOLD, DEFAULT_BELOW_THRESHOLD),
            ): NumberSelector(
                NumberSelectorConfig(min=1000, max=50000, step=100, mode=NumberSelectorMode.BOX, unit_of_measurement="W")
            ),
            vol.Optional(
                CONF_BELOW_DURATION,
                default=defaults.get(CONF_BELOW_DURATION, DEFAULT_BELOW_DURATION),
            ): NumberSelector(
                NumberSelectorConfig(min=0, max=3600, step=10, mode=NumberSelectorMode.BOX, unit_of_measurement="s")
            ),
            vol.Optional(
                CONF_NOTIFY_SERVICE,
                default=defaults.get(CONF_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE),
            ): TextSelector(),
            vol.Optional(
                CONF_NOTIFY_TARGET, default=defaults.get(CONF_NOTIFY_TARGET, "")
            ): TextSelector(),
            vol.Required(
                CONF_ENABLE_WALLBOX,
                default=defaults.get(CONF_ENABLE_WALLBOX, DEFAULT_ENABLE_WALLBOX),
            ): BooleanSelector(),
        }
    )


def _wallbox_count_schema(defaults: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_WALLBOX_COUNT,
                default=defaults.get(CONF_WALLBOX_COUNT, DEFAULT_WALLBOX_COUNT),
            ): NumberSelector(
                NumberSelectorConfig(min=1, max=MAX_WALLBOXES, step=1, mode=NumberSelectorMode.BOX)
            ),
            vol.Required(
                CONF_MIN_AMP, default=defaults.get(CONF_MIN_AMP, DEFAULT_MIN_AMP)
            ): NumberSelector(
                NumberSelectorConfig(min=6, max=32, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="A")
            ),
            vol.Required(
                CONF_REDUCE_STEP, default=defaults.get(CONF_REDUCE_STEP, DEFAULT_REDUCE_STEP)
            ): NumberSelector(
                NumberSelectorConfig(min=1, max=16, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="A")
            ),
        }
    )


def _wallboxes_schema(count: int, existing: list) -> vol.Schema:
    """Zwei Entity-Felder pro Wallbox, alle in einem Schritt."""
    fields: dict = {}
    for i in range(count):
        prev = existing[i] if i < len(existing) else {}
        fields[
            vol.Required(f"{CONF_WB_AMP}_{i}", default=prev.get(CONF_WB_AMP))
        ] = EntitySelector(EntitySelectorConfig(domain="number"))
        fields[
            vol.Required(f"{CONF_WB_MAX_AMP}_{i}", default=prev.get(CONF_WB_MAX_AMP))
        ] = EntitySelector(EntitySelectorConfig(domain="number"))
    return vol.Schema(fields)


def _collect_wallboxes(user_input: dict, count: int) -> list:
    return [
        {
            CONF_WB_AMP: user_input[f"{CONF_WB_AMP}_{i}"],
            CONF_WB_MAX_AMP: user_input[f"{CONF_WB_MAX_AMP}_{i}"],
        }
        for i in range(count)
    ]


class LastspitzeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Setup-Assistent: Leistungssensor, Schwellwerte, optional beliebig viele Wallboxen."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict = {}

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            name = user_input.pop(CONF_NAME)
            self._data.update(user_input)
            self._data[CONF_NAME] = name
            if self._data[CONF_ENABLE_WALLBOX]:
                return await self.async_step_wallbox_count()
            self._data[CONF_WALLBOXES] = []
            return await self._async_finish()

        schema = vol.Schema({vol.Required(CONF_NAME, default=DEFAULT_NAME): str}).extend(
            _base_schema({}).schema
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_wallbox_count(self, user_input=None):
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_wallboxes()
        return self.async_show_form(
            step_id="wallbox_count", data_schema=_wallbox_count_schema(self._data)
        )

    async def async_step_wallboxes(self, user_input=None):
        count = int(self._data[CONF_WALLBOX_COUNT])
        if user_input is not None:
            self._data[CONF_WALLBOXES] = _collect_wallboxes(user_input, count)
            return await self._async_finish()
        return self.async_show_form(
            step_id="wallboxes", data_schema=_wallboxes_schema(count, [])
        )

    async def _async_finish(self):
        name = self._data.pop(CONF_NAME)
        await self.async_set_unique_id(f"{name}_{self._data[CONF_POWER_SENSOR]}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=name, data=self._data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return LastspitzeOptionsFlow()


class LastspitzeOptionsFlow(config_entries.OptionsFlow):
    """Gleicher 3-Schritt-Ablauf wie beim Setup, vorbefüllt mit den aktuellen Werten."""

    def __init__(self) -> None:
        self._data: dict = {}

    async def async_step_init(self, user_input=None):
        current = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            self._data.update(user_input)
            if self._data[CONF_ENABLE_WALLBOX]:
                return await self.async_step_wallbox_count()
            self._data[CONF_WALLBOXES] = []
            return self.async_create_entry(title="", data=self._data)

        return self.async_show_form(step_id="init", data_schema=_base_schema(current))

    async def async_step_wallbox_count(self, user_input=None):
        current = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_wallboxes()
        return self.async_show_form(
            step_id="wallbox_count", data_schema=_wallbox_count_schema(current)
        )

    async def async_step_wallboxes(self, user_input=None):
        current = {**self.config_entry.data, **self.config_entry.options}
        count = int(self._data[CONF_WALLBOX_COUNT])
        if user_input is not None:
            self._data[CONF_WALLBOXES] = _collect_wallboxes(user_input, count)
            return self.async_create_entry(title="", data=self._data)
        existing = current.get(CONF_WALLBOXES, [])
        return self.async_show_form(
            step_id="wallboxes", data_schema=_wallboxes_schema(count, existing)
        )
