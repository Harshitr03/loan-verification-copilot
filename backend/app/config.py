from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LVC_", env_file=".env", extra="ignore")
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "lvc"
    jwt_secret: str = "dev-secret-change-me"
    jwt_ttl_min: int = 480
    anthropic_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
