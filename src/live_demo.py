"""Live OSM + OpenWeather smoke test for the configured geographic scope."""

import json

from .adapters import DEFAULT_LOCATION, OpenStreetMapAdapter, OpenWeatherAdapter


def main() -> None:
    location = OpenStreetMapAdapter().probe(DEFAULT_LOCATION)
    weather = OpenWeatherAdapter().probe(location)
    print(json.dumps({"location": location, "weather": weather}, indent=2))


if __name__ == "__main__":
    main()
