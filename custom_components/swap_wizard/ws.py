"""Comandi WebSocket usati dal pannello. Tutti riservati agli amministratori."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from .const import BRANCHES, DATA_MANAGER, DOMAIN
from .journal import JournalError
from .manager import SwapError, SwapManager
from .planner import PlanError, list_devices, propose_device_swap, propose_entity_swap

_MAPPING = vol.Schema(
    {
        vol.Required("kind"): str,
        vol.Required("old"): str,
        vol.Required("new"): str,
        vol.Optional("note"): vol.Any(str, None),
    },
    extra=vol.ALLOW_EXTRA,
)
_MAPPINGS = [_MAPPING]
_ERRORS = (ValueError, JournalError, SwapError, PlanError)
_BRANCH = vol.In(BRANCHES)


def _manager(hass: HomeAssistant) -> SwapManager:
    return hass.data[DOMAIN][DATA_MANAGER]


async def _respond(connection, msg, awaitable) -> None:
    try:
        connection.send_result(msg["id"], await awaitable)
    except _ERRORS as err:
        connection.send_error(msg["id"], "swap_error", str(err))


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "swap_wizard/devices"})
@websocket_api.async_response
async def ws_devices(hass, connection, msg) -> None:
    connection.send_result(msg["id"], list_devices(hass))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "swap_wizard/propose_device",
        vol.Required("old_device_id"): str,
        vol.Required("new_device_id"): str,
    }
)
@websocket_api.async_response
async def ws_propose_device(hass, connection, msg) -> None:
    try:
        connection.send_result(
            msg["id"], propose_device_swap(hass, msg["old_device_id"], msg["new_device_id"])
        )
    except _ERRORS as err:
        connection.send_error(msg["id"], "swap_error", str(err))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "swap_wizard/propose_entity",
        vol.Required("old"): str,
        vol.Required("new"): str,
    }
)
@websocket_api.async_response
async def ws_propose_entity(hass, connection, msg) -> None:
    try:
        connection.send_result(msg["id"], propose_entity_swap(hass, msg["old"], msg["new"]))
    except _ERRORS as err:
        connection.send_error(msg["id"], "swap_error", str(err))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "swap_wizard/preview",
        vol.Required("mappings"): _MAPPINGS,
        vol.Optional("hints", default=[]): [str],
        vol.Optional("include_dashboards", default=False): bool,
        vol.Optional("branch", default="ha"): _BRANCH,
        vol.Optional("nodered_path", default=""): str,
    }
)
@websocket_api.async_response
async def ws_preview(hass, connection, msg) -> None:
    await _respond(
        connection,
        msg,
        _manager(hass).async_preview(
            msg["mappings"], msg["hints"], msg["include_dashboards"], msg["branch"], msg["nodered_path"]
        ),
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "swap_wizard/apply",
        vol.Required("mappings"): _MAPPINGS,
        vol.Optional("hints", default=[]): [str],
        vol.Optional("include_dashboards", default=False): bool,
        vol.Required("token"): str,
        vol.Required("files"): [str],
        vol.Required("backup"): bool,
        vol.Optional("title", default=""): str,
        vol.Optional("note", default=""): str,
        vol.Optional("branch", default="ha"): _BRANCH,
        vol.Optional("nodered_path", default=""): str,
        vol.Optional("restart_nodered", default=False): bool,
        vol.Optional("nodered_addon", default=""): str,
    }
)
@websocket_api.async_response
async def ws_apply(hass, connection, msg) -> None:
    await _respond(
        connection,
        msg,
        _manager(hass).async_apply(
            msg["mappings"],
            msg["hints"],
            msg["include_dashboards"],
            msg["token"],
            msg["files"],
            msg["backup"],
            msg["title"],
            msg["note"],
            msg["branch"],
            msg["nodered_path"],
            msg["restart_nodered"],
            msg["nodered_addon"],
        ),
    )


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "swap_wizard/history"})
@websocket_api.async_response
async def ws_history(hass, connection, msg) -> None:
    await _respond(connection, msg, _manager(hass).async_history())


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "swap_wizard/operation",
        vol.Required("operation_id"): str,
        vol.Optional("branch", default="ha"): _BRANCH,
    }
)
@websocket_api.async_response
async def ws_operation(hass, connection, msg) -> None:
    await _respond(connection, msg, _manager(hass).async_operation(msg["operation_id"], msg["branch"]))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "swap_wizard/rollback",
        vol.Required("operation_id"): str,
        vol.Optional("force", default=False): bool,
        vol.Optional("branch", default="ha"): _BRANCH,
        vol.Optional("restart_nodered", default=False): bool,
        vol.Optional("nodered_addon", default=""): str,
    }
)
@websocket_api.async_response
async def ws_rollback(hass, connection, msg) -> None:
    await _respond(
        connection,
        msg,
        _manager(hass).async_rollback(
            msg["operation_id"], msg["force"], msg["branch"], msg["restart_nodered"], msg["nodered_addon"]
        ),
    )


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "swap_wizard/nodered_detect"})
@websocket_api.async_response
async def ws_nodered_detect(hass, connection, msg) -> None:
    await _respond(connection, msg, _manager(hass).async_nodered_detect())


def async_register(hass: HomeAssistant) -> None:
    for handler in (
        ws_devices,
        ws_propose_device,
        ws_propose_entity,
        ws_preview,
        ws_apply,
        ws_history,
        ws_operation,
        ws_rollback,
        ws_nodered_detect,
    ):
        websocket_api.async_register_command(hass, handler)
