"""Button entities for RemoteRelay remote actions."""

from __future__ import annotations

from typing import Any

from homeassistant.core import callback

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_DEVICE_ID,
    CONF_DISPLAY_NAME,
    DEFAULT_REMOTE_KEY_ICONS,
    DEFAULT_REMOTE_KEY_LABELS,
    DOMAIN,
    REMOTE_DIRECT_COMMANDS,
    REMOTE_NAV_KEYS,
)

LEGACY_REMOTE_KEY_ORDER = (
    "home",
    "back",
    "info",
    "up",
    "left",
    "ok",
    "right",
    "down",
    "play_pause",
    "next_track",
    "previous_track",
    "vol_up",
    "vol_down",
    "mute_toggle",
    "channel_up",
    "channel_down",
    "power_toggle",
)
NAV_KEYS = set(REMOTE_NAV_KEYS)
LEGACY_DIRECT_COMMANDS = set(REMOTE_DIRECT_COMMANDS)
LEGACY_KEY_ID_TO_COMMAND = {
    "power_toggle": "power_off",
    "vol_up": "volume_up",
    "vol_down": "volume_down",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RemoteRelay buttons from config entry."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime["coordinator"]
    api = runtime["api"]

    entities_by_id: dict[str, RemoteRelayCommandButton] = {}

    @callback
    def _sync_entities() -> None:
        definitions = _resolve_profile_remote_key_definitions(coordinator.data or {})
        to_add: list[RemoteRelayCommandButton] = []
        for definition in definitions:
            key_id = str(definition["id"])
            if key_id in entities_by_id:
                continue
            entity = RemoteRelayCommandButton(entry, coordinator, api, definition)
            entities_by_id[key_id] = entity
            to_add.append(entity)
        if to_add:
            async_add_entities(to_add)

    _sync_entities()
    coordinator.async_add_listener(_sync_entities)


def _normalize_remote_token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _resolve_remote_icon(key_id: str) -> str:
    if key_id in DEFAULT_REMOTE_KEY_ICONS:
        return DEFAULT_REMOTE_KEY_ICONS[key_id]
    if key_id.startswith("num_"):
        suffix = key_id.split("_", maxsplit=1)[-1]
        return f"mdi:numeric-{suffix}-circle-outline"
    return "mdi:remote"


def _build_fallback_remote_key_order(definitions: list[dict[str, str]]) -> list[dict[str, str]]:
    by_id = {entry["id"]: entry for entry in definitions}
    ordered: list[dict[str, str]] = []
    for key_id in LEGACY_REMOTE_KEY_ORDER:
        if key_id in by_id:
            ordered.append(by_id.pop(key_id))
    ordered.extend(by_id.values())
    return ordered


def _resolve_profile_remote_key_definitions(data: dict[str, Any]) -> list[dict[str, str]]:
    definitions: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    raw_definitions = data.get("remoteKeyDefinitions")
    if isinstance(raw_definitions, list):
        for raw_entry in raw_definitions:
            if not isinstance(raw_entry, dict):
                continue
            key_id = _normalize_remote_token(raw_entry.get("id"))
            if not key_id or key_id in seen_ids:
                continue
            seen_ids.add(key_id)
            label = str(raw_entry.get("label") or DEFAULT_REMOTE_KEY_LABELS.get(key_id) or key_id).strip()
            definitions.append(
                {
                    "id": key_id,
                    "label": label or key_id,
                    "icon": _resolve_remote_icon(key_id),
                }
            )
    if definitions:
        return _build_fallback_remote_key_order(definitions)

    capabilities = data.get("capabilities")
    raw_keys = capabilities.get("remoteKeys") if isinstance(capabilities, dict) else None
    if isinstance(raw_keys, list):
        for raw_key in raw_keys:
            key_id = _normalize_remote_token(raw_key)
            if not key_id or key_id in seen_ids:
                continue
            seen_ids.add(key_id)
            definitions.append(
                {
                    "id": key_id,
                    "label": DEFAULT_REMOTE_KEY_LABELS.get(key_id, key_id),
                    "icon": _resolve_remote_icon(key_id),
                }
            )

    return _build_fallback_remote_key_order(definitions)


class RemoteRelayCommandButton(CoordinatorEntity, ButtonEntity):
    """Button that dispatches one RemoteRelay command."""

    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, coordinator, api, definition: dict[str, str]) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._api = api
        self._command_key = str(definition["id"])
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
        if self._supports_remote_key_command():
            await self._api.async_send_command({"command": "remote_key", "keyId": self._command_key})
            if self._command_key == "power_toggle":
                await self.coordinator.async_request_refresh()
            return

        if self._command_key in NAV_KEYS:
            await self._api.async_send_command({"command": "navigate", "key": self._command_key})
            return

        legacy_command = LEGACY_KEY_ID_TO_COMMAND.get(self._command_key, self._command_key)
        if legacy_command in LEGACY_DIRECT_COMMANDS:
            await self._api.async_send_command({"command": legacy_command})
            if legacy_command == "power_off":
                await self.coordinator.async_request_refresh()
            return

        raise ValueError(f"Unsupported button command: {self._command_key}")

    def _supports_remote_key_command(self) -> bool:
        data = self.coordinator.data or {}
        raw = data.get("remoteKeyDefinitions")
        return isinstance(raw, list) and len(raw) > 0
