"""Platform for sensor integration."""

import datetime
import logging

from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
)
from homeassistant.const import ATTR_ATTRIBUTION
from .const import ATTRIBUTION, DOMAIN, DEFAULT_DETAILS_LIMIT
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = datetime.timedelta(minutes=1)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Add sensors for passed config_entry in HA."""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    connector = entry_data["connector"]

    # Read options, falling back to defaults
    details_limit = DEFAULT_DETAILS_LIMIT
    planned_enabled = True

    # Create the coordinator to manage polling
    # One global coordinator that updates all data once per minute
    if "coordinator" not in entry_data:
        entry_data["coordinator"] = PublicTransportVictoriaGlobalCoordinator(hass, connector)
    coordinator = entry_data["coordinator"]

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    # Create sensors for the first 5 departures
    new_devices = [PublicTransportVictoriaSensor(coordinator, i) for i in range(5)]

    # Create disruptions sensors
    new_devices.append(PublicTransportVictoriaDisruptionsCountSensor(coordinator, current=True))
    new_devices.append(PublicTransportVictoriaDisruptionsDetailSensor(coordinator, current=True, details_limit=details_limit))
    if planned_enabled:
        new_devices.append(PublicTransportVictoriaDisruptionsCountSensor(coordinator, current=False))
        new_devices.append(PublicTransportVictoriaDisruptionsDetailSensor(coordinator, current=False, details_limit=details_limit))

    async_add_entities(new_devices)


class PublicTransportVictoriaGlobalCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Public Transport Victoria data."""

    def __init__(self, hass, connector):
        """Initialize the coordinator."""
        self.connector = connector
        super().__init__(
            hass,
            _LOGGER,
            name="Public Transport Victoria (Global)",
            update_interval=datetime.timedelta(minutes=1),
        )

    async def _async_update_data(self):
        """Fetch all data from Public Transport Victoria."""
        _LOGGER.debug("Fetching all data from Public Transport Victoria API.")
        await self.connector.async_update_all()
        # Return a bundle used by all sensors
        return {
            "departures": self.connector.departures,
            "disruptions_current": self.connector.disruptions_current,
            "disruptions_planned": self.connector.disruptions_planned,
        }


class PublicTransportVictoriaSensor(CoordinatorEntity, Entity):
    """Representation of a Public Transport Victoria Sensor."""

    def __init__(self, coordinator, number):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._number = number
        self._connector = coordinator.connector

    @property
    def state(self):
        """Return the state of the sensor."""
        deps = (self.coordinator.data or {}).get("departures", [])
        if len(deps) > self._number:
            return deps[self._number].get("departure", "No data")
        return "No data"

    @property
    def name(self):
        """Return the name of the sensor."""
        return "{} line to {} from {} {}".format(
            self._connector.route_name,
            self._connector.direction_name,
            self._connector.stop_name,
            self._number,
        )

    @property
    def unique_id(self):
        """Return Unique ID string."""
        return "{}-{}-{}-dep-{}".format(
            self._connector.route,
            self._connector.direction,
            self._connector.stop,
            self._number,
        )

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the sensor."""
        deps = (self.coordinator.data or {}).get("departures", [])
        if len(deps) > self._number:
            attr = deps[self._number]
            attr[ATTR_ATTRIBUTION] = ATTRIBUTION
            return attr
        return {}

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, str(self._connector.route))},
            "name": "{} line".format(self._connector.route_name),
            "manufacturer": "Public Transport Victoria",
            "model": "{} to {} from {}".format(self._connector.route_name, self._connector.direction_name, self._connector.stop_name),
        }

    @property
    def icon(self):
        return "mdi:train" if self._connector.route_type == 0 else (
            "mdi:tram" if self._connector.route_type == 1 else (
                "mdi:bus" if self._connector.route_type == 2 else "mdi:transit-connection"
            )
        )


class PublicTransportVictoriaDisruptionsCountSensor(CoordinatorEntity, Entity):
    """Representation of a disruptions count sensor."""

    def __init__(self, coordinator, current: bool):
        super().__init__(coordinator)
        self._current = current

    @property
    def state(self):
        dis = (self.coordinator.data or {}).get("disruptions_current" if self._current else (self.coordinator.data or {}).get("disruptions_planned"))
        return len(dis or [])

    @property
    def name(self):
        label = "current disruptions" if self._current else "planned disruptions"
        return "{} line {}".format(self.coordinator.connector.route_name, label)

    @property
    def unique_id(self):
        return "{}-{}-{}".format(self.coordinator.connector.route, "current" if self._current else "planned", "disruptions-count")

    @property
    def extra_state_attributes(self):
        attr = {ATTR_ATTRIBUTION: ATTRIBUTION}
        return attr

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, str(self.coordinator.connector.route))},
            "name": "{} line".format(self.coordinator.connector.route_name),
            "manufacturer": "Public Transport Victoria",
        }

    @property
    def icon(self):
        return "mdi:alert" if self._current else "mdi:calendar-clock"


class PublicTransportVictoriaDisruptionsDetailSensor(CoordinatorEntity, Entity):
    """Representation of a disruptions detail sensor."""

    def __init__(self, coordinator, current: bool, details_limit: int):
        super().__init__(coordinator)
        self._current = current
        self._details_limit = details_limit

    @property
    def state(self):
        # A brief state: first disruption title, else 'No disruptions'
        if self.coordinator.data and len(self.coordinator.data) > 0:
            return self.coordinator.data[0].get("title") or "Disruption"
        return "No disruptions"

    @property
    def name(self):
        label = "current disruption details" if self._current else "planned disruption details"
        return "{} line {}".format(self.coordinator.connector.route_name, label)

    @property
    def unique_id(self):
        return "{}-{}-{}".format(self.coordinator.connector.route, "current" if self._current else "planned", "disruptions-detail")

    @property
    def extra_state_attributes(self):
        dis = (self.coordinator.data or {}).get("disruptions_current" if self._current else (self.coordinator.data or {}).get("disruptions_planned")) or []
        disruptions = dis[: self._details_limit]
        attr = {
            ATTR_ATTRIBUTION: ATTRIBUTION,
            "disruptions": disruptions,
            "total_disruptions": len(self.coordinator.data or []),
        }
        return attr

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, str(self.coordinator.connector.route))},
            "name": "{} line".format(self.coordinator.connector.route_name),
            "manufacturer": "Public Transport Victoria",
        }

    @property
    def icon(self):
        return "mdi:note-text"
