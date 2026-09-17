import logging
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Self

import httpx
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy.exc import SQLAlchemyError

from app.db import cache_get, cache_set
from app.external import build_cache_key


logger = logging.getLogger(__name__)

WEATHER_CACHE_TTL_SECONDS = 60 * 60
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_DAILY_FIELDS = ",".join(
    (
        "weather_code",
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_probability_max",
        "precipitation_sum",
        "wind_speed_10m_max",
    )
)

WeatherUnavailableReason = Literal[
    "date_outside_forecast_range",
    "request_failed",
    "invalid_response",
]


class DailyWeather(BaseModel):
    date: date
    weather_code: int | None
    summary: str
    temperature_max_c: float | None
    temperature_min_c: float | None
    precipitation_probability_max: int | None
    precipitation_sum_mm: float | None
    wind_speed_max_kmh: float | None


class WeatherResult(BaseModel):
    source: Literal["open_meteo"] = "open_meteo"
    status: Literal["available", "not_available_for_date", "unavailable"]
    latitude: float | None = None
    longitude: float | None = None
    timezone: str | None = None
    days: list[DailyWeather] = Field(default_factory=list)
    unavailable_reason: WeatherUnavailableReason | None = None


class _DailyForecast(BaseModel):
    time: list[date]
    weather_code: list[int | None]
    temperature_2m_max: list[float | None]
    temperature_2m_min: list[float | None]
    precipitation_probability_max: list[int | None]
    precipitation_sum: list[float | None]
    wind_speed_10m_max: list[float | None]

    @model_validator(mode="after")
    def matching_lengths(self) -> Self:
        expected = len(self.time)
        values = (
            self.weather_code,
            self.temperature_2m_max,
            self.temperature_2m_min,
            self.precipitation_probability_max,
            self.precipitation_sum,
            self.wind_speed_10m_max,
        )
        if any(len(items) != expected for items in values):
            raise ValueError("Open-Meteo daily arrays have different lengths")
        return self


class _ForecastResponse(BaseModel):
    latitude: float
    longitude: float
    timezone: str
    daily: _DailyForecast


class WeatherClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def forecast(
        self,
        *,
        latitude: float,
        longitude: float,
        start_date: date,
        end_date: date,
    ) -> WeatherResult:
        if not -90 <= latitude <= 90:
            raise ValueError("latitude must be between -90 and 90")
        if not -180 <= longitude <= 180:
            raise ValueError("longitude must be between -180 and 180")
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")

        today = datetime.now(timezone.utc).date()
        last_forecast_date = today + timedelta(days=15)
        if start_date < today or end_date > last_forecast_date:
            return WeatherResult(
                status="not_available_for_date",
                unavailable_reason="date_outside_forecast_range",
            )

        cache_key = build_cache_key(
            "weather:open-meteo",
            {
                "latitude": round(latitude, 5),
                "longitude": round(longitude, 5),
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        )
        cached = await self._cached(cache_key)
        if cached is not None:
            return cached

        try:
            response = await self._http.get(
                _FORECAST_URL,
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "daily": _DAILY_FIELDS,
                    "timezone": "auto",
                },
            )
            response.raise_for_status()
            upstream = _ForecastResponse.model_validate(response.json())
            daily = upstream.daily
            expected_dates = [
                start_date + timedelta(days=offset)
                for offset in range((end_date - start_date).days + 1)
            ]
            if daily.time != expected_dates:
                return WeatherResult(
                    status="not_available_for_date",
                    unavailable_reason="date_outside_forecast_range",
                )
            result = WeatherResult(
                status="available",
                latitude=upstream.latitude,
                longitude=upstream.longitude,
                timezone=upstream.timezone,
                days=[
                    DailyWeather(
                        date=day,
                        weather_code=daily.weather_code[index],
                        summary=wmo_summary(daily.weather_code[index]),
                        temperature_max_c=daily.temperature_2m_max[index],
                        temperature_min_c=daily.temperature_2m_min[index],
                        precipitation_probability_max=(
                            daily.precipitation_probability_max[index]
                        ),
                        precipitation_sum_mm=daily.precipitation_sum[index],
                        wind_speed_max_kmh=daily.wind_speed_10m_max[index],
                    )
                    for index, day in enumerate(daily.time)
                ],
            )
        except httpx.HTTPError as error:
            status = (
                error.response.status_code
                if isinstance(error, httpx.HTTPStatusError)
                else None
            )
            logger.warning(
                "Open-Meteo forecast failed (status=%s)",
                status or "network_error",
            )
            return WeatherResult(
                status="unavailable",
                unavailable_reason="request_failed",
            )
        except (ValueError, ValidationError):
            logger.warning("Open-Meteo returned an invalid response")
            return WeatherResult(
                status="unavailable",
                unavailable_reason="invalid_response",
            )

        try:
            await cache_set(
                cache_key,
                result.model_dump(mode="json"),
                ttl_seconds=WEATHER_CACHE_TTL_SECONDS,
            )
        except SQLAlchemyError:
            logger.warning("Could not persist Open-Meteo cache entry")
        return result

    async def _cached(self, key: str) -> WeatherResult | None:
        try:
            payload = await cache_get(key)
            return (
                WeatherResult.model_validate(payload)
                if payload is not None
                else None
            )
        except (SQLAlchemyError, ValidationError):
            logger.warning("Ignoring unavailable or invalid Open-Meteo cache entry")
            return None


def wmo_summary(code: int | None) -> str:
    summaries = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        56: "Light freezing drizzle",
        57: "Dense freezing drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        66: "Light freezing rain",
        67: "Heavy freezing rain",
        71: "Slight snowfall",
        73: "Moderate snowfall",
        75: "Heavy snowfall",
        77: "Snow grains",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        85: "Slight snow showers",
        86: "Heavy snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail",
    }
    return summaries.get(code, "Unknown")
