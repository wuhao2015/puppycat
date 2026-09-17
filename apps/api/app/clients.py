from dataclasses import dataclass

import httpx

from app.config import Settings
from app.external.places import PlacesClient
from app.external.search import SearchClient
from app.external.weather import WeatherClient
from app.gemini import GeminiClient


@dataclass
class AppClients:
    http: httpx.AsyncClient
    gemini: GeminiClient
    places: PlacesClient
    search: SearchClient
    weather: WeatherClient

    @classmethod
    def create(cls, settings: Settings) -> "AppClients":
        http = httpx.AsyncClient(
            timeout=httpx.Timeout(20.0, connect=5.0),
            follow_redirects=True,
            headers={"User-Agent": "Puppycat-Travel/0.1"},
        )
        return cls(
            http=http,
            gemini=GeminiClient(
                api_key=settings.gemini_api_key,
                default_model=settings.gemini_default_model,
            ),
            places=PlacesClient(http, api_key=settings.google_places_api_key),
            search=SearchClient(http, api_key=settings.tavily_api_key),
            weather=WeatherClient(http),
        )

    async def start(self) -> None:
        await self.gemini.initialize()

    async def close(self) -> None:
        try:
            await self.gemini.close()
        finally:
            await self.http.aclose()
