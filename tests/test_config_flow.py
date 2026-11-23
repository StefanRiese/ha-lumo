"""Tests of the config flow, reauth, reconfigure, options and setup of the entry."""

from __future__ import annotations

from ipaddress import ip_address
from urllib.parse import urlparse

import pytest
from homeassistant.config_entries import SOURCE_USER, SOURCE_ZEROCONF, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lumo.config_flow import normalize_host
from custom_components.lumo.const import (
    CONF_ACCOUNTS,
    CONF_ALLOW_HOMEWORK_WRITE,
    CONF_ENABLE_GRADES,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSL,
    DOMAIN,
)

from .fake_server import PASSWORD, FakeLumo


def _conn(url: str, password: str = PASSWORD) -> dict:
    parsed = urlparse(url)
    return {
        CONF_HOST: parsed.hostname,
        CONF_PORT: parsed.port,
        CONF_SSL: False,
        CONF_PASSWORD: password,
    }


def _entry(url: str, *, unique_id: str | None = None, **options) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        data=_conn(url),
        options={
            CONF_ACCOUNTS: ["k3x9ab"],
            CONF_ENABLE_GRADES: False,
            CONF_ALLOW_HOMEWORK_WRITE: False,
            **options,
        },
        unique_id=unique_id or f"{urlparse(url).hostname}:{urlparse(url).port}",
        title="Lumo",
    )


async def _unload(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("lumo.local", "lumo.local"),
        ("  http://lumo.local:8080/ ", "lumo.local"),
        ("https://lumo.example.org/app", "lumo.example.org"),
        ("192.168.1.50:8080", "192.168.1.50"),
        ("[::1]:8080", "::1"),
        ("fe80::1", "fe80::1"),
    ],
)
def test_normalize_host(typed: str, expected: str) -> None:
    assert normalize_host(typed) == expected


async def test_user_flow_with_account_choice(
    hass: HomeAssistant, fake: tuple[FakeLumo, str]
) -> None:
    _, url = fake
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], _conn(url))
    assert result["step_id"] == "accounts"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ACCOUNTS: ["p7q2mz"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PASSWORD] == PASSWORD
    # both switches are off by default
    assert result["options"] == {
        CONF_ACCOUNTS: ["p7q2mz"],
        CONF_ENABLE_GRADES: False,
        CONF_ALLOW_HOMEWORK_WRITE: False,
    }
    entry = result["result"]
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert list(entry.runtime_data.coordinators) == ["p7q2mz"]
    await _unload(hass, entry)


async def test_single_account_skips_the_choice(
    hass: HomeAssistant, fake: tuple[FakeLumo, str]
) -> None:
    server, url = fake
    del server.accounts[1]
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _conn(url))
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_ACCOUNTS] == ["k3x9ab"]
    await hass.async_block_till_done()
    await _unload(hass, result["result"])


@pytest.mark.parametrize(
    ("override", "error"),
    [
        ({CONF_PASSWORD: "wrong"}, "invalid_auth"),
        ({CONF_PORT: 1}, "cannot_connect"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant, fake: tuple[FakeLumo, str], override: dict, error: str
) -> None:
    _, url = fake
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**_conn(url), **override}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_user_flow_no_accounts(hass: HomeAssistant, fake: tuple[FakeLumo, str]) -> None:
    server, url = fake
    server.accounts.clear()
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _conn(url))
    assert result["errors"] == {"base": "no_accounts"}


async def test_user_flow_not_lumo(hass: HomeAssistant, fake: tuple[FakeLumo, str]) -> None:
    server, url = fake
    original = server.healthz

    async def other(request):
        from aiohttp import web

        return web.json_response({"status": "ok", "app": "something else"})

    server.healthz = other  # type: ignore[method-assign]
    await server.stop()
    url = await server.start()
    server.healthz = original  # type: ignore[method-assign]
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _conn(url))
    assert result["errors"] == {"base": "not_lumo"}


async def test_user_flow_already_configured(
    hass: HomeAssistant, fake: tuple[FakeLumo, str]
) -> None:
    _, url = fake
    entry = _entry(url)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _conn(url))
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    await _unload(hass, entry)


async def test_new_entry_is_identified_by_the_server_id(
    hass: HomeAssistant, fake: tuple[FakeLumo, str]
) -> None:
    server, url = fake
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _conn(url))
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ACCOUNTS: ["k3x9ab"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == server.server_id
    await hass.config_entries.async_unload(result["result"].entry_id)


async def test_server_without_id_is_identified_by_its_address(
    hass: HomeAssistant, fake: tuple[FakeLumo, str]
) -> None:
    server, url = fake
    server.server_id = None  # a server older than Lumo 0.27
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _conn(url))
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ACCOUNTS: ["k3x9ab"]}
    )
    parsed = urlparse(url)
    assert result["result"].unique_id == f"{parsed.hostname}:{parsed.port}"
    await hass.config_entries.async_unload(result["result"].entry_id)


