"""Small, dependency-free adapters for OpenStreetMap and OpenWeather.

Secrets are intentionally read only inside OpenWeatherAdapter and are never
returned in records, exceptions, or LangGraph state.
"""

import json
import os
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_LOCATION = "Washtenaw County, Michigan, USA"
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
OPENWEATHER_CURRENT_URL = "https://api.openweathermap.org/data/2.5/weather"


class AdapterError(RuntimeError):
    """A source returned a permanent or otherwise actionable error."""


class RateLimitError(AdapterError):
    """A source returned HTTP 429, optionally with a retry-after estimate."""

    def __init__(self, retry_after_seconds: Optional[int] = None):
        self.retry_after_seconds = retry_after_seconds
        super().__init__("Source rate limit reached")


class AccessError(AdapterError):
    """A source rejected the request because of authentication or access rules."""


def _request_json(url: str, params: dict, headers: dict) -> object:
    request = Request(
        "{}?{}".format(url, urlencode(params)),
        headers=headers,
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        if error.code == 429:
            retry_after = error.headers.get("Retry-After")
            try:
                retry_after_seconds = int(retry_after) if retry_after else None
            except ValueError:
                retry_after_seconds = None
            raise RateLimitError(retry_after_seconds) from error
        if error.code in {401, 403}:
            raise AccessError("Source rejected the supplied credentials or access.") from error
        # Do not include error.url: OpenWeather's URL contains the API key.
        raise AdapterError("Source returned HTTP {}".format(error.code)) from error
    except URLError as error:
        raise AdapterError("Unable to reach source: {}".format(error.reason)) from error


def load_openweather_api_key(
    path: Optional[Path] = None,
) -> str:
    """Load either a bare key or OPENWEATHER_API_KEY=<key> from a local file."""
    key_path = path or Path(__file__).resolve().parents[1] / "apikey.local"
    try:
        lines = key_path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise AccessError("OpenWeather API key file is unavailable.") from error

    for line in lines:
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        if "=" in value:
            variable_name, possible_key = value.split("=", 1)
            if variable_name.strip().upper() in {
                "OPENWEATHER_API_KEY",
                "OPENWEATHER_KEY",
                "API_KEY",
            }:
                value = possible_key.strip()
        value = value.strip("'\"")
        if value:
            return value
    raise AccessError("OpenWeather API key file contains no key.")


class OpenStreetMapAdapter:
    """Resolve a place through Nominatim's public search endpoint."""

    def probe(self, location_query: str = DEFAULT_LOCATION) -> dict:
        data = _request_json(
            NOMINATIM_SEARCH_URL,
            {
                "q": location_query,
                "format": "jsonv2",
                "limit": 1,
                "addressdetails": 1,
            },
            {
                "Accept": "application/json",
                "User-Agent": os.getenv(
                    "LONGGRAPH_USER_AGENT",
                    "longgraph-local/0.1 (development)",
                ),
            },
        )
        if not data:
            raise AdapterError("OpenStreetMap found no location for the query.")

        place = data[0]
        osm_type = place["osm_type"]
        osm_id = place["osm_id"]
        return {
            "entity_key": "osm:{}:{}".format(osm_type, osm_id),
            "osm_type": osm_type,
            "osm_id": osm_id,
            "name": place.get("name") or place.get("display_name"),
            "address": place.get("display_name"),
            "latitude": float(place["lat"]),
            "longitude": float(place["lon"]),
            "bounding_box": place.get("boundingbox", []),
        }


class OpenWeatherAdapter:
    """Fetch current weather for an OSM-normalized geographic record."""

    def __init__(self, api_key_path: Optional[Path] = None):
        self._api_key_path = api_key_path

    def probe(self, location_record: dict) -> dict:
        if "latitude" not in location_record or "longitude" not in location_record:
            raise AdapterError("OpenWeather requires latitude and longitude from OpenStreetMap.")

        data = _request_json(
            OPENWEATHER_CURRENT_URL,
            {
                "lat": location_record["latitude"],
                "lon": location_record["longitude"],
                "units": "metric",
                "appid": load_openweather_api_key(self._api_key_path),
            },
            {"Accept": "application/json"},
        )
        weather = data.get("weather", [{}])[0]
        main = data.get("main", {})
        wind = data.get("wind", {})
        return {
            "entity_key": location_record["entity_key"],
            "temperature_c": main.get("temp"),
            "humidity_pct": main.get("humidity"),
            "wind_speed_mps": wind.get("speed"),
            "weather_description": weather.get("description"),
            "observed_at": data.get("dt"),
        }
