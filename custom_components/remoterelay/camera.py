"""Camera entities for RemoteRelay webcam/screen snapshots and stream_source."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.camera import Camera

CAMERA_SUPPORT_STREAM = 0
try:  # Newer HA variants
    from homeassistant.components.camera import CameraEntityFeature  # type: ignore

    CAMERA_SUPPORT_STREAM = int(getattr(CameraEntityFeature, "STREAM", 0))
except ImportError:  # pragma: no cover - compatibility with older HA builds
    try:
        from homeassistant.components.camera.const import SUPPORT_STREAM  # type: ignore

        CAMERA_SUPPORT_STREAM = int(SUPPORT_STREAM)
    except ImportError:  # pragma: no cover - fallback when stream flag is unavailable
        CAMERA_SUPPORT_STREAM = 0
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import RemoteRelayApiError
from .const import CONF_DEVICE_ID, CONF_DISPLAY_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)


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
        name = str(item.get("name") or camera_id).strip() or camera_id
        definitions.append({"id": camera_id, "name": name})
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
    """Set up RemoteRelay camera entities."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime["coordinator"]
    api = runtime["api"]

    entities_by_id: dict[str, RemoteRelayCameraEntity] = {}

    @callback
    def _sync_entities() -> None:
        definitions = _resolve_camera_definitions(coordinator.data or {})
        to_add: list[RemoteRelayCameraEntity] = []
        for definition in definitions:
            camera_id = str(definition["id"])
            if camera_id in entities_by_id:
                continue
            entity = RemoteRelayCameraEntity(entry, coordinator, api, camera_id, str(definition["name"]))
            entities_by_id[camera_id] = entity
            to_add.append(entity)
        if to_add:
            async_add_entities(to_add)

    _sync_entities()
    coordinator.async_add_listener(_sync_entities)


class RemoteRelayCameraEntity(CoordinatorEntity, Camera):
    """Camera entity backed by daemon snapshot endpoint."""

    _attr_should_poll = False
    _attr_supported_features = CAMERA_SUPPORT_STREAM

    def __init__(self, entry: ConfigEntry, coordinator, api, camera_id: str, camera_name: str) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        Camera.__init__(self)
        self._entry = entry
        self._api = api
        self._camera_id = camera_id
        self._attr_name = camera_name
        self._attr_content_type = "image/jpeg"
        device_id = str(entry.data.get(CONF_DEVICE_ID) or "remoterelay").strip() or "remoterelay"
        self._attr_unique_id = f"{device_id}-camera-{camera_id}"

    @property
    def available(self) -> bool:
        if not self.coordinator.last_update_success:
            return False
        return self._camera_data() is not None

    async def async_camera_image(self, width: int | None = None, height: int | None = None) -> bytes | None:
        try:
            return await self._api.async_get_camera_snapshot(self._camera_id, width=width, height=height)
        except RemoteRelayApiError as err:
            _LOGGER.debug("RemoteRelay camera snapshot failed for %s: %s", self._camera_id, err)
            return None

    async def stream_source(self) -> str | None:
        camera_data = self._camera_data() or {}
        stream_url = str(camera_data.get("streamUrl") or "").strip()
        if stream_url:
            # Local bridge defaults tuned for low latency in Home Assistant stream pipeline.
            return self._api.build_camera_stream_url(
                self._camera_id,
                width=640,
                height=360,
                fps=15,
            )
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        camera_data = self._camera_data() or {}
        stream_url = str(camera_data.get("streamUrl") or "").strip() or None
        return {
            "camera_id": self._camera_id,
            "camera_type": camera_data.get("cameraType"),
            "snapshot_url": camera_data.get("snapshotUrl"),
            "stream_url": stream_url,
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
