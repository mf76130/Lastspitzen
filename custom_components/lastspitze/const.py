"""Konstanten für die Lastspitze-Integration."""

DOMAIN = "lastspitze"

CONF_NAME = "name"
CONF_POWER_SENSOR = "power_sensor"
CONF_ENABLE_WALLBOX = "enable_wallbox_control"
CONF_WALLBOX_COUNT = "wallbox_count"
CONF_WALLBOXES = "wallboxes"
CONF_WB_AMP = "amp_entity"
CONF_WB_MAX_AMP = "max_amp_entity"
CONF_WB_POWER = "power_entity"
CONF_WB_STATUS = "status_entity"
CONF_ABOVE_THRESHOLD = "above_threshold_w"
CONF_ABOVE_DURATION = "above_duration_s"
CONF_BELOW_THRESHOLD = "below_threshold_w"
CONF_BELOW_DURATION = "below_duration_s"
CONF_MIN_AMP = "min_amp"
CONF_REDUCE_STEP = "reduce_step_a"
CONF_CALC_REDUCTION = "calc_reduction"
CONF_PHASES = "charging_phases"
CONF_VOLTAGE = "voltage_v"
CONF_TARGET_BUFFER = "target_buffer_w"
CONF_CHARGING_STATES = "charging_states"
CONF_IDLE_STATES = "idle_states"
CONF_IGNORE_KEYWORDS = "ignore_keywords"
CONF_NOTIFY_SERVICE = "notify_service"
CONF_NOTIFY_TARGET = "notify_target"

DEFAULT_NAME = "Lastspitze"
DEFAULT_ENABLE_WALLBOX = True
DEFAULT_WALLBOX_COUNT = 1
DEFAULT_ABOVE_THRESHOLD = 9000
DEFAULT_ABOVE_DURATION = 120
DEFAULT_BELOW_THRESHOLD = 8000
DEFAULT_BELOW_DURATION = 600
DEFAULT_MIN_AMP = 6
DEFAULT_REDUCE_STEP = 2
DEFAULT_CALC_REDUCTION = True
DEFAULT_PHASES = 3
DEFAULT_VOLTAGE = 230
# Abstand unter der Warnschwelle (W), auf den geregelt wird
DEFAULT_TARGET_BUFFER = 100
# Status-Werte (klein geschrieben, kommagetrennt), die "Wallbox lädt gerade" bedeuten
DEFAULT_CHARGING_STATES = "charging,laden,lädt,ladend,on,true,in use"
# Status-Werte, die sicher "lädt nicht" bedeuten. Alles Unbekannte wird als ladend behandelt (lieber drosseln als nichts tun).
DEFAULT_IDLE_STATES = "idle,sleep,off,standby,complete,completed,finished,waitcar,wait_car,disconnected,unplugged,not_charging,false,unavailable_car"
# Sensoren mit diesen Begriffen im Namen zählen nicht als "größter Verbraucher" (Summen-/Nennwerte)
DEFAULT_IGNORE_KEYWORDS = "gesamt,total,rated,nennleistung,alle phasen,alle_phasen,house load,house_load,hausverbrauch"

# Eine Wallbox gilt als "ladend", wenn ihr Leistungssensor mehr als diesen Wert (W) zeigt
MIN_ACTIVE_W = 300
DEFAULT_NOTIFY_SERVICE = "notify.pushover"

QUARTER_MINUTES = (0, 15, 30, 45)
