"""Config Flow für die Lastspitze-Integration."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
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
    CONF_WALLBOX_AMP,
    CONF_WALLBOX_MAX_AMP,
    CONF_ABOVE_THRESHOLD,
    CONF_ABOVE_DURATION,
    CONF_BELOW_THRESHOLD,
    CONF_BELOW_DURATION,
    CONF_MIN_AMP,
    CONF_REDUCE_STEP,
    CONF_NOTIFY_SERVICE,
    CONF_NOTIFY_TARGET,
    DEFAULT_NAME,
    DEFAULT_ABOVE_THRESHOLD,
    DEFAULT_ABOVE_DURATION,
    DEFAULT_BELOW_THRESHOLD,
    DEFAULT_BELOW_DURATION,
    DEFAULT_MIN_AMP,
    DEFAULT_REDUCE_STEP,
    DEFAULT_NOTIFY_SERVICE,
)


def _entities_schema(defaults: dict) -> vol.Schema:
    """Schema für Entity-Auswahl + Schwellwerte, wird in Setup und Options genutzt."""
    return vol.Schema(
        {
            vol.Required(
                CONF_POWER_SENSOR, default=defaults.get(CONF_POWER_SENSOR)
            ): EntitySelector(EntitySelectorConfig(domain="sensor", device_class="power")),
            vol.Required(
                CONF_WALLBOX_AMP, default=defaults.get(CONF_WALLBOX_AMP)
            ): EntitySelector(EntitySelectorConfig(domain="number")),
            vol.Required(
                CONF_WALLBOX_MAX_AMP, default=defaults.get(CONF_WALLBOX_MAX_AMP)
            ): EntitySelector(EntitySelectorConfig(domain="number")),
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
                CONF_MIN_AMP, default=defaults.get(CONF_MIN_AMP, DEFAULT_MIN_AMP)
            ): NumberSelector(
                NumberSelectorConfig(min=6, max=32, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="A")
            ),
            vol.Optional(
                CONF_REDUCE_STEP, default=defaults.get(CONF_REDUCE_STEP, DEFAULT_REDUCE_STEP)
            ): NumberSelector(
                NumberSelectorConfig(min=1, max=16, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="A")
            ),
            vol.Optional(
                CONF_NOTIFY_SERVICE,
                default=defaults.get(CONF_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE),
            ): TextSelector(),
            vol.Optional(
                CONF_NOTIFY_TARGET, default=defaults.get(CONF_NOTIFY_TARGET, "")
            ): TextSelector(),
        }
    )


class LastspitzeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Setup-Assistent: fragt Leistungssensor, Wallbox-Entities und Schwellwerte ab."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input.pop(CONF_NAME, DEFAULT_NAME)
            await self.async_set_unique_id(f"{name}_{user_input[CONF_POWER_SENSOR]}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=name, data=user_input)

        schema = vol.Schema({vol.Required(CONF_NAME, default=DEFAULT_NAME): str}).extend(
            _entities_schema({}).schema
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return LastspitzeOptionsFlow(config_entry)


class LastspitzeOptionsFlow(config_entries.OptionsFlow):
    """Erlaubt nachträgliches Ändern von Entities/Schwellwerten ohne Neu-Setup."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        defaults = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=_entities_schema(defaults))
