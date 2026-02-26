"""RemoteRelay Home Assistant integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RemoteRelayLocalApiClient
from .const import CONF_ACCESS_TOKEN, CONF_API_BASE_URL, DOMAIN
from .coordinator import RemoteRelayCoordinator

PLATFORMS: list[Platform] = [Platform.MEDIA_PLAYER, Platform.REMOTE]

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration from YAML (unused, config-entry only)."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("logger", _LOGGER)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up RemoteRelay from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("logger", _LOGGER)

    session = async_get_clientsession(hass)
    api = RemoteRelayLocalApiClient(
        session=session,
        base_url=entry.data[CONF_API_BASE_URL],
        token=entry.data.get(CONF_ACCESS_TOKEN),
    )
    coordinator = RemoteRelayCoordinator(hass, entry, api)
    await coordinator.async_refresh()
    if not coordinator.last_update_success:
        _LOGGER.warning(
            "RemoteRelay daemon is currently unreachable during setup for %s. "
            "Entity will still load to allow Wake-on-LAN.",
            entry.title,
        )

    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "logger": _LOGGER,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok
