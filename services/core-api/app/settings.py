"""Configuracion del servicio. Todo por entorno: cero credenciales en codigo."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Valor por defecto heredado del Hito 2. Mientras siga igual, el Centinela
# responde 503 a proposito en lugar de aceptar una clave publica.
CLAVE_INSEGURA = "change-me"


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
    agency_master_key: str = CLAVE_INSEGURA
    # Nombre ratificado 2026-11-08. Si se define, gana sobre agency_master_key.
    sentinel_master_key: str | None = None

    # v4.4.0 - Router HTTP del Custodio. Tokens de servicio por rol, no login.
    # Si ningun token esta configurado y CUSTODIO_ALLOW_DEV_HEADER=false, el
    # router responde 503 (falla cerrado).
    custodio_token_superadmin: str | None = None
    custodio_token_contadora: str | None = None
    custodio_token_secretaria: str | None = None
    custodio_token_bodega: str | None = None
    custodio_token_chofer: str | None = None
    custodio_token_system_cron: str | None = None
    custodio_allow_dev_header: bool = False

    # Compatibilidad con la primera version del router (X-Gate-Key).
    gate_api_key: str = CLAVE_INSEGURA

    # Push webhook del Centinela al CRM Central (PDR 4.2)
    agency_crm_webhook_url: str | None = None

    # Integraciones (se pueden completar tambien en system_settings)
    evolution_url: str | None = None
    evolution_instance: str | None = None
    evolution_api_key: str | None = None
    bunny_cdn_host: str | None = None

    # Modulo 1 - Bunny.net Storage (subida de evidencias)
    bunny_storage_zone: str | None = None
    bunny_storage_api_key: str | None = None
    bunny_storage_endpoint: str = "https://storage.bunnycdn.com"

    # Modulo 1 - Juez Binario "Jeb" (Gemini Flash con salida JSON forzada)
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout: float = 8.0

    # Modo SANDBOX (Direccion 2026-11-08): sin credenciales reales, WhatsApp
    # encola en sandbox_outbox, Bunny devuelve URLs simuladas y el Juez cae al
    # deterministico. Se apaga por .env o desde Superadmin.
    sandbox_mode: bool = True

    # Modulo 1 - Debounce. Si es None, manda system_settings.
    debounce_seconds: float | None = None
    debounce_poll_seconds: float = 1.0
    whatsapp_worker_enabled: bool = True

    sentinel_http_timeout: float = 3.0
    log_level: str = "INFO"

    @property
    def clave_maestra_sentinel(self) -> str:
        """Clave efectiva del Centinela (SENTINEL_MASTER_KEY gana si existe)."""
        return (self.sentinel_master_key or self.agency_master_key or "").strip()


@lru_cache
def get_settings() -> Settings:
    return Settings()
