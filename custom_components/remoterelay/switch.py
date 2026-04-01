"""Switch entities for RemoteRelay camera capture controls."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ID, CONF_DISPLAY_NAME, DOMAIN


def _normalize_camera_id(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _resolve_camera_definitions(data: dict[str, Any]) -> list[dict[str, str]]:
    raw = data.get("cameras")
    if not isinstance(raw, list):
        return []

    definitions: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        camera_id = _normalize_camera_id(item.get("id"))
        if not camera_id or camera_id in seen:
            continue
        seen.add(camera_id)
        camera_name = str(item.get("name") or camera_id).strip() or camera_id
        definitions.append({"id": camera_id, "name": camera_name})
    return definitions


def _find_camera_data(data: dict[str, Any], camera_id: str) -> dict[str, Any] | None:
    raw = data.get("cameras")
    if not isinstance(raw, list):
        return None
    for item in raw:
        if not isinstance(item, dict):
            continue
        if _normalize_camera_id(item.get("id")) == camera_id:
            return item
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RemoteRelay camera capture switches."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime["coordinator"]
    api = runtime["api"]

    entities_by_id: dict[str, RemoteRelayCameraCaptureSwitch] = {}

    @callback
    def _sync_entities() -> None:
        definitions = _resolve_camera_definitions(coordinator.data or {})
        to_add: list[RemoteRelayCameraCaptureSwitch] = []
        for definition in definitions:
            camera_id = str(definition["id"])
            if camera_id in entities_by_id:
                continue
            entity = RemoteRelayCameraCaptureSwitch(
                entry,
                coordinator,
                api,
                camera_id,
                str(definition["name"]),
            )
            entities_by_id[camera_id] = entity
            to_add.append(entity)
        if to_add:
            async_add_entities(to_add)

    _sync_entities()
    coordinator.async_add_listener(_sync_entities)


class RemoteRelayCameraCaptureSwitch(CoordinatorEntity, SwitchEntity):
    """Switch that toggles camera capture for a specific camera source."""

    _attr_should_poll = False
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:camera-switch"

    def __init__(self, entry: ConfigEntry, coordinator, api, camera_id: str, camera_name: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._api = api
        self._camera_id = camera_id
        self._camera_name = camera_name
        self._attr_name = f"{camera_name} Capture"
        device_id = str(entry.data.get(CONF_DEVICE_ID) or "remoterelay").strip() or "remoterelay"
        self._attr_unique_id = f"{device_id}-camera-capture-{camera_id}"

    @property
    def available(self) -> bool:
        return bool(self.coordinator.last_update_success)

    @property
    def is_on(self) -> bool:
        camera_data = self._camera_data() or {}
        return camera_data.get("captureEnabled", True) is not False

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set_enabled(False)

    async def _set_enabled(self, enabled: bool) -> None:
        await self._api.async_send_command(
            {
                "command": "camera_capture_set",
                "cameraId": self._camera_id,
                "enabled": bool(enabled),
            }
        )
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        camera_data = self._camera_data() or {}
        return {
            "camera_id": self._camera_id,
            "camera_type": camera_data.get("cameraType"),
            "screen_device_id": camera_data.get("screenDeviceId"),
            "webcam_device_id": camera_data.get("webcamDeviceId"),
        }

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._entry.data.get(CONF_DEVICE_ID))},
            "name": str(self._entry.data.get(CONF_DISPLAY_NAME, "RemoteRelay")),
            "manufacturer": "RemoteRelay",
            "model": "RemoteRelay PC Bridge",
        }

    def _camera_data(self) -> dict[str, Any] | None:
        data = self.coordinator.data or {}
        return _find_camera_data(data, self._camera_id)
