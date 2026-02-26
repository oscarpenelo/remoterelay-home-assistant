"""Local HTTP client for the RemoteRelay daemon Home Assistant bridge API."""

from __future__ import annotations

from typing import Any

import aiohttp

from .const import API_HEADER_AUTHORIZATION, API_TIMEOUT_SECONDS


class RemoteRelayApiError(Exception):
    """Base API error."""


class RemoteRelayPairingError(RemoteRelayApiError):
    """Pairing-specific error."""


class RemoteRelayLocalApiClient:
    """Minimal client for the local daemon API."""

    def __init__(self, session: aiohttp.ClientSession, base_url: str, token: str | None = None) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._token = token

    @property
    def base_url(self) -> str:
        return self._base_url

    def with_token(self, token: str) -> "RemoteRelayLocalApiClient":
        return RemoteRelayLocalApiClient(self._session, self._base_url, token)

    async def async_health(self) -> dict[str, Any]:
        return await self._request_json("GET", "/ha/v1/health", authenticated=False)

    async def async_exchange_pairing_code(
        self,
        pairing_code: str,
        integration_instance_id: str,
        integration_name: str = "homeassistant",
    ) -> dict[str, Any]:
        payload = {
            "pairingCode": pairing_code,
            "integrationInstanceId": integration_instance_id,
            "integrationName": integration_name,
            "requestedScopes": ["ha.control"],
        }
        try:
            return await self._request_json(
                "POST",
                "/ha/v1/pairing/exchange",
                json=payload,
                authenticated=False,
            )
        except RemoteRelayApiError as err:
            raise RemoteRelayPairingError(str(err)) from err

    async def async_get_device_profile(self) -> dict[str, Any]:
        return await self._request_json("GET", "/ha/v1/device")

    async def async_send_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request_json("POST", "/ha/v1/commands", json=payload)

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {}
        if authenticated and self._token:
            headers[API_HEADER_AUTHORIZATION] = f"Bearer {self._token}"

        url = f"{self._base_url}{path}"
        timeout = aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS)
        try:
            async with self._session.request(method, url, json=json, headers=headers, timeout=timeout) as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400:
                    raise RemoteRelayApiError(data.get("message", f"HTTP {resp.status}"))
                if not isinstance(data, dict):
                    raise RemoteRelayApiError("Invalid JSON response type.")
                return data
        except aiohttp.ClientError as err:
            raise RemoteRelayApiError(str(err)) from err
