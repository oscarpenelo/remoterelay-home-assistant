"""Small Home Assistant compatibility harness for dependency-free unit tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from typing import Any


COMPONENT_ROOT = (
    Path(__file__).resolve().parents[1] / "custom_components" / "remoterelay"
)


class AbortFlow(Exception):
    """Minimal replacement for Home Assistant's AbortFlow."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ConfigEntryAuthFailed(Exception):
    """Minimal replacement for Home Assistant's auth failure exception."""


class UpdateFailed(Exception):
    """Minimal replacement for Home Assistant's coordinator failure exception."""


class RemoteRelayApiError(Exception):
    """API error shape consumed by the coordinator."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class RemoteRelayPairingError(RemoteRelayApiError):
    """Pairing error shape consumed by the config flow."""


class FakeConfigEntry:
    """Mutable test double for a Home Assistant config entry."""

    def __init__(
        self,
        *,
        data: dict[str, Any],
        entry_id: str = "entry-1",
        title: str = "RemoteRelay PC",
        unique_id: str | None = "device-1",
    ) -> None:
        self.data = dict(data)
        self.entry_id = entry_id
        self.title = title
        self.unique_id = unique_id


class FakeConfigEntriesManager:
    """Record config entry updates made by flows and coordinators."""

    def __init__(self) -> None:
        self.updates: list[tuple[FakeConfigEntry, dict[str, Any]]] = []

    def async_update_entry(
        self,
        entry: FakeConfigEntry,
        *,
        data: dict[str, Any] | None = None,
        title: str | None = None,
    ) -> bool:
        next_data = dict(entry.data if data is None else data)
        changed = next_data != entry.data or (title is not None and title != entry.title)
        entry.data = next_data
        if title is not None:
            entry.title = title
        self.updates.append((entry, next_data))
        return changed


class FakeHass:
    """Minimal Home Assistant object required by the component."""

    def __init__(self) -> None:
        self.config_entries = FakeConfigEntriesManager()
        self.data = {"remoterelay": {"logger": object()}}
        self.session = object()


class FakeConfigFlow:
    """ConfigFlow behavior needed by the production flow under test."""

    handler = ""

    def __init_subclass__(cls, *, domain: str | None = None, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if domain is not None:
            cls.handler = domain

    async def async_set_unique_id(
        self, unique_id: str | None = None, *, raise_on_progress: bool = True
    ) -> None:
        del raise_on_progress
        self.unique_id = unique_id
        self.context["unique_id"] = unique_id

    def _abort_if_unique_id_configured(
        self, updates: dict[str, Any] | None = None, **kwargs: Any
    ) -> None:
        del kwargs
        self.configured_updates = updates
        if self.existing_entry_configured:
            raise AbortFlow("already_configured")

    def _get_reauth_entry(self) -> FakeConfigEntry:
        return self.reauth_entry

    def _abort_if_unique_id_mismatch(self, *, reason: str = "unique_id_mismatch") -> None:
        if self.reauth_entry.unique_id != self.unique_id:
            raise AbortFlow(reason)

    def async_update_reload_and_abort(
        self,
        entry: FakeConfigEntry,
        *,
        data_updates: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        del kwargs
        merged_data = {**entry.data, **data_updates}
        self.hass.config_entries.async_update_entry(entry, data=merged_data)
        self.reload_update = dict(data_updates)
        return {
            "type": "abort",
            "reason": "reauth_successful",
            "entry": entry,
        }

    def async_create_entry(self, *, title: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"type": "create_entry", "title": title, "data": data}

    def async_show_form(self, **kwargs: Any) -> dict[str, Any]:
        return {"type": "form", **kwargs}

    def async_show_menu(self, **kwargs: Any) -> dict[str, Any]:
        return {"type": "menu", **kwargs}

    def async_abort(self, *, reason: str, **kwargs: Any) -> dict[str, Any]:
        return {"type": "abort", "reason": reason, **kwargs}


class FakeOptionsFlow:
    """Placeholder base for the component's options flow."""

    def async_create_entry(self, *, title: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"type": "create_entry", "title": title, "data": data}


