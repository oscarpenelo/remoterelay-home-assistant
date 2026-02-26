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
