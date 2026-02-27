"""RemoteRelay media_player entity."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.media_player import MediaPlayerEntity
from homeassistant.components.media_player.const import MediaPlayerEntityFeature, MediaPlayerState
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_platform
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_BROADCAST_ADDRESS,
    CONF_DEVICE_ID,
    CONF_DISPLAY_NAME,
    CONF_INPUT_SOURCES,
    CONF_MAC_ADDRESSES,
    CONF_SELECTED_SOURCE_ID,
    DOMAIN,
)

def _build_support_flags() -> MediaPlayerEntityFeature:
    flags = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.PREVIOUS_TRACK
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
    )

    # Compatibility across Home Assistant versions:
    # some versions expose PLAY_PAUSE, others only PLAY and PAUSE.
    play_pause_flag = getattr(MediaPlayerEntityFeature, "PLAY_PAUSE", None)
    if play_pause_flag is not None:
        flags |= play_pause_flag
    else:
        play_flag = getattr(MediaPlayerEntityFeature, "PLAY", None)
        pause_flag = getattr(MediaPlayerEntityFeature, "PAUSE", None)
        if play_flag is not None:
            flags |= play_flag
        if pause_flag is not None:
            flags |= pause_flag

    return flags


SUPPORT_FLAGS = _build_support_flags()

_LOGGER = logging.getLogger(__name__)
NAV_KEYS = {"up", "down", "left", "right", "ok", "back", "home", "info"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RemoteRelay media player from config entry."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "navigate",
        {
            vol.Required("key"): vol.In(sorted(NAV_KEYS)),
        },
        "async_navigate",
    )
    async_add_entities([RemoteRelayMediaPlayer(hass, entry, runtime["coordinator"], runtime["api"])])


class RemoteRelayMediaPlayer(CoordinatorEntity, MediaPlayerEntity):
    """RemoteRelay media player entity."""

    _attr_should_poll = False
    _attr_supported_features = SUPPORT_FLAGS

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, coordinator, api) -> None:
        super().__init__(coordinator)
        self.hass = hass
        self._entry = entry
        self._api = api
        self._attr_unique_id = entry.data.get(CONF_DEVICE_ID)

    @property
    def name(self) -> str | None:
        """Return display name."""
        data = self.coordinator.data or {}
        profile_name = str(data.get("displayName") or "").strip()
        if profile_name:
            return profile_name
        return str(self._entry.data.get(CONF_DISPLAY_NAME, "RemoteRelay"))

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
    def available(self) -> bool:
        """Expose entity as always available; state reflects daemon reachability."""
        return True

    @property
    def state(self) -> MediaPlayerState | None:
        """Return media player state."""
        if not self.coordinator.last_update_success:
            return MediaPlayerState.OFF

        data = self.coordinator.data or {}
        power_state = str(data.get("powerState") or "unknown")
        if power_state == "on":
            return MediaPlayerState.ON
        if power_state == "off":
            return MediaPlayerState.OFF
        return MediaPlayerState.ON

    @property
    def source_list(self) -> list[str]:
        """Return available source names."""
        return [src.get("name", "Unknown") for src in self._sources()]

    @property
    def source(self) -> str | None:
        """Return selected source name if available."""
        selected = self._selected_source_id()
        if not selected:
            return None
        for src in self._sources():
            if str(src.get("id") or "") == selected:
                return str(src.get("name"))
        return None

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info for registry."""
        return {
            "identifiers": {(DOMAIN, self._entry.data.get(CONF_DEVICE_ID))},
            "name": self.name or "RemoteRelay",
            "manufacturer": "RemoteRelay",
            "model": "RemoteRelay PC Bridge",
        }

    async def async_turn_on(self) -> None:
        """Send Wake-on-LAN magic packet from Home Assistant host."""
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
        _LOGGER.debug("Sent Wake-on-LAN packets for %s MAC address(es).", len(unique_macs))

    async def async_turn_off(self) -> None:
        await self._api.async_send_command({"command": "power_off"})
        await self.coordinator.async_request_refresh()

    async def async_media_play_pause(self) -> None:
        await self._api.async_send_command({"command": "play_pause"})

    async def async_media_play(self) -> None:
        await self._api.async_send_command({"command": "play_pause"})

    async def async_media_pause(self) -> None:
        await self._api.async_send_command({"command": "play_pause"})

    async def async_media_next_track(self) -> None:
        await self._api.async_send_command({"command": "next_track"})

    async def async_media_previous_track(self) -> None:
        await self._api.async_send_command({"command": "previous_track"})

    async def async_mute_volume(self, mute: bool) -> None:
        # The daemon currently exposes toggle; a future contract revision can add explicit set.
        if mute:
            await self._api.async_send_command({"command": "mute_toggle"})
        else:
            await self._api.async_send_command({"command": "mute_toggle"})

    async def async_volume_up(self) -> None:
        await self._api.async_send_command({"command": "volume_up"})

    async def async_volume_down(self) -> None:
        await self._api.async_send_command({"command": "volume_down"})

    async def async_select_source(self, source: str) -> None:
        source_id = self._source_name_to_id(source)
        if not source_id:
            raise ValueError(f"Unknown source: {source}")
        await self._api.async_send_command({"command": "select_source", "sourceId": source_id})
        await self.coordinator.async_request_refresh()

    async def async_navigate(self, key: str) -> None:
        normalized = str(key).strip().lower()
        if normalized not in NAV_KEYS:
            raise ValueError(f"Unsupported navigation key: {key}")
        await self._api.async_send_command({"command": "navigate", "key": normalized})

    def _sources(self) -> list[dict[str, Any]]:
        data = self.coordinator.data or {}
        raw_sources = data.get("inputSources")
        if not isinstance(raw_sources, list):
            raw_sources = self._entry.data.get(CONF_INPUT_SOURCES, [])
        return [src for src in raw_sources if isinstance(src, dict)]

    def _selected_source_id(self) -> str:
        data = self.coordinator.data or {}
        selected = data.get("selectedSourceId")
        if selected is None:
            selected = self._entry.data.get(CONF_SELECTED_SOURCE_ID)
        return str(selected or "").strip()

    def _source_name_to_id(self, source_name: str) -> str | None:
        for src in self._sources():
            if src.get("name") == source_name:
                return str(src.get("id"))
        return None