class FakeDataUpdateCoordinator:
    """Capture constructor arguments used by the production coordinator."""

    @classmethod
    def __class_getitem__(cls, item: Any) -> type["FakeDataUpdateCoordinator"]:
        del item
        return cls

    def __init__(self, hass: FakeHass, logger: Any, **kwargs: Any) -> None:
        self.hass = hass
        self.logger = logger
        self.coordinator_init_kwargs = kwargs


class _Schema:
    def __init__(self, schema: Any) -> None:
        self.schema = schema


def _identity_marker(key: Any, **kwargs: Any) -> Any:
    del kwargs
    return key


def _register_module(name: str, **attributes: Any) -> ModuleType:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_component_modules() -> tuple[ModuleType, ModuleType, ModuleType]:
    """Load production modules after installing only the HA surfaces they use."""
    voluptuous = _register_module(
        "voluptuous",
        Schema=_Schema,
        Required=_identity_marker,
        Optional=_identity_marker,
    )
    del voluptuous

    homeassistant = _register_module("homeassistant")
    homeassistant.__path__ = []
    config_entries = _register_module(
        "homeassistant.config_entries",
        ConfigEntry=FakeConfigEntry,
        ConfigFlow=FakeConfigFlow,
        OptionsFlow=FakeOptionsFlow,
        SOURCE_REAUTH="reauth",
    )
    homeassistant.config_entries = config_entries
    _register_module(
        "homeassistant.const",
        CONF_HOST="host",
        CONF_NAME="name",
        CONF_PORT="port",
    )
    _register_module(
        "homeassistant.core",
        HomeAssistant=FakeHass,
        callback=lambda function: function,
    )
    _register_module("homeassistant.data_entry_flow", FlowResult=dict)
    exceptions = _register_module(
        "homeassistant.exceptions",
        ConfigEntryAuthFailed=ConfigEntryAuthFailed,
    )
    homeassistant.exceptions = exceptions

    helpers = _register_module("homeassistant.helpers")
    helpers.__path__ = []
    _register_module(
        "homeassistant.helpers.aiohttp_client",
        async_get_clientsession=lambda hass: hass.session,
    )
    _register_module(
        "homeassistant.helpers.update_coordinator",
        DataUpdateCoordinator=FakeDataUpdateCoordinator,
        UpdateFailed=UpdateFailed,
    )

    custom_components = _register_module("custom_components")
    custom_components.__path__ = [str(COMPONENT_ROOT.parent)]
    package = _register_module("custom_components.remoterelay")
    package.__path__ = [str(COMPONENT_ROOT)]

    const_module = _load_module(
        "custom_components.remoterelay.const", COMPONENT_ROOT / "const.py"
    )
    api_module = _register_module(
        "custom_components.remoterelay.api",
        RemoteRelayApiError=RemoteRelayApiError,
        RemoteRelayLocalApiClient=object,
        RemoteRelayPairingError=RemoteRelayPairingError,
    )
    package.const = const_module
    package.api = api_module

    config_flow_module = _load_module(
        "custom_components.remoterelay.config_flow", COMPONENT_ROOT / "config_flow.py"
    )
    coordinator_module = _load_module(
        "custom_components.remoterelay.coordinator", COMPONENT_ROOT / "coordinator.py"
    )
    return const_module, config_flow_module, coordinator_module


def prepare_flow(flow: Any, hass: FakeHass, *, source: str = "user") -> Any:
    """Attach state normally supplied by Home Assistant's flow manager."""
    flow.hass = hass
    flow.context = {"source": source}
    flow.source = source
    flow.unique_id = None
    flow.existing_entry_configured = False
    flow.configured_updates = None
    flow.reauth_entry = None
    flow.reload_update = None
    return flow
