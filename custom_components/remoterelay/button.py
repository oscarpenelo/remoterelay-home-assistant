"""Button entities for RemoteRelay remote actions."""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ID, CONF_DISPLAY_NAME, DOMAIN, REMOTE_BUTTONS, REMOTE_DIRECT_COMMANDS, REMOTE_NAV_KEYS

NAV_KEYS = set(REMOTE_NAV_KEYS)
DIRECT_COMMANDS = set(REMOTE_DIRECT_COMMANDS)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RemoteRelay buttons from config entry."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime["coordinator"]
    api = runtime["api"]
    entities = [
        RemoteRelayCommandButton(entry, coordinator, api, definition)
        for definition in REMOTE_BUTTONS
    ]
    async_add_entities(entities)


class RemoteRelayCommandButton(CoordinatorEntity, ButtonEntity):
    """Button that dispatches one RemoteRelay command."""

    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, coordinator, api, definition: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._api = api
        self._command_key = str(definition["key"])
        self._label = str(definition["label"])
        self._attr_icon = str(definition.get("icon") or "mdi:remote")

        device_id = str(entry.data.get(CONF_DEVICE_ID) or "remoterelay").strip() or "remoterelay"
        self._attr_unique_id = f"{device_id}-button-{self._command_key}"

    @property
    def name(self) -> str | None:
        return self._label

    @property
    def available(self) -> bool:
        return bool(self.coordinator.last_update_success)

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._entry.data.get(CONF_DEVICE_ID))},
            "name": str(self._entry.data.get(CONF_DISPLAY_NAME, "RemoteRelay")),
            "manufacturer": "RemoteRelay",
            "model": "RemoteRelay PC Bridge",
        }

    async def async_press(self) -> None:
        if self._command_key in NAV_KEYS:
            await self._api.async_send_command({"command": "navigate", "key": self._command_key})
            return

        if self._command_key in DIRECT_COMMANDS:
            await self._api.async_send_command({"command": self._command_key})
            if self._command_key == "power_off":
                await self.coordinator.async_request_refresh()
            return

        raise ValueError(f"Unsupported button command: {self._command_key}")
