"""Lastspitze-Integration: Viertelstunden-Leistungstracking + Wallbox-Drosselung."""
from __future__ import annotations

import logging
import math
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
    CONF_ENABLE_WALLBOX,
    CONF_WALLBOXES,
    CONF_WB_AMP,
    CONF_WB_MAX_AMP,
    CONF_WB_POWER,
    CONF_WB_STATUS,
    CONF_ABOVE_THRESHOLD,
    CONF_ABOVE_DURATION,
    CONF_BELOW_THRESHOLD,
    CONF_BELOW_DURATION,
    CONF_MIN_AMP,
    CONF_REDUCE_STEP,
    CONF_CALC_REDUCTION,
    CONF_PHASES,
    CONF_VOLTAGE,
    CONF_TARGET_BUFFER,
    CONF_CHARGING_STATES,
    CONF_IDLE_STATES,
    CONF_IGNORE_KEYWORDS,
    CONF_NOTIFY_SERVICE,
    CONF_NOTIFY_TARGET,
    DEFAULT_ABOVE_THRESHOLD,
    DEFAULT_ABOVE_DURATION,
    DEFAULT_BELOW_THRESHOLD,
    DEFAULT_BELOW_DURATION,
    DEFAULT_MIN_AMP,
    DEFAULT_REDUCE_STEP,
    DEFAULT_CALC_REDUCTION,
    DEFAULT_PHASES,
    DEFAULT_VOLTAGE,
    DEFAULT_TARGET_BUFFER,
    DEFAULT_CHARGING_STATES,
    DEFAULT_IDLE_STATES,
    DEFAULT_IGNORE_KEYWORDS,
    MIN_ACTIVE_W,
    DEFAULT_NOTIFY_SERVICE,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor"]

# Mindestens so viele Sekunden einer Viertelstunde müssen erfasst sein (50 %), sonst wird der Wert verworfen
MIN_QUARTER_COVERAGE_S = 450