async def test_same_server_by_another_address_is_already_configured(
    hass: HomeAssistant, fake: tuple[FakeLumo, str]
) -> None:
    server, url = fake
    # set up under another address (say IPv6 or the name): same server id
    MockConfigEntry(
        domain=DOMAIN,
        data={**_conn(url), CONF_HOST: "lumo.local"},
        unique_id=server.server_id,
        title="Lumo",
    ).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _conn(url))
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_setup_adopts_the_server_id(hass: HomeAssistant, fake: tuple[FakeLumo, str]) -> None:
    server, url = fake
    entry = _entry(url)  # made before servers had an id: unique id is the address
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.unique_id == server.server_id
    await _unload(hass, entry)


async def test_setup_keeps_the_unique_id_of_a_duplicate(
    hass: HomeAssistant, fake: tuple[FakeLumo, str]
) -> None:
    server, url = fake
    first = _entry(url, unique_id=server.server_id)
    first.add_to_hass(hass)
    second = MockConfigEntry(
        domain=DOMAIN,
        data={**_conn(url), CONF_HOST: "localhost"},
        options={CONF_ACCOUNTS: ["k3x9ab"]},
        unique_id="localhost:1",
        title="Lumo",
    )
    second.add_to_hass(hass)
    await hass.config_entries.async_setup(second.entry_id)
    await hass.async_block_till_done()
    assert second.unique_id == "localhost:1"  # not changed to an id another entry has
    await hass.config_entries.async_unload(second.entry_id)


async def test_setup_with_wrong_password_starts_reauth(
    hass: HomeAssistant, fake: tuple[FakeLumo, str]
) -> None:
    _, url = fake
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=_conn(url, "changed"),
        options={CONF_ACCOUNTS: ["k3x9ab"]},
        unique_id="x",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_setup_retries_when_server_is_down(hass: HomeAssistant, socket_enabled: None) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "127.0.0.1", CONF_PORT: 1, CONF_SSL: False, CONF_PASSWORD: "x"},
        options={CONF_ACCOUNTS: ["k3x9ab"]},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_reauth_flow(hass: HomeAssistant, fake: tuple[FakeLumo, str]) -> None:
    _, url = fake
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=_conn(url, "changed"),
        options={CONF_ACCOUNTS: ["k3x9ab"]},
        unique_id="x",
    )
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "still wrong"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: PASSWORD}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == PASSWORD
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    await _unload(hass, entry)


async def test_reconfigure_flow(hass: HomeAssistant, fake: tuple[FakeLumo, str]) -> None:
    _, url = fake
    entry = _entry(url)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    # a different server (another port) is refused
    second = FakeLumo()
    other_url = await second.start()
    try:
        other = _conn(other_url)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], other)
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "wrong_server"
    finally:
        await second.stop()

    result = await entry.start_reconfigure_flow(hass)
    new_password = {**_conn(url), CONF_SSL: False}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], new_password)
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    await _unload(hass, entry)


async def test_reconfigure_to_another_address_of_the_same_server(
    hass: HomeAssistant, fake: tuple[FakeLumo, str]
) -> None:
    server, url = fake
    entry = _entry(url, unique_id=server.server_id)
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, CONF_HOST: "lumo.invalid"},  # not reachable by this name
    )
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _conn(url))
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == urlparse(url).hostname
    assert entry.unique_id == server.server_id


async def test_options_flow_switches_and_reloads(
    hass: HomeAssistant, fake: tuple[FakeLumo, str]
) -> None:
    server, url = fake
    entry = _entry(url)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert "grades" not in [p for _, p in server.requests]

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    # all children of the server are offered, not only the selected one
    accounts_field = next(k for k in result["data_schema"].schema if k == CONF_ACCOUNTS)
    offered = result["data_schema"].schema[accounts_field].validators[0].options
    assert set(offered) == {"k3x9ab", "p7q2mz"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_ACCOUNTS: ["k3x9ab", "p7q2mz"],
            CONF_ENABLE_GRADES: True,
            CONF_ALLOW_HOMEWORK_WRITE: True,
            "calendar_filter": "exams_only",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["calendar_filter"] == "exams_only"
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert set(entry.runtime_data.coordinators) == {"k3x9ab", "p7q2mz"}
    coordinator = entry.runtime_data.coordinators["k3x9ab"]
    assert coordinator.enable_grades and coordinator.allow_homework_write
    assert "grades" in [p for _, p in server.requests]
    await _unload(hass, entry)


async def test_options_reject_empty_selection(
    hass: HomeAssistant, fake: tuple[FakeLumo, str]
) -> None:
    _, url = fake
    entry = _entry(url)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    from homeassistant.data_entry_flow import InvalidData

    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_ACCOUNTS: [], CONF_ENABLE_GRADES: False, CONF_ALLOW_HOMEWORK_WRITE: False},
        )
    hass.config_entries.options.async_abort(result["flow_id"])
    await _unload(hass, entry)


