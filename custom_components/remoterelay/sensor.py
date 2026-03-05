"""Sensor entities for RemoteRelay numeric sensors."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ID, CONF_DISPLAY_NAME, DOMAIN


def _normalize_sensor_id(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _resolve_numeric_sensors(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw = data.get("sensors")
    if not isinstance(raw, list):
        return []

    sensors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        sensor_type = str(item.get("sensorType") or "").strip().lower()
        if sensor_type != "number":
            continue
        sensor_id = _normalize_sensor_id(item.get("id"))
        if not sensor_id or sensor_id in seen:
            continue
        seen.add(sensor_id)
        sensors.append(
            {
                "id": sensor_id,
                "name": str(item.get("name") or sensor_id).strip() or sensor_id,
            }
        )
    return sensors


def _find_sensor_data(data: dict[str, Any], sensor_id: str) -> dict[str, Any] | None:
    raw = data.get("sensors")
    if not isinstance(raw, list):
        return None

    for item in raw:
        if not isinstance(item, dict):
            continue
        if _normalize_sensor_id(item.get("id")) == sensor_id:
            return item
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RemoteRelay numeric sensors."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime["coordinator"]

    entities_by_id: dict[str, RemoteRelayNumericSensor] = {}

    @callback
    def _sync_entities() -> None:
        definitions = _resolve_numeric_sensors(coordinator.data or {})
        to_add: list[RemoteRelayNumericSensor] = []
        for definition in definitions:
            sensor_id = str(definition["id"])
            if sensor_id in entities_by_id:
                continue
            entity = RemoteRelayNumericSensor(entry, coordinator, sensor_id, str(definition["name"]))
            entities_by_id[sensor_id] = entity
            to_add.append(entity)
        if to_add:
            async_add_entities(to_add)

    _sync_entities()
    coordinator.async_add_listener(_sync_entities)


class RemoteRelayNumericSensor(CoordinatorEntity, SensorEntity):
    """Numeric sensor mirrored from daemon profile."""

    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, coordinator, sensor_id: str, sensor_name: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._sensor_id = sensor_id
        self._sensor_name = sensor_name
        device_id = str(entry.data.get(CONF_DEVICE_ID) or "remoterelay").strip() or "remoterelay"
        self._attr_unique_id = f"{device_id}-sensor-{sensor_id}"
        self._attr_name = sensor_name

    @property
    def native_value(self) -> float | int | None:
        sensor = self._sensor_data()
        if not isinstance(sensor, dict):
            return None
        value = sensor.get("value")
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @property
    def native_unit_of_measurement(self) -> str | None:
        sensor = self._sensor_data()
        if not isinstance(sensor, dict):
            return None
        unit = str(sensor.get("unit") or "").strip()
        return unit or None

    @property
    def available(self) -> bool:
        sensor = self._sensor_data()
        if not isinstance(sensor, dict):
            return False
        if not self.coordinator.last_update_success:
            return False
        return bool(sensor.get("available", True))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        sensor = self._sensor_data() or {}
        return {
            "sensor_id": self._sensor_id,
            "source": sensor.get("source"),
            "poll_interval_seconds": sensor.get("pollIntervalSeconds"),
            "last_updated_at": sensor.get("lastUpdatedAt"),
            "last_error": sensor.get("lastError"),
            "state_class": sensor.get("stateClass"),
            "device_class": sensor.get("deviceClass"),
        }

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._entry.data.get(CONF_DEVICE_ID))},
            "name": str(self._entry.data.get(CONF_DISPLAY_NAME, "RemoteRelay")),
            "manufacturer": "RemoteRelay",
            "model": "RemoteRelay PC Bridge",
        }

    def _sensor_data(self) -> dict[str, Any] | None:
        data = self.coordinator.data or {}
        return _find_sensor_data(data, self._sensor_id)
