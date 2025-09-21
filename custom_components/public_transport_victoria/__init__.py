"""Public Transport Victoria integration."""
import asyncio
import logging
import voluptuous as vol


from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_ID
from homeassistant.core import HomeAssistant

from .const import (
    CONF_DIRECTION, CONF_DIRECTION_NAME, CONF_ROUTE, CONF_ROUTE_NAME,
    CONF_ROUTE_TYPE, CONF_ROUTE_TYPE_NAME, CONF_STOP, CONF_STOP_NAME, DOMAIN,
    OPT_PLANNED_ENABLED, OPT_DEPARTURES_SCAN_MIN, OPT_DISRUPTIONS_SCAN_MIN, OPT_DETAILS_LIMIT,
    DEFAULT_PLANNED_ENABLED, DEFAULT_DEPARTURES_SCAN_MIN, DEFAULT_DISRUPTIONS_SCAN_MIN, DEFAULT_DETAILS_LIMIT,
)
from .PublicTransportVictoria.public_transport_victoria import Connector


# Define the logger
_LOGGER = logging.getLogger(__name__)


PLATFORMS = ["sensor", "binary_sensor"]


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Public Transport Victoria component."""
    hass.data.setdefault(DOMAIN, {})

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Public Transport Victoria from a config entry."""
    connector = Connector(
        hass,
        entry.data[CONF_ID],
        entry.data[CONF_API_KEY],
        entry.data[CONF_ROUTE_TYPE],
        entry.data[CONF_ROUTE],
        entry.data[CONF_DIRECTION],
        entry.data[CONF_STOP],
        entry.data[CONF_ROUTE_TYPE_NAME],
        entry.data[CONF_ROUTE_NAME],
        entry.data[CONF_DIRECTION_NAME],
        entry.data[CONF_STOP_NAME],
    )
    await connector._init()

    hass.data[DOMAIN][entry.entry_id] = connector

    # Use the new async_forward_entry_setups method

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload entities when options are updated
    async def _update_listener(hass: HomeAssistant, updated_entry: ConfigEntry):
        await hass.config_entries.async_reload(updated_entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in PLATFORMS
            ]
        )
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
