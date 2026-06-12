from __future__ import annotations

import hashlib

import httpx

from app.cache import CacheBackend
from app.config import Settings, get_settings
from app.schemas import DayWeather, GeoPoint

# WMO weather codes -> short human summary (condensed to the common buckets).
_WMO = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    80: "Rain showers",
    81: "Rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Thunderstorm with heavy hail",
}


class WeatherClient:
    """Open-Meteo forecast client. Free, no API key. Implements DataSource."""

    name = "open_meteo"

    def __init__(self, cache: CacheBackend, settings: Settings | None = None) -> None:
        self._cache = cache
        self._settings = settings or get_settings()

    def is_configured(self) -> bool:
        return True  # Open-Meteo needs no credentials.

    @staticmethod
    def _cache_key(location: GeoPoint, start: str, end: str) -> str:
        digest = hashlib.sha256(
            f"{location.lat:.3f},{location.lng:.3f}|{start}|{end}".encode()
        ).hexdigest()[:32]
        return f"weather:{digest}"

    async def forecast(
        self, location: GeoPoint, start_date: str, end_date: str
    ) -> dict[str, DayWeather]:
        """Return a mapping of ISO date -> DayWeather for the trip window."""
        key = self._cache_key(location, start_date, end_date)
        cached = await self._cache.get(key)
        if cached is not None:
            return {d: DayWeather.model_validate(w) for d, w in cached.items()}

        params = {
            "latitude": location.lat,
            "longitude": location.lng,
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
            "timezone": "auto",
            "start_date": start_date,
            "end_date": end_date,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get("https://api.open-meteo.com/v1/forecast", params=params)
            resp.raise_for_status()
            data = resp.json()

        daily = data.get("daily", {})
        dates = daily.get("time", [])
        result: dict[str, DayWeather] = {}
        for i, day in enumerate(dates):
            code = _get(daily, "weather_code", i)
            result[day] = DayWeather(
                date=day,
                summary=_WMO.get(int(code), "Unknown") if code is not None else None,
                temp_max_c=_get(daily, "temperature_2m_max", i),
                temp_min_c=_get(daily, "temperature_2m_min", i),
                precipitation_mm=_get(daily, "precipitation_sum", i),
            )

        await self._cache.set(
            key,
            {d: w.model_dump(mode="json") for d, w in result.items()},
            self._settings.cache_ttl_weather,
        )
        return result


def _get(daily: dict, field: str, idx: int):
    values = daily.get(field) or []
    return values[idx] if idx < len(values) else None