class LastspitzeManager:
    """Verwaltet Viertelstunden-Integration, Monatsmaximum und Wallbox-Drosselung."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        opts = {**entry.data, **entry.options}

        self.power_sensor = opts[CONF_POWER_SENSOR]
        self.enable_wallbox = bool(opts.get(CONF_ENABLE_WALLBOX, True))
        self.wallboxes = opts.get(CONF_WALLBOXES, [])  # list of {"amp_entity", "max_amp_entity"}
        self.above_threshold = float(opts.get(CONF_ABOVE_THRESHOLD, DEFAULT_ABOVE_THRESHOLD))
        self.above_duration = int(opts.get(CONF_ABOVE_DURATION, DEFAULT_ABOVE_DURATION))
        self.below_threshold = float(opts.get(CONF_BELOW_THRESHOLD, DEFAULT_BELOW_THRESHOLD))
        self.below_duration = int(opts.get(CONF_BELOW_DURATION, DEFAULT_BELOW_DURATION))
        self.min_amp = int(opts.get(CONF_MIN_AMP, DEFAULT_MIN_AMP))
        self.reduce_step = int(opts.get(CONF_REDUCE_STEP, DEFAULT_REDUCE_STEP))
        self.calc_reduction = bool(opts.get(CONF_CALC_REDUCTION, DEFAULT_CALC_REDUCTION))
        self.phases = int(opts.get(CONF_PHASES, DEFAULT_PHASES))
        self.voltage = float(opts.get(CONF_VOLTAGE, DEFAULT_VOLTAGE))
        self.target_buffer = float(opts.get(CONF_TARGET_BUFFER, DEFAULT_TARGET_BUFFER))
        self.charging_states = self._split(opts.get(CONF_CHARGING_STATES, DEFAULT_CHARGING_STATES))
        self.idle_states = self._split(opts.get(CONF_IDLE_STATES, DEFAULT_IDLE_STATES))
        self.ignore_keywords = tuple(
            self._split(opts.get(CONF_IGNORE_KEYWORDS, DEFAULT_IGNORE_KEYWORDS))
        )
        self.notify_service = opts.get(CONF_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE)
        self.notify_target = opts.get(CONF_NOTIFY_TARGET, "")

        # Viertelstunden-Integration (Trapez-Näherung aus dem Leistungssensor)
        self._accumulated_wh = 0.0
        self._observed_s = 0.0  # Sekunden der laufenden Viertelstunde, die wirklich erfasst wurden
        self._last_sample_time = None
        self._last_power_w = 0.0
        self.quarter_coverage = None  # Anteil (0..1) der zuletzt ausgewerteten Viertelstunde, der erfasst war

        # Debounce-Zustände für "for:"-artiges Verhalten
        self._above_since = None
        self._below_since = None

        # öffentlicher Zustand, von den Sensor-Entities gelesen
        self.current_kw = 0.0
        self.month_max_kw = 0.0
        self.last_month_kw = 0.0

        self._unsub = []
        self.sensors = []

        # merkt sich, welche Wallboxen die Integration selbst gedrosselt hat
        # (amp_entity -> zuletzt von UNS gesetzter Wert). Nur diese werden
        # später wieder automatisch hochgesetzt.
        self._throttled_by_us: dict[str, int] = {}

    def register_sensor(self, sensor) -> None:
        self.sensors.append(sensor)

    @staticmethod
    def _split(value) -> set:
        """Kommagetrennten Text in eine Menge kleingeschriebener Begriffe umwandeln."""
        return {v.strip().lower() for v in str(value or "").split(",") if v.strip()}

    @staticmethod
    def _quarter_start(moment) -> str:
        """Beginn der Viertelstunde (UTC, ISO) zu einem Zeitpunkt."""
        floored = moment.replace(minute=(moment.minute // 15) * 15, second=0, microsecond=0)
        return floored.isoformat()

    def accumulator_snapshot(self) -> dict:
        """Laufende Viertelstunde, damit sie Neustarts/Neuladen übersteht."""
        return {
            "quarter_start": self._quarter_start(dt_util.utcnow()),
            "accumulated_wh": self._accumulated_wh,
            "observed_s": self._observed_s,
        }

    def restore_accumulator(self, data: dict) -> None:
        """Gespeicherte Viertelstunde übernehmen - nur, wenn sie noch die aktuelle ist."""
        try:
            if data.get("quarter_start") != self._quarter_start(dt_util.utcnow()):
                return
            self._accumulated_wh = float(data.get("accumulated_wh", 0.0))
            self._observed_s = float(data.get("observed_s", 0.0))
        except (ValueError, TypeError, AttributeError):
            return
        _LOGGER.info(
            "Lastspitze: laufende Viertelstunde wiederhergestellt (%.0f s erfasst).", self._observed_s
        )

    async def async_setup(self) -> None:
        self._last_sample_time = dt_util.utcnow()
        # Startwert für die Trapezregel, sonst wäre das erste Intervall zu klein
        start_state = self.hass.states.get(self.power_sensor)
        if start_state is not None:
            try:
                self._last_power_w = max(0.0, float(start_state.state))
            except (ValueError, TypeError):
                pass
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
        amp_entities = [wb[CONF_WB_AMP] for wb in self.wallboxes]
        if amp_entities:
            self._unsub.append(
                async_track_state_change_event(
                    self.hass, amp_entities, self._async_wallbox_amp_changed
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
            dt_s = (now - self._last_sample_time).total_seconds()
            # Lücken (Sensor ausgefallen, Neustart) nicht hochrechnen
            if 0 < dt_s <= 60:
                avg_w = (power_w + self._last_power_w) / 2
                self._accumulated_wh += avg_w * dt_s / 3600
                self._observed_s += dt_s
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
    def _async_wallbox_amp_changed(self, event) -> None:
        """Erkennt manuelle Eingriffe: weicht der neue Wert von dem ab, den WIR
        zuletzt gesetzt haben, hat der Nutzer selbst geregelt -> nicht mehr
        automatisch anfassen, bis die nächste eigene Drosselung stattfindet."""
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        if entity_id not in self._throttled_by_us or new_state is None:
            return
        try:
            new_value = int(float(new_state.state))
        except (ValueError, TypeError):
            return
        if new_value != self._throttled_by_us[entity_id]:
            _LOGGER.info(
                "Lastspitze: %s wurde manuell auf %s A geändert, wird nicht mehr automatisch zurückgesetzt.",
                entity_id, new_value,
            )
            self._throttled_by_us.pop(entity_id, None)
            self._update_sensors()

    @callback
    def _async_quarter_boundary(self, now) -> None:
        """Wird bei :00/:15/:30/:45 aufgerufen - entspricht utility_meter cycle: quarter-hourly."""
        self._async_sample(now)
        observed_s = self._observed_s
        self.quarter_coverage = round(min(1.0, observed_s / 900), 2)
        if observed_s >= MIN_QUARTER_COVERAGE_S:
            # Mittelwert über die tatsächlich erfasste Zeit (bei Lücken nicht zu klein)
            kw = (self._accumulated_wh / 1000) / (observed_s / 3600)
            self.current_kw = round(kw, 3)
            if self.current_kw > self.month_max_kw:
                self.month_max_kw = self.current_kw
        else:
            _LOGGER.warning(
                "Lastspitze: Viertelstunde nur %.0f s erfasst (Neustart?), Wert wird nicht übernommen.",
                observed_s,
            )
        self._accumulated_wh = 0.0
        self._observed_s = 0.0
        self._update_sensors()

    @callback
    def _async_month_boundary(self, now) -> None:
        if now.day != 1:
            return
        self.last_month_kw = self.month_max_kw
        self.month_max_kw = 0.0
        self._update_sensors()

    def _check_warning_throttle(self) -> None:
        if not self.enable_wallbox or not self.wallboxes:
            return
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
                self.hass.async_create_task(self._async_restore(power_w))
                self._below_since = None
        else:
            self._below_since = None

    def _read_power_w(self, entity_id: str | None) -> float | None:
        """Leistungssensor einer Wallbox in W lesen (kW wird umgerechnet)."""
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        try:
            value = float(state.state)
        except (ValueError, TypeError):
            return None
        if state.attributes.get("unit_of_measurement") == "kW":
            value *= 1000
        return value

    def _read_status(self, entity_id: str | None) -> str | None:
        """Status-Entity einer Wallbox lesen (klein geschrieben) oder None, wenn unbekannt."""
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable", ""):
            return None
        return state.state.strip().lower()

    def _read_wallboxes(self) -> list[dict]:
        """Zustand aller Wallboxen erfassen (Strom, Max, Leistung, lädt ja/nein)."""
        wpa = self.voltage * self.phases  # Watt pro Ampere
        wbs = []
        for wb in self.wallboxes:
            amp_entity = wb[CONF_WB_AMP]
            amp_state = self.hass.states.get(amp_entity)
            try:
                current = int(float(amp_state.state))
            except (ValueError, AttributeError, TypeError):
                continue
            max_state = self.hass.states.get(wb.get(CONF_WB_MAX_AMP) or "")
            try:
                max_amp = int(float(max_state.state))
            except (ValueError, AttributeError, TypeError):
                max_amp = None
            p = self._read_power_w(wb.get(CONF_WB_POWER))
            has_sensor = p is not None
            status = self._read_status(wb.get(CONF_WB_STATUS))
            status_unknown = False
            if status is not None:
                # Status hat Vorrang: der Leistungssensor kann verzögert melden
                if status in self.charging_states:
                    charging = True
                elif status in self.idle_states:
                    charging = False
                else:
                    charging = True  # unbekannter Status: lieber drosseln als nichts tun
                    status_unknown = True
                if charging and has_sensor and p > MIN_ACTIVE_W:
                    eff = min(float(current), p / wpa)
                else:
                    eff = float(current)  # lädt laut Status, Leistung noch nicht sichtbar
            else:
                charging = (p > MIN_ACTIVE_W) if has_sensor else True
                # tatsächlich gezogener Strom (nie mehr als eingestellt)
                eff = min(float(current), p / wpa) if has_sensor else float(current)
            wbs.append(
                {"entity": amp_entity, "current": current, "max_amp": max_amp, "power": p,
                 "charging": charging, "eff": eff, "cut": 0.0, "status": status,
                 "status_unknown": status_unknown}
            )
        return wbs

    async def _async_throttle(self, power_w: float) -> None:
        top_device = self._find_top_consumer()
        wpa = self.voltage * self.phases  # Watt pro Ampere
        wbs = self._read_wallboxes()
        for w in wbs:
            w["cap"] = (
                max(0.0, (w["eff"] - self.min_amp) * wpa)
                if (w["charging"] and w["current"] > self.min_amp) else 0.0
            )

        # Nötige Entlastung bis knapp unter die Warnschwelle, gleichmäßig auf ladende Wallboxen verteilt
        if self.calc_reduction:
            remaining = max(0.0, power_w - (self.above_threshold - self.target_buffer))
            open_wbs = [w for w in wbs if w["cap"] > 0]
            while open_wbs and remaining > 0.5:
                share = remaining / len(open_wbs)
                capped = [w for w in open_wbs if w["cap"] - w["cut"] < share]
                if not capped:
                    for w in open_wbs:
                        w["cut"] += share
                    break
                for w in capped:
                    take = w["cap"] - w["cut"]
                    w["cut"] += take
                    remaining -= take
                    open_wbs.remove(w)

        changes = []
        expected_w = 0.0
        for w in wbs:
            entity, current = w["entity"], w["current"]
            if w["status_unknown"]:
                changes.append(
                    f"{entity}: Status „{w['status']}“ unbekannt, wird als ladend behandelt "
                    "(Status-Werte in der Konfiguration ergänzen)"
                )
            if not w["charging"]:
                if w["status"] is not None:
                    reason = f"Status: {w['status']}"
                else:
                    reason = f"{w['power']:.0f} W"
                changes.append(f"{entity}: lädt nicht ({reason}), unverändert")
                continue
            if current <= self.min_amp:
                changes.append(f"{entity}: bereits am Minimum ({self.min_amp} A)")
                continue

            if self.calc_reduction:
                if w["cut"] <= 0:
                    continue
                new_amp = math.floor((w["eff"] * wpa - w["cut"]) / wpa + 1e-9)
            else:
                new_amp = current - self.reduce_step
            new_amp = max(self.min_amp, min(new_amp, current - 1))

            est_w = max(0.0, (w["eff"] - new_amp) * wpa)
            expected_w += est_w
            self._throttled_by_us[entity] = new_amp  # vor dem Setzen, damit es nicht als manuell gilt
            await self.hass.services.async_call(
                "number", "set_value",
                {"entity_id": entity, "value": new_amp},
                blocking=True,
            )
            changes.append(f"{entity}: {current} A → {new_amp} A (≈ −{est_w:.0f} W)")
        self._update_sensors()

        message = (
            f"Gesamtbezug seit {self.above_duration // 60} Min über "
            f"{self.above_threshold / 1000:.1f} kW ({power_w:.0f} W).\n"
            f"Größter Verbraucher gerade: {top_device}.\n"
            + "\n".join(changes)
        )
        if expected_w > 0:
            message += f"\nErwartete Entlastung ≈ {expected_w:.0f} W (Ziel < {self.above_threshold:.0f} W)."
        if expected_w < power_w - self.above_threshold:
            message += "\nHinweis: Die Wallboxen allein reichen rechnerisch nicht, um unter den Zielwert zu kommen."
        await self._notify("⚠️ Lastspitze über Schwellwert", message)

    async def _async_restore(self, power_w: float) -> None:
        """Ladestrom schrittweise wieder erhöhen, solange der Bezug unter der Warnschwelle bleibt."""
        wpa = self.voltage * self.phases
        wbs = [w for w in self._read_wallboxes() if w["entity"] in self._throttled_by_us]
        if not wbs:
            return

        changes = []
        # Nicht ladende Wallboxen belasten das Netz nicht -> direkt auf Maximum zurück
        charging = []
        for w in wbs:
            if not w["charging"] and w["max_amp"] is not None:
                if w["current"] < w["max_amp"]:
                    await self.hass.services.async_call(
                        "number", "set_value",
                        {"entity_id": w["entity"], "value": w["max_amp"]},
                        blocking=True,
                    )
                    changes.append(f"{w['entity']}: wieder auf Maximum ({w['max_amp']} A)")
                self._throttled_by_us.pop(w["entity"], None)
            elif w["max_amp"] is not None:
                charging.append(w)
            else:
                continue  # Maximum unbekannt -> nicht anfassen

        # Spielraum bis knapp unter die Warnschwelle in ganze Ampere umrechnen
        headroom_w = (self.above_threshold - self.target_buffer) - power_w
        budget_a = int(max(0.0, headroom_w) // wpa)
        raised_w = 0.0
        # reihum je 1 A an die ladenden Wallboxen vergeben (gleichmäßig)
        while budget_a > 0:
            candidates = [w for w in charging if w["current"] < w["max_amp"]]
            if not candidates:
                break
            for w in candidates:
                if budget_a <= 0:
                    break
                w["current"] += 1
                w["raised"] = w.get("raised", 0) + 1
                budget_a -= 1

        for w in charging:
            entity = w["entity"]
            orig = self._throttled_by_us.get(entity)
            if w.get("raised"):
                new_amp = w["current"]
                self._throttled_by_us[entity] = new_amp  # vor dem Setzen, damit es nicht als manuell gilt
                await self.hass.services.async_call(
                    "number", "set_value",
                    {"entity_id": entity, "value": new_amp},
                    blocking=True,
                )
                raised_w += w["raised"] * wpa
                changes.append(f"{entity}: {new_amp - w['raised']} A → {new_amp} A")
                if new_amp >= w["max_amp"]:
                    self._throttled_by_us.pop(entity, None)  # wieder am Maximum
            elif w["current"] >= w["max_amp"]:
                self._throttled_by_us.pop(entity, None)  # schon am Maximum

        self._update_sensors()
        if not changes:
            return  # kein Spielraum für +1 A: nichts ändern, nichts melden

        still_throttled = any(w["entity"] in self._throttled_by_us for w in wbs)
        if still_throttled:
            title = "↗️ Ladestrom schrittweise erhöht"
            tail = f"\nNetzbezug {power_w:.0f} W, Spielraum bis Warnschwelle ≈ {max(0.0, headroom_w):.0f} W."
        else:
            title = "✅ Lastspitze vorbei"
            tail = ""
        await self._notify(
            title,
            f"Verbrauch seit {self.below_duration // 60} Min unter "
            f"{self.below_threshold / 1000:.1f} kW.\n" + "\n".join(changes) + tail,
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
            label = f"{state.name} {state.entity_id}".lower()
            if any(k in label for k in self.ignore_keywords):
                continue  # Summen- und Nennwerte sind keine echten Verbraucher
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


def _migrate_legacy_wallbox(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Alte Einzel-Wallbox-Konfiguration (vor 1.1.0) automatisch in die neue Listenform überführen."""
    if CONF_WALLBOXES in entry.data:
        return  # bereits im neuen Format
    legacy_amp = entry.data.get("wallbox_amp_entity")
    legacy_max = entry.data.get("wallbox_max_amp_entity")
    if not legacy_amp or not legacy_max:
        return  # nichts zu migrieren (z.B. Neuinstallation)

    new_data = dict(entry.data)
    new_data.pop("wallbox_amp_entity", None)
    new_data.pop("wallbox_max_amp_entity", None)
    new_data[CONF_ENABLE_WALLBOX] = True
    new_data[CONF_WALLBOXES] = [{CONF_WB_AMP: legacy_amp, CONF_WB_MAX_AMP: legacy_max}]
    hass.config_entries.async_update_entry(entry, data=new_data)
    _LOGGER.info("Lastspitze: bestehende Wallbox-Konfiguration automatisch auf neues Format migriert.")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _migrate_legacy_wallbox(hass, entry)
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
