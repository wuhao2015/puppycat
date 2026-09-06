from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    database_url: str = (
        "postgresql+asyncpg://puppycat:puppycat-local@localhost:5432/puppycat"
    )

    jwt_secret: str = "dev-only-change-before-deploying"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080
    signup_code: str = "dev-invite-only"

    gemini_api_key: str = ""
    gemini_default_model: str = "gemini-3.7-flash"
    google_places_api_key: str = ""
    tavily_api_key: str = ""
    next_public_mapbox_token: str = ""

    cors_allow_origins: str = "http://localhost:3000"

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_allow_origins.split(",")
            if origin.strip()
        ]


settings = Settings()
