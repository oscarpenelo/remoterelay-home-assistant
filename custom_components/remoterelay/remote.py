"""Remote entity for RemoteRelay."""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.components.remote import RemoteEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_BROADCAST_ADDRESS, CONF_DEVICE_ID, CONF_DISPLAY_NAME, CONF_MAC_ADDRESSES, DOMAIN
from .const import REMOTE_COMMAND_ALIASES, REMOTE_DIRECT_COMMANDS, REMOTE_NAV_KEYS

NAV_KEYS = set(REMOTE_NAV_KEYS)
LEGACY_DIRECT_COMMANDS = set(REMOTE_DIRECT_COMMANDS)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RemoteRelay remote entity from a config entry."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([RemoteRelayRemoteEntity(entry, runtime["coordinator"], runtime["api"])])


def _normalize_remote_token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _normalize_profile_remote_keys(data: dict[str, Any]) -> set[str]:
    normalized: set[str] = set()

    raw_definitions = data.get("remoteKeyDefinitions")
    if isinstance(raw_definitions, list):
        for entry in raw_definitions:
            if not isinstance(entry, dict):
                continue
            key_id = _normalize_remote_token(entry.get("id"))
            if key_id:
                normalized.add(key_id)

    if normalized:
        return normalized

    capabilities = data.get("capabilities")
    if isinstance(capabilities, dict):
        raw_keys = capabilities.get("remoteKeys")
        if isinstance(raw_keys, list):
            for item in raw_keys:
                key_id = _normalize_remote_token(item)
                if key_id:
                    normalized.add(key_id)

    return normalized


