from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, sourced from environment / .env.

    Every external dependency is selected here so swapping implementations
    (LLM provider, web-search provider, cache backend) is a config change.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://puppycat:puppycat@localhost:5432/puppycat"

    # LLM provider
    llm_provider: str = "openai"
    openai_api_key: str = ""
    openai_base_url: str = ""
    llm_cheap_model: str = "gpt-4o-mini"
    llm_synthesis_model: str = "gpt-4o"

    # Google Places
    google_places_api_key: str = ""

    # Web search
    web_search_provider: str = "tavily"
    tavily_api_key: str = ""
    brave_search_api_key: str = ""

    # Cost controls
    daily_llm_budget_usd: float = 2.0

    # Cache TTLs (seconds)
    cache_ttl_places: int = 21600
    cache_ttl_web_search: int = 3600
    cache_ttl_weather: int = 10800

    # App
    app_api_key: str = "dev-local-key"
    cors_allow_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
