from dataclasses import dataclass

from app.config import Settings
from app.gemini import GeminiClient


@dataclass
class AppClients:
    gemini: GeminiClient

    @classmethod
    def create(cls, settings: Settings) -> "AppClients":
        return cls(
            gemini=GeminiClient(
                api_key=settings.gemini_api_key,
                default_model=settings.gemini_default_model,
            )
        )

    async def start(self) -> None:
        await self.gemini.initialize()

    async def close(self) -> None:
        await self.gemini.close()
