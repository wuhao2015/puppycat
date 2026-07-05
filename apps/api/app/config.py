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

    # LLM provider  ("gemini" or "openai")
    llm_provider: str = "gemini"
    # Gemini (Google AI Studio — free tier available)
    gemini_api_key: str = ""
    # Prefer the strongest free Gemini text model, then fall back to other free
    # Gemini models when the primary endpoint is busy or quota-limited.
    llm_cheap_model: str = "gemini-3.5-flash"
    llm_synthesis_model: str = "gemini-3.5-flash"
    llm_fallback_models: str = (
        "gemini-3-flash-preview,"
        "gemini-2.5-pro,"
        "gemini-3.1-flash-lite,"
        "gemini-2.5-flash,"
        "gemini-2.5-flash-lite"
    )
    # OpenAI (kept as a fallback option)
    openai_api_key: str = ""
    openai_base_url: str = ""

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
    cors_allow_origins: str = "http://localhost:3000"

    # Auth (JWT + invite-only registration)
    jwt_secret: str = "dev-insecure-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 days
    # Shared invite code required to register. Anyone with it can create an account.
    signup_code: str = "puppycat-invite"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    @property
    def llm_fallback_model_list(self) -> list[str]:
        return [m.strip() for m in self.llm_fallback_models.split(",") if m.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
