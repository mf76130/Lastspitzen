"""Konstanten für die Lastspitze-Integration."""

DOMAIN = "lastspitze"

CONF_NAME = "name"
CONF_POWER_SENSOR = "power_sensor"
CONF_WALLBOX_AMP = "wallbox_amp_entity"
CONF_WALLBOX_MAX_AMP = "wallbox_max_amp_entity"
CONF_ABOVE_THRESHOLD = "above_threshold_w"
CONF_ABOVE_DURATION = "above_duration_s"
CONF_BELOW_THRESHOLD = "below_threshold_w"
CONF_BELOW_DURATION = "below_duration_s"
CONF_MIN_AMP = "min_amp"
CONF_REDUCE_STEP = "reduce_step_a"
CONF_NOTIFY_SERVICE = "notify_service"
CONF_NOTIFY_TARGET = "notify_target"

DEFAULT_NAME = "Lastspitze"
DEFAULT_ABOVE_THRESHOLD = 9000
DEFAULT_ABOVE_DURATION = 120
DEFAULT_BELOW_THRESHOLD = 8000
DEFAULT_BELOW_DURATION = 600
DEFAULT_MIN_AMP = 6
DEFAULT_REDUCE_STEP = 2
DEFAULT_NOTIFY_SERVICE = "notify.pushover"

QUARTER_MINUTES = (0, 15, 30, 45)
