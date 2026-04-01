"""Camera entities for RemoteRelay webcam/screen snapshots and direct MJPEG live view."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
from aiohttp import web
from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
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
        # Keep camera entities available even if one coordinator refresh fails.
        # Streaming/snapshots can still work while /device polling is intermittent.
        return True

    async def async_camera_image(self, width: int | None = None, height: int | None = None) -> bytes | None:
        try:
            return await self._api.async_get_camera_snapshot(self._camera_id, width=width, height=height)
        except RemoteRelayApiError as err:
            _LOGGER.debug("RemoteRelay camera snapshot failed for %s: %s", self._camera_id, err)
            return None

    async def stream_source(self) -> str | None:
        return self._api.build_camera_stream_url(self._camera_id, stream_format="mjpeg")

    async def handle_async_mjpeg_stream(self, request: web.Request) -> web.StreamResponse | None:
        stream_url = self._api.build_camera_stream_url(self._camera_id, stream_format="mjpeg")
        websession = async_get_clientsession(self.hass)
        try:
            async with websession.get(stream_url) as upstream:
                if upstream.status >= 400:
                    body = await upstream.text()
                    return web.Response(
                        status=upstream.status,
                        text=body or f"Upstream MJPEG stream failed with status {upstream.status}",
                    )

                response = web.StreamResponse(
                    status=upstream.status,
                    headers={
                        "Content-Type": upstream.headers.get(
                            "Content-Type",
                            "multipart/x-mixed-replace; boundary=ffmpeg",
                        ),
                        "Cache-Control": "no-store",
                        "Pragma": "no-cache",
                    },
                )
                await response.prepare(request)

                async for chunk in upstream.content.iter_chunked(64 * 1024):
                    if not chunk:
                        continue
                    await response.write(chunk)

                await response.write_eof()
                return response
        except aiohttp.ClientError as err:
            _LOGGER.debug("RemoteRelay MJPEG stream failed for %s: %s", self._camera_id, err)
            return None
        except (asyncio.CancelledError, ConnectionResetError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        camera_data = self._camera_data() or {}
        stream_url = (
            str(camera_data.get("streamUrl") or "").strip()
            or f"/ha/v1/cameras/{self._camera_id}/stream.mjpeg"
        )
        snapshot_url = str(camera_data.get("snapshotUrl") or "").strip() or f"/ha/v1/cameras/{self._camera_id}/snapshot"
        return {
            "camera_id": self._camera_id,
            "camera_type": camera_data.get("cameraType"),
            "capture_enabled": camera_data.get("captureEnabled", True),
            "snapshot_url": snapshot_url,
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
