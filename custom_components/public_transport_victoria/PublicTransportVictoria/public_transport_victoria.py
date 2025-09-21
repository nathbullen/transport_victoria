"""Public Transport Victoria API connector."""
import aiohttp
import asyncio
import datetime
import hmac
import logging
from hashlib import sha1

from homeassistant.util import Throttle
from homeassistant.util.dt import get_time_zone


BASE_URL = "https://timetableapi.ptv.vic.gov.au"
DEPARTURES_PATH = "/v3/departures/route_type/{}/stop/{}/route/{}?direction_id={}&max_results={}"
DIRECTIONS_PATH = "/v3/directions/route/{}"
MIN_TIME_BETWEEN_UPDATES = datetime.timedelta(minutes=2)
MAX_RESULTS = 5
ROUTE_TYPES_PATH = "/v3/route_types"
ROUTES_PATH = "/v3/routes?route_types={}"
STOPS_PATH = "/v3/stops/route/{}/route_type/{}"
DISRUPTIONS_PATH = "/v3/disruptions?route_ids={}&route_types={}&disruption_status={}"

_LOGGER = logging.getLogger(__name__)

class Connector:
    """Public Transport Victoria connector."""

    manufacturer = "Demonstration Corp"

    def __init__(self, hass, id, api_key, route_type=None, route=None,
                 direction=None, stop=None, route_type_name=None,
                 route_name=None, direction_name=None, stop_name=None):
        """Init Public Transport Victoria connector."""
        self.hass = hass
        self.id = id
        self.api_key = api_key
        self.route_type = route_type
        self.route = route
        self.direction = direction
        self.stop = stop
        self.route_type_name = route_type_name
        self.route_name = route_name
        self.direction_name = direction_name
        self.stop_name = stop_name
        self.disruptions_current = []
        self.disruptions_planned = []

    async def _init(self):
        """Async Init Public Transport Victoria connector."""
        self.departures_path = DEPARTURES_PATH.format(
            self.route_type, self.stop, self.route, self.direction, MAX_RESULTS
        )
        await self.async_update()

    async def async_route_types(self):
        """Get route types from Public Transport Victoria API."""
        url = build_URL(self.id, self.api_key, ROUTE_TYPES_PATH)

        async with aiohttp.ClientSession() as session:
            response = await session.get(url)

        if response is not None and response.status == 200:
            response = await response.json()
            _LOGGER.debug(response)
            route_types = {}
            for r in response["route_types"]:
                route_types[r["route_type"]] = r["route_type_name"]

            return route_types

    async def async_routes(self, route_type):
        """Get routes from Public Transport Victoria API."""
        url = build_URL(self.id, self.api_key, ROUTES_PATH.format(route_type))

        async with aiohttp.ClientSession() as session:
            response = await session.get(url)

        if response is not None and response.status == 200:
            response = await response.json()
            _LOGGER.debug(response)
            routes = {}
            for r in response["routes"]:
                routes[r["route_id"]] = r["route_name"]

            self.route_type = route_type

            return routes

    async def async_directions(self, route):
        """Get directions from Public Transport Victoria API."""
        url = build_URL(self.id, self.api_key, DIRECTIONS_PATH.format(route))

        async with aiohttp.ClientSession() as session:
            response = await session.get(url)

        if response is not None and response.status == 200:
            response = await response.json()
            _LOGGER.debug(response)
            directions = {}
            for r in response["directions"]:
                directions[r["direction_id"]] = r["direction_name"]

            self.route = route

            return directions

    async def async_stops(self, route):
        """Get stops from Public Transport Victoria API."""
        url = build_URL(self.id, self.api_key, STOPS_PATH.format(route, self.route_type))

        async with aiohttp.ClientSession() as session:
            response = await session.get(url)

        if response is not None and response.status == 200:
            response = await response.json()
            _LOGGER.debug(response)
            stops = {}
            for r in response["stops"]:
                stops[r["stop_id"]] = r["stop_name"]

            self.route = route

            return stops

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self):
        """Update the departure information."""
        url = build_URL(self.id, self.api_key, self.departures_path)

        async with aiohttp.ClientSession() as session:
            response = await session.get(url)

        if response is not None and response.status == 200:
            response = await response.json()
            _LOGGER.debug(response)
            self.departures = []
            for r in response["departures"]:
                if r["estimated_departure_utc"] is not None:
                    r["departure"] = convert_utc_to_local(
                        r["estimated_departure_utc"], self.hass
                        )                
                else:
                    r["departure"] = convert_utc_to_local(
                        r["scheduled_departure_utc"], self.hass
                        )
                self.departures.append(r)

        for departure in self.departures:
            _LOGGER.debug(departure)

    async def async_update_disruptions(self, disruption_status: int):
        """Update disruptions for the configured route.

        disruption_status: 0 = current, 1 = planned
        """
        # Build disruptions query filtering to the configured route and type
        disruptions_path = DISRUPTIONS_PATH.format(self.route, self.route_type, disruption_status)
        url = build_URL(self.id, self.api_key, disruptions_path)

        async with aiohttp.ClientSession() as session:
            response = await session.get(url)

        if response is not None and response.status == 200:
            response = await response.json()
            _LOGGER.debug(response)

            # Normalise disruptions list from possible response shapes
            disruptions_raw = []
            if isinstance(response.get("disruptions"), list):
                disruptions_raw = response.get("disruptions", [])
            elif isinstance(response.get("disruptions"), dict):
                # Combine all lists under disruptions dict
                for value in response.get("disruptions", {}).values():
                    if isinstance(value, list):
                        disruptions_raw.extend(value)

            # Store a trimmed disruption object for attributes
            normalised = []
            for d in disruptions_raw:
                try:
                    normalised.append({
                        "disruption_id": d.get("disruption_id"),
                        "title": d.get("title"),
                        "description": d.get("description"),
                        "disruption_status": d.get("disruption_status"),
                        "from_date": d.get("from_date") or d.get("from_time"),
                        "to_date": d.get("to_date") or d.get("to_time"),
                        "last_updated": d.get("last_updated"),
                        "url": d.get("url") or d.get("url_web"),
                        "routes": [r.get("route_id") for r in d.get("routes", []) if isinstance(r, dict)],
                    })
                except Exception as err:
                    _LOGGER.debug("Error normalising disruption: %s", err)

            if disruption_status == 0:
                self.disruptions_current = normalised
            else:
                self.disruptions_planned = normalised

        if disruption_status == 0:
            for disruption in self.disruptions_current:
                _LOGGER.debug(disruption)
        else:
            for disruption in self.disruptions_planned:
                _LOGGER.debug(disruption)

        return self.disruptions_current if disruption_status == 0 else self.disruptions_planned

def build_URL(id, api_key, request):
    request = request + ('&' if ('?' in request) else '?')
    raw = request + 'devid={}'.format(id)
    hashed = hmac.new(api_key.encode('utf-8'), raw.encode('utf-8'), sha1)
    signature = hashed.hexdigest()
    url = BASE_URL + raw + '&signature={}'.format(signature)
    _LOGGER.debug(url)
    return url

def convert_utc_to_local(utc, hass):
    """Convert UTC to Home Assistant local time."""
    d = datetime.datetime.strptime(utc, "%Y-%m-%dT%H:%M:%SZ")
    # Get the Home Assistant configured time zone
    local_tz = get_time_zone(hass.config.time_zone)
    # Convert the time to the Home Assistant time zone
    d = d.replace(tzinfo=datetime.timezone.utc).astimezone(local_tz)
    return d.strftime("%I:%M %p")
