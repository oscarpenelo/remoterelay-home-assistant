"""Constants for the RemoteRelay integration."""

from __future__ import annotations

DOMAIN = "remoterelay"

ZEROCONF_SERVICE_TYPE = "_remoterelay._tcp.local."
DEFAULT_API_PORT = 49171
DEFAULT_POLL_INTERVAL_SECONDS = 5

CONF_DEVICE_ID = "device_id"
CONF_DISPLAY_NAME = "display_name"
CONF_ACCESS_TOKEN = "access_token"
CONF_INTEGRATION_INSTANCE_ID = "integration_instance_id"
CONF_TOKEN_EXPIRES_AT = "token_expires_at"
CONF_MAC_ADDRESSES = "mac_addresses"
CONF_INPUT_SOURCES = "input_sources"
CONF_SELECTED_SOURCE_ID = "selected_source_id"
CONF_BROADCAST_ADDRESS = "broadcast_address"
CONF_PROTO_VERSION = "proto_version"
CONF_API_BASE_URL = "api_base_url"

API_TIMEOUT_SECONDS = 10
API_HEADER_AUTHORIZATION = "Authorization"

REMOTE_NAV_KEYS = ("up", "down", "left", "right", "ok", "back", "home", "info")
REMOTE_DIRECT_COMMANDS = (
    "play_pause",
    "next_track",
    "previous_track",
    "volume_up",
    "volume_down",
    "mute_toggle",
    "power_off",
)

REMOTE_COMMAND_ALIASES: dict[str, str] = {
    "power_off": "power_toggle",
    "off": "power_toggle",
    "power": "power_toggle",
    "volume_up": "vol_up",
    "vol_up": "vol_up",
    "volume_down": "vol_down",
    "vol_down": "vol_down",
    "mute": "mute_toggle",
    "playpause": "play_pause",
    "play-pause": "play_pause",
    "next": "next_track",
    "previous": "previous_track",
    "prev": "previous_track",
    "enter": "ok",
    "select": "ok",
    "return": "back",
}

DEFAULT_REMOTE_KEY_LABELS: dict[str, str] = {
    "power_toggle": "Power",
    "home": "Home",
    "back": "Back",
    "previous_track": "Previous",
    "play_pause": "Play/Pause",
    "next_track": "Next",
    "info": "Info",
    "mute_toggle": "Mute",
    "ok": "OK",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "vol_up": "Volume Up",
    "vol_down": "Volume Down",
    "channel_up": "Channel Up",
    "channel_down": "Channel Down",
    "num_0": "0",
    "num_1": "1",
    "num_2": "2",
    "num_3": "3",
    "num_4": "4",
    "num_5": "5",
    "num_6": "6",
    "num_7": "7",
    "num_8": "8",
    "num_9": "9",
}

DEFAULT_REMOTE_KEY_ICONS: dict[str, str] = {
    "power_toggle": "mdi:power",
    "home": "mdi:home",
    "back": "mdi:arrow-left",
    "info": "mdi:information-outline",
    "up": "mdi:chevron-up",
    "left": "mdi:chevron-left",
    "ok": "mdi:check-circle-outline",
    "right": "mdi:chevron-right",
    "down": "mdi:chevron-down",
    "play_pause": "mdi:play-pause",
    "next_track": "mdi:skip-next",
    "previous_track": "mdi:skip-previous",
    "vol_up": "mdi:volume-plus",
    "vol_down": "mdi:volume-minus",
    "mute_toggle": "mdi:volume-mute",
    "channel_up": "mdi:chevron-up-circle-outline",
    "channel_down": "mdi:chevron-down-circle-outline",
}
