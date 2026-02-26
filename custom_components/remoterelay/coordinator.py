"""Data update coordinator for RemoteRelay."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import RemoteRelayApiError, RemoteRelayLocalApiClient
from .const import (
    CONF_DEVICE_ID,
    CONF_DISPLAY_NAME,
    CONF_MAC_ADDRESSES,
    DEFAULT_POLL_INTERVAL_SECONDS,
    DOMAIN,
)


class RemoteRelayCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that polls the local daemon device profile."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: RemoteRelayLocalApiClient) -> None:
        super().__init__(
            hass,
            logger=hass.data[DOMAIN]["logger"],
            name=f"{DOMAIN}_device_profile",
            update_interval=timedelta(seconds=DEFAULT_POLL_INTERVAL_SECONDS),
        )
        self.entry = entry
        self.api = api

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            profile = await self.api.async_get_device_profile()
            await self._async_maybe_sync_config_entry(profile)
            return profile
        except RemoteRelayApiError as err:
            raise UpdateFailed(str(err)) from err

    async def _async_maybe_sync_config_entry(self, profile: dict[str, Any]) -> None:
        if not isinstance(profile, dict):
            return

        current_data = dict(self.entry.data)
        next_data = dict(current_data)
        changed = False

        profile_device_id = str(profile.get("deviceId") or "").strip()
        if profile_device_id and profile_device_id != str(current_data.get(CONF_DEVICE_ID) or ""):
            next_data[CONF_DEVICE_ID] = profile_device_id
            changed = True

        profile_display_name = str(profile.get("displayName") or "").strip()
        if profile_display_name and profile_display_name != str(current_data.get(CONF_DISPLAY_NAME) or ""):
            next_data[CONF_DISPLAY_NAME] = profile_display_name
            changed = True

        profile_macs = self._normalize_profile_macs(profile.get("macAddresses"))
        current_macs = [str(mac).strip() for mac in current_data.get(CONF_MAC_ADDRESSES, []) if str(mac).strip()]
        if profile_macs and profile_macs != current_macs:
            next_data[CONF_MAC_ADDRESSES] = profile_macs
            changed = True

        if changed:
            self.hass.config_entries.async_update_entry(self.entry, data=next_data)

    @staticmethod
    def _normalize_profile_macs(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []

        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            if isinstance(item, dict):
                candidate = str(item.get("value") or "").strip()
            else:
                candidate = str(item or "").strip()
            if not candidate:
                continue
            upper = candidate.upper()
            if upper in seen:
                continue
            seen.add(upper)
            normalized.append(candidate)
        return normalized
