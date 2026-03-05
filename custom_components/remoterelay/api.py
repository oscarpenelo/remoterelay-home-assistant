"""Local HTTP client for the RemoteRelay daemon Home Assistant bridge API."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

import aiohttp

from .const import API_HEADER_AUTHORIZATION, API_TIMEOUT_SECONDS


class RemoteRelayApiError(Exception):
    """Base API error."""

    def __init__(self, message: str, *, code: str | None = None, status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


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
            raise RemoteRelayPairingError(str(err), code=err.code, status=err.status) from err

    async def async_get_device_profile(self) -> dict[str, Any]:
        return await self._request_json("GET", "/ha/v1/device")

    async def async_send_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request_json("POST", "/ha/v1/commands", json=payload)

    async def async_get_camera_snapshot(
        self,
        camera_id: str,
        *,
        width: int | None = None,
        height: int | None = None,
    ) -> bytes:
        safe_camera_id = quote(str(camera_id or "").strip(), safe="")
        path = f"/ha/v1/cameras/{safe_camera_id}/snapshot"
        params: dict[str, str] = {}
        if width is not None:
            params["width"] = str(int(width))
        if height is not None:
            params["height"] = str(int(height))
        return await self._request_bytes("GET", path, params=params)

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        headers = self._build_headers(authenticated=authenticated)

        url = f"{self._base_url}{path}"
        timeout = aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS)
        try:
            async with self._session.request(
                method,
                url,
                json=json,
                params=params,
                headers=headers,
                timeout=timeout,
            ) as resp:
                try:
                    data = await resp.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError):
                    data = None

                if resp.status >= 400:
                    if isinstance(data, dict):
                        raise RemoteRelayApiError(
                            str(data.get("message") or f"HTTP {resp.status}"),
                            code=str(data.get("code") or "").strip() or None,
                            status=resp.status,
                        )
                    raw_text = await resp.text()
                    raise RemoteRelayApiError(raw_text or f"HTTP {resp.status}", status=resp.status)
                if not isinstance(data, dict):
                    raise RemoteRelayApiError("Invalid JSON response type.")
                return data
        except aiohttp.ClientError as err:
            raise RemoteRelayApiError(str(err)) from err

    async def _request_bytes(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        authenticated: bool = True,
    ) -> bytes:
        headers = self._build_headers(authenticated=authenticated)
        url = f"{self._base_url}{path}"
        timeout = aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS)
        try:
            async with self._session.request(
                method,
                url,
                params=params,
                headers=headers,
                timeout=timeout,
            ) as resp:
                data = await resp.read()
                if resp.status >= 400:
                    error_message = f"HTTP {resp.status}"
                    payload = None
                    if data:
                        try:
                            decoded = data.decode(errors="ignore")
                            parsed = json.loads(decoded)
                            payload = parsed if isinstance(parsed, dict) else None
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            payload = None
                    if isinstance(payload, dict):
                        error_message = str(payload.get("message") or error_message)
                        raise RemoteRelayApiError(
                            error_message,
                            code=str(payload.get("code") or "").strip() or None,
                            status=resp.status,
                        )
                    elif data:
                        error_message = data.decode(errors="ignore") or error_message
                    raise RemoteRelayApiError(error_message, status=resp.status)
                if not data:
                    raise RemoteRelayApiError("Empty binary response.")
                return data
        except aiohttp.ClientError as err:
            raise RemoteRelayApiError(str(err)) from err

    def _build_headers(self, *, authenticated: bool) -> dict[str, str]:
        headers: dict[str, str] = {}
        if authenticated and self._token:
            headers[API_HEADER_AUTHORIZATION] = f"Bearer {self._token}"
        return headers
