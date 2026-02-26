"""Constants for the RemoteRelay integration."""

from __future__ import annotations

DOMAIN = "remoterelay"

ZEROCONF_SERVICE_TYPE = "_remoterelay._tcp.local."
DEFAULT_API_PORT = 49171
DEFAULT_POLL_INTERVAL_SECONDS = 15

CONF_DEVICE_ID = "device_id"
CONF_DISPLAY_NAME = "display_name"
CONF_ACCESS_TOKEN = "access_token"
CONF_TOKEN_EXPIRES_AT = "token_expires_at"
CONF_MAC_ADDRESSES = "mac_addresses"
CONF_BROADCAST_ADDRESS = "broadcast_address"
CONF_PROTO_VERSION = "proto_version"
CONF_API_BASE_URL = "api_base_url"

API_TIMEOUT_SECONDS = 5
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

# Button entities exposed for plug-and-play control on the HA Device page.
REMOTE_BUTTONS = (
    {"key": "home", "label": "Home", "icon": "mdi:home"},
    {"key": "back", "label": "Back", "icon": "mdi:arrow-left"},
    {"key": "info", "label": "Info", "icon": "mdi:information-outline"},
    {"key": "up", "label": "Up", "icon": "mdi:chevron-up"},
    {"key": "left", "label": "Left", "icon": "mdi:chevron-left"},
    {"key": "ok", "label": "OK", "icon": "mdi:check-circle-outline"},
    {"key": "right", "label": "Right", "icon": "mdi:chevron-right"},
    {"key": "down", "label": "Down", "icon": "mdi:chevron-down"},
    {"key": "play_pause", "label": "Play/Pause", "icon": "mdi:play-pause"},
    {"key": "next_track", "label": "Next", "icon": "mdi:skip-next"},
    {"key": "previous_track", "label": "Previous", "icon": "mdi:skip-previous"},
    {"key": "volume_up", "label": "Volume Up", "icon": "mdi:volume-plus"},
    {"key": "volume_down", "label": "Volume Down", "icon": "mdi:volume-minus"},
    {"key": "mute_toggle", "label": "Mute", "icon": "mdi:volume-mute"},
    {"key": "power_off", "label": "Power Off", "icon": "mdi:power"},
)