class RemoteRelayRemoteEntity(CoordinatorEntity, RemoteEntity):
    """RemoteRelay remote entity."""

    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, coordinator, api) -> None:
        super().__init__(coordinator)
        self.hass = coordinator.hass
        self._entry = entry
        self._api = api
        device_id = entry.data.get(CONF_DEVICE_ID)
        self._attr_unique_id = f"{device_id}-remote" if device_id else None

    @property
    def name(self) -> str | None:
        """Return entity name."""
        data = self.coordinator.data or {}
        profile_name = str(data.get("displayName") or "").strip()
        base_name = profile_name or str(self._entry.data.get(CONF_DISPLAY_NAME, "RemoteRelay")).strip() or "RemoteRelay"
        return f"{base_name} Remote"

    @property
    def available(self) -> bool:
        """Expose entity as always available; state reflects daemon reachability."""
        return True

    @property
    def is_on(self) -> bool | None:
        """Remote entity logical power mirrors daemon availability."""
        return bool(self.coordinator.last_update_success)

    @property
    def _mac_addresses(self) -> list[str]:
        return [str(mac).strip() for mac in self._entry.data.get(CONF_MAC_ADDRESSES, []) if str(mac).strip()]

    @property
    def _broadcast_address(self) -> str | None:
        value = self._entry.data.get(CONF_BROADCAST_ADDRESS)
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @property
    def device_info(self) -> dict[str, Any]:
        """Attach to the same HA device as media_player entity."""
        return {
            "identifiers": {(DOMAIN, self._entry.data.get(CONF_DEVICE_ID))},
            "name": str(self._entry.data.get(CONF_DISPLAY_NAME, "RemoteRelay")),
            "manufacturer": "RemoteRelay",
            "model": "RemoteRelay PC Bridge",
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Send Wake-on-LAN packets for all configured MAC addresses."""
        if not self._mac_addresses:
            raise ValueError("No MAC addresses configured for Wake-on-LAN.")

        unique_macs = list(dict.fromkeys(str(mac).strip() for mac in self._mac_addresses if str(mac).strip()))
        for mac in unique_macs:
            service_data: dict[str, Any] = {"mac": mac}
            if self._broadcast_address:
                service_data["broadcast_address"] = self._broadcast_address
            await self.hass.services.async_call(
                "wake_on_lan",
                "send_magic_packet",
                service_data,
                blocking=True,
            )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Map remote off to daemon power-off."""
        supports_remote_key = self._supports_remote_key_command()
        key_id = "power_toggle" if supports_remote_key and "power_toggle" in self._available_remote_keys() else None
        if key_id:
            await self._api.async_send_command({"command": "remote_key", "keyId": key_id})
        else:
            await self._api.async_send_command({"command": "power_off"})
        await self.coordinator.async_request_refresh()

    async def async_send_command(self, command: list[str] | str, **kwargs: Any) -> None:
        """Send one or more commands to RemoteRelay daemon.

        Supported commands (strings):
        - Navigation: up/down/left/right/ok/back/home/info
        - Media: play_pause, next_track, previous_track
        - Audio: volume_up, volume_down, mute_toggle
        - Power: power_off

        Convenience aliases:
        - enter, select -> ok
        - return -> back
        - playpause -> play_pause
        - vol_up / vol_down
        - next / previous
        """

        commands = command if isinstance(command, list) else [command]
        normalized_commands = [self._normalize_command(item) for item in commands]

        repeats = max(1, int(kwargs.get("num_repeats", 1) or 1))
        delay_secs = float(kwargs.get("delay_secs", 0) or 0)

        for repeat_index in range(repeats):
            for item in normalized_commands:
                await self._dispatch_command(item)
                if delay_secs > 0:
                    await asyncio.sleep(delay_secs)
            # Avoid an extra sleep after the last repeat if delay was provided.
            if repeat_index == repeats - 1:
                continue

    async def _dispatch_command(self, command: str) -> None:
        key_id = self._resolve_remote_key_id(command)
        if key_id and self._supports_remote_key_command():
            await self._api.async_send_command({"command": "remote_key", "keyId": key_id})
            if key_id == "power_toggle":
                await self.coordinator.async_request_refresh()
            return

        # Legacy fallback for older daemon versions.
        if command in NAV_KEYS:
            await self._api.async_send_command({"command": "navigate", "key": command})
            return
        if command in LEGACY_DIRECT_COMMANDS:
            await self._api.async_send_command({"command": command})
            if command == "power_off":
                await self.coordinator.async_request_refresh()
            return

        raise ValueError(f"Unsupported remote command: {command}")

    def _available_remote_keys(self) -> set[str]:
        data = self.coordinator.data or {}
        return _normalize_profile_remote_keys(data)

    def _supports_remote_key_command(self) -> bool:
        data = self.coordinator.data or {}
        raw = data.get("remoteKeyDefinitions")
        return isinstance(raw, list) and len(raw) > 0

    def _resolve_remote_key_id(self, command: str) -> str | None:
        available = self._available_remote_keys()
        if not available:
            return None

        normalized = _normalize_remote_token(command)
        if normalized in available:
            return normalized

        alias_candidate = _normalize_remote_token(REMOTE_COMMAND_ALIASES.get(normalized))
        if alias_candidate and alias_candidate in available:
            return alias_candidate

        # Backward-compat aliases expected by users/service calls.
        if normalized.startswith("number_"):
            number_alias = f"num_{normalized.split('_')[-1]}"
            if number_alias in available:
                return number_alias
        if normalized.isdigit() and len(normalized) == 1:
            number_alias = f"num_{normalized}"
            if number_alias in available:
                return number_alias
        return None

    @staticmethod
    def _normalize_command(value: Any) -> str:
        normalized = _normalize_remote_token(value)
        if not normalized:
            return ""
        aliases = {
            "enter": "ok",
            "select": "ok",
            "return": "back",
            "playpause": "play_pause",
            "next": "next_track",
            "previous": "previous_track",
            "prev": "previous_track",
            "vol_up": "volume_up",
            "vol_down": "volume_down",
            "mute": "mute_toggle",
            "off": "power_off",
        }
        return aliases.get(normalized, normalized)
