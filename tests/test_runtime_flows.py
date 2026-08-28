"""Regression tests for discovery identity, persistence, and reauthentication."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import unittest
from uuid import UUID

from tests.ha_test_harness import (
    AbortFlow,
    COMPONENT_ROOT,
    ConfigEntryAuthFailed,
    FakeConfigEntry,
    FakeHass,
    RemoteRelayApiError,
    RemoteRelayPairingError,
    UpdateFailed,
    load_component_modules,
    prepare_flow,
)


CONST, CONFIG_FLOW, COORDINATOR = load_component_modules()


class FakeRemoteRelayClient:
    """Scriptable local bridge client used by config flow tests."""

    behaviors: dict[str, dict[str, Any]] = {}
    exchanges: list[tuple[str, str, str]] = []

    def __init__(self, session: Any, base_url: str, token: str | None = None) -> None:
        del session, token
        self.base_url = base_url

    async def async_health(self) -> dict[str, Any]:
        value = self.behaviors[self.base_url]["health"]
        if isinstance(value, Exception):
            raise value
        return dict(value)

    async def async_exchange_pairing_code(
        self, pairing_code: str, integration_instance_id: str
    ) -> dict[str, Any]:
        self.exchanges.append(
            (self.base_url, pairing_code, integration_instance_id)
        )
        value = self.behaviors[self.base_url]["exchange"]
        if isinstance(value, Exception):
            raise value
        return dict(value)


def pairing_response(
    *, device_id: str = "device-1", access_token: str = "fresh-token"
) -> dict[str, Any]:
    return {
        "accessToken": access_token,
        "expiresAt": "2099-04-15T08:00:00.000Z",
        "device": {
            "deviceId": device_id,
            "displayName": "Office PC",
            "macAddresses": [{"value": "AA:BB:CC:DD:EE:FF"}],
            "inputSources": [],
            "selectedSourceId": "",
            "protoVersion": "1",
        },
    }


class ConfigFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        FakeRemoteRelayClient.behaviors = {}
        FakeRemoteRelayClient.exchanges = []
        CONFIG_FLOW.RemoteRelayLocalApiClient = FakeRemoteRelayClient
        self.hass = FakeHass()

    def make_flow(self, *, source: str = "user") -> Any:
        return prepare_flow(
            CONFIG_FLOW.RemoteRelayConfigFlow(), self.hass, source=source
        )

    async def test_zeroconf_updates_host_port_and_api_base_url(self) -> None:
        flow = self.make_flow(source="zeroconf")
        flow.existing_entry_configured = True
        discovery = SimpleNamespace(
            properties={"device_id": "device-1", "display_name": "Office PC"},
            name="Office-PC._remoterelay._tcp.local.",
            ip_addresses=["192.0.2.25"],
            ip_address=None,
            host="office-pc.local.",
            hostname=None,
            port=49172,
        )

        with self.assertRaises(AbortFlow) as raised:
            await flow.async_step_zeroconf(discovery)

        self.assertEqual(raised.exception.reason, "already_configured")
        self.assertEqual(
            flow.configured_updates,
            {
                CONFIG_FLOW.CONF_HOST: "192.0.2.25",
                CONFIG_FLOW.CONF_PORT: 49172,
                CONST.CONF_API_BASE_URL: "http://192.0.2.25:49172",
                CONST.CONF_DISPLAY_NAME: "Office PC",
            },
        )

    def test_ipv6_base_url_escapes_scope_identifier(self) -> None:
        self.assertEqual(
            CONFIG_FLOW.RemoteRelayConfigFlow._build_base_url(
                "fe80::1234%eth0", 49171
            ),
            "http://[fe80::1234%25eth0]:49171",
        )

    async def test_initial_pairing_reuses_and_persists_instance_id(self) -> None:
        flow = self.make_flow(source="zeroconf")
        flow._pending_host = "192.0.2.10"
        flow._pending_host_candidates = ["192.0.2.10", "office-pc.local"]
        flow._pending_port = 49171
        flow._discovered_device_id = "device-1"
        flow.unique_id = "device-1"

        first_url = "http://192.0.2.10:49171"
        second_url = "http://office-pc.local:49171"
        FakeRemoteRelayClient.behaviors = {
            first_url: {
                "health": {"pairingEnabled": True, "deviceId": "device-1"},
                "exchange": RemoteRelayPairingError(
                    "temporary failure", code="server_error", status=500
                ),
            },
            second_url: {
                "health": {"pairingEnabled": True, "deviceId": "device-1"},
                "exchange": pairing_response(),
            },
        }

        result = await flow.async_step_pair({"pairing_code": "123456"})

        self.assertEqual(result["type"], "create_entry")
        instance_ids = [item[2] for item in FakeRemoteRelayClient.exchanges]
        self.assertEqual(len(instance_ids), 2)
        self.assertEqual(instance_ids[0], instance_ids[1])
        UUID(instance_ids[0])
        self.assertEqual(
            result["data"][CONST.CONF_INTEGRATION_INSTANCE_ID], instance_ids[0]
        )

    async def test_legacy_reauth_persists_uuid_before_exchange_and_preserves_identity(
        self,
    ) -> None:
        entry = FakeConfigEntry(
            entry_id="legacy-entry-not-a-uuid",
            unique_id="device-1",
            data={
                CONST.CONF_API_BASE_URL: "http://192.0.2.40:49171",
                CONST.CONF_ACCESS_TOKEN: "old-token",
                CONST.CONF_DEVICE_ID: "device-1",
                CONST.CONF_DISPLAY_NAME: "Office PC",
                CONST.CONF_PROTO_VERSION: "1",
            },
        )
        flow = self.make_flow(source="reauth")
        flow.reauth_entry = entry

        form = await flow.async_step_reauth(entry.data)

        self.assertEqual(form["type"], "form")
        self.assertEqual(form["step_id"], "reauth_confirm")
        persisted_instance_id = entry.data[CONST.CONF_INTEGRATION_INSTANCE_ID]
        UUID(persisted_instance_id)
        self.assertNotEqual(persisted_instance_id, entry.entry_id)
        self.assertEqual(len(self.hass.config_entries.updates), 1)

        base_url = "http://192.0.2.40:49171"
        FakeRemoteRelayClient.behaviors = {
            base_url: {
                "health": {"pairingEnabled": True, "deviceId": "device-1"},
                "exchange": pairing_response(access_token="new-token"),
            }
        }
        result = await flow.async_step_reauth_confirm(
            {"pairing_code": "654321"}
        )

        self.assertEqual(result["reason"], "reauth_successful")
        self.assertEqual(entry.unique_id, "device-1")
        self.assertEqual(entry.data[CONST.CONF_DEVICE_ID], "device-1")
        self.assertEqual(entry.data[CONST.CONF_ACCESS_TOKEN], "new-token")
        self.assertEqual(
            entry.data[CONST.CONF_TOKEN_EXPIRES_AT],
            "2099-04-15T08:00:00.000Z",
        )
        self.assertEqual(
            entry.data[CONST.CONF_INTEGRATION_INSTANCE_ID], persisted_instance_id
        )
        self.assertEqual(
            FakeRemoteRelayClient.exchanges[0][2], persisted_instance_id
        )

    async def test_reauth_reuses_existing_instance_id(self) -> None:
        instance_id = "73c53874-d018-4fdb-8904-f8ebf84c266f"
        entry = FakeConfigEntry(
            unique_id="device-1",
            data={
                CONFIG_FLOW.CONF_HOST: "office-pc.local",
                CONFIG_FLOW.CONF_PORT: 49171,
                CONST.CONF_API_BASE_URL: "http://office-pc.local:49171",
                CONST.CONF_ACCESS_TOKEN: "old-token",
                CONST.CONF_DEVICE_ID: "device-1",
                CONST.CONF_INTEGRATION_INSTANCE_ID: instance_id,
            },
        )
        flow = self.make_flow(source="reauth")
        flow.reauth_entry = entry
        await flow.async_step_reauth(entry.data)
        self.assertEqual(flow._integration_instance_id, instance_id)
        self.assertEqual(self.hass.config_entries.updates, [])

    async def test_reauth_rejects_wrong_device_before_consuming_code(self) -> None:
        entry = FakeConfigEntry(
            unique_id="device-1",
            data={
                CONFIG_FLOW.CONF_HOST: "192.0.2.50",
                CONFIG_FLOW.CONF_PORT: 49171,
                CONST.CONF_API_BASE_URL: "http://192.0.2.50:49171",
                CONST.CONF_ACCESS_TOKEN: "old-token",
                CONST.CONF_DEVICE_ID: "device-1",
                CONST.CONF_INTEGRATION_INSTANCE_ID: "73c53874-d018-4fdb-8904-f8ebf84c266f",
            },
        )
        flow = self.make_flow(source="reauth")
        flow.reauth_entry = entry
        await flow.async_step_reauth(entry.data)
        FakeRemoteRelayClient.behaviors = {
            "http://192.0.2.50:49171": {
                "health": {"pairingEnabled": True, "deviceId": "device-2"},
                "exchange": pairing_response(device_id="device-2"),
            }
        }

        result = await flow.async_step_reauth_confirm(
            {"pairing_code": "123456"}
        )

        self.assertEqual(result, {"type": "abort", "reason": "wrong_device"})
        self.assertEqual(FakeRemoteRelayClient.exchanges, [])
        self.assertEqual(entry.unique_id, "device-1")
        self.assertEqual(entry.data[CONST.CONF_DEVICE_ID], "device-1")
        self.assertEqual(entry.data[CONST.CONF_ACCESS_TOKEN], "old-token")

    async def test_invalid_reauth_code_does_not_mutate_entry(self) -> None:
        entry = FakeConfigEntry(
            unique_id="device-1",
            data={
                CONFIG_FLOW.CONF_HOST: "192.0.2.60",
                CONFIG_FLOW.CONF_PORT: 49171,
                CONST.CONF_API_BASE_URL: "http://192.0.2.60:49171",
                CONST.CONF_ACCESS_TOKEN: "old-token",
                CONST.CONF_DEVICE_ID: "device-1",
                CONST.CONF_INTEGRATION_INSTANCE_ID: "73c53874-d018-4fdb-8904-f8ebf84c266f",
            },
        )
        original_data = dict(entry.data)
        flow = self.make_flow(source="reauth")
        flow.reauth_entry = entry
        await flow.async_step_reauth(entry.data)
        FakeRemoteRelayClient.behaviors = {
            "http://192.0.2.60:49171": {
                "health": {"pairingEnabled": True, "deviceId": "device-1"},
                "exchange": RemoteRelayPairingError(
                    "bad code", code="invalid_pairing_code", status=401
                ),
            }
        }

        result = await flow.async_step_reauth_confirm(
            {"pairing_code": "wrong"}
        )

        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"], {"base": "invalid_auth"})
        self.assertEqual(entry.data, original_data)


class CoordinatorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.hass = FakeHass()
        self.entry = FakeConfigEntry(
            unique_id="device-1",
            data={CONST.CONF_DEVICE_ID: "device-1"},
        )

    def make_coordinator(self, error: RemoteRelayApiError) -> Any:
        class FailingApi:
            async def async_get_device_profile(self) -> dict[str, Any]:
                raise error

        return COORDINATOR.RemoteRelayCoordinator(
            self.hass, self.entry, FailingApi()
        )

    async def test_401_raises_config_entry_auth_failed(self) -> None:
        coordinator = self.make_coordinator(
            RemoteRelayApiError("unauthorized", status=401)
        )
        self.assertIs(
            coordinator.coordinator_init_kwargs["config_entry"], self.entry
        )

        with self.assertRaises(ConfigEntryAuthFailed):
            await coordinator._async_update_data()

    async def test_non_auth_api_error_remains_update_failed(self) -> None:
        coordinator = self.make_coordinator(
            RemoteRelayApiError("server failure", status=500)
        )

        with self.assertRaises(UpdateFailed):
            await coordinator._async_update_data()

    async def test_profile_rename_updates_config_entry_data_and_title(self) -> None:
        class RenamedDeviceApi:
            async def async_get_device_profile(self) -> dict[str, Any]:
                return {
                    "deviceId": "device-1",
                    "displayName": "Windows Server",
                }

        self.entry.title = "Current PC"
        self.entry.data[CONST.CONF_DISPLAY_NAME] = "Current PC"
        coordinator = COORDINATOR.RemoteRelayCoordinator(
            self.hass, self.entry, RenamedDeviceApi()
        )

        profile = await coordinator._async_update_data()

        self.assertEqual(profile["displayName"], "Windows Server")
        self.assertEqual(
            self.entry.data[CONST.CONF_DISPLAY_NAME], "Windows Server"
        )
        self.assertEqual(self.entry.title, "Windows Server")
        self.assertEqual(self.entry.unique_id, "device-1")
        self.assertEqual(len(self.hass.config_entries.updates), 1)

    async def test_device_identity_mismatch_is_not_persisted(self) -> None:
        class WrongDeviceApi:
            async def async_get_device_profile(self) -> dict[str, Any]:
                return {"deviceId": "device-2", "displayName": "Wrong PC"}

        original_data = dict(self.entry.data)
        coordinator = COORDINATOR.RemoteRelayCoordinator(
            self.hass, self.entry, WrongDeviceApi()
        )

        with self.assertRaises(UpdateFailed) as raised:
            await coordinator._async_update_data()

        self.assertIn("identity mismatch", str(raised.exception))
        self.assertEqual(self.entry.unique_id, "device-1")
        self.assertEqual(self.entry.data, original_data)
        self.assertEqual(self.hass.config_entries.updates, [])


class MetadataTests(unittest.TestCase):
    def test_reauth_translations_are_complete(self) -> None:
        paths = [
            COMPONENT_ROOT / "strings.json",
            *(COMPONENT_ROOT / "translations").glob("*.json"),
        ]
        for path in paths:
            with self.subTest(path=path.name):
                payload = json.loads(path.read_text(encoding="utf-8"))
                config = payload["config"]
                self.assertIn("reauth_confirm", config["step"])
                self.assertIn("reauth_successful", config["abort"])
                self.assertIn("wrong_device", config["abort"])

    def test_hacs_declares_supported_home_assistant_version(self) -> None:
        hacs_path = COMPONENT_ROOT.parents[1] / "hacs.json"
        payload = json.loads(hacs_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["homeassistant"], "2024.11.0")


if __name__ == "__main__":
    unittest.main()
