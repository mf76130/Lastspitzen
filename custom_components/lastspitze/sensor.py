"""Sensor-Entities für die Lastspitze-Integration."""
from __future__ import annotations

import json

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    manager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            LastspitzeAktuellSensor(manager, entry),
            LastspitzeMonatMaxSensor(manager, entry),
            LastspitzeLetzterMonatSensor(manager, entry),
        ]
    )


class _BaseLastspitzeSensor(RestoreEntity, SensorEntity):
    _attr_native_unit_of_measurement = "kW"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 3

    def __init__(self, manager, entry: ConfigEntry) -> None:
        self.manager = manager
        self._entry = entry
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Lastspitze (custom)",
        }
        manager.register_sensor(self)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            if last.state not in ("unknown", "unavailable"):
                try:
                    self._restore(float(last.state))
                except ValueError:
                    pass
            self._restore_extra(last.attributes)

    def _restore(self, value: float) -> None:
        """In Unterklassen überschreiben."""

    def _restore_extra(self, attributes: dict) -> None:
        """Optional in Unterklassen überschreiben, für zusätzliche Attribute."""


class LastspitzeAktuellSensor(_BaseLastspitzeSensor):
    _attr_name = "Lastspitze aktuell"
    _attr_icon = "mdi:transmission-tower"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_aktuell"

    @property
    def native_value(self):
        return self.manager.current_kw

    @property
    def extra_state_attributes(self):
        # Nachverfolgung, welche Wallboxen die Integration selbst gedrosselt hat -
        # übersteht so auch einen HA-Neustart (via RestoreEntity).
        return {"throttled_wallboxes": json.dumps(self.manager._throttled_by_us)}

    def _restore(self, value: float) -> None:
        self.manager.current_kw = value

    def _restore_extra(self, attributes: dict) -> None:
        raw = attributes.get("throttled_wallboxes")
        if not raw:
            return
        try:
            data = json.loads(raw)
            self.manager._throttled_by_us.update({k: int(v) for k, v in data.items()})
        except (ValueError, TypeError):
            pass


class LastspitzeMonatMaxSensor(_BaseLastspitzeSensor):
    _attr_name = "Lastspitze Monat Max"
    _attr_icon = "mdi:arrow-up-bold"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_monat_max"

    @property
    def native_value(self):
        return self.manager.month_max_kw

    def _restore(self, value: float) -> None:
        self.manager.month_max_kw = value


class LastspitzeLetzterMonatSensor(_BaseLastspitzeSensor):
    _attr_name = "Lastspitze Letzter Monat"
    _attr_icon = "mdi:calendar-arrow-left"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_letzter_monat"

    @property
    def native_value(self):
        return self.manager.last_month_kw

    def _restore(self, value: float) -> None:
        self.manager.last_month_kw = value