async def test_vanished_account_is_skipped(hass: HomeAssistant, fake: tuple[FakeLumo, str]) -> None:
    _, url = fake
    entry = _entry(url, **{CONF_ACCOUNTS: ["k3x9ab", "gone42"]})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert list(entry.runtime_data.coordinators) == ["k3x9ab"]
    await _unload(hass, entry)


def _discovery(url: str, **overrides):
    from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

    parsed = urlparse(url)
    values = {
        "ip_address": ip_address(parsed.hostname),
        "ip_addresses": [ip_address(parsed.hostname)],
        "hostname": "lumo.local.",
        "name": "Lumo (lumo)._lumo._tcp.local.",
        "port": parsed.port,
        "properties": {"app": "lumo"},
        "type": "_lumo._tcp.local.",
    }
    return ZeroconfServiceInfo(**{**values, **overrides})


async def test_zeroconf_discovery_flow(hass: HomeAssistant, fake: tuple[FakeLumo, str]) -> None:
    _, url = fake
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=_discovery(url)
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "wrong"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: PASSWORD}
    )
    assert result["step_id"] == "accounts"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ACCOUNTS: ["k3x9ab"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    parsed = urlparse(url)
    assert result["data"] == {
        CONF_HOST: parsed.hostname,
        CONF_PORT: parsed.port,
        CONF_SSL: False,
        CONF_PASSWORD: PASSWORD,
    }
    await hass.async_block_till_done()
    await _unload(hass, result["result"])


async def test_zeroconf_ignores_other_services(
    hass: HomeAssistant, fake: tuple[FakeLumo, str]
) -> None:
    _, url = fake
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_ZEROCONF},
        data=_discovery(url, properties={"app": "other"}),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_lumo"


async def test_zeroconf_skips_server_set_up_by_name(
    hass: HomeAssistant, fake: tuple[FakeLumo, str]
) -> None:
    _, url = fake
    parsed = urlparse(url)
    # typed in by hand with the mDNS name instead of the address
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "Lumo.local", CONF_PORT: parsed.port, CONF_SSL: False, CONF_PASSWORD: "x"},
        unique_id=f"lumo.local:{parsed.port}",
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=_discovery(url)
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_zeroconf_skips_server_set_up_by_another_address(hass: HomeAssistant) -> None:
    # set up with the IPv4 address, announced first with its IPv6 address
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.50", CONF_PORT: 8080, CONF_SSL: False, CONF_PASSWORD: "x"},
        unique_id="192.168.1.50:8080",
    )
    entry.add_to_hass(hass)
    info = _discovery(
        "http://192.168.1.50:8080",
        ip_address=ip_address("fd00::50"),
        ip_addresses=[ip_address("fd00::50"), ip_address("192.168.1.50")],
        hostname="other.local.",
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=info
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_zeroconf_recognises_the_server_by_its_id(hass: HomeAssistant) -> None:
    server_id = "0b9b6f1e-2c1d-4c55-9a52-5d2f6a3f3a11"
    named = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "mylumo.home", CONF_PORT: 8080, CONF_SSL: False, CONF_PASSWORD: "x"},
        unique_id=server_id,
    )
    named.add_to_hass(hass)
    info = _discovery(
        "http://192.168.1.60:8080",
        ip_address=ip_address("fd00::60"),
        ip_addresses=[ip_address("fd00::60"), ip_address("192.168.1.60")],
        hostname="other.local.",
        properties={"app": "lumo", "id": server_id},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=info
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert named.data[CONF_HOST] == "mylumo.home"  # a name typed in by hand is kept


async def test_zeroconf_follows_the_ipv4_address_of_a_server_with_an_id(
    hass: HomeAssistant,
) -> None:
    server_id = "0b9b6f1e-2c1d-4c55-9a52-5d2f6a3f3a11"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.50", CONF_PORT: 8080, CONF_SSL: False, CONF_PASSWORD: "x"},
        unique_id=server_id,
    )
    entry.add_to_hass(hass)
    info = _discovery(
        "http://192.168.1.60:8080",
        ip_address=ip_address("fd00::60"),
        ip_addresses=[ip_address("fd00::60"), ip_address("192.168.1.60")],
        hostname="other.local.",
        properties={"app": "lumo", "id": server_id},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=info
    )
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == "192.168.1.60"  # not the IPv6 address


async def test_zeroconf_follows_a_new_address(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.50", CONF_PORT: 8080, CONF_SSL: False, CONF_PASSWORD: "x"},
        unique_id="192.168.1.50:8080",
    )
    entry.add_to_hass(hass)
    info = _discovery("http://192.168.1.60:8080", hostname="other.local.")
    # same unique id only for the same address: a new address is a new flow ...
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=info
    )
    assert result["step_id"] == "discovery_confirm"
    # ... and the same address is recognised
    again = _discovery("http://192.168.1.50:8080", hostname="other.local.")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=again
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
