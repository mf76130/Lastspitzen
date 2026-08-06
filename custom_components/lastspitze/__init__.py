"""Lastspitze-Integration: Viertelstunden-Leistungstracking + Wallbox-Drosselung."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_time_interval,
    async_track_time_change,
    async_track_state_change_event,
)
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    QUARTER_MINUTES,
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
    DEFAULT_ABOVE_THRESHOLD,
    DEFAULT_ABOVE_DURATION,
    DEFAULT_BELOW_THRESHOLD,
    DEFAULT_BELOW_DURATION,
    DEFAULT_MIN_AMP,
    DEFAULT_REDUCE_STEP,
    DEFAULT_NOTIFY_SERVICE,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor"]


class LastspitzeManager:
    """Verwaltet Viertelstunden-Integration, Monatsmaximum und Wallbox-Drosselung."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        opts = {**entry.data, **entry.options}

        self.power_sensor = opts[CONF_POWER_SENSOR]
        self.amp_entity = opts[CONF_WALLBOX_AMP]
        self.max_amp_entity = opts[CONF_WALLBOX_MAX_AMP]
        self.above_threshold = float(opts.get(CONF_ABOVE_THRESHOLD, DEFAULT_ABOVE_THRESHOLD))
        self.above_duration = int(opts.get(CONF_ABOVE_DURATION, DEFAULT_ABOVE_DURATION))
        self.below_threshold = float(opts.get(CONF_BELOW_THRESHOLD, DEFAULT_BELOW_THRESHOLD))
        self.below_duration = int(opts.get(CONF_BELOW_DURATION, DEFAULT_BELOW_DURATION))
        self.min_amp = int(opts.get(CONF_MIN_AMP, DEFAULT_MIN_AMP))
        self.reduce_step = int(opts.get(CONF_REDUCE_STEP, DEFAULT_REDUCE_STEP))
        self.notify_service = opts.get(CONF_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE)
        self.notify_target = opts.get(CONF_NOTIFY_TARGET, "")

        # Viertelstunden-Integration (Trapez-Näherung aus dem Leistungssensor)
        self._accumulated_wh = 0.0
        self._last_sample_time = None
        self._last_power_w = 0.0

        # Debounce-Zustände für "for:"-artiges Verhalten
        self._above_since = None
        self._below_since = None

        # öffentlicher Zustand, von den Sensor-Entities gelesen
        self.current_kw = 0.0
        self.month_max_kw = 0.0
        self.last_month_kw = 0.0

        self._unsub = []
        self.sensors = []

    def register_sensor(self, sensor) -> None:
        self.sensors.append(sensor)

    async def async_setup(self) -> None:
        self._last_sample_time = dt_util.utcnow()
        self._unsub.append(
            async_track_time_interval(self.hass, self._async_sample, timedelta(seconds=10))
        )
        self._unsub.append(
            async_track_time_change(
                self.hass, self._async_quarter_boundary, minute=list(QUARTER_MINUTES), second=1
            )
        )
        self._unsub.append(
            async_track_time_change(
                self.hass, self._async_month_boundary, hour=0, minute=0, second=5
            )
        )
        self._unsub.append(
            async_track_state_change_event(
                self.hass, [self.power_sensor], self._async_power_changed
            )
        )

    async def async_unload(self) -> None:
        for unsub in self._unsub:
            unsub()
        self._unsub = []

    def _update_sensors(self) -> None:
        for sensor in self.sensors:
            sensor.async_write_ha_state()

    @callback
    def _async_sample(self, now) -> None:
        """Leistung seit letztem Sample per Trapezregel aufintegrieren (-> Wh)."""
        state = self.hass.states.get(self.power_sensor)
        if state is None or state.state in ("unknown", "unavailable"):
            return
        try:
            power_w = max(0.0, float(state.state))  # Einspeisung (negativ) zählt nicht als Bezug
        except ValueError:
            return
        now = dt_util.utcnow()
        if self._last_sample_time is not None:
            dt_hours = (now - self._last_sample_time).total_seconds() / 3600
            avg_w = (power_w + self._last_power_w) / 2
            self._accumulated_wh += avg_w * dt_hours
        self._last_sample_time = now
        self._last_power_w = power_w

    @callback
    def _async_power_changed(self, event) -> None:
        new_state = event.data.get("new_state")
        if new_state is not None:
            try:
                self._last_power_w = max(0.0, float(new_state.state))
            except ValueError:
                pass
        self._check_warning_throttle()

    @callback
    def _async_quarter_boundary(self, now) -> None:
        """Wird bei :00/:15/:30/:45 aufgerufen - entspricht utility_meter cycle: quarter-hourly."""
        self._async_sample(now)
        kwh = self._accumulated_wh / 1000
        self.current_kw = round(kwh * 4, 3)
        self._accumulated_wh = 0.0
        if self.current_kw > self.month_max_kw:
            self.month_max_kw = self.current_kw
        self._update_sensors()

    @callback
    def _async_month_boundary(self, now) -> None:
        if now.day != 1:
            return
        self.last_month_kw = self.month_max_kw
        self.month_max_kw = 0.0
        self._update_sensors()

    def _check_warning_throttle(self) -> None:
        state = self.hass.states.get(self.power_sensor)
        if state is None:
            return
        try:
            power_w = max(0.0, float(state.state))  # Einspeisung (negativ) zählt nicht als Bezug
        except ValueError:
            return

        now = dt_util.utcnow()

        if power_w > self.above_threshold:
            if self._above_since is None:
                self._above_since = now
            elif (now - self._above_since).total_seconds() >= self.above_duration:
                self.hass.async_create_task(self._async_throttle(power_w))
                self._above_since = None  # erst nach Abfallen unter Schwelle neu bewaffnen
        else:
            self._above_since = None

        if power_w < self.below_threshold:
            if self._below_since is None:
                self._below_since = now
            elif (now - self._below_since).total_seconds() >= self.below_duration:
                self.hass.async_create_task(self._async_restore())
                self._below_since = None
        else:
            self._below_since = None

    async def _async_throttle(self, power_w: float) -> None:
        top_device = self._find_top_consumer()
        amp_state = self.hass.states.get(self.amp_entity)
        try:
            current_amp = int(float(amp_state.state))
        except (ValueError, AttributeError, TypeError):
            current_amp = self.min_amp
        new_amp = max(self.min_amp, current_amp - self.reduce_step)

        message = (
            f"Gesamtbezug seit {self.above_duration // 60} Min über "
            f"{self.above_threshold / 1000:.1f} kW ({power_w:.0f} W).\n"
            f"Größter Verbraucher gerade: {top_device}.\n"
        )
        if current_amp > self.min_amp:
            message += f"Ladestrom Auto wird von {current_amp} A auf {new_amp} A reduziert."
        else:
            message += (
                f"Auto lädt bereits mit Minimalstrom ({self.min_amp} A), "
                "Lastspitze bleibt eventuell bestehen."
            )

        await self._notify("⚠️ Lastspitze über Schwellwert", message)

        if current_amp > self.min_amp:
            await self.hass.services.async_call(
                "number", "set_value",
                {"entity_id": self.amp_entity, "value": new_amp},
                blocking=True,
            )

    async def _async_restore(self) -> None:
        amp_state = self.hass.states.get(self.amp_entity)
        max_state = self.hass.states.get(self.max_amp_entity)
        try:
            current_amp = int(float(amp_state.state))
            max_amp = int(float(max_state.state))
        except (ValueError, AttributeError, TypeError):
            return
        if current_amp < max_amp:
            await self.hass.services.async_call(
                "number", "set_value",
                {"entity_id": self.amp_entity, "value": max_amp},
                blocking=True,
            )
            await self._notify(
                "✅ Lastspitze vorbei",
                f"Verbrauch seit {self.below_duration // 60} Min unter "
                f"{self.below_threshold / 1000:.1f} kW – Ladestrom wieder auf Maximum ({max_amp} A) gesetzt.",
            )

    def _find_top_consumer(self) -> str:
        best_name, best_val = "unbekannt", -1.0
        for state in self.hass.states.async_all("sensor"):
            if state.entity_id == self.power_sensor:
                continue
            uom = state.attributes.get("unit_of_measurement")
            dclass = state.attributes.get("device_class")
            if uom != "W" and dclass != "power":
                continue
            try:
                val = float(state.state)
            except ValueError:
                continue
            if val > best_val:
                best_val = val
                best_name = f"{state.name} ({val:.0f} W)"
        return best_name

    async def _notify(self, title: str, message: str) -> None:
        if not self.notify_service:
            return
        domain, _, service = self.notify_service.partition(".")
        data = {"title": title, "message": message}
        if self.notify_target:
            data["target"] = self.notify_target
        try:
            await self.hass.services.async_call(domain or "notify", service or self.notify_service, data)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Konnte Benachrichtigung nicht senden: %s", err)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager = LastspitzeManager(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await manager.async_setup()
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager: LastspitzeManager = hass.data[DOMAIN][entry.entry_id]
    await manager.async_unload()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
