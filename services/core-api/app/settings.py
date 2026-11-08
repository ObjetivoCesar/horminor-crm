"""Configuracion del servicio. Todo por entorno: cero credenciales en codigo."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "orminorth-core-api"
    environment: str = "local"

    database_url: str = "postgresql://orminorth:orminorth@localhost:5433/orminorth"
    redis_url: str = "redis://localhost:6380/0"

    migrations_dir: str = "db/migrations"
    auto_migrate: bool = True

    # API del CRM Central de la agencia (Modulo 5)
    agency_master_key: str = "change-me"

    # Integraciones (se pueden completar tambien en system_settings)
    evolution_url: str | None = None
    evolution_instance: str | None = None
    evolution_api_key: str | None = None
    bunny_cdn_host: str | None = None

    sentinel_http_timeout: float = 3.0
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
