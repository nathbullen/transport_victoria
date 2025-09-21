"""Binary sensors for Public Transport Victoria disruptions."""
import datetime
import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import ATTR_ATTRIBUTION

from .const import ATTRIBUTION, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up binary sensors for Public Transport Victoria from a config entry."""
    connector = hass.data[DOMAIN][config_entry.entry_id]

    # Reuse the current disruptions coordinator from sensors if available
    # If not available, we simply won't create the binary sensor here.
    # For simplicity, rely on the count/detail sensors' coordinator to exist.
    # Users who disable planned sensors still have current coordinator.
    from .sensor import PublicTransportVictoriaDisruptionsCoordinator

    try:
        # Create a lightweight coordinator with default 15 minute refresh if needed
        coordinator = PublicTransportVictoriaDisruptionsCoordinator(hass, connector, 0, 15)
        await coordinator.async_config_entry_first_refresh()
        async_add_entities([PTVCurrentDisruptionsBinarySensor(coordinator)])
    except Exception as err:
        _LOGGER.debug("Skipping binary sensor setup: %s", err)


class PTVCurrentDisruptionsBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor that is on when there are current disruptions."""

    def __init__(self, coordinator):
        super().__init__(coordinator)

    @property
    def is_on(self):
        return bool(self.coordinator.data)

    @property
    def name(self):
        return "{} line current disruption active".format(self.coordinator.connector.route_name)

    @property
    def unique_id(self):
        return "{}-current-disruptions-binary".format(self.coordinator.connector.route)

    @property
    def extra_state_attributes(self):
        return {ATTR_ATTRIBUTION: ATTRIBUTION}

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, str(self.coordinator.connector.route))},
            "name": "{} line".format(self.coordinator.connector.route_name),
            "manufacturer": "Public Transport Victoria",
        }

    @property
    def icon(self):
        return "mdi:alert"


