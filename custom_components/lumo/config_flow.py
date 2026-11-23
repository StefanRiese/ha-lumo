"""Config, reauth, reconfigure and options flow of the Lumo integration."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from ipaddress import IPv4Address, ip_address
from typing import Any, NamedTuple

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from . import LumoConfigEntry, base_url
from .api import (
    LumoAuthError,
    LumoClient,
    LumoConnectionError,
    LumoError,
    LumoRateLimitedError,
    LumoSetupRequiredError,
)
from .const import (
    CALENDAR_ALL,
    CALENDAR_FILTERS,
    CONF_ACCOUNTS,
    CONF_ALLOW_HOMEWORK_WRITE,
    CONF_CALENDAR_FILTER,
    CONF_ENABLE_GRADES,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSL,
    DEFAULT_PORT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def normalize_host(host: str) -> str:
    """Strips a pasted scheme, path and port: `http://lumo.local:8080/` -> `lumo.local`."""
    host = host.strip()
    host = re.sub(r"^[a-z][a-z0-9+.-]*://", "", host, flags=re.IGNORECASE)
    host = host.split("/", 1)[0]
    if host.startswith("["):  # [::1] or [::1]:8080
        return host.split("]", 1)[0].lstrip("[")
    if host.count(":") == 1:  # host:port
        host = host.split(":", 1)[0]
    return host


class CannotValidate(Exception):
    """Validation failed; `reason` is the key of the error text."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class Validated(NamedTuple):
    """What a working connection tells: the children and the identity of the server."""

    accounts: list[dict[str, Any]]
    server_id: str | None  # None: a server older than Lumo 0.27 (no UUID)


def legacy_unique_id(host: str, port: int) -> str:
    """The unique id before the server had an identity: its address."""
    return f"{host.strip('[]').lower()}:{port}"


def _server_id(health: dict[str, Any]) -> str | None:
    value = health.get("id")
    return value if isinstance(value, str) and value else None


def _preferred_host(info: ZeroconfServiceInfo) -> str:
    """The IPv4 address if the server announces one (it is the stable one), else the first."""
    for address in info.ip_addresses:
        if isinstance(address, IPv4Address):
            return str(address)
    return info.host


def _is_ip(host: str) -> bool:
    try:
        ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True


async def validate_connection(host: str, port: int, ssl: bool, password: str) -> Validated:
    """Checks that a Lumo server answers and accepts the password."""
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
        client = LumoClient(session, base_url(host, port, ssl), password, timeout=15)
        try:
            health = await client.healthz()
            if not isinstance(health, dict) or health.get("app") != "lumo":
                raise CannotValidate("not_lumo")
            await client.login()
            return Validated(await client.accounts(), _server_id(health))
        except LumoAuthError as err:
            raise CannotValidate("invalid_auth") from err
        except LumoRateLimitedError as err:
            raise CannotValidate("rate_limited") from err
        except LumoSetupRequiredError as err:
            raise CannotValidate("setup_required") from err
        except LumoConnectionError as err:
            raise CannotValidate("cannot_connect") from err
        except (LumoError, ValueError, AttributeError) as err:
            _LOGGER.debug("Unexpected answer from the Lumo server: %s", err)
            raise CannotValidate("not_lumo") from err


def _connection_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=65535)
            ),
            vol.Required(CONF_SSL, default=defaults.get(CONF_SSL, False)): bool,
            vol.Required(CONF_PASSWORD): str,
        }
    )


def _accounts_schema(names: Mapping[str, str], selected: list[str]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_ACCOUNTS, default=selected): vol.All(
                cv.multi_select(dict(names)), vol.Length(min=1)
            )
        }
    )


def _names(accounts: list[dict[str, Any]]) -> dict[str, str]:
    return {a["id"]: a.get("name") or a["id"] for a in accounts}


class LumoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up one Lumo server; the children to follow are chosen in a second step."""

    VERSION = 1

    def __init__(self) -> None:
        self._connection: dict[str, Any] = {}
        self._accounts: list[dict[str, Any]] = []
        self._discovered: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> LumoOptionsFlow:
        return LumoOptionsFlow()

    # --- identity of the server -----------------------------------------------------

    def _abort_if_configured(self, unique_id: str) -> None:
        if any(e.unique_id == unique_id for e in self._async_current_entries(include_ignore=True)):
            raise AbortFlow("already_configured")

    async def _set_unique_id(self, server_id: str | None, fallback: str | None) -> None:
        """The unique id is the UUID of the server (its address for servers without one)."""
        unique_id = server_id or fallback
        if unique_id is None:
            return
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

    # --- new entry ------------------------------------------------------------------

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = normalize_host(user_input[CONF_HOST])
            self._abort_if_configured(legacy_unique_id(host, user_input[CONF_PORT]))
            try:
                self._accounts, server_id = await validate_connection(
                    host, user_input[CONF_PORT], user_input[CONF_SSL], user_input[CONF_PASSWORD]
                )
            except CannotValidate as err:
                errors["base"] = err.reason
            else:
                # The same server reached by another address (IPv4, IPv6, name) has the same id.
                await self._set_unique_id(server_id, legacy_unique_id(host, user_input[CONF_PORT]))
                if not self._accounts:
                    errors["base"] = "no_accounts"
                else:
                    self._connection = {**user_input, CONF_HOST: host}
                    if len(self._accounts) == 1:
                        return self._create([self._accounts[0]["id"]])
                    return await self.async_step_accounts()
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                _connection_schema(user_input or {}), user_input
            ),
            errors=errors,
        )

    # --- discovery (mDNS, `_lumo._tcp`) ----------------------------------------------

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        if discovery_info.properties.get("app") != "lumo":
            return self.async_abort(reason="not_lumo")
        host, port = _preferred_host(discovery_info), discovery_info.port or DEFAULT_PORT
        announced_id = discovery_info.properties.get("id")
        server_id = announced_id if isinstance(announced_id, str) and announced_id else None
        # An entry typed in by hand may use the name instead of the address, and the server is
        # announced with an IPv4 and an IPv6 address: any of them is the same server.
        names = {host.lower(), discovery_info.hostname.rstrip(".").lower()}
        names |= {str(address).lower() for address in discovery_info.ip_addresses}
        for entry in self._async_current_entries():
            if entry.data[CONF_PORT] == port and entry.data[CONF_HOST].strip("[]").lower() in names:
                return self.async_abort(reason="already_configured")
        unique_id = server_id or legacy_unique_id(host, port)
        await self.async_set_unique_id(unique_id)
        entry = self.hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, unique_id)
        # The same server with a new address (DHCP): follow it. An entry typed in with a name
        # keeps its name.
        updates = {CONF_HOST: host} if entry is None or _is_ip(entry.data[CONF_HOST]) else None
        self._abort_if_unique_id_configured(updates=updates)
        self._discovered = {CONF_HOST: host, CONF_PORT: port, CONF_SSL: False}
        self.context["title_placeholders"] = {"host": host}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        host, port = self._discovered[CONF_HOST], self._discovered[CONF_PORT]
        if user_input is not None:
            try:
                self._accounts, server_id = await validate_connection(
                    host, port, False, user_input[CONF_PASSWORD]
                )
            except CannotValidate as err:
                errors["base"] = err.reason
            else:
                await self._set_unique_id(server_id, None)  # the announcement may lack the id
                if not self._accounts:
                    errors["base"] = "no_accounts"
                else:
                    self._connection = {
                        **self._discovered,
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    }
                    if len(self._accounts) == 1:
                        return self._create([self._accounts[0]["id"]])
                    return await self.async_step_accounts()
        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={"host": host, "port": str(port)},
            errors=errors,
        )

    async def async_step_accounts(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        names = _names(self._accounts)
        if user_input is not None:
            return self._create(user_input[CONF_ACCOUNTS])
        return self.async_show_form(
            step_id="accounts", data_schema=_accounts_schema(names, list(names))
        )

    def _create(self, account_ids: list[str]) -> ConfigFlowResult:
        host = self._connection[CONF_HOST]
        return self.async_create_entry(
            title=f"Lumo ({host})",
            data=self._connection,
            options={
                CONF_ACCOUNTS: account_ids,
                CONF_ENABLE_GRADES: False,
                CONF_ALLOW_HOMEWORK_WRITE: False,
            },
        )

    # --- reauth / reconfigure -------------------------------------------------------

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await validate_connection(
                    entry.data[CONF_HOST],
                    entry.data[CONF_PORT],
                    entry.data[CONF_SSL],
                    user_input[CONF_PASSWORD],
                )
            except CannotValidate as err:
                errors["base"] = err.reason
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={"host": entry.data[CONF_HOST]},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = normalize_host(user_input[CONF_HOST])
            try:
                _, server_id = await validate_connection(
                    host, user_input[CONF_PORT], user_input[CONF_SSL], user_input[CONF_PASSWORD]
                )
            except CannotValidate as err:
                errors["base"] = err.reason
            else:
                # The same server (by its id, or for an entry from before the ids by its
                # address) may be reached by another address.
                known = {server_id, legacy_unique_id(host, user_input[CONF_PORT])}
                if entry.unique_id not in known:
                    return self.async_abort(reason="wrong_server")
                new_id = server_id if server_id and server_id != entry.unique_id else None
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=new_id or entry.unique_id,
                    data_updates={**user_input, CONF_HOST: host},
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_connection_schema(user_input or entry.data),
            errors=errors,
        )


class LumoOptionsFlow(OptionsFlow):
    """Children to follow plus the two opt-in switches (both off by default)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry: LumoConfigEntry = self.config_entry  # type: ignore[assignment]
        # All children of the server if the entry is loaded, otherwise only the selected ones.
        runtime = getattr(entry, "runtime_data", None)
        selected: list[str] = entry.options.get(CONF_ACCOUNTS, [])
        if runtime is not None:
            names = _names(list(runtime.server_accounts.values()))
        else:
            names = {account_id: account_id for account_id in selected}
        for account_id in selected:  # keep a selected child that vanished from the server
            names.setdefault(account_id, account_id)

        if user_input is not None:
            return self.async_create_entry(data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_ACCOUNTS): vol.All(cv.multi_select(names), vol.Length(min=1)),
                vol.Required(CONF_ENABLE_GRADES): bool,
                vol.Required(CONF_ALLOW_HOMEWORK_WRITE): bool,
                vol.Required(CONF_CALENDAR_FILTER, default=CALENDAR_ALL): SelectSelector(
                    SelectSelectorConfig(
                        options=list(CALENDAR_FILTERS),
                        translation_key=CONF_CALENDAR_FILTER,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {
                    CONF_ACCOUNTS: selected,
                    CONF_ENABLE_GRADES: entry.options.get(CONF_ENABLE_GRADES, False),
                    CONF_ALLOW_HOMEWORK_WRITE: entry.options.get(CONF_ALLOW_HOMEWORK_WRITE, False),
                    CONF_CALENDAR_FILTER: entry.options.get(CONF_CALENDAR_FILTER, CALENDAR_ALL),
                },
            ),
        )
