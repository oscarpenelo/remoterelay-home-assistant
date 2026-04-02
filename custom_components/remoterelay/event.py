"""Event entities for RemoteRelay doorbell presses."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ID, CONF_DISPLAY_NAME, DOMAIN


def _normalize_doorbell_id(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _normalize_trigger_count(value: Any) -> int | None:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, numeric)


def _normalize_timestamp(value: Any) -> str | None:
    candidate = str(value or "").strip()
    return candidate or None


def _resolve_doorbell_definitions(data: dict[str, Any]) -> list[dict[str, str]]:
    raw = data.get("doorbells")
    if not isinstance(raw, list):
        return []

    definitions: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        doorbell_id = _normalize_doorbell_id(item.get("id"))
        if not doorbell_id or doorbell_id in seen:
            continue
        seen.add(doorbell_id)
        name = str(item.get("name") or doorbell_id).strip() or doorbell_id
        definitions.append({"id": doorbell_id, "name": name})
    return definitions


def _find_doorbell_data(data: dict[str, Any], doorbell_id: str) -> dict[str, Any] | None:
    raw = data.get("doorbells")
    if not isinstance(raw, list):
        return None
    for item in raw:
        if not isinstance(item, dict):
            continue
        if _normalize_doorbell_id(item.get("id")) == doorbell_id:
            return item
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RemoteRelay doorbell event entities."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime["coordinator"]

    entities_by_id: dict[str, RemoteRelayDoorbellEventEntity] = {}

    @callback
    def _sync_entities() -> None:
        definitions = _resolve_doorbell_definitions(coordinator.data or {})
        to_add: list[RemoteRelayDoorbellEventEntity] = []
        for definition in definitions:
            doorbell_id = str(definition["id"])
            if doorbell_id in entities_by_id:
                continue
            entity = RemoteRelayDoorbellEventEntity(
                entry,
                coordinator,
                doorbell_id,
                str(definition["name"]),
            )
            entities_by_id[doorbell_id] = entity
            to_add.append(entity)
        if to_add:
            async_add_entities(to_add)

    _sync_entities()
    coordinator.async_add_listener(_sync_entities)


class RemoteRelayDoorbellEventEntity(CoordinatorEntity, EventEntity):
    """Event entity that fires when the daemon reports a doorbell press."""

    _attr_should_poll = False
    _attr_device_class = EventDeviceClass.DOORBELL
    _attr_event_types = ["pressed"]
    _attr_icon = "mdi:doorbell-video"

    def __init__(self, entry: ConfigEntry, coordinator, doorbell_id: str, doorbell_name: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._doorbell_id = doorbell_id
        self._attr_name = doorbell_name
        device_id = str(entry.data.get(CONF_DEVICE_ID) or "remoterelay").strip() or "remoterelay"
        self._attr_unique_id = f"{device_id}-doorbell-{doorbell_id}"
        initial = self._doorbell_data() or {}
        self._last_seen_trigger_count = _normalize_trigger_count(initial.get("triggerCount"))
        self._last_seen_trigger_at = _normalize_timestamp(initial.get("lastTriggeredAt"))

    @property
    def available(self) -> bool:
        doorbell_data = self._doorbell_data() or {}
        return bool(self.coordinator.last_update_success and doorbell_data.get("enabled", False))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        doorbell_data = self._doorbell_data() or {}
        return {
            "doorbell_id": self._doorbell_id,
            "linked_camera_id": doorbell_data.get("linkedCameraId"),
            "trigger_count": _normalize_trigger_count(doorbell_data.get("triggerCount")) or 0,
            "last_source": doorbell_data.get("lastSource"),
            "last_reason": doorbell_data.get("lastReason"),
            "trigger_url": doorbell_data.get("triggerUrl"),
        }

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._entry.data.get(CONF_DEVICE_ID))},
            "name": str(self._entry.data.get(CONF_DISPLAY_NAME, "RemoteRelay")),
            "manufacturer": "RemoteRelay",
            "model": "RemoteRelay PC Bridge",
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        doorbell_data = self._doorbell_data() or {}
        trigger_count = _normalize_trigger_count(doorbell_data.get("triggerCount"))
        trigger_at = _normalize_timestamp(doorbell_data.get("lastTriggeredAt"))

        should_trigger = False
        if trigger_count is not None and self._last_seen_trigger_count is not None:
            should_trigger = trigger_count > self._last_seen_trigger_count
        elif trigger_at and self._last_seen_trigger_at:
            should_trigger = trigger_at != self._last_seen_trigger_at

        if should_trigger:
            event_data = {
                "doorbell_id": self._doorbell_id,
                "linked_camera_id": doorbell_data.get("linkedCameraId"),
                "source": doorbell_data.get("lastSource"),
                "reason": doorbell_data.get("lastReason"),
                "trigger_url": doorbell_data.get("triggerUrl"),
            }
            self._trigger_event(
                "pressed",
                {key: value for key, value in event_data.items() if value is not None and value != ""},
            )

        self._last_seen_trigger_count = trigger_count
        self._last_seen_trigger_at = trigger_at
        super()._handle_coordinator_update()

    def _doorbell_data(self) -> dict[str, Any] | None:
        data = self.coordinator.data or {}
        return _find_doorbell_data(data, self._doorbell_id)
