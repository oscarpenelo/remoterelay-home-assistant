"""Config flow for RemoteRelay."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any
from urllib.parse import urlsplit
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
    CONF_INTEGRATION_INSTANCE_ID,
    CONF_MAC_ADDRESSES,
    CONF_PROTO_VERSION,
    CONF_SELECTED_SOURCE_ID,
    CONF_TOKEN_EXPIRES_AT,
    DEFAULT_API_PORT,
    DOMAIN,
)

CONF_PAIRING_CODE = "pairing_code"
_LOGGER = logging.getLogger(__name__)


class RemoteRelayConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RemoteRelay."""

    VERSION = 1

    def __init__(self) -> None:
        self._pending_host: str | None = None
        self._pending_host_candidates: list[str] = []
        self._pending_port: int = DEFAULT_API_PORT
        self._discovered_device_id: str | None = None
        self._discovered_display_name: str | None = None
        self._discovered_proto: str = "1"
        self._integration_instance_id = str(uuid4())

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
            self._pending_host_candidates = [self._pending_host] if self._pending_host else []
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

        discovered_hosts = self._resolve_discovery_hosts(discovery_info)
        discovered_host = discovered_hosts[0] if discovered_hosts else ""
        discovered_port = int(getattr(discovery_info, "port", DEFAULT_API_PORT))

        if not discovered_host:
            return self.async_abort(reason="cannot_connect")

        await self.async_set_unique_id(device_id)
        self._abort_if_unique_id_configured(
            updates={
                CONF_HOST: discovered_host,
                CONF_PORT: discovered_port,
                CONF_API_BASE_URL: self._build_base_url(discovered_host, discovered_port),
            }
        )

        self._pending_host = discovered_host
        self._pending_host_candidates = discovered_hosts
        self._pending_port = discovered_port

        return await self.async_step_pair()

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> FlowResult:
        """Start reauthentication for an entry with an invalid local token."""
        entry = self._get_reauth_entry()
        data = entry.data

        stored_base_url = str(data.get(CONF_API_BASE_URL) or "").strip()
        parsed_host = ""
        parsed_port: int | None = None
        if stored_base_url:
            try:
                parsed = urlsplit(stored_base_url)
                parsed_host = str(parsed.hostname or "").strip()
                parsed_port = parsed.port
            except ValueError:
                _LOGGER.warning(
                    "RemoteRelay config entry %s has an invalid API base URL.",
                    entry.entry_id,
                )

        self._pending_host = self._normalize_host(data.get(CONF_HOST)) or parsed_host
        self._pending_host_candidates = [self._pending_host] if self._pending_host else []
        try:
            self._pending_port = int(data.get(CONF_PORT) or parsed_port or DEFAULT_API_PORT)
        except (TypeError, ValueError):
            self._pending_port = parsed_port or DEFAULT_API_PORT

        self._discovered_device_id = str(
            entry.unique_id or data.get(CONF_DEVICE_ID) or ""
        ).strip() or None
        self._discovered_display_name = str(
            data.get(CONF_DISPLAY_NAME) or entry.title or "RemoteRelay"
        ).strip()
        self._discovered_proto = str(data.get(CONF_PROTO_VERSION) or "1").strip() or "1"
        stored_instance_id = str(data.get(CONF_INTEGRATION_INSTANCE_ID) or "").strip()
        if stored_instance_id:
            self._integration_instance_id = stored_instance_id
        else:
            self.hass.config_entries.async_update_entry(
                entry,
                data={
                    **entry.data,
                    CONF_INTEGRATION_INSTANCE_ID: self._integration_instance_id,
                },
            )

        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Exchange a fresh pairing code without replacing the config entry."""
        return await self._async_pairing_step(user_input, step_id="reauth_confirm")

    async def async_step_pair(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Exchange local pairing code for a token."""
        return await self._async_pairing_step(user_input, step_id="pair")

    async def _async_pairing_step(
        self,
        user_input: dict[str, Any] | None,
        *,
        step_id: str,
    ) -> FlowResult:
        """Exchange a pairing code for initial setup or reauthentication."""
        errors: dict[str, str] = {}

        if not self._pending_host:
            if self.source == config_entries.SOURCE_REAUTH:
                return self.async_abort(reason="cannot_connect")
            return await self.async_step_user()

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            pairing_code = str(user_input[CONF_PAIRING_CODE]).strip()
            candidate_hosts = self._connection_candidates()
            last_pairing_error: str | None = None
            wrong_device_detected = False
            expected_device_id = str(self._discovered_device_id or "").strip()

            for candidate_host in candidate_hosts:
                base_url = self._build_base_url(candidate_host, self._pending_port)
                api = RemoteRelayLocalApiClient(session=session, base_url=base_url)
                paired: dict[str, Any] | None = None
                health: dict[str, Any] = {}
                try:
                    health = await api.async_health()
                    if not bool(health.get("pairingEnabled")):
                        last_pairing_error = "pairing_not_enabled"
                        _LOGGER.warning(
                            "RemoteRelay pairing disabled on %s:%s.",
                            candidate_host,
                            self._pending_port,
                        )
                        continue

                    health_device_id = str(health.get("deviceId") or "").strip()
                    if (
                        expected_device_id
                        and health_device_id
                        and health_device_id != expected_device_id
                    ):
                        wrong_device_detected = True
                        _LOGGER.warning(
                            "RemoteRelay pairing candidate %s:%s belongs to device %s, expected %s.",
                            candidate_host,
                            self._pending_port,
                            health_device_id,
                            expected_device_id,
                        )
                        continue

                    paired = await api.async_exchange_pairing_code(
                        pairing_code=pairing_code,
                        integration_instance_id=self._integration_instance_id,
                    )
                except RemoteRelayPairingError as err:
                    if err.code in {"invalid_pairing_code", "invalid_request"}:
                        errors["base"] = "invalid_auth"
                        _LOGGER.warning(
                            "RemoteRelay invalid pairing code on %s:%s (%s).",
                            candidate_host,
                            self._pending_port,
                            err,
                        )
                        break
                    if err.code in {"auth_required", "home_assistant_disabled"}:
                        last_pairing_error = "pairing_not_enabled"
                        _LOGGER.warning(
                            "RemoteRelay pairing unavailable on %s:%s (code=%s).",
                            candidate_host,
                            self._pending_port,
                            err.code,
                        )
                        continue

                    _LOGGER.warning(
                        "RemoteRelay pairing exchange failed on %s:%s (code=%s status=%s): %s",
                        candidate_host,
                        self._pending_port,
                        err.code,
                        err.status,
                        err,
                    )
                    continue
                except Exception as err:
                    _LOGGER.warning(
                        "RemoteRelay pairing connectivity failed on %s:%s: %s",
                        candidate_host,
                        self._pending_port,
                        err,
                    )
                    continue

                if paired is None:
                    continue

                self._pending_host = candidate_host
                self._pending_host_candidates = [candidate_host]
                device = paired.get("device", {})
                if not isinstance(device, dict):
                    continue

                device_id = str(
                    device.get("deviceId")
                    or health.get("deviceId")
                    or self._discovered_device_id
                    or ""
                ).strip()
                access_token = str(paired.get("accessToken") or "").strip()
                if not device_id or not access_token:
                    _LOGGER.warning(
                        "RemoteRelay pairing response from %s:%s is missing identity or token.",
                        candidate_host,
                        self._pending_port,
                    )
                    continue

                if expected_device_id and device_id != expected_device_id:
                    wrong_device_detected = True
                    _LOGGER.warning(
                        "RemoteRelay pairing response belongs to device %s, expected %s.",
                        device_id,
                        expected_device_id,
                    )
                    continue

                if self.source == config_entries.SOURCE_REAUTH:
                    entry = self._get_reauth_entry()
                    entry_unique_id = str(entry.unique_id or "").strip()
                    entry_device_id = str(entry.data.get(CONF_DEVICE_ID) or "").strip()
                    preserved_device_id = entry_unique_id or entry_device_id
                    if preserved_device_id and device_id != preserved_device_id:
                        return self.async_abort(reason="wrong_device")

                    if entry_unique_id:
                        await self.async_set_unique_id(device_id)
                        self._abort_if_unique_id_mismatch(reason="wrong_device")

                    data_updates: dict[str, Any] = {
                        CONF_ACCESS_TOKEN: access_token,
                        CONF_INTEGRATION_INSTANCE_ID: self._integration_instance_id,
                        CONF_API_BASE_URL: base_url,
                        CONF_HOST: candidate_host,
                        CONF_PORT: self._pending_port,
                    }
                    if "expiresAt" in paired:
                        data_updates[CONF_TOKEN_EXPIRES_AT] = paired.get("expiresAt")

                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates=data_updates,
                    )

                current_unique_id = getattr(self, "unique_id", None)
                if current_unique_id is None:
                    await self.async_set_unique_id(device_id)
                elif str(current_unique_id) != device_id:
                    return self.async_abort(reason="wrong_device")
                self._abort_if_unique_id_configured()

                title = str(device.get("displayName") or self._discovered_display_name or "RemoteRelay")
                data = {
                    CONF_API_BASE_URL: base_url,
                    CONF_ACCESS_TOKEN: access_token,
                    CONF_INTEGRATION_INSTANCE_ID: self._integration_instance_id,
                    CONF_TOKEN_EXPIRES_AT: paired.get("expiresAt"),
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

            if "base" not in errors:
                if wrong_device_detected:
                    return self.async_abort(reason="wrong_device")
                errors["base"] = last_pairing_error or "cannot_connect"

        schema = vol.Schema({vol.Required(CONF_PAIRING_CODE): str})
        placeholders = {
            "host": self._pending_host,
            "port": str(self._pending_port),
            "name": self._discovered_display_name or "RemoteRelay",
        }
        return self.async_show_form(
            step_id=step_id,
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
    def _normalize_host(value: Any) -> str:
        return str(value or "").strip().rstrip(".")

    @classmethod
    def _resolve_discovery_hosts(cls, discovery_info: Any) -> list[str]:
        ipv4_candidates: list[str] = []
        ipv6_candidates: list[str] = []
        host_candidates: list[str] = []

        ip_addresses = getattr(discovery_info, "ip_addresses", None)
        if isinstance(ip_addresses, (list, tuple, set)):
            for value in ip_addresses:
                normalized = cls._normalize_host(value)
                if not normalized:
                    continue
                if ":" in normalized:
                    ipv6_candidates.append(normalized)
                else:
                    ipv4_candidates.append(normalized)

        for value in [getattr(discovery_info, "ip_address", None)]:
            normalized = cls._normalize_host(value)
            if not normalized:
                continue
            if ":" in normalized:
                ipv6_candidates.append(normalized)
            else:
                ipv4_candidates.append(normalized)

        for value in [getattr(discovery_info, "host", None), getattr(discovery_info, "hostname", None)]:
            normalized = cls._normalize_host(value)
            if normalized:
                host_candidates.append(normalized)

        ordered = [*ipv4_candidates, *host_candidates, *ipv6_candidates]
        deduped: list[str] = []
        seen: set[str] = set()
        for candidate in ordered:
            key = candidate.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(candidate)
        return deduped

    def _connection_candidates(self) -> list[str]:
        candidates = [*self._pending_host_candidates]
        if self._pending_host:
            candidates.append(self._pending_host)

        deduped: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized = self._normalize_host(candidate)
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(normalized)
        return deduped or ([self._pending_host] if self._pending_host else [])

    @classmethod
    def _build_base_url(cls, host: str, port: int) -> str:
        normalized_host = cls._normalize_host(host)
        if ":" in normalized_host and not normalized_host.startswith("["):
            ipv6_host = normalized_host.replace("%", "%25")
            return f"http://[{ipv6_host}]:{int(port)}"
        return f"http://{normalized_host}:{int(port)}"

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
