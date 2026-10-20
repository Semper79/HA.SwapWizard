"""Swap Wizard: sostituzione guidata di telefoni, dispositivi ed entita' in Home Assistant."""
from __future__ import annotations

from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import ws
from .const import (
    DATA_MANAGER,
    DATA_SETUP_DONE,
    DOMAIN,
    PANEL_URL_PATH,
    PANEL_WEBCOMPONENT,
    STATIC_URL,
    VERSION,
)
from .manager import SwapManager


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = hass.data.setdefault(DOMAIN, {})
    data[DATA_MANAGER] = SwapManager(hass, entry)

    if not data.get(DATA_SETUP_DONE):
        ws.async_register(hass)
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "frontend"), False)]
        )
        data[DATA_SETUP_DONE] = True

    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=PANEL_WEBCOMPONENT,
        sidebar_title="Swap Wizard",
        sidebar_icon="mdi:swap-horizontal-bold",
        module_url=f"{STATIC_URL}/panel.js?v={VERSION}",
        require_admin=True,
        embed_iframe=False,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    frontend.async_remove_panel(hass, PANEL_URL_PATH)
    hass.data.get(DOMAIN, {}).pop(DATA_MANAGER, None)
    return True
