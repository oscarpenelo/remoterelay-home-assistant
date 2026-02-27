"""Select entity for RemoteRelay input sources."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ID, CONF_DISPLAY_NAME, CONF_INPUT_SOURCES, CONF_SELECTED_SOURCE_ID, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RemoteRelay select entities from config entry."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([RemoteRelayInputSourceSelect(entry, runtime["coordinator"], runtime["api"])])


class RemoteRelayInputSourceSelect(CoordinatorEntity, SelectEntity):
    """Select entity mirroring daemon input sources."""

    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, coordinator, api) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._api = api
        device_id = str(entry.data.get(CONF_DEVICE_ID) or "remoterelay").strip() or "remoterelay"
        self._attr_unique_id = f"{device_id}-input-source"
        self._attr_icon = "mdi:video-input-hdmi"

    @property
    def name(self) -> str | None:
        return "Input Source"

    @property
    def available(self) -> bool:
        return bool(self.coordinator.last_update_success)

    @property
    def options(self) -> list[str]:
        return [str(src.get("name") or "Unknown") for src in self._sources()]

    @property
    def current_option(self) -> str | None:
        selected_source_id = self._selected_source_id()
        if not selected_source_id:
            return None
        for src in self._sources():
            if str(src.get("id") or "") == selected_source_id:
                return str(src.get("name") or "")
        return None

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._entry.data.get(CONF_DEVICE_ID))},
            "name": str(self._entry.data.get(CONF_DISPLAY_NAME, "RemoteRelay")),
            "manufacturer": "RemoteRelay",
            "model": "RemoteRelay PC Bridge",
        }

    async def async_select_option(self, option: str) -> None:
        source_id = self._source_name_to_id(option)
        if not source_id:
            raise ValueError(f"Unknown input source: {option}")
        await self._api.async_send_command({"command": "select_source", "sourceId": source_id})
        await self.coordinator.async_request_refresh()

    def _sources(self) -> list[dict[str, Any]]:
        data = self.coordinator.data or {}
        raw = data.get("inputSources")
        if not isinstance(raw, list):
            raw = self._entry.data.get(CONF_INPUT_SOURCES, [])
        return [entry for entry in raw if isinstance(entry, dict)]

    def _selected_source_id(self) -> str:
        data = self.coordinator.data or {}
        selected_source_id = data.get("selectedSourceId")
        if selected_source_id is None:
            selected_source_id = self._entry.data.get(CONF_SELECTED_SOURCE_ID)
        return str(selected_source_id or "").strip()

    def _source_name_to_id(self, source_name: str) -> str | None:
        for src in self._sources():
            if str(src.get("name") or "") == source_name:
                return str(src.get("id") or "")
        return None
