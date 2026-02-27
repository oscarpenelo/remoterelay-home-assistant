"""Config flow for RemoteRelay."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RemoteRelayLocalApiClient, RemoteRelayPairingError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_API_BASE_URL,
    CONF_DEVICE_ID,
    CONF_DISPLAY_NAME,
    CONF_INPUT_SOURCES,
    CONF_MAC_ADDRESSES,
    CONF_PROTO_VERSION,
    CONF_SELECTED_SOURCE_ID,
    DEFAULT_API_PORT,
    DOMAIN,
)

CONF_PAIRING_CODE = "pairing_code"


class RemoteRelayConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RemoteRelay."""

    VERSION = 1

    def __init__(self) -> None:
        self._pending_host: str | None = None
        self._pending_port: int = DEFAULT_API_PORT
        self._discovered_device_id: str | None = None
        self._discovered_display_name: str | None = None
        self._discovered_proto: str = "1"

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Zeroconf-first entry point."""
        if self._pending_host:
            return await self.async_step_pair()

        return self.async_show_menu(
            step_id="user",
            menu_options=["wait_for_discovery", "manual"],
        )

    async def async_step_wait_for_discovery(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Explain that zeroconf discovery is the preferred flow."""
        return self.async_abort(reason="wait_for_discovery")

    async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manual setup fallback if zeroconf discovery is not available."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._pending_host = str(user_input[CONF_HOST]).strip()
            self._pending_port = int(user_input[CONF_PORT])
            self._discovered_display_name = str(user_input.get(CONF_NAME) or "RemoteRelay").strip()
            return await self.async_step_pair()

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_API_PORT): int,
                vol.Optional(CONF_NAME, default="RemoteRelay"): str,
            }
        )
        return self.async_show_form(step_id="manual", data_schema=schema, errors=errors)

    async def async_step_zeroconf(self, discovery_info: Any) -> FlowResult:
        """Handle zeroconf discovery."""
        txt = discovery_info.properties or {}

        device_id = self._txt_get(txt, "device_id")
        if not device_id:
            return self.async_abort(reason="not_supported")

        self._discovered_device_id = device_id
        self._discovered_display_name = self._txt_get(txt, "display_name") or discovery_info.name.rstrip(".")
        self._discovered_proto = self._txt_get(txt, "proto") or "1"

        await self.async_set_unique_id(device_id)
        self._abort_if_unique_id_configured(
            updates={
                CONF_HOST: str(getattr(discovery_info, "host", getattr(discovery_info, "hostname", ""))),
                CONF_PORT: int(getattr(discovery_info, "port", DEFAULT_API_PORT)),
            }
        )

        host = getattr(discovery_info, "host", None)
        if host is None and getattr(discovery_info, "ip_address", None) is not None:
            host = str(discovery_info.ip_address)
        if not host:
            return self.async_abort(reason="cannot_connect")

        self._pending_host = str(host)
        self._pending_port = int(getattr(discovery_info, "port", DEFAULT_API_PORT))

        return await self.async_step_pair()

    async def async_step_pair(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Exchange local pairing code for a token."""
        errors: dict[str, str] = {}

        if not self._pending_host:
            return await self.async_step_user()

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            base_url = f"http://{self._pending_host}:{self._pending_port}"
            api = RemoteRelayLocalApiClient(session=session, base_url=base_url)
            try:
                await api.async_health()
                paired = await api.async_exchange_pairing_code(
                    pairing_code=str(user_input[CONF_PAIRING_CODE]).strip(),
                    integration_instance_id=str(uuid4()),
                )
            except RemoteRelayPairingError:
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                device = paired.get("device", {})
                device_id = str(device.get("deviceId") or self._discovered_device_id or uuid4())
                current_unique_id = getattr(self, "unique_id", None)
                if current_unique_id is None:
                    await self.async_set_unique_id(device_id)
                elif str(current_unique_id) != device_id:
                    return self.async_abort(reason="already_configured")
                self._abort_if_unique_id_configured()

                title = str(device.get("displayName") or self._discovered_display_name or "RemoteRelay")
                data = {
                    CONF_API_BASE_URL: base_url,
                    CONF_ACCESS_TOKEN: paired.get("accessToken"),
                    CONF_DEVICE_ID: device_id,
                    CONF_DISPLAY_NAME: title,
                    CONF_MAC_ADDRESSES: [m.get("value") for m in device.get("macAddresses", []) if isinstance(m, dict)],
                    CONF_INPUT_SOURCES: self._normalize_profile_sources(device.get("inputSources")),
                    CONF_SELECTED_SOURCE_ID: str(device.get("selectedSourceId") or "").strip(),
                    CONF_PROTO_VERSION: str(device.get("protoVersion") or self._discovered_proto or "1"),
                    CONF_HOST: self._pending_host,
                    CONF_PORT: self._pending_port,
                }
                return self.async_create_entry(title=title, data=data)

        schema = vol.Schema({vol.Required(CONF_PAIRING_CODE): str})
        placeholders = {
            "host": self._pending_host,
            "port": str(self._pending_port),
            "name": self._discovered_display_name or "RemoteRelay",
        }
        return self.async_show_form(
            step_id="pair",
            data_schema=schema,
            errors=errors,
            description_placeholders=placeholders,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Return options flow (placeholder for future settings)."""
        return RemoteRelayOptionsFlow()

    @staticmethod
    def _txt_get(txt: dict[Any, Any], key: str) -> str | None:
        value = txt.get(key)
        if value is None:
            key_bytes = key.encode()
            value = txt.get(key_bytes)
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode(errors="ignore")
        return str(value)

    @staticmethod
    def _normalize_profile_sources(value: Any) -> list[dict[str, str]]:
        if not isinstance(value, list):
            return []

        normalized: list[dict[str, str]] = []
        seen_ids: set[str] = set()
        for item in value:
            if not isinstance(item, dict):
                continue

            source_id = str(item.get("id") or "").strip()
            if not source_id:
                continue

            source_id_key = source_id.lower()
            if source_id_key in seen_ids:
                continue
            seen_ids.add(source_id_key)

            source_name = str(item.get("name") or "").strip() or "Unknown"
            source_type = str(item.get("type") or "").strip()
            normalized.append(
                {
                    "id": source_id,
                    "name": source_name,
                    "type": source_type,
                }
            )

        return normalized


class RemoteRelayOptionsFlow(config_entries.OptionsFlow):
    """Placeholder options flow."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return self.async_create_entry(title="", data={})
